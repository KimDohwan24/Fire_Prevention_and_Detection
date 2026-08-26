"""업로드 영상의 AI 판정 결과를 테스트 이벤트로 저장한다.

실시간 프레임 수집(`event_service`)과 달리 AI가 영상 전체 판정을 끝낸 뒤 결과와
증거 프레임을 한 번에 보낸다. 이 경로는 항상 VIDEO_TEST + event_is_test=true 이며
알림/문자/119 훅을 호출하지 않는다.
"""
import io
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, UnidentifiedImageError

import config
import db
from errors import ApiError

logger = logging.getLogger("fireguard.video_test")

MAX_EVIDENCE_IMAGES = 3
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_RESULTS = {"FIRE", "NO_FIRE"}
ALLOWED_CLASSES = {"FLAME", "SMOKE"}
ALLOWED_ROLES = {"FIRST", "CONFIRMATION", "PEAK"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FILE_FIELD_RE = re.compile(r"^evidence_[0-2]$")
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _bad(field: str, message: str):
    raise ApiError(400, "BAD_REQUEST", message, field=field)


def _dict(value, field: str) -> dict:
    if not isinstance(value, dict):
        _bad(field, f"{field} 는 객체여야 합니다.")
    return value


def _string(value, field: str, *, max_length: int = 255) -> str:
    if not isinstance(value, str) or not value.strip():
        _bad(field, f"{field} 는 비어 있지 않은 문자열이어야 합니다.")
    result = value.strip()
    if len(result) > max_length:
        _bad(field, f"{field} 는 {max_length}자를 넘을 수 없습니다.")
    return result


def _integer(value, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _bad(field, f"{field} 는 {minimum} 이상의 정수여야 합니다.")
    return value


def _number(value, field: str, *, minimum: float = 0,
            maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _bad(field, f"{field} 는 숫자여야 합니다.")
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        _bad(field, f"{field} 는 유한한 숫자여야 합니다.")
    if result < minimum or (maximum is not None and result > maximum):
        end = f"~{maximum}" if maximum is not None else " 이상"
        _bad(field, f"{field} 는 {minimum}{end} 범위여야 합니다.")
    return result


def _optional_number(value, field: str, *, minimum: float = 0,
                     maximum: float | None = None) -> float | None:
    if value is None:
        return None
    return _number(value, field, minimum=minimum, maximum=maximum)


def _timestamp(value, field: str) -> datetime:
    if not isinstance(value, str):
        _bad(field, f"{field} 은 ISO 8601 문자열이어야 합니다.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _bad(field, f"{field} 은 ISO 8601 형식이어야 합니다.")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _event_class(detected_classes: list[str]) -> str | None:
    classes = set(detected_classes)
    if classes == {"FLAME", "SMOKE"}:
        return "FLAME_SMOKE"
    return next(iter(classes), None)


def _validate_detection(value, field: str) -> dict:
    det = _dict(value, field)
    cls = det.get("cls")
    if cls not in ("flame", "smoke"):
        _bad(f"{field}.cls", "증거 검출 클래스는 flame 또는 smoke 여야 합니다.")
    conf = _number(det.get("conf"), f"{field}.conf", maximum=1)
    if det.get("bbox_format") != "xywhn":
        _bad(f"{field}.bbox_format", "bbox_format 은 xywhn 이어야 합니다.")
    bbox = det.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        _bad(f"{field}.bbox", "bbox 는 정규화된 [cx, cy, w, h] 4개 값이어야 합니다.")
    normalized_bbox = [
        _number(v, f"{field}.bbox", maximum=1) for v in bbox
    ]
    if normalized_bbox[2] <= 0 or normalized_bbox[3] <= 0:
        _bad(f"{field}.bbox", "bbox 의 너비와 높이는 0보다 커야 합니다.")
    return {
        "cls": cls,
        "conf": conf,
        "bbox": normalized_bbox,
        "bbox_format": "xywhn",
    }


def _validate_evidence(values, *, duration_sec: float) -> list[dict]:
    if not isinstance(values, list):
        _bad("evidence", "evidence 는 리스트여야 합니다.")
    if len(values) > MAX_EVIDENCE_IMAGES:
        _bad("evidence", f"증거 이미지는 최대 {MAX_EVIDENCE_IMAGES}장입니다.")

    result = []
    fields: set[str] = set()
    frames: set[int] = set()
    for index, value in enumerate(values):
        field = f"evidence[{index}]"
        item = _dict(value, field)
        file_field = _string(item.get("file_field"), f"{field}.file_field", max_length=30)
        if not FILE_FIELD_RE.fullmatch(file_field) or file_field in fields:
            _bad(f"{field}.file_field", "file_field 는 중복 없는 evidence_0~evidence_2 여야 합니다.")
        fields.add(file_field)

        frame_index = _integer(item.get("frame_index"), f"{field}.frame_index")
        if frame_index in frames:
            _bad(f"{field}.frame_index", "같은 프레임은 증거 이미지로 중복 전송할 수 없습니다.")
        frames.add(frame_index)

        offset = _number(item.get("offset_sec"), f"{field}.offset_sec")
        if offset > duration_sec + 0.001:
            _bad(f"{field}.offset_sec", "증거 프레임 위치가 영상 길이를 넘었습니다.")
        confidence = _number(item.get("confidence"), f"{field}.confidence", maximum=1)

        roles = item.get("roles")
        if not isinstance(roles, list) or not roles \
                or not all(isinstance(role, str) for role in roles) \
                or len(roles) != len(set(roles)):
            _bad(f"{field}.roles", "roles 는 중복 없는 역할 리스트여야 합니다.")
        if not set(roles) <= ALLOWED_ROLES:
            _bad(f"{field}.roles", "지원하지 않는 증거 이미지 역할입니다.")

        detections = item.get("detections")
        if not isinstance(detections, list) or not detections:
            _bad(f"{field}.detections", "증거 이미지에는 화재·연기 검출이 필요합니다.")
        normalized_detections = [
            _validate_detection(det, f"{field}.detections[{det_index}]")
            for det_index, det in enumerate(detections)
        ]
        top_conf = max(det["conf"] for det in normalized_detections)
        if abs(top_conf - confidence) > 0.0001:
            _bad(f"{field}.confidence", "증거 confidence 는 검출 목록의 최고값과 같아야 합니다.")

        result.append({
            "file_field": file_field,
            "frame_index": frame_index,
            "offset_sec": offset,
            "confidence": confidence,
            "roles": roles,
            "detections": normalized_detections,
        })
    return result


def _validate_manifest(manifest: dict) -> dict:
    manifest = _dict(manifest, "manifest")
    job_id = manifest.get("job_id")
    if job_id is not None and (
        not isinstance(job_id, str) or not JOB_ID_RE.fullmatch(job_id)
    ):
        _bad("job_id", "job_id??щ컮瑜댁? ?곸긽 ?뚯뒪??ID?댁빞 ?⑸땲??")
    cctv_no = _integer(manifest.get("cctv_no"), "cctv_no", minimum=1)
    result = manifest.get("result")
    if result not in ALLOWED_RESULTS:
        _bad("result", "result 는 FIRE 또는 NO_FIRE 여야 합니다.")

    started_at = _timestamp(manifest.get("started_at"), "started_at")
    finished_at = _timestamp(manifest.get("finished_at"), "finished_at")
    if finished_at < started_at:
        _bad("finished_at", "finished_at 은 started_at 보다 빠를 수 없습니다.")

    raw_video = _dict(manifest.get("video"), "video")
    video = {
        "name": _string(raw_video.get("name"), "video.name"),
        "duration_sec": _number(raw_video.get("duration_sec"), "video.duration_sec"),
        "source_fps": _number(raw_video.get("source_fps"), "video.source_fps", minimum=0.001),
    }

    raw_model = _dict(manifest.get("model"), "model")
    sha256 = _string(raw_model.get("sha256"), "model.sha256", max_length=64).lower()
    if not SHA256_RE.fullmatch(sha256):
        _bad("model.sha256", "model.sha256 은 64자리 SHA-256 값이어야 합니다.")
    model = {
        "filename": _string(raw_model.get("filename"), "model.filename"),
        "sha256": sha256,
        "confidence": _number(raw_model.get("confidence"), "model.confidence", maximum=1),
        "iou": _number(raw_model.get("iou"), "model.iou", maximum=1),
        "imgsz": _integer(raw_model.get("imgsz"), "model.imgsz", minimum=1),
        "device": _string(raw_model.get("device"), "model.device", max_length=50),
        "inference_fps": _number(raw_model.get("inference_fps"),
                                 "model.inference_fps", minimum=0.001),
        "max_det": _integer(raw_model.get("max_det"), "model.max_det", minimum=1),
    }

    raw_stats = _dict(manifest.get("statistics"), "statistics")
    processed = _integer(raw_stats.get("processed_frames"),
                         "statistics.processed_frames", minimum=1)
    positive = _integer(raw_stats.get("positive_frames"), "statistics.positive_frames")
    if positive > processed:
        _bad("statistics.positive_frames", "positive_frames 는 processed_frames 를 넘을 수 없습니다.")
    threshold = _integer(raw_stats.get("threshold_frames"),
                         "statistics.threshold_frames", minimum=1)
    window_sec = _number(raw_stats.get("window_sec"), "statistics.window_sec", minimum=0.001)
    first_offset = _optional_number(raw_stats.get("first_detected_offset_sec"),
                                    "statistics.first_detected_offset_sec")
    confirmed_offset = _optional_number(raw_stats.get("confirmed_offset_sec"),
                                        "statistics.confirmed_offset_sec")
    max_confidence = _optional_number(raw_stats.get("max_confidence"),
                                      "statistics.max_confidence", maximum=1)

    detected_classes = raw_stats.get("detected_classes")
    if not isinstance(detected_classes, list) \
            or not all(isinstance(cls, str) for cls in detected_classes) \
            or len(detected_classes) != len(set(detected_classes)):
        _bad("statistics.detected_classes", "detected_classes 는 중복 없는 리스트여야 합니다.")
    if not set(detected_classes) <= ALLOWED_CLASSES:
        _bad("statistics.detected_classes", "detected_classes 는 FLAME 또는 SMOKE 만 허용합니다.")

    if positive == 0:
        if first_offset is not None or max_confidence is not None or detected_classes:
            _bad("statistics", "양성 프레임이 없으면 검출 시점·신뢰도·클래스도 없어야 합니다.")
    elif first_offset is None or max_confidence is None or not detected_classes:
        _bad("statistics", "양성 프레임이 있으면 최초 시점·신뢰도·클래스가 필요합니다.")

    if first_offset is not None and first_offset > video["duration_sec"] + 0.001:
        _bad("statistics.first_detected_offset_sec", "최초 검출 시점이 영상 길이를 넘었습니다.")
    if confirmed_offset is not None and confirmed_offset > video["duration_sec"] + 0.001:
        _bad("statistics.confirmed_offset_sec", "확정 시점이 영상 길이를 넘었습니다.")

    if result == "FIRE":
        if confirmed_offset is None or positive < threshold:
            _bad("result", "FIRE 결과에는 임계값 이상의 양성 프레임과 확정 시점이 필요합니다.")
    elif confirmed_offset is not None:
        _bad("statistics.confirmed_offset_sec", "NO_FIRE 결과에는 확정 시점이 없어야 합니다.")

    evidence = _validate_evidence(manifest.get("evidence"),
                                  duration_sec=video["duration_sec"])
    expected_roles = set()
    role_counts = {role: 0 for role in ALLOWED_ROLES}
    for item in evidence:
        expected_roles.update(item["roles"])
        for role in item["roles"]:
            role_counts[role] += 1
    required_roles = {"FIRST", "PEAK"} if positive else set()
    if result == "FIRE":
        required_roles.add("CONFIRMATION")
    if expected_roles != required_roles:
        _bad("evidence", f"증거 역할은 {sorted(required_roles)}와 정확히 일치해야 합니다.")
    if any(role_counts[role] != 1 for role in required_roles):
        _bad("evidence", "FIRST, CONFIRMATION, PEAK 역할은 각각 한 프레임에만 지정해야 합니다.")

    if positive == 0 and evidence:
        _bad("evidence", "양성 프레임이 없으면 증거 이미지도 없어야 합니다.")
    if positive > 0:
        peak = next(item for item in evidence if "PEAK" in item["roles"])
        first = next(item for item in evidence if "FIRST" in item["roles"])
        if abs(peak["confidence"] - max_confidence) > 0.0001:
            _bad("evidence", "PEAK 증거의 confidence 가 전체 최고 신뢰도와 다릅니다.")
        if abs(first["offset_sec"] - first_offset) > 0.001:
            _bad("evidence", "FIRST 증거의 영상 시점이 최초 검출 시점과 다릅니다.")
        if result == "FIRE":
            confirmation = next(item for item in evidence if "CONFIRMATION" in item["roles"])
            if abs(confirmation["offset_sec"] - confirmed_offset) > 0.001:
                _bad("evidence", "CONFIRMATION 증거의 영상 시점이 확정 시점과 다릅니다.")

    return {
        "job_id": job_id,
        "cctv_no": cctv_no,
        "result": result,
        "started_at": started_at,
        "finished_at": finished_at,
        "video": video,
        "model": model,
        "statistics": {
            "processed_frames": processed,
            "positive_frames": positive,
            "threshold_frames": threshold,
            "window_sec": window_sec,
            "first_detected_offset_sec": first_offset,
            "confirmed_offset_sec": confirmed_offset,
            "max_confidence": max_confidence,
            "detected_classes": detected_classes,
        },
        "evidence": evidence,
    }


def _read_images(evidence: list[dict], uploads) -> dict[str, bytes]:
    expected = {item["file_field"] for item in evidence}
    provided = set(uploads.keys())
    if provided != expected:
        _bad("evidence", "manifest의 증거 목록과 업로드된 이미지 필드가 일치해야 합니다.")

    images = {}
    for field in expected:
        upload = uploads.get(field)
        raw = upload.stream.read(MAX_IMAGE_BYTES + 1)
        if not raw:
            _bad(field, "증거 이미지가 비어 있습니다.")
        if len(raw) > MAX_IMAGE_BYTES:
            _bad(field, "증거 이미지 한 장은 10MB를 넘을 수 없습니다.")
        try:
            with Image.open(io.BytesIO(raw)) as image:
                image_format = image.format
                image.verify()
        except (UnidentifiedImageError, OSError):
            _bad(field, "증거 이미지는 정상적인 JPEG 파일이어야 합니다.")
        if image_format != "JPEG":
            _bad(field, "증거 이미지는 JPEG 형식이어야 합니다.")
        images[field] = raw
    return images


def _cctv_snapshot(row: dict) -> dict:
    return {
        "cctv_no": row["cctv_no"],
        "cctv_name": row["cctv_name"],
        "cctv_location": row["cctv_location"],
        "cctv_address": row["cctv_address"],
        "cctv_lat": float(row["cctv_lat"]) if row["cctv_lat"] is not None else None,
        "cctv_lng": float(row["cctv_lng"]) if row["cctv_lng"] is not None else None,
    }


def _test_timestamp(value, offset_sec: float | None = None) -> datetime | None:
    """AI 테스트 시각을 DB timestamp 형식으로 맞춘다."""
    if value is None:
        result = datetime.now()
    elif isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(str(value))
        except ValueError:
            result = datetime.now()
    if result.tzinfo is not None:
        result = result.astimezone(timezone.utc).replace(tzinfo=None)
    if offset_sec is not None:
        result += timedelta(seconds=float(offset_sec))
    return result


def register_video_test_detection(*, job_id: str, sample_name: str,
                                  cctv_no: int, started_at,
                                  progress: dict, media_url: str | None) -> dict:
    """첫 양성 프레임을 임시(PENDING) 테스트 이벤트로 즉시 기록한다."""
    if not JOB_ID_RE.fullmatch(job_id or ""):
        raise ApiError(404, "VIDEO_TEST_JOB_NOT_FOUND", "영상 테스트 작업을 찾을 수 없습니다.")

    first_offset = progress.get("first_detected_offset_sec")
    if first_offset is None:
        first_offset = progress.get("offset_sec", 0)
    first_at = _test_timestamp(started_at, first_offset)
    event_class = progress.get("event_class") or "FLAME_SMOKE"
    confidence = progress.get("confidence")
    detections = progress.get("detections") or []
    metadata = {
        "job_id": job_id,
        "sample_name": sample_name,
        "mode": "UI_VIDEO_TEST",
        "phase": "DETECTING",
    }

    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            SELECT event_no, event_status, event_class, event_confidence
            FROM fire_event
            WHERE event_source_type = 'VIDEO_TEST'
              AND event_source_metadata->>'job_id' = %s
            ORDER BY event_no DESC
            LIMIT 1
            FOR UPDATE
            """,
            (job_id,),
        )
        existing = cur.fetchone()
        if existing:
            event_no = existing["event_no"]
            event_status = existing["event_status"]
        else:
            cur.execute(
                """
                SELECT cctv_no, cctv_name, cctv_location, cctv_address,
                       cctv_lat, cctv_lng
                FROM cctv WHERE cctv_no = %s
                """,
                (cctv_no,),
            )
            cctv = cur.fetchone()
            if cctv is None:
                raise ApiError(404, "CCTV_NOT_FOUND", "카메라를 찾을 수 없습니다.")

            snapshot = _cctv_snapshot(dict(cctv))
            cur.execute(
                """
                INSERT INTO fire_event (
                    cctv_no, event_status, event_class,
                    event_first_detected_at, event_detected_frames,
                    event_threshold_frames, event_confidence,
                    event_is_test, event_source_type, event_source_metadata,
                    event_cctv_snapshot, event_first_detected_offset_sec,
                    event_test_started_at
                )
                VALUES (%s, 'PENDING', %s, %s, %s, %s, %s,
                        true, 'VIDEO_TEST', %s::jsonb, %s::jsonb, %s, %s)
                RETURNING event_no
                """,
                (
                    cctv_no, event_class, first_at,
                    progress.get("positive_frames", 1),
                    progress.get("threshold_frames", config.EVENT_THRESHOLD_FRAMES),
                    confidence, json.dumps(metadata, ensure_ascii=False),
                    json.dumps(snapshot, ensure_ascii=False), first_offset,
                    _test_timestamp(started_at),
                ),
            )
            event_no = cur.fetchone()["event_no"]
            event_status = "PENDING"

        if media_url and not existing:
            cur.execute(
                """
                INSERT INTO event_media (
                    event_no, media_url, media_detections, media_confidence,
                    media_captured_at, media_is_primary, media_is_first,
                    media_frame_index, media_source_offset_sec
                )
                VALUES (%s, %s, %s::jsonb, %s, %s, true, true, %s, %s)
                """,
                (
                    event_no, media_url, json.dumps(detections, ensure_ascii=False),
                    confidence, first_at, progress.get("frame_index"), first_offset,
                ),
            )

    return {
        "event_no": event_no,
        "event_status": event_status,
        "media_url": media_url,
        "first_detected_offset_sec": first_offset,
    }


def apply_video_test_operator_decision(event_no: int, decision: str,
                                       user_no: int, reason: str = "") -> dict:
    """관제자의 화재 확정/오탐 판단을 이벤트에 반영한다."""
    if decision not in {"CONFIRM_FIRE", "DISMISS"}:
        raise ApiError(400, "BAD_REQUEST", "decision은 CONFIRM_FIRE 또는 DISMISS여야 합니다.",
                       field="decision")

    now = datetime.now()
    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            SELECT e.event_no, e.event_status, e.event_class,
                   e.event_confidence, e.event_source_metadata, c.cctv_name
            FROM fire_event e
            JOIN cctv c ON c.cctv_no = e.cctv_no
            WHERE e.event_no = %s AND e.event_is_test = true
            FOR UPDATE
            """,
            (event_no,),
        )
        event = cur.fetchone()
        if event is None:
            raise ApiError(404, "VIDEO_TEST_EVENT_NOT_FOUND", "영상 테스트 이벤트를 찾을 수 없습니다.")

        metadata = dict(event.get("event_source_metadata") or {})
        previous = metadata.get("operator_decision")
        if previous and previous != decision:
            raise ApiError(409, "VIDEO_TEST_DECISION_CONFLICT",
                           "이미 다른 관제자 판단이 반영된 테스트 이벤트입니다.")

        metadata.update({
            "operator_decision": decision,
            "operator_user_no": user_no,
            "operator_decided_at": now.isoformat(),
            "operator_reason": reason.strip() if isinstance(reason, str) else "",
            "decision_source": "HUMAN",
        })
        status = "CONFIRMED" if decision == "CONFIRM_FIRE" else "DISMISSED"
        detected_at = now if decision == "CONFIRM_FIRE" else None
        cur.execute(
            """
            UPDATE fire_event
            SET event_status = %s,
                event_detected_at = %s,
                event_source_metadata = %s::jsonb
            WHERE event_no = %s
            RETURNING event_no, event_status, event_class, event_confidence
            """,
            (status, detected_at, json.dumps(metadata, ensure_ascii=False), event_no),
        )
        result = dict(cur.fetchone())
        result["cctv_name"] = event["cctv_name"]
        result["operator_decision"] = decision

    if decision == "CONFIRM_FIRE":
        from services import report_service

        try:
            result["test_report"] = report_service.send_test_report(event_no)
        except Exception as exc:  # noqa: BLE001
            # 테스트 판정 저장은 성공했으므로 mock 서버 장애가 판정 자체를
            # 실패시키지 않게 하고, API 응답에 전송 실패를 남긴다.
            logger.exception("테스트 mock-119 신고 전송 실패 (event_no=%s)", event_no)
            result["test_report"] = {
                "report_status": "FAILED",
                "report_error": str(exc)[:500],
            }

    # 사람의 판단은 사용자 활동이력에도 별도로 남긴다.
    from services import activity_service
    activity_type = (activity_service.FIRE_CONFIRMED
                     if decision == "CONFIRM_FIRE"
                     else activity_service.FIRE_DISMISSED)
    detail = f"{result['cctv_name']} 영상 테스트 " \
             f"{'화재 확정' if decision == 'CONFIRM_FIRE' else '오탐 처리'}"
    activity_service.record(user_no, activity_type, target_no=event_no, detail=detail)
    return result


def _create_video_test_legacy(manifest: dict, uploads) -> dict:
    """검증된 영상 판정과 JPEG 최대 3장을 하나의 테스트 이벤트로 저장한다."""
    data = _validate_manifest(manifest)
    images = _read_images(data["evidence"], uploads)
    stats = data["statistics"]
    event_class = _event_class(stats["detected_classes"])
    event_status = "CONFIRMED" if data["result"] == "FIRE" else "DISMISSED"

    source_metadata = {
        "result": data["result"],
        "video": data["video"],
        "model": data["model"],
        "decision": {
            "processed_frames": stats["processed_frames"],
            "positive_frames": stats["positive_frames"],
            "threshold_frames": stats["threshold_frames"],
            "window_sec": stats["window_sec"],
            "detected_classes": stats["detected_classes"],
        },
    }

    written_paths: list[Path] = []
    media_rows = []
    try:
        with db.get_cursor(commit=True) as cur:
            cur.execute(
                """
                SELECT cctv_no, cctv_name, cctv_location, cctv_address,
                       cctv_lat, cctv_lng
                FROM cctv WHERE cctv_no = %s
                """,
                (data["cctv_no"],),
            )
            cctv = cur.fetchone()
            if cctv is None:
                raise ApiError(404, "CCTV_NOT_FOUND", "카메라를 찾을 수 없습니다.")
            snapshot = _cctv_snapshot(dict(cctv))

            first_at = None
            if stats["first_detected_offset_sec"] is not None:
                first_at = data["started_at"] + timedelta(
                    seconds=stats["first_detected_offset_sec"]
                )
            confirmed_at = None
            if stats["confirmed_offset_sec"] is not None:
                confirmed_at = data["started_at"] + timedelta(
                    seconds=stats["confirmed_offset_sec"]
                )

            cur.execute(
                """
                INSERT INTO fire_event (
                    cctv_no, event_status, event_class,
                    event_first_detected_at, event_detected_at,
                    event_detected_frames, event_threshold_frames,
                    event_confidence, event_is_test, event_source_type,
                    event_source_metadata, event_cctv_snapshot,
                    event_processed_frames, event_first_detected_offset_sec,
                    event_confirmed_offset_sec, event_test_started_at,
                    event_test_finished_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    true, 'VIDEO_TEST', %s::jsonb, %s::jsonb,
                    %s, %s, %s, %s, %s
                )
                RETURNING event_no
                """,
                (
                    data["cctv_no"], event_status, event_class, first_at, confirmed_at,
                    stats["positive_frames"], stats["threshold_frames"],
                    stats["max_confidence"], json.dumps(source_metadata, ensure_ascii=False),
                    json.dumps(snapshot, ensure_ascii=False), stats["processed_frames"],
                    stats["first_detected_offset_sec"], stats["confirmed_offset_sec"],
                    data["started_at"], data["finished_at"],
                ),
            )
            event_no = cur.fetchone()["event_no"]
            target_dir = Path(config.MEDIA_ROOT) / "video-tests" / str(event_no)
            target_dir.mkdir(parents=True, exist_ok=True)

            for index, item in enumerate(data["evidence"]):
                filename = f"evidence_{index + 1}_frame_{item['frame_index']}.jpg"
                target = target_dir / filename
                written_paths.append(target)
                target.write_bytes(images[item["file_field"]])
                media_url = f"/media/video-tests/{event_no}/{filename}"
                captured_at = data["started_at"] + timedelta(seconds=item["offset_sec"])
                roles = set(item["roles"])

                cur.execute(
                    """
                    INSERT INTO event_media (
                        event_no, media_url, media_detections, media_confidence,
                        media_captured_at, media_is_primary, media_is_first,
                        media_is_confirmation, media_frame_index,
                        media_source_offset_sec
                    )
                    VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING media_no
                    """,
                    (
                        event_no, media_url,
                        json.dumps(item["detections"], ensure_ascii=False),
                        item["confidence"], captured_at, "PEAK" in roles,
                        "FIRST" in roles, "CONFIRMATION" in roles,
                        item["frame_index"], item["offset_sec"],
                    ),
                )
                media_rows.append({
                    "media_no": cur.fetchone()["media_no"],
                    "media_url": media_url,
                    "media_is_primary": "PEAK" in roles,
                    "media_is_first": "FIRST" in roles,
                    "media_is_confirmation": "CONFIRMATION" in roles,
                    "media_frame_index": item["frame_index"],
                    "media_source_offset_sec": item["offset_sec"],
                })
    except Exception:
        for path in written_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    return {
        "event_no": event_no,
        "result": data["result"],
        "event_status": event_status,
        "event_class": event_class,
        "event_confidence": stats["max_confidence"],
        "event_detected_frames": stats["positive_frames"],
        "event_threshold_frames": stats["threshold_frames"],
        "event_processed_frames": stats["processed_frames"],
        "video": data["video"],
        "statistics": data["statistics"],
        "media": media_rows,
    }


def create_video_test(manifest: dict, uploads) -> dict:
    """최종 판정을 저장하고 DETECTING 단계에서 만든 이벤트를 이어서 갱신한다."""
    data = _validate_manifest(manifest)
    images = _read_images(data["evidence"], uploads)
    stats = data["statistics"]
    ai_event_class = _event_class(stats["detected_classes"])
    ai_event_status = "CONFIRMED" if data["result"] == "FIRE" else "DISMISSED"
    source_metadata = {
        "result": data["result"],
        "video": data["video"],
        "model": data["model"],
        "decision": {
            "processed_frames": stats["processed_frames"],
            "positive_frames": stats["positive_frames"],
            "threshold_frames": stats["threshold_frames"],
            "window_sec": stats["window_sec"],
            "detected_classes": stats["detected_classes"],
        },
    }
    if data["job_id"]:
        source_metadata["job_id"] = data["job_id"]

    written_paths: list[Path] = []
    try:
        with db.get_cursor(commit=True) as cur:
            cur.execute(
                """
                SELECT cctv_no, cctv_name, cctv_location, cctv_address,
                       cctv_lat, cctv_lng
                FROM cctv WHERE cctv_no = %s
                """,
                (data["cctv_no"],),
            )
            cctv = cur.fetchone()
            if cctv is None:
                raise ApiError(404, "CCTV_NOT_FOUND", "카메라를 찾을 수 없습니다.")
            snapshot = _cctv_snapshot(dict(cctv))

            first_at = None
            if stats["first_detected_offset_sec"] is not None:
                first_at = data["started_at"] + timedelta(
                    seconds=stats["first_detected_offset_sec"]
                )
            confirmed_at = None
            if stats["confirmed_offset_sec"] is not None:
                confirmed_at = data["started_at"] + timedelta(
                    seconds=stats["confirmed_offset_sec"]
                )

            existing = None
            if data["job_id"]:
                cur.execute(
                    """
                    SELECT event_no, event_status, event_class, event_confidence,
                           event_detected_at, event_detected_frames,
                           event_source_metadata
                    FROM fire_event
                    WHERE event_source_type = 'VIDEO_TEST'
                      AND event_source_metadata->>'job_id' = %s
                    ORDER BY event_no DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (data["job_id"],),
                )
                existing = cur.fetchone()

            existing_metadata = dict(existing.get("event_source_metadata") or {}) if existing else {}
            operator_decision = existing_metadata.get("operator_decision")
            if operator_decision == "CONFIRM_FIRE":
                effective_result = "FIRE"
                event_status = "CONFIRMED"
            elif operator_decision == "DISMISS":
                effective_result = "NO_FIRE"
                event_status = "DISMISSED"
            else:
                effective_result = data["result"]
                event_status = ai_event_status

            source_metadata = {**existing_metadata, **source_metadata}
            source_metadata.update({
                "ai_result": data["result"],
                "effective_result": effective_result,
            })

            if existing:
                event_no = existing["event_no"]
                event_class = ai_event_class or existing["event_class"]
                existing_frames = int(existing["event_detected_frames"] or 0)
                detected_frames = max(existing_frames, stats["positive_frames"])
                event_confidence = stats["max_confidence"]
                if event_confidence is None:
                    event_confidence = existing["event_confidence"]
                event_detected_at = (
                    (confirmed_at or existing["event_detected_at"] or datetime.now())
                    if event_status == "CONFIRMED" else None
                )
                cur.execute(
                    """
                    UPDATE fire_event
                    SET event_status = %s,
                        event_class = %s,
                        event_first_detected_at = COALESCE(event_first_detected_at, %s),
                        event_detected_at = %s,
                        event_detected_frames = %s,
                        event_threshold_frames = %s,
                        event_confidence = %s,
                        event_source_metadata = %s::jsonb,
                        event_cctv_snapshot = %s::jsonb,
                        event_processed_frames = %s,
                        event_first_detected_offset_sec = COALESCE(
                            event_first_detected_offset_sec, %s
                        ),
                        event_confirmed_offset_sec = %s,
                        event_test_finished_at = %s
                    WHERE event_no = %s
                    """,
                    (
                        event_status, event_class, first_at, event_detected_at,
                        detected_frames, stats["threshold_frames"], event_confidence,
                        json.dumps(source_metadata, ensure_ascii=False),
                        json.dumps(snapshot, ensure_ascii=False), stats["processed_frames"],
                        stats["first_detected_offset_sec"], stats["confirmed_offset_sec"],
                        data["finished_at"], event_no,
                    ),
                )
            else:
                event_class = ai_event_class
                event_detected_at = confirmed_at if event_status == "CONFIRMED" else None
                cur.execute(
                    """
                    INSERT INTO fire_event (
                        cctv_no, event_status, event_class,
                        event_first_detected_at, event_detected_at,
                        event_detected_frames, event_threshold_frames,
                        event_confidence, event_is_test, event_source_type,
                        event_source_metadata, event_cctv_snapshot,
                        event_processed_frames, event_first_detected_offset_sec,
                        event_confirmed_offset_sec, event_test_started_at,
                        event_test_finished_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        true, 'VIDEO_TEST', %s::jsonb, %s::jsonb,
                        %s, %s, %s, %s, %s
                    )
                    RETURNING event_no
                    """,
                    (
                        data["cctv_no"], event_status, event_class, first_at,
                        event_detected_at, stats["positive_frames"],
                        stats["threshold_frames"], stats["max_confidence"],
                        json.dumps(source_metadata, ensure_ascii=False),
                        json.dumps(snapshot, ensure_ascii=False), stats["processed_frames"],
                        stats["first_detected_offset_sec"], stats["confirmed_offset_sec"],
                        data["started_at"], data["finished_at"],
                    ),
                )
                event_no = cur.fetchone()["event_no"]

            cur.execute(
                """
                SELECT media_frame_index, media_is_first
                FROM event_media WHERE event_no = %s
                """,
                (event_no,),
            )
            existing_media = cur.fetchall()
            has_first_media = any(row["media_is_first"] for row in existing_media)
            existing_frame_indexes = {
                row["media_frame_index"] for row in existing_media
                if row["media_frame_index"] is not None
            }

            target_dir = Path(config.MEDIA_ROOT) / "video-tests" / str(event_no)
            target_dir.mkdir(parents=True, exist_ok=True)
            for index, item in enumerate(data["evidence"]):
                roles = set(item["roles"])
                if has_first_media and "FIRST" in roles:
                    roles.discard("FIRST")
                if not roles:
                    continue

                if item["frame_index"] in existing_frame_indexes:
                    if "CONFIRMATION" in roles or "PEAK" in roles:
                        cur.execute(
                            """
                            UPDATE event_media
                            SET media_is_confirmation = media_is_confirmation OR %s,
                                media_is_primary = media_is_primary OR %s
                            WHERE event_no = %s AND media_frame_index = %s
                            """,
                            (
                                "CONFIRMATION" in roles, "PEAK" in roles,
                                event_no, item["frame_index"],
                            ),
                        )
                    continue

                filename = f"evidence_{index + 1}_frame_{item['frame_index']}.jpg"
                target = target_dir / filename
                written_paths.append(target)
                target.write_bytes(images[item["file_field"]])
                media_url = f"/media/video-tests/{event_no}/{filename}"
                captured_at = data["started_at"] + timedelta(seconds=item["offset_sec"])
                if "PEAK" in roles:
                    cur.execute(
                        "UPDATE event_media SET media_is_primary = false WHERE event_no = %s",
                        (event_no,),
                    )
                cur.execute(
                    """
                    INSERT INTO event_media (
                        event_no, media_url, media_detections, media_confidence,
                        media_captured_at, media_is_primary, media_is_first,
                        media_is_confirmation, media_frame_index,
                        media_source_offset_sec
                    )
                    VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        event_no, media_url,
                        json.dumps(item["detections"], ensure_ascii=False),
                        item["confidence"], captured_at, "PEAK" in roles,
                        "FIRST" in roles, "CONFIRMATION" in roles,
                        item["frame_index"], item["offset_sec"],
                    ),
                )

            cur.execute(
                """
                SELECT media_no, media_url, media_confidence,
                       media_captured_at, media_is_primary, media_is_first,
                       media_is_confirmation, media_frame_index,
                       media_source_offset_sec
                FROM event_media WHERE event_no = %s ORDER BY media_no
                """,
                (event_no,),
            )
            media_rows = [dict(row) for row in cur.fetchall()]
    except Exception:
        for path in written_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    return {
        "event_no": event_no,
        "result": effective_result,
        "ai_result": data["result"],
        "event_status": event_status,
        "operator_decision": operator_decision,
        "event_class": event_class,
        "event_confidence": stats["max_confidence"],
        "event_detected_frames": stats["positive_frames"],
        "event_threshold_frames": stats["threshold_frames"],
        "event_processed_frames": stats["processed_frames"],
        "video": data["video"],
        "statistics": data["statistics"],
        "media": media_rows,
    }
