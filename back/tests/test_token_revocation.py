"""토큰 폐기 — 로그아웃과 계정 정지가 살아있는 토큰을 죽인다.

JWT 는 무상태라 이미 발급한 토큰을 회수할 수 없다. 그래서 사용자마다
"이 시각 이전 발급분은 안 받는다"는 기준선(users.user_token_valid_from)을 두고
매 요청 대조한다 (auth._assert_not_revoked).

**사용자 단위라서 그 사람의 다른 기기도 함께 끊긴다.** 토큰 하나만 죽이려면 jti 별
폐기 목록이 필요한데, 매 요청 DB 조회가 드는 건 똑같으면서 표가 하나 더 늘고
만료행 청소까지 따라온다. 관제 계정 규모에서는 기준선 하나가 낫다고 봤다.

⚠️ **해상도가 1초다.** 토큰의 iat 는 정수 초이고 기준선은 마이크로초까지 있어서,
   같은 초 안에서는 "로그아웃 직전 발급"과 "직후 발급"을 구분할 수 없다. 둘 중
   하나를 골라야 하는데 — 같은 초 발급분을 죽이면 로그아웃 직후 재로그인한 새
   토큰까지 죽어서 사용자가 갇힌다. 그래서 **살리는 쪽**을 골랐다.
   대가는 로그인과 로그아웃이 같은 초에 일어난 경우 옛 토큰이 살아남는 것인데,
   사람이 1초 안에 들어왔다 나가는 일은 없고 다음 로그아웃에서 어차피 죽는다.

   그래서 아래 테스트들은 시간을 흘려보내는 대신 **발급 시각을 명시한 토큰**을
   만들어 경계를 정확히 지정한다. 실제 시계로 도는 왕복은 맨 아래 한 건에서 확인한다.
"""
import time
from datetime import datetime, timedelta, timezone

import jwt

import config
import db
from conftest import PW
from services import account_recovery


def _login(client, user_id="admin01"):
    res = client.post("/api/auth/login", json={"user_id": user_id, "user_pw": PW})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.get_json()['access_token']}"}


def _aged_token(user_no, user_id, role="ADMIN", seconds_ago=5):
    """seconds_ago 초 전에 발급된 것처럼 보이는 토큰 헤더.

    issue_token 을 그대로 쓰면 iat 가 '지금'이라 같은 초 안에 세워진 기준선을
    넘어서지 못한다. 폐기가 걸리는지 보려면 발급 시각이 확실히 이전이어야 한다.
    """
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "user_no": user_no, "user_id": user_id, "user_role": role,
            "user_status": "ACTIVE",
            "iat": now - timedelta(seconds=seconds_ago),
            "exp": now + timedelta(hours=config.JWT_EXPIRES_HOURS),
        },
        config.JWT_SECRET, algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def _cutoff(user_no):
    return db.query_one(
        "SELECT user_token_valid_from AS c FROM users WHERE user_no = %s", (user_no,)
    )["c"]


# ---------- 로그아웃 ----------

def test_logout_sets_the_cutoff(client):
    headers = _login(client)
    assert _cutoff(1) is None

    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert _cutoff(1) is not None


def test_token_issued_before_logout_is_rejected(client):
    headers = _aged_token(1, "admin01")
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    client.post("/api/auth/logout", headers=headers)

    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 401
    assert res.get_json()["code"] == "TOKEN_REVOKED"


def test_logout_still_records_activity(client):
    """폐기와 기록은 별개다 — 토큰은 죽어도 '언제 나갔나'는 남아야 한다."""
    headers = _login(client)
    client.post("/api/auth/logout", headers=headers)

    rows = db.query(
        "SELECT activity_type FROM user_activity WHERE user_no = 1 ORDER BY activity_no"
    )
    assert [r["activity_type"] for r in rows] == ["LOGIN", "LOGOUT"]


def test_relogin_right_after_logout_works(client):
    """로그아웃 직후 재로그인이 **즉시** 되어야 한다.

    기준선을 초 단위로 자르지 않으면 방금 받은 새 토큰이 곧바로 거부된다
    (새 토큰 iat=100 < 기준선 100.7). 이 테스트가 그 회귀를 잡는다.
    """
    headers = _login(client)
    client.post("/api/auth/logout", headers=headers)

    fresh = _login(client)
    assert client.get("/api/auth/me", headers=fresh).status_code == 200


def test_logout_kills_every_device_of_that_user(client):
    """사용자 단위 폐기 — 한 기기에서 나가면 나머지도 끊긴다."""
    phone = _aged_token(1, "admin01")
    desktop = _aged_token(1, "admin01", seconds_ago=3)

    client.post("/api/auth/logout", headers=phone)

    assert client.get("/api/auth/me", headers=phone).status_code == 401
    assert client.get("/api/auth/me", headers=desktop).status_code == 401


def test_logout_does_not_affect_other_users(client):
    admin = _aged_token(1, "admin01")
    viewer = _aged_token(2, "viewer01", role="VIEWER")

    client.post("/api/auth/logout", headers=admin)

    assert client.get("/api/auth/me", headers=admin).status_code == 401
    assert client.get("/api/auth/me", headers=viewer).status_code == 200


# ---------- 계정 정지 · 탈퇴 ----------

def test_suspending_a_user_kills_their_token(client, admin_headers):
    """관리자가 정지시키면 즉시 효력을 가져야 한다.

    이게 없으면 정지된 사람이 토큰 만료(기본 12시간)까지 계속 쓴다.
    """
    viewer = _aged_token(2, "viewer01", role="VIEWER")
    assert client.get("/api/auth/me", headers=viewer).status_code == 200

    res = client.put("/api/users/2", headers=admin_headers,
                     json={"user_status": "SUSPENDED"})
    assert res.status_code == 200

    res = client.get("/api/auth/me", headers=viewer)
    assert res.status_code == 401
    assert res.get_json()["code"] == "TOKEN_REVOKED"


def test_withdrawing_a_user_kills_their_token(client, admin_headers):
    viewer = _aged_token(2, "viewer01", role="VIEWER")

    client.put("/api/users/2", headers=admin_headers,
               json={"user_status": "WITHDRAWN"})

    assert client.get("/api/auth/me", headers=viewer).status_code == 401


def test_suspending_one_user_leaves_others_alone(client, admin_headers):
    viewer = _aged_token(2, "viewer01", role="VIEWER")

    client.put("/api/users/2", headers=admin_headers,
               json={"user_status": "SUSPENDED"})

    assert client.get("/api/users", headers=admin_headers).status_code == 200
    assert client.get("/api/auth/me", headers=viewer).status_code == 401


def test_plain_profile_update_does_not_revoke(client):
    """상태를 안 건드리는 수정은 폐기 사유가 아니다."""
    viewer = _aged_token(2, "viewer01", role="VIEWER")

    res = client.put("/api/users/2", headers=viewer, json={"user_name": "바뀐이름"})
    assert res.status_code == 200
    assert client.get("/api/auth/me", headers=viewer).status_code == 200


# ---------- 비밀번호 변경 · 재설정 ----------

def test_password_change_revokes_existing_tokens(client, admin_headers):
    """비밀번호를 바꾸면 기존 토큰을 죽인다 — 도난당한 기기까지 회수하기 위해서.

    예전에는 '살려둔다'가 명시적 방침이었지만 2026-08-25 에 뒤집혔다. 관리자가
    유출 의심 계정의 비밀번호를 강제로 바꿨는데 옛 세션이 살아 있으면 회수 의미가 없다.
    """
    viewer = _aged_token(2, "viewer01", role="VIEWER")

    res = client.put("/api/users/2", headers=admin_headers,
                     json={"user_pw": "Reset#2026"})
    assert res.status_code == 200

    res = client.get("/api/auth/me", headers=viewer)
    assert res.status_code == 401
    assert res.get_json()["code"] == "TOKEN_REVOKED"


def test_own_password_change_kills_other_devices(client):
    """본인 비밀번호 변경(PUT /api/users/password)도 모든 세션을 끊는다.

    요청에 쓴 토큰조차 죽는 것이 표준 동작이다 — 프론트는 직후 401 TOKEN_REVOKED
    를 받아 로그인 화면으로 돌아간다. 폐기 해상도가 1초라 '지금' 발급된 토큰은
    같은 초 컷오프와 비교돼 살아남으므로, 위 테스트들과 같이 발급 시각을
    명시한 토큰으로 경계를 지정한다.
    """
    phone = _aged_token(2, "viewer01", role="VIEWER")
    desktop = _aged_token(2, "viewer01", role="VIEWER", seconds_ago=3)

    res = client.put("/api/users/password", headers=desktop,
                     json={"current_password": PW, "new_password": "Rotate#2026"})
    assert res.status_code == 200

    # 방금 요청에 쓴 기기(desktop)와 다른 기기(phone) 둘 다 끊긴다
    assert client.get("/api/auth/me", headers=desktop).status_code == 401
    res = client.get("/api/auth/me", headers=phone)
    assert res.status_code == 401
    assert res.get_json()["code"] == "TOKEN_REVOKED"


def test_password_reset_kills_existing_tokens(client):
    """계정찾기로 재설정하면 옛 토큰 전부 폐기 — 도난 시나리오의 핵심 경로."""
    victim = _aged_token(2, "viewer01", role="VIEWER")
    row = db.query_one("SELECT user_no, user_pw FROM users WHERE user_no = 2")
    code = account_recovery.issue_code(row["user_no"], row["user_pw"])

    res = client.post("/api/auth/password-reset/confirm",
                      json={"user_id": "viewer01", "code": code,
                            "user_pw": "Rotate#2026"})
    assert res.status_code == 200

    res = client.get("/api/auth/me", headers=victim)
    assert res.status_code == 401
    assert res.get_json()["code"] == "TOKEN_REVOKED"


# ---------- 경계 ----------

def test_admin_required_routes_also_check_revocation(client):
    """login_required 만 막고 admin_required 를 빼먹으면 관리자 API 가 뚫린다."""
    admin = _aged_token(1, "admin01")
    assert client.get("/api/users", headers=admin).status_code == 200

    client.post("/api/auth/logout", headers=admin)

    res = client.get("/api/users", headers=admin)
    assert res.status_code == 401
    assert res.get_json()["code"] == "TOKEN_REVOKED"


def test_token_without_iat_is_rejected_once_a_cutoff_exists(client):
    """이 기능 배포 이전에 나간 토큰에는 iat 가 없다.

    기준선이 세워진 뒤에는 그런 토큰을 믿을 근거가 없으므로 거부한다
    (iat 를 0, 즉 1970년으로 취급한다).
    """
    token = jwt.encode(
        {"user_no": 1, "user_id": "admin01", "user_role": "ADMIN",
         "user_status": "ACTIVE",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        config.JWT_SECRET, algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 기준선이 없으면 아직 통과한다
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    db.execute("UPDATE users SET user_token_valid_from = now() WHERE user_no = 1")

    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 401
    assert res.get_json()["code"] == "TOKEN_REVOKED"


def test_token_of_deleted_user_is_rejected(client):
    """사용자 행이 사라진 토큰 — 서명은 멀쩡해도 받아줄 수 없다."""
    headers = _aged_token(2, "viewer01", role="VIEWER")
    db.execute("DELETE FROM cctv WHERE user_no = 2")
    db.execute("DELETE FROM users WHERE user_no = 2")

    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 401
    assert res.get_json()["code"] == "INVALID_TOKEN"


def test_cutoff_survives_across_requests(client):
    """기준선은 한 번 서면 계속 유효하다 — 다음 요청에서 되살아나지 않는다.

    로그아웃 → 재로그인 → 그 사이 옛 토큰이 부활하지 않는지 본다. 로그인이
    기준선을 지우는 구현이었다면 여기서 옛 토큰이 다시 통과해 버린다.
    """
    old = _aged_token(1, "admin01")
    client.post("/api/auth/logout", headers=old)
    assert client.get("/api/auth/me", headers=old).status_code == 401

    _login(client)  # 재로그인

    assert client.get("/api/auth/me", headers=old).status_code == 401


# ---------- 실제 시계로 도는 왕복 1건 ----------

def test_end_to_end_with_real_clock(client):
    """조작한 토큰 없이, 실제 로그인→로그아웃 순서만으로 폐기가 걸리는지 본다.

    해상도가 1초라 로그인과 로그아웃 사이를 1초 이상 벌려야 한다. 위 테스트들이
    경계를 정확히 지정하는 대신 시간을 안 쓰는 것과 달리, 이 한 건은 느려도
    실제 흐름 그대로를 확인한다.
    """
    headers = _login(client)
    time.sleep(1.05)

    client.post("/api/auth/logout", headers=headers)

    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 401
    assert res.get_json()["code"] == "TOKEN_REVOKED"


# ---------- 권한 등급 변경 ----------

def test_demoting_an_admin_kills_their_token(client, admin_headers):
    """강등은 즉시 효력을 가져야 한다.

    권한 검사는 DB 가 아니라 **토큰에 박힌 user_role** 을 본다(auth.admin_required).
    폐기하지 않으면 강등당한 사람의 토큰 클레임은 여전히 ADMIN 이라 만료(기본 12시간)
    까지 관리자 API 를 그대로 쓴다.
    """
    db.execute("UPDATE users SET user_role = 'ADMIN' WHERE user_no = 2")
    victim = _aged_token(2, "viewer01", role="ADMIN")
    assert client.get("/api/users", headers=victim).status_code == 200

    res = client.put("/api/users/2", headers=admin_headers, json={"user_role": "VIEWER"})
    assert res.status_code == 200

    res = client.get("/api/users", headers=victim)
    assert res.status_code == 401
    assert res.get_json()["code"] == "TOKEN_REVOKED"


def test_promoting_a_user_also_kills_their_token(client, admin_headers):
    """승격도 폐기한다 — '등급이 달라졌다'만 보고 방향은 따지지 않는다.

    옛 토큰으로는 어차피 새 권한을 못 쓰므로(클레임이 VIEWER 그대로) 살려둘 값어치가
    없고, 방향을 따지는 조건은 나중에 등급이 늘면 곧바로 구멍이 된다.
    """
    viewer = _aged_token(2, "viewer01", role="VIEWER")
    assert client.get("/api/auth/me", headers=viewer).status_code == 200

    client.put("/api/users/2", headers=admin_headers, json={"user_role": "ADMIN"})

    assert client.get("/api/auth/me", headers=viewer).status_code == 401


def test_writing_the_same_role_does_not_revoke(client, admin_headers):
    """값이 그대로면 폐기 사유가 아니다 — 폼이 통째로 PUT 하는 경우를 죽이지 않는다."""
    viewer = _aged_token(2, "viewer01", role="VIEWER")

    res = client.put("/api/users/2", headers=admin_headers,
                     json={"user_role": "VIEWER", "user_name": "그대로"})
    assert res.status_code == 200

    assert client.get("/api/auth/me", headers=viewer).status_code == 200


def test_demoting_one_user_leaves_others_alone(client, admin_headers):
    viewer = _aged_token(2, "viewer01", role="VIEWER")

    client.put("/api/users/2", headers=admin_headers, json={"user_role": "ADMIN"})

    assert client.get("/api/users", headers=admin_headers).status_code == 200
    assert client.get("/api/auth/me", headers=viewer).status_code == 401
