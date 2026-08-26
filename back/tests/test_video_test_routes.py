"""관리자 UI용 샘플 영상 테스트 API 검증."""

import io
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import config
import db
import pytest


def _wait_for_terminal(client, job_id, headers):
    current = None
    for _ in range(100):
        current = client.get(
            f"/api/video-tests/jobs/{job_id}",
            headers=headers,
        ).get_json()
        if current["status"] in {"SUCCEEDED", "FAILED"}:
            return current
        time.sleep(0.01)
    return current


def test_sample_list_is_admin_only(client, admin_headers, viewer_headers, tmp_path, monkeypatch):
    sample_root = tmp_path / "ai-model" / "samples"
    sample_root.mkdir(parents=True)
    (sample_root / "fire_test.mp4").write_bytes(b"sample")
    (sample_root / "readme.txt").write_text("ignore", encoding="utf-8")
    monkeypatch.setattr(config, "AI_MODEL_ROOT", tmp_path / "ai-model")

    response = client.get("/api/video-tests/samples", headers=admin_headers)

    assert response.status_code == 200
    assert response.get_json() == {
        "items": [{
            "name": "fire_test.mp4",
            "extension": "mp4",
            "size_bytes": 6,
            "preview_url": "/media/video-tests/samples/fire_test.mp4",
        }],
    }

    denied = client.get("/api/video-tests/samples", headers=viewer_headers)
    assert denied.status_code == 403
    assert denied.get_json()["code"] == "FORBIDDEN"


def test_run_sample_uses_selected_cctv_and_returns_ai_result(
    client, admin_headers, tmp_path, monkeypatch,
):
    model_root = tmp_path / "ai-model"
    sample_root = model_root / "samples"
    sample_root.mkdir(parents=True)
    sample_path = sample_root / "fire_test.mp4"
    sample_path.write_bytes(b"sample")
    python_path = model_root / ".venv" / "Scripts" / "python.exe"
    script_path = model_root / "validate_video.py"
    python_path.parent.mkdir(parents=True)
    python_path.write_bytes(b"python")
    script_path.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr(config, "AI_MODEL_ROOT", model_root)
    monkeypatch.setattr(config, "AI_PYTHON", python_path)
    monkeypatch.setattr(config, "AI_VALIDATE_SCRIPT", script_path)

    def fake_run(command, **kwargs):
        result_path = Path(command[command.index("--result-json") + 1])
        result_path.write_text(json.dumps({
            "event_no": 77,
            "result": "NO_FIRE",
            "cctv_no": 2,
        }), encoding="utf-8")
        assert command[command.index("--video") + 1] == str(sample_path.resolve())
        assert command[command.index("--cctv-no") + 1] == "2"
        assert kwargs["cwd"] == str(model_root)
        return SimpleNamespace(returncode=0, stdout="AI output")

    monkeypatch.setattr("services.video_test_runner.subprocess.run", fake_run)

    response = client.post(
        "/api/video-tests/run-sample",
        json={"sample_name": "fire_test.mp4", "cctv_no": 2},
        headers=admin_headers,
    )

    assert response.status_code == 202
    job = response.get_json()
    assert job["job_id"]
    assert job["cctv_no"] == 2
    assert job["sample_name"] == "fire_test.mp4"

    completed = _wait_for_terminal(client, job["job_id"], admin_headers)

    assert completed["status"] == "SUCCEEDED"
    assert completed["result"] == {
        "event_no": 77,
        "result": "NO_FIRE",
        "cctv_no": 2,
    }


def test_progress_endpoint_marks_confirmation_and_saves_evidence(
    client, admin_headers, tmp_path, monkeypatch,
):
    model_root = tmp_path / "ai-model"
    sample_root = model_root / "samples"
    sample_root.mkdir(parents=True)
    (sample_root / "fire_test.mp4").write_bytes(b"sample")
    python_path = model_root / ".venv" / "Scripts" / "python.exe"
    script_path = model_root / "validate_video.py"
    python_path.parent.mkdir(parents=True)
    python_path.write_bytes(b"python")
    script_path.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr(config, "AI_MODEL_ROOT", model_root)
    monkeypatch.setattr(config, "AI_PYTHON", python_path)
    monkeypatch.setattr(config, "AI_VALIDATE_SCRIPT", script_path)
    monkeypatch.setattr(config, "MEDIA_ROOT", str(tmp_path / "media"))

    started = threading.Event()
    release = threading.Event()

    def fake_run(command, **kwargs):
        started.set()
        release.wait(2)
        result_path = Path(command[command.index("--result-json") + 1])
        result_path.write_text(json.dumps({"event_no": 88, "result": "FIRE"}), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="AI output")

    monkeypatch.setattr("services.video_test_runner.subprocess.run", fake_run)

    response = client.post(
        "/api/video-tests/run-sample",
        json={"sample_name": "fire_test.mp4", "cctv_no": 1},
        headers=admin_headers,
    )
    job_id = response.get_json()["job_id"]
    assert started.wait(1)

    progress = {
        "phase": "FIRE_CONFIRMED",
        "frame_index": 24,
        "event_class": "FLAME",
        "confidence": 0.91,
        "processed_frames": 30,
        "positive_frames": 10,
        "threshold_frames": 10,
        "first_detected_offset_sec": 2.0,
        "confirmed_offset_sec": 8.0,
    }
    progress_response = client.post(
        f"/api/internal/video-tests/{job_id}/progress",
        data={
            "progress": json.dumps(progress),
            "image": (io.BytesIO(b"\xff\xd8fake-jpeg"), "progress.jpg"),
        },
        content_type="multipart/form-data",
        headers={"X-Internal-Key": config.INTERNAL_API_KEY},
    )

    assert progress_response.status_code == 200
    progress_body = progress_response.get_json()
    assert progress_body["alarm_triggered"] is True
    assert progress_body["phase"] == "FIRE_CONFIRMED"
    assert progress_body["media_url"].startswith("/media/video-tests/jobs/")

    release.set()
    completed = _wait_for_terminal(client, job_id, admin_headers)
    assert completed["status"] == "SUCCEEDED"


@pytest.mark.parametrize(
    ("decision", "expected_status", "expected_alarm", "activity_type"),
    [
        ("CONFIRM_FIRE", "CONFIRMED", True, "FIRE_CONFIRMED"),
        ("DISMISS", "DISMISSED", False, "FIRE_DISMISSED"),
    ],
)
def test_operator_can_decide_after_first_detection(
    client, admin_headers, tmp_path, monkeypatch,
    decision, expected_status, expected_alarm, activity_type,
):
    """최초 감지 이벤트를 관제자가 확정하거나 오탐 처리할 수 있다."""
    model_root = tmp_path / "ai-model"
    sample_root = model_root / "samples"
    sample_root.mkdir(parents=True)
    (sample_root / "fire_test.mp4").write_bytes(b"sample")
    python_path = model_root / ".venv" / "Scripts" / "python.exe"
    script_path = model_root / "validate_video.py"
    python_path.parent.mkdir(parents=True)
    python_path.write_bytes(b"python")
    script_path.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr(config, "AI_MODEL_ROOT", model_root)
    monkeypatch.setattr(config, "AI_PYTHON", python_path)
    monkeypatch.setattr(config, "AI_VALIDATE_SCRIPT", script_path)
    monkeypatch.setattr(config, "MEDIA_ROOT", str(tmp_path / "media"))

    started = threading.Event()
    release = threading.Event()
    event_no_holder = {}

    def fake_run(command, **kwargs):
        started.set()
        release.wait(2)
        result_path = Path(command[command.index("--result-json") + 1])
        result_path.write_text(json.dumps({
            "event_no": event_no_holder["event_no"],
            "result": "FIRE" if decision == "CONFIRM_FIRE" else "NO_FIRE",
            "event_status": expected_status,
        }), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="AI output")

    monkeypatch.setattr("services.video_test_runner.subprocess.run", fake_run)

    try:
        response = client.post(
            "/api/video-tests/run-sample",
            json={"sample_name": "fire_test.mp4", "cctv_no": 1},
            headers=admin_headers,
        )
        assert response.status_code == 202
        job_id = response.get_json()["job_id"]
        assert started.wait(1)

        progress_response = client.post(
            f"/api/internal/video-tests/{job_id}/progress",
            data={
                "progress": json.dumps({
                    "phase": "DETECTING",
                    "frame_index": 12,
                    "offset_sec": 4.0,
                    "event_class": "FLAME",
                    "confidence": 0.91,
                    "processed_frames": 13,
                    "positive_frames": 1,
                    "threshold_frames": 10,
                }),
                "image": (io.BytesIO(b"\xff\xd8first-detection"), "progress.jpg"),
            },
            content_type="multipart/form-data",
            headers={"X-Internal-Key": config.INTERNAL_API_KEY},
        )

        assert progress_response.status_code == 200
        detecting = progress_response.get_json()
        assert detecting["phase"] == "DETECTING"
        assert detecting["human_review_required"] is True
        assert detecting["alarm_triggered"] is False
        assert detecting["event_no"]
        assert detecting["first_detection_media_url"].startswith("/media/video-tests/jobs/")
        event_no_holder["event_no"] = detecting["event_no"]

        pending = db.query_one(
            "SELECT event_status FROM fire_event WHERE event_no = %s",
            (detecting["event_no"],),
        )
        assert pending["event_status"] == "PENDING"

        decision_response = client.post(
            f"/api/video-tests/jobs/{job_id}/decision",
            json={"decision": decision, "reason": "관제 화면 확인"},
            headers=admin_headers,
        )

        assert decision_response.status_code == 200
        decided = decision_response.get_json()
        assert decided["operator_decision"] == decision
        assert decided["phase"] == (
            "FIRE_CONFIRMED" if decision == "CONFIRM_FIRE" else "DISMISSED"
        )
        assert decided["alarm_triggered"] is expected_alarm

        event = db.query_one(
            "SELECT event_status, event_source_metadata FROM fire_event WHERE event_no = %s",
            (detecting["event_no"],),
        )
        assert event["event_status"] == expected_status
        assert event["event_source_metadata"]["operator_decision"] == decision
        assert event["event_source_metadata"]["operator_user_no"] == 1

        activity = db.query_one(
            """SELECT activity_type, activity_target_no
               FROM user_activity
               WHERE user_no = 1
               ORDER BY activity_no DESC LIMIT 1""",
        )
        assert activity["activity_type"] == activity_type
        assert activity["activity_target_no"] == detecting["event_no"]
    finally:
        release.set()

    completed = _wait_for_terminal(client, job_id, admin_headers)
    assert completed["status"] == "SUCCEEDED"


def test_run_sample_rejects_unknown_sample(client, admin_headers, tmp_path, monkeypatch):
    (tmp_path / "samples").mkdir()
    monkeypatch.setattr(config, "AI_MODEL_ROOT", tmp_path)

    response = client.post(
        "/api/video-tests/run-sample",
        json={"sample_name": "missing.mp4", "cctv_no": 1},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.get_json()["code"] == "SAMPLE_NOT_FOUND"


def test_run_sample_rejects_invalid_cctv_number(client, admin_headers, tmp_path, monkeypatch):
    (tmp_path / "samples").mkdir()
    (tmp_path / "samples" / "fire_test.mp4").write_bytes(b"sample")
    monkeypatch.setattr(config, "AI_MODEL_ROOT", tmp_path)

    response = client.post(
        "/api/video-tests/run-sample",
        json={"sample_name": "fire_test.mp4", "cctv_no": "1"},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.get_json()["field"] == "cctv_no"


# ---------- 실전 모드(live) ----------
#
# live=true 면 모의 판정(validate_video.py) 대신 run_video.py --send 를 돌려서
# 검출이 실검출 API(POST /api/internal/detections)로 들어간다 — 실제 텔레그램
# 알림과 무응답 시 119 신고까지 이어지는 경로다. run_video.py 는 진행상황
# 콜백이 없으므로 최종 stdout 의 "event_no=NN" 한 줄로만 결과를 판정한다.

def _setup_live_env(tmp_path, monkeypatch):
    """AI 실행 환경(가짜 파이썬 + run_video.py + 샘플)을 만든다."""
    model_root = tmp_path / "ai-model"
    sample_root = model_root / "samples"
    sample_root.mkdir(parents=True)
    sample_path = sample_root / "fire_test.mp4"
    sample_path.write_bytes(b"sample")
    python_path = model_root / ".venv" / "Scripts" / "python.exe"
    python_path.parent.mkdir(parents=True)
    python_path.write_bytes(b"python")
    (model_root / "run_video.py").write_text("# fake", encoding="utf-8")
    script_path = model_root / "validate_video.py"
    script_path.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr(config, "AI_MODEL_ROOT", model_root)
    monkeypatch.setattr(config, "AI_PYTHON", python_path)
    monkeypatch.setattr(config, "AI_VALIDATE_SCRIPT", script_path)
    return model_root, sample_path


def test_run_sample_rejects_non_boolean_live(client, admin_headers, tmp_path, monkeypatch):
    """live 는 boolean 만 받는다 — 문자열 "true" 같은 값은 400."""
    (tmp_path / "samples").mkdir()
    (tmp_path / "samples" / "fire_test.mp4").write_bytes(b"sample")
    monkeypatch.setattr(config, "AI_MODEL_ROOT", tmp_path)

    response = client.post(
        "/api/video-tests/run-sample",
        json={"sample_name": "fire_test.mp4", "cctv_no": 1, "live": "true"},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.get_json()["field"] == "live"


def test_live_run_builds_run_video_send_command_and_confirms(
    client, admin_headers, tmp_path, monkeypatch,
):
    """live=true: run_video.py --send 명령이 구성되고, stdout 의 event_no 로 확정 처리."""
    model_root, sample_path = _setup_live_env(tmp_path, monkeypatch)
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout=">>> 화재 확정 CONFIRMED  event_no=61\n",
        )

    monkeypatch.setattr("services.video_test_runner.subprocess.run", fake_run)

    response = client.post(
        "/api/video-tests/run-sample",
        json={"sample_name": "fire_test.mp4", "cctv_no": 2, "live": True},
        headers=admin_headers,
    )

    assert response.status_code == 202
    job = response.get_json()
    assert job["live"] is True

    completed = _wait_for_terminal(client, job["job_id"], admin_headers)
    assert completed["status"] == "SUCCEEDED"
    assert completed["phase"] == "FIRE_CONFIRMED"
    assert completed["alarm_triggered"] is True
    assert completed["event_no"] == 61
    assert completed["finished_at"] is not None

    command = captured["command"]
    assert command[0] == str(config.AI_PYTHON)
    assert command[1] == str(model_root / "run_video.py")
    assert "--send" in command
    assert command[command.index("--video") + 1] == str(sample_path.resolve())
    assert command[command.index("--cctv-no") + 1] == "2"
    assert command[command.index("--api") + 1] == f"http://127.0.0.1:{config.APP_PORT}"
    assert captured["kwargs"]["cwd"] == str(model_root)
    # run_video.py 는 X-Internal-Key 를 --key > 환경변수 > 루트 .env 순으로 찾는다
    assert captured["kwargs"]["env"]["INTERNAL_API_KEY"] == config.INTERNAL_API_KEY


def test_live_run_without_event_no_is_dismissed(
    client, admin_headers, tmp_path, monkeypatch,
):
    """stdout 에 event_no 가 없으면(확정 미달) DISMISSED 로 끝난다."""
    _setup_live_env(tmp_path, monkeypatch)

    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="검출 없음 — 판정 종료\n")

    monkeypatch.setattr("services.video_test_runner.subprocess.run", fake_run)

    response = client.post(
        "/api/video-tests/run-sample",
        json={"sample_name": "fire_test.mp4", "cctv_no": 1, "live": True},
        headers=admin_headers,
    )
    assert response.status_code == 202

    completed = _wait_for_terminal(client, response.get_json()["job_id"], admin_headers)
    assert completed["status"] == "SUCCEEDED"
    assert completed["phase"] == "DISMISSED"
    assert completed["alarm_triggered"] is False
    assert completed["event_no"] is None


def test_live_run_nonzero_exit_fails_with_stdout_tail(
    client, admin_headers, tmp_path, monkeypatch,
):
    """run_video.py 가 0 이 아닌 코드로 죽으면 FAILED + stdout 꼬리가 에러 메시지."""
    _setup_live_env(tmp_path, monkeypatch)

    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=1, stdout="Traceback: 모델 로드 실패\n")

    monkeypatch.setattr("services.video_test_runner.subprocess.run", fake_run)

    response = client.post(
        "/api/video-tests/run-sample",
        json={"sample_name": "fire_test.mp4", "cctv_no": 1, "live": True},
        headers=admin_headers,
    )
    assert response.status_code == 202

    completed = _wait_for_terminal(client, response.get_json()["job_id"], admin_headers)
    assert completed["status"] == "FAILED"
    assert completed["error"]["code"] == "AI_PROCESS_FAILED"
    assert "모델 로드 실패" in completed["error"]["message"]


def test_run_sample_without_live_keeps_mock_path(
    client, admin_headers, tmp_path, monkeypatch,
):
    """live 생략 시 기존 validate_video.py 경로 그대로다 — job 의 live 는 false."""
    model_root, _ = _setup_live_env(tmp_path, monkeypatch)

    def fake_run(command, **kwargs):
        result_path = Path(command[command.index("--result-json") + 1])
        result_path.write_text(json.dumps({
            "event_no": 77, "result": "NO_FIRE", "cctv_no": 1,
        }), encoding="utf-8")
        assert command[1] == str(model_root / "validate_video.py")
        return SimpleNamespace(returncode=0, stdout="AI output")

    monkeypatch.setattr("services.video_test_runner.subprocess.run", fake_run)

    response = client.post(
        "/api/video-tests/run-sample",
        json={"sample_name": "fire_test.mp4", "cctv_no": 1},
        headers=admin_headers,
    )

    assert response.status_code == 202
    job = response.get_json()
    assert job["live"] is False

    completed = _wait_for_terminal(client, job["job_id"], admin_headers)
    assert completed["status"] == "SUCCEEDED"
