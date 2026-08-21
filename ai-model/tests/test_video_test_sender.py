"""영상 테스트 multipart 전송 계약."""
import json
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from fireguard_detect.video_test import EvidenceFrame
from fireguard_detect.video_test_sender import VideoTestSender, VideoTestSenderError


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"items": []}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return self.response

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return self.response


def test_lists_only_active_cctvs_with_internal_key():
    session = FakeSession(FakeResponse(payload={"items": [{"cctv_no": 1}]}))
    sender = VideoTestSender("http://localhost:5000/", "secret", session=session)

    assert sender.list_active_cctvs() == [{"cctv_no": 1}]
    _, url, kwargs = session.calls[0]
    assert url == "http://localhost:5000/api/internal/cctvs"
    assert kwargs["params"] == {"cctv_status": "ACTIVE"}
    assert kwargs["headers"] == {"X-Internal-Key": "secret"}


def test_submit_sends_manifest_and_jpeg_multipart(monkeypatch):
    class Encoded:
        @staticmethod
        def tobytes():
            return b"\xff\xd8fake-jpeg"

    class FakeCv2:
        @staticmethod
        def imencode(extension, image):
            assert extension == ".jpg"
            return True, Encoded()

    monkeypatch.setitem(sys.modules, "cv2", FakeCv2)
    session = FakeSession(FakeResponse(201, {"event_no": 42, "result": "FIRE"}))
    sender = VideoTestSender("http://localhost:5000", "secret", session=session)
    evidence = EvidenceFrame(
        frame_index=1,
        offset_sec=0,
        image=np.zeros((8, 8, 3), dtype=np.uint8),
        detections=[],
        confidence=0.9,
        roles={"FIRST", "CONFIRMATION", "PEAK"},
    )
    manifest = {"evidence": [evidence.metadata("evidence_0")]}

    response = sender.submit(manifest, [evidence])

    assert response["event_no"] == 42
    _, url, kwargs = session.calls[0]
    assert url.endswith("/api/internal/video-tests")
    assert json.loads(kwargs["data"]["manifest"])["evidence"][0]["file_field"] == "evidence_0"
    assert kwargs["files"]["evidence_0"][2] == "image/jpeg"
    assert kwargs["files"]["evidence_0"][1].startswith(b"\xff\xd8")


def test_http_error_contains_backend_message():
    session = FakeSession(FakeResponse(400, {"message": "manifest 오류"}))
    sender = VideoTestSender("http://localhost:5000", "secret", session=session)

    with pytest.raises(VideoTestSenderError, match="manifest 오류"):
        sender.list_active_cctvs()


def test_send_progress_sends_job_status_and_jpeg(monkeypatch):
    class Encoded:
        @staticmethod
        def tobytes():
            return b"\xff\xd8progress-jpeg"

    class FakeCv2:
        @staticmethod
        def imencode(extension, image):
            assert extension == ".jpg"
            return True, Encoded()

    monkeypatch.setitem(sys.modules, "cv2", FakeCv2)
    session = FakeSession(FakeResponse(200, {"job_id": "a" * 32, "phase": "DETECTING"}))
    sender = VideoTestSender("http://localhost:5000", "secret", session=session)

    response = sender.send_progress(
        "a" * 32,
        {"phase": "DETECTING", "frame_index": 12},
        SimpleNamespace(index=12, image="frame"),
    )

    assert response["phase"] == "DETECTING"
    _, url, kwargs = session.calls[0]
    assert url.endswith(f"/api/internal/video-tests/{'a' * 32}/progress")
    assert json.loads(kwargs["data"]["progress"])["frame_index"] == 12
    assert kwargs["files"]["image"][2] == "image/jpeg"
    assert kwargs["files"]["image"][1].startswith(b"\xff\xd8")


def test_manifest_and_image_count_must_match():
    sender = VideoTestSender("http://localhost:5000", "secret",
                             session=FakeSession(FakeResponse()))

    with pytest.raises(VideoTestSenderError, match="개수가 다릅니다"):
        sender.submit({"evidence": [{}]}, [])
