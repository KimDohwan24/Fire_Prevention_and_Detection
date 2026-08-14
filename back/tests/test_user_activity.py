"""사용자 활동이력 (접속 / 로그아웃).

남기는 것은 두 가지뿐이다 — 들어왔다(LOGIN), 나갔다(LOGOUT).
IP·User-Agent 는 의도적으로 수집하지 않는다.

로그인은 이미 있던 엔드포인트에 기록이 붙는 것이고, 로그아웃은 엔드포인트 자체가
새로 생긴다. JWT 가 무상태라 프론트가 토큰만 지우면 서버는 나간 사실을 알 수 없다.
"""
import db
from conftest import PW


def _activities(user_no):
    return db.query(
        """
        SELECT activity_no, user_no, activity_type, activity_at
        FROM user_activity WHERE user_no = %s ORDER BY activity_no
        """,
        (user_no,),
    )


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

def test_activities_returns_newest_first(client, admin_headers):
    client.post("/api/auth/login", json={"user_id": "admin01", "user_pw": PW})
    client.post("/api/auth/logout", headers=admin_headers)

    res = client.get("/api/users/1/activities", headers=admin_headers)
    assert res.status_code == 200

    items = res.get_json()["items"]
    assert [i["activity_type"] for i in items] == ["LOGOUT", "LOGIN"]


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
