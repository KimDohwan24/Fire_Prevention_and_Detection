"""관리자 알림 API 테스트 — 명세서 6번 섹션.

GET  /api/alerts                     내 알림 목록 (로그인 사용자 본인 것만)
POST /api/alerts/<alert_no>/respond  알림 응답 (READ 화재확인 / CANCEL 오탐취소)
"""
from conftest import make_alert, make_event

import db


# ---------- GET /api/alerts ----------

def test_list_alerts_requires_token(client):
    """토큰 없이 호출하면 401."""
    r = client.get("/api/alerts")
    assert r.status_code == 401
    assert r.get_json()["code"] == "UNAUTHORIZED"


def test_list_alerts_returns_only_my_alerts_with_joined_fields(client, admin_headers):
    """같은 이벤트에 두 사용자 알림이 있어도 내(user_no=1) 것만 보인다.

    항목에는 JOIN 으로 내려주는 event_class, cctv_name 이 포함되어야 한다.
    """
    event_no = make_event()
    my_alert = make_alert(event_no, user_no=1)
    make_alert(event_no, user_no=2)  # 다른 사용자의 알림 — 목록에 나오면 안 됨

    r = client.get("/api/alerts", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["total_count"] == 1
    (item,) = body["items"]
    assert item["alert_no"] == my_alert
    assert item["event_no"] == event_no
    # JOIN 필드 (fire_event, cctv)
    assert item["event_class"] == "FLAME"
    assert item["cctv_name"] == "정문 카메라"
    # 기본 필드도 함께 확인
    assert item["alert_status"] == "SENT"
    assert item["alert_channel"] == "PUSH"
    assert item["alert_responded_at"] is None


def test_list_alerts_filter_by_alert_status(client, admin_headers):
    """?alert_status=SENT 필터가 동작한다."""
    event_no = make_event()
    sent_no = make_alert(event_no, status="SENT")
    make_alert(event_no, status="READ", responded=True)

    r = client.get("/api/alerts?alert_status=SENT", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["total_count"] == 1
    assert body["items"][0]["alert_no"] == sent_no
    assert body["items"][0]["alert_status"] == "SENT"


def test_list_alerts_paged_shape(client, admin_headers):
    """페이징 공통 형식: items/page/size/total_count/total_pages (page 는 1부터)."""
    event_no = make_event()
    for _ in range(3):
        make_alert(event_no)

    r = client.get("/api/alerts?page=1&size=2", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert set(body.keys()) == {"items", "page", "size", "total_count", "total_pages"}
    assert body["page"] == 1
    assert body["size"] == 2
    assert body["total_count"] == 3
    assert body["total_pages"] == 2
    assert len(body["items"]) == 2


# ---------- POST /api/alerts/<alert_no>/respond ----------

def test_respond_read_success(client, admin_headers):
    """READ 응답: 200, alert_status=READ, alert_responded_at 이 채워진다."""
    alert_no = make_alert(make_event())

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    headers=admin_headers, json={"action": "READ"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["alert_no"] == alert_no
    assert body["alert_status"] == "READ"
    assert body["alert_responded_at"] is not None


def test_respond_cancel_before_deadline(client, admin_headers):
    """유예 마감 전 CANCEL: 200, alert_status=CANCELED."""
    alert_no = make_alert(make_event(), deadline_offset_sec=180)

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    headers=admin_headers, json={"action": "CANCEL"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["alert_status"] == "CANCELED"
    assert body["alert_responded_at"] is not None


def test_respond_cancel_after_deadline_conflict(client, admin_headers):
    """유예 마감이 지난 뒤 CANCEL 은 409 DEADLINE_PASSED."""
    alert_no = make_alert(make_event(), deadline_offset_sec=-10)

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    headers=admin_headers, json={"action": "CANCEL"})
    assert r.status_code == 409
    assert r.get_json()["code"] == "DEADLINE_PASSED"


def test_respond_read_after_deadline_still_succeeds(client, admin_headers):
    """마감 이후에도 READ 는 성공한다 (구현상 READ 에는 마감 검사가 없음).

    ※ 명세 확인 필요: DEADLINE_PASSED 는 'CANCEL 시도'에만 명시되어 있어
    현재 구현(READ 는 마감 무관 허용)을 기준으로 검증한다.
    """
    alert_no = make_alert(make_event(), deadline_offset_sec=-10)

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    headers=admin_headers, json={"action": "READ"})
    assert r.status_code == 200
    assert r.get_json()["alert_status"] == "READ"


# ---------- 늦은 READ 와 NO_RESPONSE 상태 보존 ----------
# 규칙: 에스컬레이션이 이미 NO_RESPONSE 로 바꾼 알림에 늦게 READ 하면
# 상태는 NO_RESPONSE 그대로 두고 alert_responded_at 만 기록한다.
# (119 신고가 이미 나간 이력을 늦은 확인이 지워서는 안 된다)

def test_respond_read_on_no_response_preserves_status(client, admin_headers):
    """NO_RESPONSE 알림에 늦은 READ: 200, 상태는 NO_RESPONSE 유지 + responded_at 만 기록."""
    alert_no = make_alert(make_event(), status="NO_RESPONSE", deadline_offset_sec=-10)

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    headers=admin_headers, json={"action": "READ"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["alert_no"] == alert_no
    assert body["alert_status"] == "NO_RESPONSE"  # READ 로 덮어쓰면 안 됨
    assert body["alert_responded_at"] is not None

    # DB 에서도 상태 보존 + 응답 시각 기록을 재확인
    row = db.query_one(
        "SELECT alert_status, alert_responded_at FROM alert WHERE alert_no = %s",
        (alert_no,),
    )
    assert row["alert_status"] == "NO_RESPONSE"
    assert row["alert_responded_at"] is not None


def test_respond_second_read_on_acknowledged_no_response_conflict(client, admin_headers):
    """늦은 READ 로 이미 확인한 NO_RESPONSE 알림에 또 READ 하면 409 ALREADY_RESPONDED."""
    alert_no = make_alert(make_event(), status="NO_RESPONSE", deadline_offset_sec=-10)

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    headers=admin_headers, json={"action": "READ"})
    assert r.status_code == 200

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    headers=admin_headers, json={"action": "READ"})
    assert r.status_code == 409
    assert r.get_json()["code"] == "ALREADY_RESPONDED"


def test_respond_read_on_sent_still_sets_read(client, admin_headers):
    """회귀: SENT 알림에 READ 하면 여전히 alert_status=READ."""
    alert_no = make_alert(make_event(), status="SENT")

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    headers=admin_headers, json={"action": "READ"})
    assert r.status_code == 200
    assert r.get_json()["alert_status"] == "READ"


def test_respond_already_responded_conflict(client, admin_headers):
    """이미 응답한 알림에 다시 응답하면 409 ALREADY_RESPONDED."""
    alert_no = make_alert(make_event(), status="READ", responded=True)

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    headers=admin_headers, json={"action": "READ"})
    assert r.status_code == 409
    assert r.get_json()["code"] == "ALREADY_RESPONDED"


def test_respond_someone_elses_alert_forbidden(client, admin_headers):
    """다른 사용자(user_no=2)의 알림에 응답하면 403 NOT_YOUR_ALERT."""
    alert_no = make_alert(make_event(), user_no=2)

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    headers=admin_headers, json={"action": "READ"})
    assert r.status_code == 403
    assert r.get_json()["code"] == "NOT_YOUR_ALERT"


def test_respond_invalid_or_missing_action(client, admin_headers):
    """action 이 READ/CANCEL 이 아니거나 없으면 400."""
    alert_no = make_alert(make_event())

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    headers=admin_headers, json={"action": "FOO"})
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    headers=admin_headers, json={})
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


def test_respond_unknown_alert_not_found(client, admin_headers):
    """존재하지 않는 알림 번호는 404 ALERT_NOT_FOUND.

    (action 검증이 먼저 수행되므로 반드시 유효한 body 를 보낸다)
    """
    r = client.post("/api/alerts/99999/respond",
                    headers=admin_headers, json={"action": "READ"})
    assert r.status_code == 404
    assert r.get_json()["code"] == "ALERT_NOT_FOUND"
