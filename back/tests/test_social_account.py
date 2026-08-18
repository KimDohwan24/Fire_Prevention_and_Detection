"""비밀번호 없는 계정(소셜 로그인) 방어.

users.user_pw 의 NOT NULL 을 풀어야 소셜 계정을 넣을 수 있는데, 그러면 비밀번호가
있다고 가정하던 코드들이 NULL 을 만나 터진다. 여기서 그 지점들을 고정한다.

여기서 다루는 것은 **비밀번호를 가정하던 경로들이 NULL 을 만났을 때**다. 소셜 계정을
실제로 만들어 로그인하는 경로(POST /api/auth/oauth/<provider>)는
tests/test_oauth_login.py 에 있다 — 이 파일의 계정은 conftest.make_social_user 로
직접 심는다. 프로바이더를 거치지 않으므로 여기 테스트는 외부 스텁이 필요 없다.

PUT /api/users/password 의 소셜 가드도 채워졌다. OAuth 로그인이 붙으면서 소셜 계정이
토큰을 얻을 수 있게 되어 도달 가능한 경로가 됐기 때문이다 (그 회귀 테스트는
test_oauth_login.py::test_social_account_cannot_change_password — 진짜 소셜 토큰으로
불러야 의미가 있어서 저쪽에 뒀다).
"""
import psycopg2
import pytest

import db
from conftest import PW, make_social_user


# ---------- 로그인 ----------

def test_social_account_cannot_log_in(client):
    """어떤 비밀번호를 넣어도 통과할 수 없다 — 아예 없기 때문이다.

    균일하게 INVALID_CREDENTIALS 로 뭉개지 않고 따로 안내하는 이유는, 그러면
    소셜 사용자가 영문도 모르고 갇히기 때문이다. 대신 그 아이디가 존재한다는
    사실은 노출된다 — 닫힌 관제 시스템이라 감수한 트레이드오프다.
    """
    make_social_user(user_id="google_1001")

    res = client.post("/api/auth/login",
                      json={"user_id": "google_1001", "user_pw": PW})
    assert res.status_code == 400
    assert res.get_json()["code"] == "SOCIAL_ACCOUNT"


def test_social_login_attempt_records_no_activity(client):
    user_no = make_social_user(user_id="google_1001")
    client.post("/api/auth/login", json={"user_id": "google_1001", "user_pw": PW})

    rows = db.query("SELECT 1 FROM user_activity WHERE user_no = %s", (user_no,))
    assert rows == []


def test_local_login_still_works(client):
    """소셜 분기를 넣다가 일반 로그인을 막지 않았는지 확인한다."""
    make_social_user(user_id="google_1001")

    res = client.post("/api/auth/login", json={"user_id": "admin01", "user_pw": PW})
    assert res.status_code == 200


# ---------- 비밀번호 재설정 ----------

def test_password_reset_request_ignores_social_account(client):
    """인증코드는 현재 비밀번호 해시를 HMAC 입력으로 쓴다 — NULL 이면 성립하지 않는다.

    걸러진 계정은 '일치하는 계정 없음' 분기로 흘러가므로 응답은 그대로 200 이다
    (계정 존재 여부를 숨기는 이 엔드포인트의 방침).
    """
    make_social_user(user_id="google_1001", name="소셜사용자")

    res = client.post("/api/auth/password-reset/request",
                      json={"user_id": "google_1001", "user_name": "소셜사용자",
                            "user_email": "social@fg.kr"})
    assert res.status_code == 200


def test_password_reset_confirm_rejects_social_account(client):
    make_social_user(user_id="google_1001")

    res = client.post("/api/auth/password-reset/confirm",
                      json={"user_id": "google_1001", "code": "ABCDEFGHJK",
                            "user_pw": "Renew#2026"})
    assert res.status_code == 400
    assert res.get_json()["code"] == "INVALID_RESET_CODE"


# ---------- 관리자 수정 ----------

def test_admin_cannot_set_password_on_social_account(client, admin_headers):
    """비밀번호를 심어도 로그인은 SOCIAL_ACCOUNT 로 계속 막힌다 — 무의미한 값만 남는다."""
    user_no = make_social_user(user_id="google_1001")

    res = client.put(f"/api/users/{user_no}", headers=admin_headers,
                     json={"user_pw": "Planted#2026"})
    assert res.status_code == 400
    body = res.get_json()
    assert body["code"] == "SOCIAL_ACCOUNT"
    assert body["field"] == "user_pw"

    still_null = db.query_one(
        "SELECT user_pw FROM users WHERE user_no = %s", (user_no,)
    )["user_pw"]
    assert still_null is None


def test_admin_can_still_edit_social_account_profile(client, admin_headers):
    """비밀번호만 막는 것이지 계정 자체를 잠그는 게 아니다."""
    user_no = make_social_user(user_id="google_1001")

    res = client.put(f"/api/users/{user_no}", headers=admin_headers,
                     json={"user_name": "이름변경"})
    assert res.status_code == 200


# ---------- DB 제약 ----------

def test_local_account_without_password_is_rejected_by_db(client):
    """NOT NULL 을 푼 대가를 CK_USERS_LOCAL_PW 가 되받는다.

    일반 계정이 비밀번호 없이 들어오는 것은 여전히 막혀야 한다 — 안 그러면
    제약을 푼 순간 로그인 불가능한 유령 계정이 생길 수 있다.
    """
    with pytest.raises(psycopg2.errors.CheckViolation):
        db.execute(
            """
            INSERT INTO users (user_id, user_pw, user_name, user_role, user_status)
            VALUES ('ghost01', NULL, '유령', 'VIEWER', 'ACTIVE')
            """
        )


def test_same_social_account_cannot_be_registered_twice(client):
    make_social_user(user_id="google_1001", provider="GOOGLE", provider_id="1001")

    with pytest.raises(psycopg2.errors.UniqueViolation):
        make_social_user(user_id="google_1001_dup",
                         provider="GOOGLE", provider_id="1001")


def test_local_accounts_are_not_blocked_by_the_provider_index(client):
    """부분 인덱스라 provider_id 가 NULL 인 일반 계정은 여럿이어도 무방하다.

    부분 인덱스가 아니었다면 두 번째 일반 계정부터 (LOCAL, NULL) 중복으로 막힌다.
    시드에 이미 4명이 있으므로 이 테스트는 그 사실만 확인하면 된다.
    """
    cnt = db.query_one(
        "SELECT count(*) AS cnt FROM users WHERE user_provider = 'LOCAL'"
    )["cnt"]
    assert cnt == 4
