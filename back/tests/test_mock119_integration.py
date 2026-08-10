"""mock-119 통합 테스트 — 실제 HTTP 로 mock 소방청 서버와 통신한다.

다른 테스트와 달리 _post_report 스텁(conftest._no_real_report_http)을 걷어내고,
테스트가 직접 mock-119/app.py 를 서브프로세스로 띄운 뒤 진짜 localhost HTTP 로
신고 전송 → 승계 흐름을 검증한다.

- 서버는 모듈 스코프 픽스처로 한 번만 띄우고(포트 6119) 끝나면 반드시 종료한다.
- 빠른 실패가 필요하므로 mode=fail(즉시 500)만 쓴다 — mode=timeout 은
  4회 × 3초 = 12초를 잡아먹으므로 테스트에서는 절대 쓰지 않는다.
"""
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
    """mode=ok: 실제 HTTP 왕복으로 DISPATCHED + R-접두 외부 접수번호 저장."""
    use_real_http(monkeypatch)
    set_agency_endpoints(f"{mock119_server}/report?mode=ok",
                         f"{mock119_server}/report?mode=ok")
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    assert result is not None
    assert result["report_status"] == "DISPATCHED"
    assert re.fullmatch(r"R-\d+", result["report_external_id"])

    (row,) = get_report_rows(event_no)
    assert row["report_status"] == "DISPATCHED"
    assert row["report_attempt_count"] == 1
    assert row["report_external_id"] == result["report_external_id"]

    # mock 서버가 신고를 실제로 수신했는지 확인 (/reports 디버그 API)
    received = requests.get(f"{mock119_server}/reports", timeout=2).json()
    assert any(r["event_no"] == event_no for r in received)


def test_takeover_between_two_real_agencies(mock119_server, monkeypatch):
    """승계 시연: 기관1 mode=fail(즉시 500) → 4회 소진 NO_RESPONSE, 기관2 mode=ok → DISPATCHED."""
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
    assert second["report_status"] == "DISPATCHED"
    assert re.fullmatch(r"R-\d+", second["report_external_id"])

    assert result["report_status"] == "DISPATCHED"
    assert result["agency_no"] == 2
