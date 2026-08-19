"""좌표 → 주소 역지오코딩 (services/geocode.py).

CCTV 등록 시점에만 부르는 함수다. 신고 경로에서는 부르지 않는다 — 119 신고는
동기라(alert_routes 의 respond 핸들러가 요청 스레드에서 start_report 를 끝낸다)
외부 API 지연이 곧 HTTP 응답 지연이 된다.

이 파일의 테스트는 실제 카카오로 나가지 않는다. requests.get 을 전부 대역으로 바꾼다.
"""
import requests

import config
from services import geocode


class FakeResponse:
    """requests.Response 대역 — status_code / json() / text 만 흉내낸다."""

    def __init__(self, status_code=200, body=None, text=""):
        self.status_code = status_code
        self._body = body
        self.text = text

    def json(self):
        if self._body is None:
            raise ValueError("본문 없음")
        return self._body


def patch_get(monkeypatch, fn):
    """requests.get 을 대역으로 바꾸고 호출 기록 리스트를 돌려준다."""
    calls = []

    def wrapper(url, **kwargs):
        calls.append((url, kwargs))
        return fn(url, kwargs)

    monkeypatch.setattr("services.geocode.requests.get", wrapper)
    return calls


def kakao_body(road=None, jibun=None):
    """카카오 coord2address 응답 형태. 값이 없는 쪽은 null 로 온다."""
    return {"documents": [{
        "road_address": {"address_name": road} if road else None,
        "address": {"address_name": jibun} if jibun else None,
    }]}


def test_returns_road_address_when_present(monkeypatch):
    """도로명주소가 있으면 그것을 쓴다."""
    patch_get(monkeypatch, lambda url, kw: FakeResponse(
        200, kakao_body(road="서울특별시 중구 세종대로 110",
                        jibun="서울 중구 태평로1가 31")))

    assert geocode.reverse_geocode(37.5665, 126.9780) == "서울특별시 중구 세종대로 110"


def test_falls_back_to_jibun_when_road_is_null(monkeypatch):
    """도로명이 없으면 지번을 쓴다.

    고속도로 본선·분기점에는 도로명주소가 아예 없다 — 도로명은 건물에 부여되는
    체계다. ITS 카메라는 대부분 고속도로라 이 경로가 예외가 아니라 주 경로다.
    (2026-08-18 실측: 판교분기점·성남 모두 road_address 가 null 이고 지번만 나왔다)
    """
    patch_get(monkeypatch, lambda url, kw: FakeResponse(
        200, kakao_body(road=None, jibun="경기 성남시 수정구 금토동 410-134")))

    assert geocode.reverse_geocode(37.40665, 127.09706) == "경기 성남시 수정구 금토동 410-134"


def test_returns_none_when_no_documents(monkeypatch):
    """주소 구역 밖 좌표는 documents 가 빈다."""
    patch_get(monkeypatch, lambda url, kw: FakeResponse(200, {"documents": []}))

    assert geocode.reverse_geocode(0.0, 0.0) is None


def test_sends_lng_as_x_and_lat_as_y(monkeypatch):
    """x 는 경도, y 는 위도다.

    뒤집어도 카카오는 에러를 주지 않고 엉뚱한 주소를 조용히 돌려준다. 사람이
    알아채기 어려운 종류의 버그라 계약으로 고정한다 (PostGIS ST_MakePoint 와 같은 함정).
    """
    calls = patch_get(monkeypatch,
                      lambda url, kw: FakeResponse(200, kakao_body(road="아무데나")))

    geocode.reverse_geocode(37.5665, 126.9780)

    _, kwargs = calls[0]
    assert kwargs["params"]["x"] == 126.9780      # 경도
    assert kwargs["params"]["y"] == 37.5665       # 위도


def test_sends_kakao_authorization_header(monkeypatch):
    """REST 키를 KakaoAK 스킴으로 싣는다 (소셜 로그인과 같은 키를 재사용한다)."""
    calls = patch_get(monkeypatch,
                      lambda url, kw: FakeResponse(200, kakao_body(road="아무데나")))

    geocode.reverse_geocode(37.5665, 126.9780)

    _, kwargs = calls[0]
    assert kwargs["headers"]["Authorization"] == f"KakaoAK {config.KAKAO_CLIENT_ID}"


def test_skips_http_when_key_missing(monkeypatch):
    """키가 없으면 호출조차 하지 않는다 — 헛된 왕복과 401 로그를 만들지 않는다."""
    monkeypatch.setattr(config, "KAKAO_CLIENT_ID", "")
    calls = patch_get(monkeypatch,
                      lambda url, kw: FakeResponse(200, kakao_body(road="안나와야함")))

    assert geocode.reverse_geocode(37.5665, 126.9780) is None
    assert calls == []


def test_returns_none_on_timeout(monkeypatch):
    """타임아웃은 None 이다 — 예외를 밖으로 던지지 않는다.

    주소 하나 때문에 카메라 등록이 실패하면 안 된다.
    """
    def boom(url, kw):
        raise requests.exceptions.Timeout("시간 초과")
    patch_get(monkeypatch, boom)

    assert geocode.reverse_geocode(37.5665, 126.9780) is None


def test_returns_none_on_error_status(monkeypatch):
    """403 같은 응답도 None 이다.

    카카오 콘솔에서 그 앱의 '카카오맵' 서비스를 안 켜면 실제로 이 403 이 온다:
    {"errorType":"NotAuthorizedError","message":"... disabled OPEN_MAP_AND_LOCAL service."}
    """
    patch_get(monkeypatch, lambda url, kw: FakeResponse(
        403, None, text='{"errorType":"NotAuthorizedError"}'))

    assert geocode.reverse_geocode(37.5665, 126.9780) is None


def test_returns_none_when_body_is_not_json(monkeypatch):
    """200 인데 본문이 JSON 이 아니어도 죽지 않는다."""
    patch_get(monkeypatch, lambda url, kw: FakeResponse(200, None, text="<html>"))

    assert geocode.reverse_geocode(37.5665, 126.9780) is None
