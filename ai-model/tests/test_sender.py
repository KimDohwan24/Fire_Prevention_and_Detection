"""백엔드 전송 단위 테스트 — requests.Session 대신 가짜를 주입한다.

계약 상대는 back/routes/internal_routes.py 의 POST /api/internal/detections.
"""
from datetime import datetime

import pytest

from fireguard_detect.sender import DetectionSender, SenderConfigError


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"event_no": 1}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, *responses):
        self._responses = list(responses) or [FakeResponse()]
        self.requests = []

    def post(self, url, **kwargs):
        self.requests.append({"url": url, **kwargs})
        if len(self._responses) > 1:
            return self._responses.pop(0)
        response = self._responses[0]
        if isinstance(response, Exception):
            raise response
        return response


def make_sender(*responses, **kwargs):
    session = FakeSession(*responses)
    kwargs.setdefault("base_url", "http://localhost:5000")
    # 아무 문자열이어도 되는 자리다 (FakeSession 은 값을 보지 않는다).
    # 예전에는 여기에 `dev-internal-key` 를 썼는데, 그건 백엔드 기본값과 같은
    # 값이라 '진짜 기본값이 있다'는 오해를 남긴다 — 그 기본값은 없어졌다.
    kwargs.setdefault("internal_key", "test-key")
    return DetectionSender(session=session, **kwargs), session


DETECTIONS = [{"cls": "flame", "conf": 0.9, "bbox": [1, 2, 3, 4]}]


def test_posts_to_the_internal_detections_endpoint():
    sender, session = make_sender()

    sender.send(cctv_no=7, detections=DETECTIONS)

    assert session.requests[0]["url"] == \
        "http://localhost:5000/api/internal/detections"


def test_trailing_slash_in_base_url_does_not_double_up():
    sender, session = make_sender(base_url="http://localhost:5000/")

    sender.send(cctv_no=7, detections=DETECTIONS)

    assert session.requests[0]["url"] == \
        "http://localhost:5000/api/internal/detections"


def test_sends_the_internal_key_header():
    """JWT 가 아니라 X-Internal-Key 로 인증한다 (auth.internal_key_required)."""
    sender, session = make_sender(internal_key="secret-key")

    sender.send(cctv_no=7, detections=DETECTIONS)

    assert session.requests[0]["headers"]["X-Internal-Key"] == "secret-key"


def test_payload_matches_the_backend_contract():
    sender, session = make_sender()
    when = datetime(2026, 8, 10, 14, 30, 5)

    sender.send(cctv_no=7, detections=DETECTIONS,
                media_url="events/2026-08-10/7_143005.jpg", captured_at=when)

    body = session.requests[0]["json"]
    assert body == {
        "cctv_no": 7,
        "captured_at": "2026-08-10T14:30:05",
        "media_url": "events/2026-08-10/7_143005.jpg",
        "detections": DETECTIONS,
    }


def test_captured_at_defaults_to_now_not_video_time(monkeypatch):
    """백엔드 윈도우 판정이 wall clock 기준이라 영상 시간축을 넣으면 깨진다."""
    sender, session = make_sender()
    monkeypatch.setattr("fireguard_detect.sender.now",
                        lambda: datetime(2026, 1, 2, 3, 4, 5))

    sender.send(cctv_no=7, detections=DETECTIONS)

    assert session.requests[0]["json"]["captured_at"] == "2026-01-02T03:04:05"


def test_successful_response_is_returned():
    sender, _ = make_sender(FakeResponse(200, {"event_no": 42,
                                               "event_status": "CONFIRMED"}))

    result = sender.send(cctv_no=7, detections=DETECTIONS)

    assert result["event_status"] == "CONFIRMED"


# ---------------------------------------------------------------- 오류 처리


def test_server_error_is_survived():
    """시연 도중 백엔드가 잠깐 죽어도 검출은 멈추면 안 된다."""
    sender, _ = make_sender(FakeResponse(500))

    assert sender.send(cctv_no=7, detections=DETECTIONS) is None
    assert sender.failures == 1


def test_connection_error_is_survived():
    sender, _ = make_sender(ConnectionError("refused"))

    assert sender.send(cctv_no=7, detections=DETECTIONS) is None
    assert sender.failures == 1


def test_failures_do_not_accumulate_after_recovery():
    sender, _ = make_sender(FakeResponse(500), FakeResponse(200))

    sender.send(cctv_no=7, detections=DETECTIONS)
    sender.send(cctv_no=7, detections=DETECTIONS)

    assert sender.consecutive_failures == 0
    assert sender.failures == 1


def test_bad_internal_key_stops_immediately():
    """설정 오류다. 프레임마다 401 을 반복해봐야 의미가 없다."""
    sender, _ = make_sender(FakeResponse(401))

    with pytest.raises(SenderConfigError, match="X-Internal-Key"):
        sender.send(cctv_no=7, detections=DETECTIONS)


def test_unknown_cctv_stops_immediately():
    sender, _ = make_sender(FakeResponse(404, {"code": "CCTV_NOT_FOUND"}))

    with pytest.raises(SenderConfigError, match="cctv_no"):
        sender.send(cctv_no=999, detections=DETECTIONS)


def test_bad_request_stops_immediately():
    """400 은 우리가 보내는 형식이 틀렸다는 뜻이라 계속 보내도 소용없다."""
    sender, _ = make_sender(FakeResponse(400, {"message": "cctv_no 는 필수"}))

    with pytest.raises(SenderConfigError):
        sender.send(cctv_no=7, detections=DETECTIONS)
