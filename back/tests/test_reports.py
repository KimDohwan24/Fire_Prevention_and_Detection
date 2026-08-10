"""119 신고 API 테스트 — 명세서 8번 섹션.

GET /api/reports   신고 이력 목록 (event_no 로 승계 이력 필터)
"""
from conftest import make_event, make_report

# 명세서 8번 응답 예시의 항목 필드 전체
REPORT_FIELDS = {
    "report_no", "event_no", "agency_no", "agency_name",
    "report_sequence", "report_external_id", "report_trigger_reason",
    "report_status", "report_address", "report_distance_km",
    "report_attempt_count", "reported_at", "report_dispatched_at",
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
    assert item["report_status"] == "DISPATCHED"
    assert item["report_trigger_reason"] == "NO_RESPONSE_TIMEOUT"
    # numeric 은 JSON 숫자로 직렬화된다
    assert isinstance(item["report_distance_km"], (int, float))
    assert abs(item["report_distance_km"] - 1.234) < 1e-6
    assert item["reported_at"] is not None
    assert item["report_dispatched_at"] is not None


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
    """?report_status= 필터: FAILED 만 / DISPATCHED 만 골라낸다."""
    event_no = make_event()
    failed_no = make_report(event_no, sequence=1, status="FAILED")
    dispatched_no = make_report(event_no, agency_no=2, sequence=2, status="DISPATCHED")

    r = client.get("/api/reports?report_status=FAILED", headers=admin_headers)
    body = r.get_json()
    assert body["total_count"] == 1
    assert body["items"][0]["report_no"] == failed_no

    r = client.get("/api/reports?report_status=DISPATCHED", headers=admin_headers)
    body = r.get_json()
    assert body["total_count"] == 1
    assert body["items"][0]["report_no"] == dispatched_no


def test_list_reports_escalation_history_for_event(client, admin_headers):
    """승계 이력: 같은 이벤트에 sequence 1(무응답)·2(재신고) 두 행.

    ?event_no= 로 둘 다 조회되고, 정렬은 최신(report_no 큰 것) 우선.
    """
    event_no = make_event()
    first = make_report(event_no, agency_no=1, sequence=1, status="NO_RESPONSE")
    second = make_report(event_no, agency_no=2, sequence=2, status="DISPATCHED")

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
    # 활성(SENDING/DISPATCHED) 신고는 이벤트당 1건만 허용된다 (UX_report_119_active).
    # 승계 이력답게 이전 순번은 NO_RESPONSE, 마지막만 DISPATCHED 로 만든다.
    for seq in range(1, 4):
        make_report(event_no, sequence=seq,
                    status="DISPATCHED" if seq == 3 else "NO_RESPONSE")

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
