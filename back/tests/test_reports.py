"""119 신고 API 테스트 — 명세서 8번 섹션.

GET /api/reports                     신고 이력 목록 (event_no 로 승계 이력 필터)
GET /api/reports/<report_no>/logs    그 신고의 119 송수신 로그
"""
from conftest import make_event, make_report

import db

# 명세서 8번 응답 예시의 항목 필드 전체
REPORT_FIELDS = {
    "report_no", "event_no", "agency_no", "agency_name",
    "report_sequence", "report_external_id", "report_trigger_reason",
    "report_status", "report_address", "report_distance_km",
    "report_attempt_count", "reported_at", "report_accepted_at",
}


def test_list_reports_requires_token(client):
    """토큰 없이 호출하면 401."""
    r = client.get("/api/reports")
    assert r.status_code == 401
    assert r.get_json()["code"] == "UNAUTHORIZED"


def test_list_reports_empty(client, admin_headers):
    """신고가 없으면 빈 목록."""
    r = client.get("/api/reports", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["items"] == []
    assert body["total_count"] == 0
    assert body["total_pages"] == 0


def test_list_reports_item_has_all_spec_fields(client, admin_headers):
    """항목에 명세서의 모든 필드가 있고 agency_name JOIN, 거리는 숫자."""
    event_no = make_event()
    report_no = make_report(event_no, agency_no=1)

    r = client.get("/api/reports", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["total_count"] == 1
    (item,) = body["items"]
    assert set(item.keys()) == REPORT_FIELDS
    assert item["report_no"] == report_no
    assert item["event_no"] == event_no
    assert item["agency_no"] == 1
    assert item["agency_name"] == "종로소방서"  # JOIN 필드
    assert item["report_sequence"] == 1
    assert item["report_status"] == "ACCEPTED"
    assert item["report_trigger_reason"] == "NO_RESPONSE_TIMEOUT"
    # numeric 은 JSON 숫자로 직렬화된다
    assert isinstance(item["report_distance_km"], (int, float))
    assert abs(item["report_distance_km"] - 1.234) < 1e-6
    assert item["reported_at"] is not None
    assert item["report_accepted_at"] is not None


def test_list_reports_filter_by_event_no(client, admin_headers):
    """?event_no= 필터: 해당 이벤트의 신고만 나온다."""
    e1, e2 = make_event(), make_event()
    r1 = make_report(e1)
    make_report(e2)

    r = client.get(f"/api/reports?event_no={e1}", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["total_count"] == 1
    assert body["items"][0]["report_no"] == r1
    assert body["items"][0]["event_no"] == e1


def test_list_reports_invalid_event_no_returns_400(client, admin_headers):
    """?event_no= 에 숫자가 아닌 값이 오면 500 이 아니라 400 BAD_REQUEST."""
    r = client.get("/api/reports?event_no=abc", headers=admin_headers)
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


def test_list_reports_filter_by_status(client, admin_headers):
    """?report_status= 필터: FAILED 만 / ACCEPTED 만 골라낸다."""
    event_no = make_event()
    failed_no = make_report(event_no, sequence=1, status="FAILED")
    dispatched_no = make_report(event_no, agency_no=2, sequence=2, status="ACCEPTED")

    r = client.get("/api/reports?report_status=FAILED", headers=admin_headers)
    body = r.get_json()
    assert body["total_count"] == 1
    assert body["items"][0]["report_no"] == failed_no

    r = client.get("/api/reports?report_status=ACCEPTED", headers=admin_headers)
    body = r.get_json()
    assert body["total_count"] == 1
    assert body["items"][0]["report_no"] == dispatched_no


def test_list_reports_escalation_history_for_event(client, admin_headers):
    """승계 이력: 같은 이벤트에 sequence 1(무응답)·2(재신고) 두 행.

    ?event_no= 로 둘 다 조회되고, 정렬은 최신(report_no 큰 것) 우선.
    """
    event_no = make_event()
    first = make_report(event_no, agency_no=1, sequence=1, status="NO_RESPONSE")
    second = make_report(event_no, agency_no=2, sequence=2, status="ACCEPTED")

    r = client.get(f"/api/reports?event_no={event_no}", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["total_count"] == 2
    # 최신순 (report_no DESC): 승계된 2차 신고가 먼저
    assert [i["report_no"] for i in body["items"]] == [second, first]
    assert body["items"][0]["report_sequence"] == 2
    assert body["items"][0]["agency_name"] == "중부소방서"
    assert body["items"][1]["report_status"] == "NO_RESPONSE"


def test_list_reports_paged_shape(client, admin_headers):
    """페이징 공통 형식과 페이지 분할."""
    event_no = make_event()
    # 활성(SENDING/ACCEPTED) 신고는 이벤트당 1건만 허용된다 (UX_report_119_active).
    # 승계 이력답게 이전 순번은 NO_RESPONSE, 마지막만 ACCEPTED 로 만든다.
    for seq in range(1, 4):
        make_report(event_no, sequence=seq,
                    status="ACCEPTED" if seq == 3 else "NO_RESPONSE")

    r = client.get("/api/reports?page=1&size=2", headers=admin_headers)
    body = r.get_json()
    assert set(body.keys()) == {"items", "page", "size", "total_count", "total_pages"}
    assert body["page"] == 1
    assert body["size"] == 2
    assert body["total_count"] == 3
    assert body["total_pages"] == 2
    assert len(body["items"]) == 2

    r = client.get("/api/reports?page=2&size=2", headers=admin_headers)
    assert len(r.get_json()["items"]) == 1


# ---------- GET /api/reports/<report_no>/logs ----------

LOG_FIELDS = {
    "log_no", "report_no", "log_attempt", "log_endpoint", "log_request",
    "log_result", "log_http_status", "log_response", "log_error",
    "log_elapsed_ms", "log_sent_at",
}


def make_log(report_no, attempt=1, result="ACCEPTED", http_status=200,
             endpoint="http://localhost:6000/report", error=None):
    return db.execute_returning(
        """
        INSERT INTO report_log (report_no, log_attempt, log_endpoint, log_request,
                                log_result, log_http_status, log_response,
                                log_error, log_elapsed_ms, log_sent_at)
        VALUES (%s, %s, %s, '{"report_uid":"FG-1","event_no":1}'::jsonb,
                %s, %s, '{"external_id":"R-000001"}'::jsonb, %s, 42, now())
        RETURNING log_no
        """,
        (report_no, attempt, endpoint, result, http_status, error),
    )["log_no"]


def test_report_logs_require_token(client):
    """토큰 없이 호출하면 401."""
    r = client.get("/api/reports/1/logs")
    assert r.status_code == 401
    assert r.get_json()["code"] == "UNAUTHORIZED"


def test_report_logs_unknown_report_404(client, admin_headers):
    """없는 신고 번호면 404 REPORT_NOT_FOUND (빈 목록이 아니다)."""
    r = client.get("/api/reports/999/logs", headers=admin_headers)
    assert r.status_code == 404
    assert r.get_json()["code"] == "REPORT_NOT_FOUND"


def test_report_logs_empty_for_report_without_logs(client, admin_headers):
    """신고는 있는데 로그가 없으면 빈 목록 (404 아님)."""
    report_no = make_report(make_event())
    r = client.get(f"/api/reports/{report_no}/logs", headers=admin_headers)
    assert r.status_code == 200
    assert r.get_json()["items"] == []


def test_report_logs_returned_in_attempt_order(client, admin_headers):
    """시도 순서대로 나오고, 각 항목이 스펙의 모든 필드를 갖는다."""
    report_no = make_report(make_event())
    make_log(report_no, attempt=2, result="REJECTED", http_status=500)
    make_log(report_no, attempt=1, result="TIMEOUT", http_status=None,
             error="모의 타임아웃")
    make_log(report_no, attempt=3)

    r = client.get(f"/api/reports/{report_no}/logs", headers=admin_headers)
    assert r.status_code == 200
    items = r.get_json()["items"]

    assert [i["log_attempt"] for i in items] == [1, 2, 3]   # 넣은 순서가 아니라 시도 순서
    assert [i["log_result"] for i in items] == ["TIMEOUT", "REJECTED", "ACCEPTED"]
    assert set(items[0].keys()) == LOG_FIELDS
    # jsonb 는 파싱된 객체로 내려간다
    assert items[0]["log_request"]["report_uid"] == "FG-1"
    assert items[0]["log_http_status"] is None
    assert items[0]["log_error"] == "모의 타임아웃"
    assert items[2]["log_response"]["external_id"] == "R-000001"


def test_report_logs_only_that_report(client, admin_headers):
    """다른 신고의 로그는 섞이지 않는다."""
    event_no = make_event()
    mine = make_report(event_no, sequence=1, status="NO_RESPONSE")
    other = make_report(event_no, agency_no=2, sequence=2)
    make_log(mine, attempt=1)
    make_log(other, attempt=1)

    r = client.get(f"/api/reports/{mine}/logs", headers=admin_headers)
    items = r.get_json()["items"]
    assert len(items) == 1
    assert items[0]["report_no"] == mine
