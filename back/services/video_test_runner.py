"""백그라운드 샘플 영상 실행기.

관리자 화면의 요청 스레드에서 AI 프로세스를 직접 기다리지 않는다. 실행 요청은
job_id 를 즉시 반환하고, AI 프로세스가 분석 중 감지 진행상황을 내부 API로 보내면
프론트가 job 상태를 폴링한다. 최종 판정·증거 이벤트 저장은 기존
``video_test_service`` 경로를 그대로 사용한다.
"""

import copy
import json
import os
import re
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import config
import db
from errors import ApiError


ALLOWED_SAMPLE_EXTENSIONS = {".avi", ".mkv", ".mov", ".mp4", ".webm"}
MAX_SAMPLE_NAME_LENGTH = 255
MAX_PROGRESS_IMAGE_BYTES = 10 * 1024 * 1024
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
PROGRESS_PHASES = {"DETECTING", "FIRE_CONFIRMED"}

_jobs: dict[str, dict] = {}
_jobs_lock = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sample_root() -> Path:
    return (Path(config.AI_MODEL_ROOT) / "samples").resolve()


def list_samples() -> list[dict]:
    root = _sample_root()
    if not root.is_dir():
        raise ApiError(503, "SAMPLE_DIRECTORY_UNAVAILABLE",
                       "AI 샘플 영상 디렉터리를 찾을 수 없습니다.")

    items = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or path.suffix.lower() not in ALLOWED_SAMPLE_EXTENSIONS:
            continue
        items.append({
            "name": path.name,
            "extension": path.suffix.lower().removeprefix("."),
            "size_bytes": path.stat().st_size,
            "preview_url": f"/media/video-tests/samples/{quote(path.name)}",
        })
    return items


def _resolve_sample(sample_name: str) -> Path:
    if (not isinstance(sample_name, str) or not sample_name.strip()
            or len(sample_name) > MAX_SAMPLE_NAME_LENGTH):
        raise ApiError(400, "BAD_REQUEST", "sample_name은 올바른 파일명이어야 합니다.",
                       field="sample_name")

    name = sample_name.strip()
    root = _sample_root()
    candidate = (root / name).resolve()
    if (Path(name).name != name
            or candidate.parent != root
            or candidate.suffix.lower() not in ALLOWED_SAMPLE_EXTENSIONS
            or not candidate.is_file()):
        raise ApiError(404, "SAMPLE_NOT_FOUND", "선택한 샘플 영상을 찾을 수 없습니다.",
                       field="sample_name")
    return candidate


def _cctv_exists(cctv_no: int) -> bool:
    return bool(db.query_one(
        "SELECT cctv_no FROM cctv WHERE cctv_no = %s",
        (cctv_no,),
    ))


def _new_job(job_id: str, sample_name: str, cctv_no: int) -> dict:
    return {
        "job_id": job_id,
        "status": "QUEUED",
        "phase": "QUEUED",
        "sample_name": sample_name,
        "cctv_no": cctv_no,
        "started_at": None,
        "finished_at": None,
        "event_no": None,
        "result": None,
        "error": None,
        "alarm_triggered": False,
        "human_review_required": False,
        "event_class": None,
        "confidence": None,
        "media_url": None,
        "first_detection_media_url": None,
        "first_detected_offset_sec": None,
        "confirmed_offset_sec": None,
        "processed_frames": 0,
        "positive_frames": 0,
        "threshold_frames": config.EVENT_THRESHOLD_FRAMES,
        "operator_decision": None,
        "operator_user_no": None,
        "operator_decided_at": None,
        "operator_reason": None,
        "test_report": None,
    }


def _public_job(job: dict) -> dict:
    return copy.deepcopy(job)


def _get_job(job_id: str) -> dict:
    if not isinstance(job_id, str) or not JOB_ID_RE.fullmatch(job_id):
        raise ApiError(404, "VIDEO_TEST_JOB_NOT_FOUND", "영상 테스트 작업을 찾을 수 없습니다.")
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise ApiError(404, "VIDEO_TEST_JOB_NOT_FOUND", "영상 테스트 작업을 찾을 수 없습니다.")
        return job


def get_job(job_id: str) -> dict:
    with _jobs_lock:
        return _public_job(_get_job(job_id))


def _update_job(job_id: str, **changes) -> dict:
    with _jobs_lock:
        job = _get_job(job_id)
        job.update(changes)
        return _public_job(job)


def _subprocess_error_message(output: str) -> str:
    cleaned = (output or "").strip()
    if len(cleaned) > 2000:
        cleaned = cleaned[-2000:]
    return cleaned or "AI 영상 분석 프로세스가 결과 없이 종료되었습니다."


def _save_progress_image(job_id: str, frame_index: int, image: bytes) -> str:
    if not image or len(image) > MAX_PROGRESS_IMAGE_BYTES:
        raise ApiError(400, "BAD_REQUEST", "감지 증거 이미지는 10MB 이하 JPEG여야 합니다.",
                       field="image")
    if not image.startswith(b"\xff\xd8"):
        raise ApiError(400, "BAD_REQUEST", "감지 증거 이미지는 JPEG여야 합니다.",
                       field="image")

    target_dir = Path(config.MEDIA_ROOT) / "video-tests" / "jobs" / job_id
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"progress_{frame_index}.jpg"
    (target_dir / filename).write_bytes(image)
    return f"/media/video-tests/jobs/{job_id}/{filename}"


def _update_progress_legacy(job_id: str, progress: dict, image: bytes | None = None) -> dict:
    """AI가 최초 감지·화재 확정 시점에 보내는 진행상황을 반영한다."""
    if not isinstance(progress, dict):
        raise ApiError(400, "BAD_REQUEST", "progress는 JSON 객체여야 합니다.", field="progress")
    phase = progress.get("phase")
    if phase not in PROGRESS_PHASES:
        raise ApiError(400, "BAD_REQUEST", "지원하지 않는 영상 테스트 진행 단계입니다.",
                       field="progress.phase")

    with _jobs_lock:
        job = _get_job(job_id)
        if job["status"] in {"SUCCEEDED", "FAILED"}:
            return _public_job(job)

        media_url = job.get("media_url")
        if image is not None:
            frame_index = progress.get("frame_index")
            if isinstance(frame_index, bool) or not isinstance(frame_index, int) or frame_index < 0:
                raise ApiError(400, "BAD_REQUEST", "frame_index는 0 이상의 정수여야 합니다.",
                               field="progress.frame_index")
            media_url = _save_progress_image(job_id, frame_index, image)

        job.update({
            "status": "RUNNING",
            "phase": phase,
            "alarm_triggered": phase == "FIRE_CONFIRMED" or job["alarm_triggered"],
            "event_class": progress.get("event_class") or job.get("event_class"),
            "confidence": progress.get("confidence", job.get("confidence")),
            "media_url": media_url,
            "first_detected_offset_sec": progress.get(
                "first_detected_offset_sec", job.get("first_detected_offset_sec")
            ),
            "confirmed_offset_sec": progress.get(
                "confirmed_offset_sec", job.get("confirmed_offset_sec")
            ),
            "processed_frames": progress.get("processed_frames", job["processed_frames"]),
            "positive_frames": progress.get("positive_frames", job["positive_frames"]),
            "threshold_frames": progress.get("threshold_frames", job["threshold_frames"]),
        })
        return _public_job(job)


def _execute_sample(sample_path: Path, cctv_no: int, job_id: str | None = None) -> dict:
    if not Path(config.AI_PYTHON).is_file() or not Path(config.AI_VALIDATE_SCRIPT).is_file():
        raise ApiError(503, "AI_NOT_CONFIGURED",
                       "AI 실행 환경 또는 영상 검증 스크립트를 찾을 수 없습니다.")

    result_path = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="fireguard-video-test-",
            suffix=".json",
            delete=False,
        ) as result_file:
            result_path = Path(result_file.name)

        child_env = os.environ.copy()
        child_env["INTERNAL_API_KEY"] = config.INTERNAL_API_KEY
        child_env["FIREGUARD_API"] = f"http://127.0.0.1:{config.APP_PORT}"

        command = [
            str(config.AI_PYTHON),
            str(config.AI_VALIDATE_SCRIPT),
            "--video", str(sample_path),
            "--cctv-no", str(cctv_no),
            "--api", child_env["FIREGUARD_API"],
            "--result-json", str(result_path),
        ]
        if job_id:
            command.extend(["--job-id", job_id])

        try:
            completed = subprocess.run(
                command,
                cwd=str(config.AI_MODEL_ROOT),
                env=child_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=config.AI_VIDEO_TEST_TIMEOUT_SEC,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ApiError(504, "AI_TIMEOUT",
                           "AI 영상 분석 시간이 제한을 초과했습니다.") from exc
        except FileNotFoundError as exc:
            raise ApiError(503, "AI_NOT_CONFIGURED",
                           "AI 실행 파일을 찾을 수 없습니다.") from exc
        except OSError as exc:
            raise ApiError(503, "AI_UNAVAILABLE",
                           "AI 영상 분석 프로세스를 시작할 수 없습니다.") from exc

        if completed.returncode != 0:
            raise ApiError(
                502,
                "AI_PROCESS_FAILED",
                _subprocess_error_message(completed.stdout),
            )

        if not result_path.is_file():
            raise ApiError(502, "AI_RESULT_INVALID",
                           "AI 영상 분석 결과 파일이 생성되지 않았습니다.")

        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ApiError(502, "AI_RESULT_INVALID",
                           "AI 영상 분석 결과를 읽을 수 없습니다.") from exc

        if not isinstance(result, dict) or not result.get("event_no"):
            raise ApiError(502, "AI_RESULT_INVALID",
                           "AI 영상 분석 결과 형식이 올바르지 않습니다.")
        return result
    finally:
        if result_path is not None:
            result_path.unlink(missing_ok=True)


def _run_job(job_id: str, sample_path: Path, cctv_no: int) -> None:
    _update_job(job_id, status="RUNNING", phase="ANALYZING", started_at=_now())
    try:
        result = _execute_sample(sample_path, cctv_no, job_id)
        final_alarm = (
            result.get("event_status") == "CONFIRMED"
            or ("event_status" not in result and result.get("result") == "FIRE")
        )
        final_phase = "FIRE_CONFIRMED" if final_alarm else "DISMISSED"
        _update_job(
            job_id,
            status="SUCCEEDED",
            phase=final_phase,
            finished_at=_now(),
            event_no=result.get("event_no"),
            result=result,
            alarm_triggered=final_alarm,
            human_review_required=False,
            event_class=result.get("event_class"),
            confidence=result.get("event_confidence"),
            media_url=(result.get("media") or [{}])[-1].get("media_url")
            if result.get("media") else None,
            first_detection_media_url=next(
                (media.get("media_url") for media in result.get("media", [])
                 if media.get("media_is_first")),
                None,
            ),
        )
    except ApiError as exc:
        _update_job(
            job_id,
            status="FAILED",
            phase="FAILED",
            finished_at=_now(),
            error={"code": exc.code, "message": exc.message},
        )
    except Exception as exc:  # 백그라운드 스레드 예외는 job 상태로 남긴다.
        _update_job(
            job_id,
            status="FAILED",
            phase="FAILED",
            finished_at=_now(),
            error={"code": "AI_UNAVAILABLE", "message": str(exc)},
        )


def start_sample(sample_name: str, cctv_no: int) -> dict:
    """샘플 분석 작업을 등록하고 즉시 job 상태를 반환한다."""
    sample_path = _resolve_sample(sample_name)
    if not _cctv_exists(cctv_no):
        raise ApiError(404, "CCTV_NOT_FOUND", "카메라를 찾을 수 없습니다.",
                       field="cctv_no")
    if not Path(config.AI_PYTHON).is_file() or not Path(config.AI_VALIDATE_SCRIPT).is_file():
        raise ApiError(503, "AI_NOT_CONFIGURED",
                       "AI 실행 환경 또는 영상 검증 스크립트를 찾을 수 없습니다.")

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = _new_job(job_id, sample_path.name, cctv_no)

    worker = threading.Thread(
        target=_run_job,
        args=(job_id, sample_path, cctv_no),
        name=f"fireguard-video-test-{job_id[:8]}",
        daemon=True,
    )
    worker.start()
    return get_job(job_id)


def run_sample(sample_name: str, cctv_no: int) -> dict:
    """하위 호환용 동기 실행 진입점. 관리자 UI는 start_sample을 사용한다."""
    sample_path = _resolve_sample(sample_name)
    if not _cctv_exists(cctv_no):
        raise ApiError(404, "CCTV_NOT_FOUND", "카메라를 찾을 수 없습니다.",
                       field="cctv_no")
    return _execute_sample(sample_path, cctv_no)


def update_progress(job_id: str, progress: dict, image: bytes | None = None) -> dict:
    """AI의 최초 감지/자동 확정 진행상황을 job과 임시 이벤트에 반영한다."""
    if not isinstance(progress, dict):
        raise ApiError(400, "BAD_REQUEST", "progress는 JSON 객체여야 합니다.", field="progress")
    phase = progress.get("phase")
    if phase not in PROGRESS_PHASES:
        raise ApiError(400, "BAD_REQUEST", "지원하지 않는 영상 테스트 진행 단계입니다.",
                       field="progress.phase")

    with _jobs_lock:
        current = _get_job(job_id)
        if current["status"] in {"SUCCEEDED", "FAILED"}:
            return _public_job(current)
        started_at = current.get("started_at")
        sample_name = current["sample_name"]
        cctv_no = current["cctv_no"]
        existing_event_no = current.get("event_no")
        operator_decision = current.get("operator_decision")
        saved_media_url = current.get("media_url")

    media_url = saved_media_url
    if image is not None:
        frame_index = progress.get("frame_index")
        if isinstance(frame_index, bool) or not isinstance(frame_index, int) or frame_index < 0:
            raise ApiError(400, "BAD_REQUEST", "frame_index는 0 이상의 정수여야 합니다.",
                           field="progress.frame_index")
        media_url = _save_progress_image(job_id, frame_index, image)

    detection = None
    if phase == "DETECTING" and existing_event_no is None:
        from services import video_test_service
        detection = video_test_service.register_video_test_detection(
            job_id=job_id,
            sample_name=sample_name,
            cctv_no=cctv_no,
            started_at=started_at,
            progress=progress,
            media_url=media_url,
        )

    with _jobs_lock:
        job = _get_job(job_id)
        if detection:
            job["event_no"] = detection["event_no"]
            job["first_detection_media_url"] = detection.get("media_url")

        operator_decision = job.get("operator_decision")
        effective_phase = phase
        if operator_decision == "DISMISS":
            effective_phase = "DISMISSED"
        elif operator_decision == "CONFIRM_FIRE" or phase == "FIRE_CONFIRMED":
            effective_phase = "FIRE_CONFIRMED"

        job.update({
            "status": "RUNNING",
            "phase": effective_phase,
            "alarm_triggered": (
                effective_phase == "FIRE_CONFIRMED"
                and operator_decision != "DISMISS"
            ) or (job["alarm_triggered"] and operator_decision != "DISMISS"),
            "human_review_required": (
                effective_phase == "DETECTING" and operator_decision is None
            ),
            "event_class": progress.get("event_class") or job.get("event_class"),
            "confidence": progress.get("confidence", job.get("confidence")),
            "media_url": media_url,
            "first_detection_media_url": (
                job.get("first_detection_media_url")
                or (media_url if phase == "DETECTING" else None)
            ),
            "first_detected_offset_sec": progress.get(
                "first_detected_offset_sec", job.get("first_detected_offset_sec")
            ),
            "confirmed_offset_sec": progress.get(
                "confirmed_offset_sec", job.get("confirmed_offset_sec")
            ),
            "processed_frames": progress.get("processed_frames", job["processed_frames"]),
            "positive_frames": progress.get("positive_frames", job["positive_frames"]),
            "threshold_frames": progress.get("threshold_frames", job["threshold_frames"]),
        })
        return _public_job(job)


def decide(job_id: str, decision: str, user_no: int, reason: str = "") -> dict:
    """관제자의 수동 확정/오탐 판단을 저장하고 job 상태를 바꾼다."""
    if decision not in {"CONFIRM_FIRE", "DISMISS"}:
        raise ApiError(400, "BAD_REQUEST", "decision은 CONFIRM_FIRE 또는 DISMISS여야 합니다.",
                       field="decision")

    with _jobs_lock:
        job = _get_job(job_id)
        if job["status"] in {"SUCCEEDED", "FAILED"}:
            can_confirm_unanswered_test = (
                job["status"] == "SUCCEEDED"
                and decision == "CONFIRM_FIRE"
                and job.get("event_no")
                and not job.get("operator_decision")
            )
            if not can_confirm_unanswered_test:
                raise ApiError(409, "VIDEO_TEST_ALREADY_FINISHED",
                               "이미 종료된 영상 테스트는 판단을 변경할 수 없습니다.")
        if not job.get("event_no"):
            raise ApiError(409, "VIDEO_TEST_DETECTION_NOT_READY",
                           "최초 화염 감지 후에 관제자 판단을 할 수 있습니다.")
        if job.get("operator_decision"):
            if job["operator_decision"] == decision:
                return _public_job(job)
            raise ApiError(409, "VIDEO_TEST_DECISION_CONFLICT",
                           "이미 다른 관제자 판단이 반영된 테스트입니다.")
        event_no = job["event_no"]

    from services import video_test_service
    decision_result = video_test_service.apply_video_test_operator_decision(
        event_no, decision, user_no, reason
    )

    with _jobs_lock:
        job = _get_job(job_id)
        job.update({
            "operator_decision": decision,
            "operator_user_no": user_no,
            "operator_decided_at": _now(),
            "operator_reason": reason.strip() if isinstance(reason, str) else "",
            "human_review_required": False,
            "phase": "FIRE_CONFIRMED" if decision == "CONFIRM_FIRE" else "DISMISSED",
            "alarm_triggered": decision == "CONFIRM_FIRE",
            "test_report": decision_result.get("test_report"),
        })
        return _public_job(job)
