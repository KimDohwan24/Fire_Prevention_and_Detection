"""119 신고 서비스 테스트 — services/report_service.py + utils/geo.py.

신고 정책 (D4 확정):
- 트리거: 사용자가 화재 확인(USER_CONFIRMED) 또는 무응답 에스컬레이션(NO_RESPONSE_TIMEOUT).
- 대상 기관: 활성(agency_is_active) 기관을 CCTV 좌표 기준 하버사인 거리 오름차순으로 시도.
- 안쪽 루프: 한 기관에 최대 MAX_REPORT_ATTEMPTS(기본 4)회 전송(report_attempt_count).
- 바깥 루프: 기관 승계(report_sequence 1, 2, ...). 소진된 기관 행은 NO_RESPONSE,
  마지막 기관까지 소진되면 그 행만 FAILED.
- DB 부분 유니크 인덱스(UX_report_119_active)로 이벤트당 진행 중 신고 1건 강제.
- 실제 HTTP 는 절대 나가지 않는다 — _post_report 를 monkeypatch 한다.
"""
import psycopg2
import pytest
import requests
from conftest import make_alert, make_alert_pair, make_event, make_report

import config
import db
from services import report_service
from utils.geo import haversine_km

# conftest 시드 좌표
CCTV1 = (37.5665, 126.9780)      # cctv 1 (정문 카메라, '본관 정문 앞')
AGENCY1 = (37.5720, 126.9794)    # 종로소방서
AGENCY2 = (37.5610, 126.9950)    # 중부소방서


class FakeResponse:
    """requests.Response 대역 — status_code 와 json() 만 흉내낸다."""

    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("본문 없음")
        return self._body


def get_report_rows(event_no=None):
    if event_no is None:
        return db.query("SELECT * FROM report_119 ORDER BY report_no")
    return db.query(
        "SELECT * FROM report_119 WHERE event_no = %s ORDER BY report_no", (event_no,)
    )


def patch_post(monkeypatch, fn):
    """_post_report 를 대역으로 바꾸고 호출 기록 리스트를 돌려준다."""
    calls = []

    def wrapper(endpoint, payload):
        calls.append((endpoint, payload))
        return fn(endpoint, payload, len(calls))

    monkeypatch.setattr("services.report_service._post_report", wrapper)
    return calls


def set_distinct_endpoints():
    """시드는 두 기관이 같은 endpoint 라서, 기관별 구분이 필요한 테스트용."""
    db.execute("UPDATE agency SET agency_endpoint = 'http://a1/report' WHERE agency_no = 1")
    db.execute("UPDATE agency SET agency_endpoint = 'http://a2/report' WHERE agency_no = 2")


# ---------- 하버사인 ----------

def test_haversine_agency1_closer_than_agency2():
    """cctv 1 기준으로 종로소방서(1)가 중부소방서(2)보다 가깝다 (거리값 자체도 상식 범위)."""
    d1 = haversine_km(*CCTV1, *AGENCY1)
    d2 = haversine_km(*CCTV1, *AGENCY2)
    assert 0.4 < d1 < 0.9      # 약 0.6km
    assert 1.2 < d2 < 2.0      # 약 1.6km
    assert d1 < d2
    # 같은 지점끼리는 0
    assert haversine_km(*CCTV1, *CCTV1) == pytest.approx(0.0, abs=1e-9)


# ---------- 성공 경로 ----------

def test_start_report_success_first_try(monkeypatch):
    """첫 시도 성공: 가장 가까운 기관(1)으로 ACCEPTED 행 1개, 거리/주소/외부ID 저장."""
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-2026-0001"}))
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    rows = get_report_rows(event_no)
    assert len(rows) == 1
    r = rows[0]
    assert r["agency_no"] == 1
    assert r["report_sequence"] == 1
    assert r["report_status"] == "ACCEPTED"
    assert r["report_external_id"] == "R-2026-0001"
    assert r["report_trigger_reason"] == "USER_CONFIRMED"
    assert r["report_attempt_count"] == 1
    assert r["report_address"] == "본관 정문 앞"  # cctv_location
    assert float(r["report_distance_km"]) == pytest.approx(
        haversine_km(*CCTV1, *AGENCY1), abs=0.002)
    assert r["reported_at"] is not None
    assert r["report_accepted_at"] is not None

    assert result is not None
    assert result["report_no"] == r["report_no"]
    assert result["report_status"] == "ACCEPTED"
    assert result["agency_no"] == 1

    # 페이로드 계약 확인
    assert len(calls) == 1
    _, payload = calls[0]
    assert payload["event_no"] == event_no
    assert payload["address"] == "본관 정문 앞"
    assert payload["lat"] == pytest.approx(CCTV1[0])
    assert payload["lng"] == pytest.approx(CCTV1[1])
    assert payload["event_class"] == "FLAME"
    assert payload["confidence"] == pytest.approx(0.9123)
    assert payload["reported_at"] is not None


def test_start_report_retry_then_success(monkeypatch):
    """2번 실패(타임아웃/거절) 후 3번째 성공 → 같은 기관, attempt_count=3, ACCEPTED."""
    def fn(ep, pl, n):
        if n == 1:
            raise requests.exceptions.Timeout("모의 타임아웃")
        if n == 2:
            return FakeResponse(500)
        return FakeResponse(200, {"external_id": "R-RETRY-01"})

    calls = patch_post(monkeypatch, fn)
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    rows = get_report_rows(event_no)
    assert len(rows) == 1
    assert rows[0]["agency_no"] == 1
    assert rows[0]["report_status"] == "ACCEPTED"
    assert rows[0]["report_attempt_count"] == 3
    assert rows[0]["report_external_id"] == "R-RETRY-01"
    assert len(calls) == 3
    assert result["report_status"] == "ACCEPTED"


def test_start_report_accepts_2xx_without_body(monkeypatch):
    """본문 없는 2xx 도 성공으로 본다 (external_id 는 NULL)."""
    patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(204, None))
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    (r,) = get_report_rows(event_no)
    assert r["report_status"] == "ACCEPTED"
    assert r["report_external_id"] is None
    assert result["report_status"] == "ACCEPTED"


# ---------- 신고 ID (멱등 키) ----------
#
# 재전송은 "상대가 못 받았다"가 아니라 "응답이 안 왔다"일 뿐이다. 같은 신고를
# 식별할 ID 가 없으면 119 쪽에서 같은 화재가 여러 건으로 접수된다.
# 발표 슬라이드 12: "동일 ID 로 최대 4회 재전송", "동일 신고 ID 유지로 중복 접수 방지".

def test_payload_carries_report_uid(monkeypatch):
    """페이로드에 신고 ID 가 실린다 — 이벤트에서 결정되는 값이라 재현 가능하다."""
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-1"}))
    event_no = make_event()

    report_service.start_report(event_no, "USER_CONFIRMED")

    _, payload = calls[0]
    assert payload["report_uid"] == report_service.report_uid(event_no)
    assert payload["report_uid"] == f"FG-{event_no}"


def test_report_uid_identical_across_retries(monkeypatch):
    """같은 기관에 재전송할 때 신고 ID 는 바뀌지 않는다."""
    def fn(ep, pl, n):
        if n < 3:
            raise requests.exceptions.Timeout("모의 타임아웃")
        return FakeResponse(200, {"external_id": "R-RETRY"})

    calls = patch_post(monkeypatch, fn)
    event_no = make_event()

    report_service.start_report(event_no, "USER_CONFIRMED")

    uids = {pl["report_uid"] for _, pl in calls}
    assert len(calls) == 3
    assert uids == {f"FG-{event_no}"}


def test_report_uid_survives_agency_takeover(monkeypatch):
    """기관을 승계해도 신고 ID 는 그대로다 — 다음 기관도 같은 화재임을 알 수 있다.

    report_119 행은 기관마다 새로 생기지만(순번 +1), 신고 ID 는 이벤트 단위다.
    """
    set_distinct_endpoints()

    def fn(ep, pl, n):
        if ep == "http://a1/report":
            raise requests.exceptions.ConnectionError("모의 연결 실패")
        return FakeResponse(200, {"external_id": "R-TAKEOVER"})

    calls = patch_post(monkeypatch, fn)
    event_no = make_event()

    report_service.start_report(event_no, "NO_RESPONSE_TIMEOUT")

    assert len(calls) == 5  # 기관1에 4회 + 기관2에 1회
    assert {pl["report_uid"] for _, pl in calls} == {f"FG-{event_no}"}


def test_report_uid_differs_between_events():
    """다른 화재는 다른 신고 ID 를 받는다."""
    assert report_service.report_uid(11) != report_service.report_uid(12)


# ---------- 승계 (기관 교체) ----------

def test_takeover_to_second_agency(monkeypatch):
    """기관 1이 4회 모두 실패 → 그 행은 NO_RESPONSE(승계), 기관 2가 sequence 2 로 ACCEPTED."""
    set_distinct_endpoints()

    def fn(ep, pl, n):
        if ep == "http://a1/report":
            raise requests.exceptions.ConnectionError("모의 연결 실패")
        return FakeResponse(200, {"external_id": "R-TAKEOVER-02"})

    calls = patch_post(monkeypatch, fn)
    event_no = make_event()

    result = report_service.start_report(event_no, "NO_RESPONSE_TIMEOUT")

    rows = get_report_rows(event_no)
    assert len(rows) == 2
    first, second = rows
    assert first["agency_no"] == 1
    assert first["report_sequence"] == 1
    assert first["report_status"] == "NO_RESPONSE"
    assert first["report_attempt_count"] == 4
    assert first["report_accepted_at"] is None
    assert second["agency_no"] == 2
    assert second["report_sequence"] == 2
    assert second["report_status"] == "ACCEPTED"
    assert second["report_external_id"] == "R-TAKEOVER-02"
    assert float(second["report_distance_km"]) == pytest.approx(
        haversine_km(*CCTV1, *AGENCY2), abs=0.002)

    # 기관 1에 4번, 기관 2에 1번
    assert [ep for ep, _ in calls] == ["http://a1/report"] * 4 + ["http://a2/report"]
    assert result["report_status"] == "ACCEPTED"
    assert result["agency_no"] == 2


def test_all_agencies_fail(monkeypatch):
    """모든 기관 소진 → 앞 기관은 NO_RESPONSE, 마지막 기관 행만 FAILED(전송실패)."""
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(503))
    event_no = make_event()

    result = report_service.start_report(event_no, "NO_RESPONSE_TIMEOUT")

    rows = get_report_rows(event_no)
    assert len(rows) == 2
    assert rows[0]["report_status"] == "NO_RESPONSE"
    assert rows[0]["report_attempt_count"] == 4
    assert rows[1]["report_status"] == "FAILED"
    assert rows[1]["report_attempt_count"] == 4
    assert rows[1]["report_sequence"] == 2
    assert len(calls) == 8  # 2개 기관 × 4회

    assert result is not None
    assert result["report_status"] == "FAILED"
    assert result["report_no"] == rows[1]["report_no"]


def test_max_attempts_configurable(monkeypatch):
    """MAX_REPORT_ATTEMPTS 를 줄이면 안쪽 루프 횟수도 줄어든다."""
    monkeypatch.setattr(config, "MAX_REPORT_ATTEMPTS", 2)
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(503))
    event_no = make_event()

    report_service.start_report(event_no, "USER_CONFIRMED")

    rows = get_report_rows(event_no)
    assert [r["report_attempt_count"] for r in rows] == [2, 2]
    assert len(calls) == 4  # 2개 기관 × 2회


# ---------- 기관 필터링 ----------

def test_inactive_agency_excluded(monkeypatch):
    """비활성 기관은 후보에서 빠진다 — 기관 1 비활성 → 곧장 기관 2, sequence 1."""
    db.execute("UPDATE agency SET agency_is_active = false WHERE agency_no = 1")
    patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-A2"}))
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    rows = get_report_rows(event_no)
    assert len(rows) == 1
    assert rows[0]["agency_no"] == 2
    assert rows[0]["report_sequence"] == 1
    assert rows[0]["report_status"] == "ACCEPTED"
    assert result["agency_no"] == 2


def test_no_active_agencies_returns_none(monkeypatch):
    """활성 기관이 하나도 없으면 None, 행도 HTTP 호출도 없다."""
    db.execute("UPDATE agency SET agency_is_active = false")
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200))
    event_no = make_event()

    assert report_service.start_report(event_no, "USER_CONFIRMED") is None
    assert get_report_rows() == []
    assert calls == []


# ---------- 멱등성 · 동시성 가드 ----------

def test_start_report_idempotent_existing_active(monkeypatch):
    """이미 진행 중(ACCEPTED) 신고가 있으면 그 정보를 돌려주고 아무 것도 안 한다."""
    event_no = make_event()
    existing_no = make_report(event_no, agency_no=1, status="ACCEPTED")
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200))

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    assert result is not None
    assert result["report_no"] == existing_no
    assert result["report_status"] == "ACCEPTED"
    assert len(get_report_rows(event_no)) == 1  # 새 행 없음
    assert calls == []                          # HTTP 호출 없음


def test_start_report_test_event_skipped(monkeypatch):
    """점검 모드(event_is_test) 이벤트는 신고하지 않는다."""
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200))
    event_no = make_event(is_test=True)

    assert report_service.start_report(event_no, "USER_CONFIRMED") is None
    assert get_report_rows() == []
    assert calls == []


def test_unique_violation_guard_returns_existing(monkeypatch):
    """행 INSERT 시점에 다른 활성 신고가 끼어들면(23505) 죽지 않고 기존 신고를 돌려준다.

    사전 체크(_find_active_report)를 무력화해서 INSERT 까지 진행시키고,
    부분 유니크 인덱스(UX_report_119_active) 위반을 실제 DB 에서 일으킨다.
    """
    event_no = make_event()
    existing_no = make_report(event_no, agency_no=1, status="SENDING")
    monkeypatch.setattr("services.report_service._find_active_report", lambda e: None)
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200))

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    assert result is not None
    assert result["report_no"] == existing_no
    assert len(get_report_rows(event_no)) == 1
    assert calls == []  # INSERT 가 막혔으므로 전송 자체가 없다


# ---------- 알림 응답(READ) 연동 — D4: 사용자가 화재 확인 시 즉시 신고 ----------

def test_read_on_sent_alert_triggers_report(client, admin_headers, monkeypatch):
    """SENT 알림에 READ 응답 → USER_CONFIRMED 사유로 신고가 만들어진다."""
    patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-READ-01"}))
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1, status="SENT")

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    json={"action": "READ"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.get_json()["alert_status"] == "READ"

    rows = get_report_rows(event_no)
    assert len(rows) == 1
    assert rows[0]["report_trigger_reason"] == "USER_CONFIRMED"
    assert rows[0]["report_status"] == "ACCEPTED"


def test_read_on_one_of_paired_alerts_reports_once(client, admin_headers, monkeypatch):
    """PUSH/SMS 두 알림 중 하나만 READ 해도 신고는 1건 (형제 종료 + 멱등 가드)."""
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-PAIR"}))
    event_no = make_event()
    push_no, _ = make_alert_pair(event_no)

    r = client.post(f"/api/alerts/{push_no}/respond",
                    json={"action": "READ"}, headers=admin_headers)
    assert r.status_code == 200

    rows = get_report_rows(event_no)
    assert len(rows) == 1
    assert rows[0]["report_trigger_reason"] == "USER_CONFIRMED"
    assert len(calls) == 1


def test_read_on_no_response_alert_does_not_report(client, admin_headers, monkeypatch):
    """NO_RESPONSE 알림에 대한 늦은 READ 는 신고를 만들지 않는다 (에스컬레이션이 이미 처리)."""
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200))
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1, status="NO_RESPONSE")

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    json={"action": "READ"}, headers=admin_headers)
    assert r.status_code == 200

    assert get_report_rows() == []
    assert calls == []


def test_cancel_does_not_report(client, admin_headers, monkeypatch):
    """CANCEL(오탐 취소)은 신고를 만들지 않는다."""
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200))
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1, status="SENT")

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    json={"action": "CANCEL"}, headers=admin_headers)
    assert r.status_code == 200

    assert get_report_rows() == []
    assert calls == []


def test_report_failure_does_not_break_respond_api(client, admin_headers, monkeypatch):
    """신고 로직이 죽어도 알림 응답 API 는 200 이어야 한다 (try/except 로 삼킨다)."""
    def boom(event_no, trigger_reason):
        raise RuntimeError("신고 실패 시뮬레이션")

    monkeypatch.setattr("services.report_service.start_report", boom)
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1, status="SENT")

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    json={"action": "READ"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.get_json()["alert_status"] == "READ"  # 알림 갱신 자체는 성공
