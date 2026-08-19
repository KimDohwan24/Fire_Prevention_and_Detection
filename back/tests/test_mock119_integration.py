"""mock-119 통합 테스트 — 실제 HTTP 로 mock 소방청 서버와 통신한다.

다른 테스트와 달리 _post_report 스텁(conftest._no_real_report_http)을 걷어내고,
테스트가 직접 mock-119/app.py 를 서브프로세스로 띄운 뒤 진짜 localhost HTTP 로
신고 전송 → 승계 흐름을 검증한다.

- 서버는 모듈 스코프 픽스처로 한 번만 띄우고(포트 6119) 끝나면 반드시 종료한다.
- 빠른 실패가 필요하므로 mode=fail(즉시 500)만 쓴다 — mode=timeout 은
  4회 × 3초 = 12초를 잡아먹으므로 테스트에서는 절대 쓰지 않는다.
"""
import base64
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests
from conftest import make_event

import db
from services import report_service

# 경로: back/tests/ → 프로젝트 루트 → mock-119/app.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MOCK_APP = PROJECT_ROOT / "mock-119" / "app.py"

MOCK_PORT = 6119
BASE = f"http://127.0.0.1:{MOCK_PORT}"


@pytest.fixture(scope="module")
def mock119_server():
    """mock-119 서버를 서브프로세스로 띄우고 /health 가 응답할 때까지 기다린다."""
    assert MOCK_APP.exists(), f"mock 서버 파일 없음: {MOCK_APP}"

    env = dict(os.environ, MOCK119_PORT=str(MOCK_PORT))
    proc = subprocess.Popen(
        [sys.executable, str(MOCK_APP)],
        cwd=str(MOCK_APP.parent),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # 기동 대기: 최대 ~5초 동안 /health 폴링
        deadline = time.monotonic() + 5.0
        while True:
            try:
                r = requests.get(f"{BASE}/health", timeout=0.5)
                if r.status_code == 200 and r.json().get("status") == "ok":
                    break
            except requests.exceptions.RequestException:
                pass
            if proc.poll() is not None:
                pytest.fail(f"mock-119 프로세스가 조기 종료됨 (exit={proc.returncode})")
            if time.monotonic() > deadline:
                pytest.fail("mock-119 서버가 5초 안에 기동하지 않음")
            time.sleep(0.1)
        yield BASE
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def use_real_http(monkeypatch):
    """conftest 의 전역 스텁을 실제 HTTP 구현으로 되돌린다.

    (테스트 본문에서 setattr 하므로 autouse 스텁보다 나중에 적용되어 이긴다.)
    """
    monkeypatch.setattr(report_service, "_post_report",
                        report_service._real_post_report)


def set_agency_endpoints(ep1: str, ep2: str):
    db.execute("UPDATE agency SET agency_endpoint = %s WHERE agency_no = 1", (ep1,))
    db.execute("UPDATE agency SET agency_endpoint = %s WHERE agency_no = 2", (ep2,))


def get_report_rows(event_no):
    return db.query(
        "SELECT * FROM report_119 WHERE event_no = %s ORDER BY report_no", (event_no,)
    )


def test_report_dispatched_via_real_mock_server(mock119_server, monkeypatch):
    """mode=ok: 실제 HTTP 왕복으로 ACCEPTED + R-접두 외부 접수번호 저장."""
    use_real_http(monkeypatch)
    set_agency_endpoints(f"{mock119_server}/report?mode=ok",
                         f"{mock119_server}/report?mode=ok")
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    assert result is not None
    assert result["report_status"] == "ACCEPTED"
    assert re.fullmatch(r"R-\d+", result["report_external_id"])

    (row,) = get_report_rows(event_no)
    assert row["report_status"] == "ACCEPTED"
    assert row["report_attempt_count"] == 1
    assert row["report_external_id"] == result["report_external_id"]

    # mock 서버가 신고를 실제로 수신했는지 확인 (/reports 디버그 API)
    received = requests.get(f"{mock119_server}/reports", timeout=2).json()
    assert any(r["event_no"] == event_no for r in received)


def test_takeover_between_two_real_agencies(mock119_server, monkeypatch):
    """승계 시연: 기관1 mode=fail(즉시 500) → 4회 소진 NO_RESPONSE, 기관2 mode=ok → ACCEPTED."""
    use_real_http(monkeypatch)
    set_agency_endpoints(f"{mock119_server}/report?mode=fail",
                         f"{mock119_server}/report?mode=ok")
    event_no = make_event()

    result = report_service.start_report(event_no, "NO_RESPONSE_TIMEOUT")

    rows = get_report_rows(event_no)
    assert len(rows) == 2
    first, second = rows
    assert first["agency_no"] == 1
    assert first["report_status"] == "NO_RESPONSE"
    assert first["report_attempt_count"] == 4
    assert second["agency_no"] == 2
    assert second["report_sequence"] == 2
    assert second["report_status"] == "ACCEPTED"
    assert re.fullmatch(r"R-\d+", second["report_external_id"])

    assert result["report_status"] == "ACCEPTED"
    assert result["agency_no"] == 2


def test_same_report_uid_is_accepted_once_per_station(mock119_server, monkeypatch):
    """같은 신고 ID 를 다시 보내면 새로 접수하지 않고 먼저 준 접수번호만 재발신한다.

    3초 타임아웃 뒤의 재전송이 출동 여러 건이 되는 걸 막는 장치다.
    여기서는 재전송을 직접 흉내내기 위해 같은 페이로드를 두 번 POST 한다.
    """
    use_real_http(monkeypatch)
    event_no = make_event()
    payload = {"report_uid": report_service.report_uid(event_no),
               "event_no": event_no, "address": "본관 정문 앞",
               "event_class": "FLAME", "confidence": 0.9}
    # mock 서버는 모듈 스코프라 접수 대장이 테스트 간에 남는데, conftest 가 매
    # 테스트마다 RESTART IDENTITY 로 event_no 를 1 로 되돌려 uid 가 겹친다.
    # 이 테스트 전용 station 을 써서 대장을 분리한다.
    url = f"{mock119_server}/report?mode=ok&station=dedupe-one"

    first = requests.post(url, json=payload, timeout=2).json()
    second = requests.post(url, json=payload, timeout=2).json()

    assert re.fullmatch(r"R-\d+", first["external_id"])
    assert first.get("duplicate") is None       # 첫 건은 진짜 접수
    assert second["external_id"] == first["external_id"]
    assert second["duplicate"] is True          # 두 번째는 재발신일 뿐

    # 수신 기록에는 2건이 남지만 접수된 것은 1건이다
    # (uid 는 다른 테스트와 겹칠 수 있으므로 이 테스트의 station 으로 걸러낸다)
    received = requests.get(f"{mock119_server}/reports", timeout=2).json()
    mine = [r for r in received if r.get("station") == "dedupe-one"]
    assert len(mine) == 2
    assert [r.get("duplicate") for r in mine] == [False, True]


def test_different_stations_accept_the_same_report_uid(mock119_server, monkeypatch):
    """소방서가 다르면 같은 신고 ID 라도 각자 접수한다 — 승계가 막히면 안 된다.

    중복 검사는 접수 서버 안에서만 의미가 있다. 기관 1이 무응답이라 기관 2로
    넘겼는데 "이미 접수됨"으로 튕기면 신고가 아무 데도 안 닿는다.
    """
    use_real_http(monkeypatch)
    event_no = make_event()
    payload = {"report_uid": report_service.report_uid(event_no),
               "event_no": event_no, "address": "본관 정문 앞",
               "event_class": "FLAME", "confidence": 0.9}

    a = requests.post(f"{mock119_server}/report?mode=ok&station=dedupe-a",
                      json=payload, timeout=2).json()
    b = requests.post(f"{mock119_server}/report?mode=ok&station=dedupe-b",
                      json=payload, timeout=2).json()

    assert a["external_id"] != b["external_id"]
    assert b.get("duplicate") is None


# ---------- 소방서 콘솔 화면 ----------
#
# 시연에서 "소방서가 무엇을 받았는지"를 보여주는 화면이다. 여기 테스트는 화면의
# 생김새가 아니라 화면이 딛고 서는 계약만 본다 — 목록에서 이미지가 빠졌는가,
# 링크로 따로 받아지는가, 표에 찍을 값이 남아 있는가.
#
# 접수 대장이 모듈 스코프로 남으므로 테스트마다 station 을 다르게 준다.

# 진짜 JPEG 일 필요는 없다 — 서버는 형식을 보지 않고 바이트를 그대로 돌려주므로,
# 왕복에서 바이트가 변하지 않았다는 것만 확인하면 된다.
JPEG_BYTES = b"\xff\xd8fake-jpeg-bytes"


def post_console_report(base: str, station: str, with_image: bool) -> dict:
    """콘솔이 표에 찍는 필드를 갖춘 신고를 한 건 보내고, 그 station 의 목록 항목을 준다."""
    payload = {
        "report_uid": f"console-{station}",
        "event_no": 9001,
        "address": "서울 강남구 테헤란로 123",
        "place": "본관 3층 복도",
        "event_class": "FLAME",
        "confidence": 0.93,
        "cctv": {"name": "본관-복도-01", "width": 1920, "height": 1080},
    }
    if with_image:
        payload["image_base64"] = base64.b64encode(JPEG_BYTES).decode()

    requests.post(f"{base}/report?mode=ok&station={station}", json=payload, timeout=2)

    received = requests.get(f"{base}/reports", timeout=2).json()
    (mine,) = [r for r in received if r.get("station") == station]
    return mine


def test_console_page_is_served(mock119_server):
    """접수 콘솔 화면이 뜬다 — 출동 지령 버튼과 콜백에 필요한 것들이 실려 있다."""
    res = requests.get(f"{mock119_server}/", timeout=2)

    assert res.status_code == 200
    assert "text/html" in res.headers["Content-Type"]
    assert "출동 지령" in res.text
    assert "X-Agency-Key" in res.text            # 인증키 헤더를 실어 보낸다
    assert "/api/reports/dispatch" in res.text   # 콜백 주소가 없을 때의 기본값


def test_reports_list_excludes_image_but_links_it(mock119_server):
    """목록에서는 base64 를 빼고 링크만 준다.

    화면이 2초마다 이 목록을 폴링하는데 수 MB base64 가 매번 실리면 브라우저가 멈춘다.
    대신 표에 찍어야 하는 값(주소·설치위치)은 그대로 남아 있어야 한다.
    """
    mine = post_console_report(mock119_server, "console-list", with_image=True)

    assert "image_base64" not in mine
    assert mine["has_image"] is True
    assert mine["image_url"] == f"/reports/{mine['index']}/image"
    assert mine["address"] == "서울 강남구 테헤란로 123"
    assert mine["place"] == "본관 3층 복도"


def test_image_route_returns_jpeg(mock119_server):
    """분리한 이미지 경로가 원본 바이트를 그대로 준다 — <img src> 로 바로 걸린다."""
    mine = post_console_report(mock119_server, "console-image", with_image=True)

    res = requests.get(f"{mock119_server}{mine['image_url']}", timeout=2)

    assert res.status_code == 200
    assert res.headers["Content-Type"] == "image/jpeg"
    assert res.content == JPEG_BYTES


def test_image_route_404_without_image(mock119_server):
    """이미지 없이 온 신고는 404 다 — 시연 중 500 이 뜨면 화면이 멎은 것처럼 보인다."""
    mine = post_console_report(mock119_server, "console-noimage", with_image=False)

    assert mine["has_image"] is False

    res = requests.get(f"{mock119_server}{mine['image_url']}", timeout=2)

    assert res.status_code == 404
    assert res.json()["error"]
