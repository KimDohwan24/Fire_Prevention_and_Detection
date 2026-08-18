"""인증 API — 명세서 2번 섹션 (POST /api/auth/login, GET /api/auth/me)."""
import db
from conftest import PW, PW_HASH


def _login(client, user_id, user_pw):
    return client.post("/api/auth/login", json={"user_id": user_id, "user_pw": user_pw})


# ---------- POST /api/auth/login ----------

def test_login_success(client):
    r = _login(client, "admin01", PW)
    assert r.status_code == 200
    body = r.get_json()

    # 토큰: 비어 있지 않은 문자열
    assert isinstance(body["access_token"], str) and body["access_token"]

    # user 객체는 명세된 4개 필드만 내려준다
    assert set(body["user"].keys()) == {"user_no", "user_id", "user_name", "user_role"}
    assert body["user"]["user_no"] == 1
    assert body["user"]["user_id"] == "admin01"
    assert body["user"]["user_role"] == "ADMIN"

    # 비밀번호 해시는 응답 어디에도 노출되면 안 된다
    assert "user_pw" not in r.get_data(as_text=True)


def test_login_wrong_password(client):
    r = _login(client, "admin01", "wrong-password")
    assert r.status_code == 401
    assert r.get_json()["code"] == "INVALID_CREDENTIALS"


def test_login_unknown_user_id(client):
    r = _login(client, "no-such-user", PW)
    assert r.status_code == 401
    assert r.get_json()["code"] == "INVALID_CREDENTIALS"


def test_login_suspended_account(client):
    r = _login(client, "susp01", PW)
    assert r.status_code == 403
    assert r.get_json()["code"] == "ACCOUNT_SUSPENDED"


def test_login_withdrawn_account(client):
    r = _login(client, "gone01", PW)
    assert r.status_code == 403
    assert r.get_json()["code"] == "ACCOUNT_WITHDRAWN"


def test_login_missing_fields(client):
    # 빈 본문
    r = client.post("/api/auth/login", json={})
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"

    # user_id 만 있는 경우
    r = client.post("/api/auth/login", json={"user_id": "admin01"})
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


def test_issued_token_actually_works(client):
    # 로그인으로 받은 토큰이 실제로 인증에 쓰인다 (세션 복원 시나리오)
    token = _login(client, "admin01", PW).get_json()["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.get_json()["user_id"] == "admin01"


# ---------- GET /api/auth/me ----------

def test_me_returns_profile_fields(client, admin_headers):
    r = client.get("/api/auth/me", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert set(body.keys()) == {
        "user_no", "user_id", "user_name", "user_email",
        "user_phone", "user_role", "user_status",
    }
    assert body["user_no"] == 1
    assert body["user_status"] == "ACTIVE"
    assert "user_pw" not in r.get_data(as_text=True)


def test_me_without_token(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert r.get_json()["code"] == "UNAUTHORIZED"


def test_me_with_garbage_token(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer abc"})
    assert r.status_code == 401
    assert r.get_json()["code"] == "INVALID_TOKEN"


def test_login_allows_pending_account(client):
    """승격 승인 대기(PENDING)는 계정 잠금이 아니다 — 로그인은 그대로 된다.

    _assert_account_usable 이 막는 것은 정지·탈퇴뿐이라는 사실을 고정해 둔다.
    여기에 PENDING 이 끼면 승인 기다리는 동안 접속이 끊긴다.
    """
    db.execute(
        "INSERT INTO users (user_id, user_pw, user_name, user_role, user_status)"
        " VALUES ('wait01', %s, '대기자', 'VIEWER', 'PENDING')",
        (PW_HASH,),
    )
    r = _login(client, "wait01", PW)
    assert r.status_code == 200
    assert r.get_json()["user"]["user_role"] == "VIEWER"
