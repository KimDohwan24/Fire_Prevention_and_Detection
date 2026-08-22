"""사용자 활동이력.

접속·로그아웃뿐 아니라 계정 변경과 관제 조치까지 남긴다. 종류만 남기면 화재 조치
이력이 전부 똑같이 보이므로 대상 번호(activity_target_no)와 한 줄 요약
(activity_detail)을 함께 기록한다.

**성공한 행위만 쌓인다.** 실패한 로그인이나 거절된 조치는 침입 시도·오조작 기록이지
활동 이력이 아니고, 한 표에 섞이면 '이 사람이 무엇을 했나'를 읽을 수 없게 된다.

조회 경로는 둘이다 — /api/me/activities 는 토큰 주인 것만(권한 검사가 필요 없다),
/api/users/{user_no}/activities 는 관리자가 남의 것을 볼 때.
"""
import db
from conftest import PW, make_alert, make_event


def _activities(user_no):
    return db.query(
        """
        SELECT activity_no, user_no, activity_type,
               activity_target_no, activity_detail, activity_at
        FROM user_activity WHERE user_no = %s ORDER BY activity_no
        """,
        (user_no,),
    )


def _login(client, user_id="admin01"):
    """API 로 로그인해 살아있는 토큰 헤더를 얻는다.

    로그아웃이 토큰을 폐기하므로, 로그아웃 뒤에도 요청을 보내야 하는 테스트는
    고정 픽스처(admin_headers) 대신 이걸 써서 새 토큰을 받아야 한다.
    """
    res = client.post("/api/auth/login", json={"user_id": user_id, "user_pw": PW})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.get_json()['access_token']}"}


# ---------- 기록: 로그인 ----------

def test_login_records_login_activity(client):
    res = client.post("/api/auth/login",
                      json={"user_id": "admin01", "user_pw": PW})
    assert res.status_code == 200

    rows = _activities(1)
    assert len(rows) == 1
    assert rows[0]["activity_type"] == "LOGIN"
    assert rows[0]["activity_at"] is not None


def test_failed_login_records_nothing(client):
    """비밀번호가 틀린 시도는 활동이력이 아니다.

    남겨야 한다면 그건 '접속 이력'이 아니라 침입 시도 로그이고, 성공한 접속과
    같은 표에 섞이면 '이 사람이 언제 들어왔나'를 읽을 수 없게 된다.
    """
    res = client.post("/api/auth/login",
                      json={"user_id": "admin01", "user_pw": "WrongPw#2026"})
    assert res.status_code == 401
    assert _activities(1) == []


def test_login_twice_records_two_rows(client):
    """1:N — 한 사용자에 여러 행이 쌓인다 (덮어쓰기가 아니다)."""
    for _ in range(2):
        client.post("/api/auth/login", json={"user_id": "admin01", "user_pw": PW})

    rows = _activities(1)
    assert [r["activity_type"] for r in rows] == ["LOGIN", "LOGIN"]


# ---------- 기록: 로그아웃 ----------

def test_logout_records_logout_activity(client, admin_headers):
    res = client.post("/api/auth/logout", headers=admin_headers)
    assert res.status_code == 200

    rows = _activities(1)
    assert len(rows) == 1
    assert rows[0]["activity_type"] == "LOGOUT"


def test_logout_requires_login(client):
    """토큰 없이 부르면 401 — 누가 나갔는지 모르면 기록할 수가 없다."""
    res = client.post("/api/auth/logout")
    assert res.status_code == 401
    assert _activities(1) == []


# ---------- 조회 ----------

def test_activities_returns_newest_first(client):
    """LOGIN → LOGOUT → LOGIN 순으로 만든 뒤 역순으로 나오는지 본다.

    로그아웃이 토큰을 폐기하므로 마지막 조회는 **새로 로그인해서 받은 토큰**으로
    해야 한다. 그 재로그인 자체가 세 번째 행이 된다.
    """
    headers = _login(client)
    client.post("/api/auth/logout", headers=headers)
    headers = _login(client)

    res = client.get("/api/users/1/activities", headers=headers)
    assert res.status_code == 200

    items = res.get_json()["items"]
    assert [i["activity_type"] for i in items] == ["LOGIN", "LOGOUT", "LOGIN"]


def test_activities_of_user_without_history_is_empty(client, admin_headers):
    res = client.get("/api/users/2/activities", headers=admin_headers)
    assert res.status_code == 200
    assert res.get_json()["items"] == []


def test_activities_404_for_unknown_user(client, admin_headers):
    res = client.get("/api/users/9999/activities", headers=admin_headers)
    assert res.status_code == 404
    assert res.get_json()["code"] == "USER_NOT_FOUND"


def test_viewer_cannot_read_other_users_activities(client, viewer_headers):
    """접속 이력은 감사 자료다 — 남의 것을 아무나 보면 안 된다."""
    res = client.get("/api/users/1/activities", headers=viewer_headers)
    assert res.status_code == 403


def test_viewer_can_read_own_activities(client, viewer_headers):
    client.post("/api/auth/login", json={"user_id": "viewer01", "user_pw": PW})

    res = client.get("/api/users/2/activities", headers=viewer_headers)
    assert res.status_code == 200
    assert [i["activity_type"] for i in res.get_json()["items"]] == ["LOGIN"]


# ---------- 조회: /api/me/activities ----------

def test_me_activities_returns_own_history(client, viewer_headers):
    client.post("/api/auth/login", json={"user_id": "viewer01", "user_pw": PW})

    res = client.get("/api/me/activities", headers=viewer_headers)
    assert res.status_code == 200
    body = res.get_json()
    assert [i["activity_type"] for i in body["items"]] == ["LOGIN"]
    assert all(i["user_no"] == 2 for i in body["items"])


def test_me_activities_requires_token(client):
    res = client.get("/api/me/activities")
    assert res.status_code == 401


def test_me_activities_never_shows_other_users(client, admin_headers, viewer_headers):
    """ADMIN 이라도 /api/me 로는 본인 것만 나온다.

    /api/users/{user_no}/activities 는 ADMIN 에게 남의 이력을 열어주지만,
    이 경로는 user_no 를 받지 않으므로 열어줄 대상 자체가 없다.
    """
    client.post("/api/auth/login", json={"user_id": "viewer01", "user_pw": PW})

    res = client.get("/api/me/activities", headers=admin_headers)
    assert res.status_code == 200
    assert res.get_json()["items"] == []          # 관리자는 아직 활동이 없다
    assert _activities(2) != []                   # 조회자에게는 있는데도


def test_me_activities_has_no_404_branch(client, viewer_headers):
    """토큰이 있으면 그 사용자는 존재한다 — 404 가 나올 여지가 없다."""
    res = client.get("/api/me/activities", headers=viewer_headers)
    assert res.status_code == 200
    assert res.get_json()["items"] == []


def test_me_activities_paginates(client, viewer_headers):
    for _ in range(3):
        client.post("/api/auth/login", json={"user_id": "viewer01", "user_pw": PW})

    res = client.get("/api/me/activities?page=1&size=2", headers=viewer_headers)
    body = res.get_json()
    assert len(body["items"]) == 2
    assert body["total_count"] == 3
    assert body["total_pages"] == 2


# ---------- 기록: 계정 변경 ----------

def test_profile_update_records_activity(client, viewer_headers):
    res = client.put("/api/users/2", headers=viewer_headers,
                     json={"user_name": "바뀐이름"})
    assert res.status_code == 200

    rows = _activities(2)
    assert len(rows) == 1
    assert rows[0]["activity_type"] == "PROFILE_UPDATED"
    assert rows[0]["activity_target_no"] == 2
    assert rows[0]["activity_detail"] == "user_name"


def test_admin_password_change_records_on_the_admin_with_target(client, admin_headers):
    """행위자와 대상이 다른 경우 — 관리자가 남의 비밀번호를 바꿨다.

    이력은 **행위자**에게 쌓이고 target 이 당한 쪽을 가리켜야 한다. 반대로
    쌓으면 조회자의 이력에 자기가 하지 않은 일이 나타난다.
    """
    res = client.put("/api/users/2", headers=admin_headers,
                     json={"user_pw": "Reset#2026"})
    assert res.status_code == 200

    types = [r["activity_type"] for r in _activities(1)]
    assert "PASSWORD_CHANGED" in types
    assert _activities(2) == []                   # 당한 쪽에는 안 쌓인다

    row = next(r for r in _activities(1) if r["activity_type"] == "PASSWORD_CHANGED")
    assert row["activity_target_no"] == 2


def test_failed_profile_update_records_nothing(client, viewer_headers):
    """403 으로 막힌 수정은 이력이 아니다."""
    res = client.put("/api/users/1", headers=viewer_headers, json={"user_name": "탈취"})
    assert res.status_code == 403
    assert _activities(2) == []


def test_password_reset_confirm_records_activity(client):
    from services import account_recovery

    pw_hash = db.query_one("SELECT user_pw FROM users WHERE user_no = 1")["user_pw"]
    code = account_recovery.issue_code(1, pw_hash)

    res = client.post("/api/auth/password-reset/confirm",
                      json={"user_id": "admin01", "code": code,
                            "user_pw": "Renew#2026"})
    assert res.status_code == 200

    rows = _activities(1)
    assert [r["activity_type"] for r in rows] == ["PASSWORD_CHANGED"]
    assert rows[0]["activity_detail"] == "비밀번호 재설정"


# ---------- 기록: 관제 조치 ----------

def test_alert_read_records_fire_confirmed(client, admin_headers):
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1)

    res = client.post(f"/api/alerts/{alert_no}/respond",
                      headers=admin_headers, json={"action": "READ"})
    assert res.status_code == 200

    rows = _activities(1)
    assert len(rows) == 1
    assert rows[0]["activity_type"] == "FIRE_CONFIRMED"
    assert rows[0]["activity_target_no"] == event_no
    assert rows[0]["activity_detail"] == "정문 카메라 화재 확인"


def test_alert_cancel_records_fire_dismissed(client, admin_headers):
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1)

    res = client.post(f"/api/alerts/{alert_no}/respond",
                      headers=admin_headers, json={"action": "CANCEL"})
    assert res.status_code == 200

    rows = _activities(1)
    assert len(rows) == 1
    assert rows[0]["activity_type"] == "FIRE_DISMISSED"
    assert rows[0]["activity_target_no"] == event_no
    assert rows[0]["activity_detail"] == "정문 카메라 오탐 취소"


def test_rejected_alert_response_records_nothing(client, viewer_headers):
    """남의 알림에 응답하려다 403 을 받은 것은 조치가 아니다."""
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1)      # 관리자 소유

    res = client.post(f"/api/alerts/{alert_no}/respond",
                      headers=viewer_headers, json={"action": "READ"})
    assert res.status_code == 403
    assert _activities(2) == []
    assert _activities(1) == []
