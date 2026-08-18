"""소셜 로그인(OAuth) 엔드포인트.

GET  /api/auth/oauth/<provider>/authorize   프로바이더 동의화면 주소 + state
POST /api/auth/oauth/<provider>             code 교환 → 우리 JWT 발급

**실제 네트워크는 한 번도 타지 않는다.** oauth_provider 의 HTTP 진입점
(_post/_get)을 테스트마다 monkeypatch 로 갈아끼운다 — conftest 의
_no_real_report_http / _no_real_its_http 와 같은 방식이다. 다만 여기서는
전역 스텁을 두지 않았다. 프로바이더 응답 모양이 테스트마다 다르고,
스텁을 깜빡한 테스트는 키 미설정(503)이나 연결 오류로 곧바로 드러난다.
"""
import time

import pytest

import config
import db
from conftest import PW
from services import oauth_provider

# 각 프로바이더가 실제로 내려주는 userinfo 응답 모양 (키 이름이 전부 다르다)
GOOGLE_USERINFO = {
    "sub": "108127319", "email": "gu@fg.kr", "name": "구글사용자",
    "picture": "https://example/p.png", "email_verified": True,
}
KAKAO_USERINFO = {
    # id 가 정수로 온다 — provider_id 는 varchar 라 str 로 바꿔 넣어야 한다
    "id": 3312244556,
    "kakao_account": {"email": "ka@fg.kr", "profile": {"nickname": "카카오사용자"}},
}
NAVER_USERINFO = {
    # 네이버는 실패해도 HTTP 200 을 주고 본문 resultcode 로 알린다
    "resultcode": "00", "message": "success",
    "response": {"id": "naver-8821", "email": "na@fg.kr", "name": "네이버사용자"},
}

_EXPECTED = {
    "GOOGLE": (GOOGLE_USERINFO, "108127319", "gu@fg.kr", "구글사용자"),
    "KAKAO": (KAKAO_USERINFO, "3312244556", "ka@fg.kr", "카카오사용자"),
    "NAVER": (NAVER_USERINFO, "naver-8821", "na@fg.kr", "네이버사용자"),
}


@pytest.fixture(autouse=True)
def oauth_keys(monkeypatch):
    """세 프로바이더 모두 키가 설정된 상태로 둔다.

    실제 .env 에는 키가 없으므로(있어도 CI 마다 다르다) 매 테스트 고정값을 심는다.
    '키 미설정' 시나리오만 자기 monkeypatch 로 다시 비운다.
    """
    for provider in ("GOOGLE", "KAKAO", "NAVER"):
        monkeypatch.setattr(config, f"{provider}_CLIENT_ID", f"{provider.lower()}-cid")
        monkeypatch.setattr(config, f"{provider}_CLIENT_SECRET", f"{provider.lower()}-sec")
    monkeypatch.setattr(config, "OAUTH_REDIRECT_BASE", "http://localhost:5173")
    yield


def stub_http(monkeypatch, userinfo, token=None):
    """토큰 교환·userinfo 조회 두 번의 외부 호출을 스텁으로 갈아끼운다."""
    monkeypatch.setattr("services.oauth_provider._post",
                        lambda url, data: token if token is not None
                        else {"access_token": "provider-access-token"})
    monkeypatch.setattr("services.oauth_provider._get",
                        lambda url, headers: userinfo)


def login(client, provider="google", code="auth-code", state=None):
    """소셜 로그인 1회. state 를 안 주면 그 프로바이더의 유효한 값을 만들어 쓴다."""
    if state is None:
        state = oauth_provider.issue_state(provider.upper())
    return client.post(f"/api/auth/oauth/{provider}",
                       json={"code": code, "state": state})


# ---------- authorize: 동의화면 주소 발급 ----------

def test_authorize_returns_url_and_state(client):
    res = client.get("/api/auth/oauth/google/authorize")
    assert res.status_code == 200
    body = res.get_json()
    assert body["authorize_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert body["state"]
    # 프론트가 sessionStorage 에 넣은 뒤 그대로 돌려줄 값이므로 URL 에도 실려야 한다
    assert f"state={body['state']}" in body["authorize_url"]


def test_authorize_url_carries_server_side_redirect_uri(client):
    """redirect_uri 는 서버가 계산한다 — 프론트와 중복 정의하지 않는 것이 설계의 핵심이다."""
    res = client.get("/api/auth/oauth/kakao/authorize")
    url = res.get_json()["authorize_url"]
    assert url.startswith("https://kauth.kakao.com/oauth/authorize?")
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A5173%2Foauth%2Fcallback%2Fkakao" in url
    assert "client_id=kakao-cid" in url
    assert "response_type=code" in url


def test_authorize_asks_google_for_openid_scope(client):
    url = client.get("/api/auth/oauth/google/authorize").get_json()["authorize_url"]
    assert "scope=openid+email+profile" in url


def test_authorize_rejects_unsupported_provider(client):
    res = client.get("/api/auth/oauth/facebook/authorize")
    assert res.status_code == 400
    assert res.get_json()["code"] == "UNSUPPORTED_PROVIDER"


def test_authorize_reports_missing_keys(client, monkeypatch):
    """키 없이 배포된 상태에서 빈 client_id 가 박힌 URL 을 내주면 안 된다."""
    monkeypatch.setattr(config, "NAVER_CLIENT_ID", "")
    res = client.get("/api/auth/oauth/naver/authorize")
    assert res.status_code == 503
    assert res.get_json()["code"] == "OAUTH_NOT_CONFIGURED"


def test_authorize_needs_no_token(client):
    """비로그인 공개 엔드포인트다 — 로그인 화면에서 부르는 것이라 토큰이 있을 리 없다."""
    assert client.get("/api/auth/oauth/naver/authorize").status_code == 200


# ---------- 신규 계정 생성 ----------

def test_first_login_creates_account(client, monkeypatch):
    stub_http(monkeypatch, GOOGLE_USERINFO)

    res = login(client)
    assert res.status_code == 200

    row = db.query_one(
        """
        SELECT user_id, user_pw, user_name, user_email, user_role,
               user_status, user_provider, user_provider_id
        FROM users WHERE user_provider = 'GOOGLE'
        """
    )
    assert row["user_provider_id"] == "108127319"
    assert row["user_id"] == "google_108127319"
    assert row["user_pw"] is None          # 소셜 계정은 비밀번호를 갖지 않는다
    assert row["user_name"] == "구글사용자"
    assert row["user_email"] == "gu@fg.kr"
    assert row["user_role"] == "VIEWER"    # 관제 권한은 관리자가 따로 올려준다
    assert row["user_status"] == "ACTIVE"


def test_response_shape_matches_local_login(client, monkeypatch):
    """POST /api/auth/login 과 완전히 같은 모양이어야 프론트가 한 경로로 받는다."""
    stub_http(monkeypatch, GOOGLE_USERINFO)
    social = login(client).get_json()

    local = client.post("/api/auth/login",
                        json={"user_id": "admin01", "user_pw": PW}).get_json()

    assert social.keys() == local.keys()
    assert social["user"].keys() == local["user"].keys()
    assert social["user"]["user_id"] == "google_108127319"
    assert social["user"]["user_role"] == "VIEWER"


def test_issued_token_actually_works(client, monkeypatch):
    """모양만 같고 쓸 수 없는 토큰이면 의미가 없다 — 보호된 경로로 직접 확인한다."""
    stub_http(monkeypatch, GOOGLE_USERINFO)
    token = login(client).get_json()["access_token"]

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.get_json()["user_id"] == "google_108127319"


def test_login_records_one_activity_row(client, monkeypatch):
    stub_http(monkeypatch, GOOGLE_USERINFO)
    user_no = login(client).get_json()["user"]["user_no"]

    rows = db.query("SELECT activity_type FROM user_activity WHERE user_no = %s",
                    (user_no,))
    assert [r["activity_type"] for r in rows] == ["LOGIN"]


# ---------- 재로그인 ----------

def test_second_login_reuses_the_same_account(client, monkeypatch):
    """같은 프로바이더 계정으로 다시 들어오면 계정이 늘지 않는다."""
    stub_http(monkeypatch, GOOGLE_USERINFO)
    first = login(client).get_json()["user"]["user_no"]
    second = login(client).get_json()["user"]["user_no"]

    assert first == second
    cnt = db.query_one(
        "SELECT count(*) AS cnt FROM users WHERE user_provider = 'GOOGLE'"
    )["cnt"]
    assert cnt == 1


def test_second_login_records_another_activity_row(client, monkeypatch):
    stub_http(monkeypatch, GOOGLE_USERINFO)
    login(client)
    user_no = login(client).get_json()["user"]["user_no"]

    cnt = db.query_one(
        "SELECT count(*) AS cnt FROM user_activity WHERE user_no = %s", (user_no,)
    )["cnt"]
    assert cnt == 2


def test_existing_social_account_is_matched_by_provider_id(client, monkeypatch):
    """user_id 가 아니라 (provider, provider_id) 로 찾는다 — user_id 는 합성값일 뿐이다."""
    from conftest import make_social_user

    user_no = make_social_user(user_id="legacy_google_user", provider="GOOGLE",
                               provider_id="108127319", name="기존사용자")
    stub_http(monkeypatch, GOOGLE_USERINFO)

    body = login(client).get_json()
    assert body["user"]["user_no"] == user_no
    assert body["user"]["user_id"] == "legacy_google_user"


# ---------- 이메일이 같은 일반 계정과 자동 연결하지 않는다 ----------

def test_matching_local_email_does_not_link_accounts(client, monkeypatch):
    """프로바이더가 이메일을 검증했다는 보장이 없어 계정 탈취 경로가 된다.

    시드의 admin01 이 admin@fg.kr 을 쓰고 있는데 같은 이메일로 소셜 로그인이
    들어오면, 자동 연결하는 구현에서는 그 사람이 ADMIN 계정을 통째로 가져간다.
    """
    stub_http(monkeypatch, {**GOOGLE_USERINFO, "email": "admin@fg.kr"})

    body = login(client).get_json()
    assert body["user"]["user_no"] != 1
    assert body["user"]["user_role"] == "VIEWER"     # ADMIN 을 물려받지 않는다
    assert body["user"]["user_id"] == "google_108127319"

    # 원래 admin01 은 그대로 LOCAL 계정으로 남아 있어야 한다
    admin = db.query_one("SELECT user_provider, user_role FROM users WHERE user_no = 1")
    assert admin["user_provider"] == "LOCAL"
    assert admin["user_role"] == "ADMIN"


# ---------- 프로바이더별 응답 파싱 ----------

@pytest.mark.parametrize("provider", ["GOOGLE", "KAKAO", "NAVER"])
def test_each_provider_response_is_normalized(client, monkeypatch, provider):
    userinfo, provider_id, email, name = _EXPECTED[provider]
    stub_http(monkeypatch, userinfo)

    res = login(client, provider=provider.lower())
    assert res.status_code == 200

    row = db.query_one(
        """
        SELECT user_id, user_name, user_email, user_provider_id
        FROM users WHERE user_provider = %s
        """,
        (provider,),
    )
    assert row["user_provider_id"] == provider_id
    assert row["user_email"] == email
    assert row["user_name"] == name
    assert row["user_id"] == f"{provider.lower()}_{provider_id}"


def test_provider_path_is_case_insensitive(client, monkeypatch):
    """경로는 소문자로 받되 대문자로 와도 받아준다. DB 에는 항상 대문자로 저장한다."""
    stub_http(monkeypatch, KAKAO_USERINFO)
    assert login(client, provider="KAKAO").status_code == 200
    assert db.query_one(
        "SELECT count(*) AS cnt FROM users WHERE user_provider = 'KAKAO'"
    )["cnt"] == 1


def test_naver_failure_body_is_treated_as_error(client, monkeypatch):
    """네이버는 실패해도 HTTP 200 이다 — resultcode 를 안 보면 성공으로 착각한다."""
    stub_http(monkeypatch, {"resultcode": "024", "message": "Authentication failed"})

    res = login(client, provider="naver")
    assert res.status_code == 502
    assert res.get_json()["code"] == "OAUTH_PROVIDER_ERROR"
    assert db.query("SELECT 1 FROM users WHERE user_provider = 'NAVER'") == []


# ---------- 실패 경로 ----------

def test_unsupported_provider(client):
    res = client.post("/api/auth/oauth/facebook",
                      json={"code": "c", "state": "s"})
    assert res.status_code == 400
    assert res.get_json()["code"] == "UNSUPPORTED_PROVIDER"


def test_missing_keys_returns_service_unavailable(client, monkeypatch):
    """키 없이 배포된 상태에서 500 이 나면 원인을 못 찾는다."""
    monkeypatch.setattr(config, "GOOGLE_CLIENT_SECRET", "")
    res = login(client)
    assert res.status_code == 503
    assert res.get_json()["code"] == "OAUTH_NOT_CONFIGURED"


def test_missing_code_is_a_field_error(client):
    state = oauth_provider.issue_state("GOOGLE")
    res = client.post("/api/auth/oauth/google", json={"state": state})
    assert res.status_code == 400
    body = res.get_json()
    assert body["code"] == "BAD_REQUEST"
    assert body["field"] == "code"


def test_forged_state_is_rejected(client, monkeypatch):
    stub_http(monkeypatch, GOOGLE_USERINFO)
    res = login(client, state="deadbeef.0123456789abcdef")
    assert res.status_code == 400
    assert res.get_json()["code"] == "INVALID_OAUTH_STATE"


def test_expired_state_is_rejected(client, monkeypatch):
    stub_http(monkeypatch, GOOGLE_USERINFO)
    stale = oauth_provider.issue_state("GOOGLE", now=time.time() - 3600)

    res = login(client, state=stale)
    assert res.status_code == 400
    assert res.get_json()["code"] == "INVALID_OAUTH_STATE"


def test_state_of_another_provider_is_rejected(client, monkeypatch):
    """provider 를 HMAC 입력에 넣었기 때문에 다른 프로바이더의 state 는 통하지 않는다."""
    stub_http(monkeypatch, KAKAO_USERINFO)
    res = login(client, provider="kakao",
                state=oauth_provider.issue_state("GOOGLE"))
    assert res.status_code == 400
    assert res.get_json()["code"] == "INVALID_OAUTH_STATE"


def test_state_check_happens_before_any_external_call(client, monkeypatch):
    """위조된 state 로는 프로바이더를 두드리지도 않는다 (남의 서버 대신 맞아주지 않게)."""
    def boom(*args, **kwargs):
        raise AssertionError("state 검증 전에 외부 호출이 나갔다")

    monkeypatch.setattr("services.oauth_provider._post", boom)
    monkeypatch.setattr("services.oauth_provider._get", boom)

    res = login(client, state="deadbeef.0123456789abcdef")
    assert res.status_code == 400


def test_token_exchange_failure_is_bad_gateway(client, monkeypatch):
    def boom(url, data):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("services.oauth_provider._post", boom)
    res = login(client)
    assert res.status_code == 502
    assert res.get_json()["code"] == "OAUTH_PROVIDER_ERROR"


def test_userinfo_failure_is_bad_gateway(client, monkeypatch):
    def boom(url, headers):
        raise RuntimeError("500 from provider")

    monkeypatch.setattr("services.oauth_provider._post",
                        lambda url, data: {"access_token": "AT"})
    monkeypatch.setattr("services.oauth_provider._get", boom)

    res = login(client)
    assert res.status_code == 502
    assert res.get_json()["code"] == "OAUTH_PROVIDER_ERROR"


def test_token_response_without_access_token_is_bad_gateway(client, monkeypatch):
    stub_http(monkeypatch, GOOGLE_USERINFO, token={"error": "invalid_grant"})
    res = login(client)
    assert res.status_code == 502
    assert res.get_json()["code"] == "OAUTH_PROVIDER_ERROR"


def test_userinfo_without_provider_id_is_bad_gateway(client, monkeypatch):
    """provider_id 가 없으면 어느 계정인지 특정할 수 없다 — 임의로 만들면 안 된다."""
    stub_http(monkeypatch, {"email": "gu@fg.kr", "name": "구글사용자"})
    res = login(client)
    assert res.status_code == 502
    assert res.get_json()["code"] == "OAUTH_PROVIDER_ERROR"


def test_user_id_collision_is_reported_not_worked_around(client, monkeypatch):
    """합성한 user_id 가 이미 쓰이고 있으면 이름을 바꿔 만들지 않고 409 로 알린다.

    자동으로 접미사를 붙이면 계정이 조용히 늘어나 나중에 누가 누구인지 못 읽는다.
    (실제로는 아이디 작성규칙상 '_' 로 시작하는 일반 계정을 만들 수 없어 드물지만,
    provider_id 가 길어 50자로 잘릴 때 서로 다른 계정이 같은 아이디가 될 수 있다.)
    """
    from conftest import PW_HASH

    db.execute(
        """
        INSERT INTO users (user_id, user_pw, user_name, user_role, user_status)
        VALUES ('google_108127319', %s, '선점자', 'VIEWER', 'ACTIVE')
        """,
        (PW_HASH,),
    )
    stub_http(monkeypatch, GOOGLE_USERINFO)

    res = login(client)
    assert res.status_code == 409
    assert res.get_json()["code"] == "DUPLICATE_USER_ID"
    # 절반만 만들어진 계정이 남으면 안 된다
    assert db.query("SELECT 1 FROM users WHERE user_provider = 'GOOGLE'") == []


# ---------- 계정 상태 ----------

def test_suspended_social_account_cannot_log_in(client, monkeypatch):
    from conftest import make_social_user

    make_social_user(user_id="google_108127319", provider="GOOGLE",
                     provider_id="108127319", status="SUSPENDED")
    stub_http(monkeypatch, GOOGLE_USERINFO)

    res = login(client)
    assert res.status_code == 403
    assert res.get_json()["code"] == "ACCOUNT_SUSPENDED"


def test_withdrawn_social_account_cannot_log_in(client, monkeypatch):
    from conftest import make_social_user

    make_social_user(user_id="google_108127319", provider="GOOGLE",
                     provider_id="108127319", status="WITHDRAWN")
    stub_http(monkeypatch, GOOGLE_USERINFO)

    res = login(client)
    assert res.status_code == 403
    assert res.get_json()["code"] == "ACCOUNT_WITHDRAWN"


def test_blocked_account_records_no_activity(client, monkeypatch):
    from conftest import make_social_user

    user_no = make_social_user(user_id="google_108127319", provider="GOOGLE",
                               provider_id="108127319", status="SUSPENDED")
    stub_http(monkeypatch, GOOGLE_USERINFO)
    login(client)

    assert db.query("SELECT 1 FROM user_activity WHERE user_no = %s", (user_no,)) == []


# ---------- 로그아웃은 그대로 동작한다 ----------

def test_social_token_can_be_revoked_by_logout(client, monkeypatch):
    """폐기 기준선은 user_no 만 본다 — 소셜 계정이라고 따로 손댈 것이 없다.

    폐기 해상도가 1초라 로그인과 로그아웃 사이를 1초 이상 벌려야 한다
    (근거는 auth._assert_not_revoked, test_token_revocation.py 와 같은 사정이다).
    """
    stub_http(monkeypatch, GOOGLE_USERINFO)
    token = login(client).get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    time.sleep(1.05)

    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 401
    assert res.get_json()["code"] == "TOKEN_REVOKED"


# ---------- 소셜 계정이 도달할 수 있게 된 경로 ----------

def test_social_account_cannot_change_password(client, monkeypatch):
    """소셜 계정은 user_pw 가 NULL 이라 가드가 없으면 .encode() 에서 500 이 난다.

    OAuth 로그인이 붙기 전에는 토큰을 못 얻어 도달 불가능한 경로였다.
    """
    stub_http(monkeypatch, GOOGLE_USERINFO)
    token = login(client).get_json()["access_token"]

    res = client.put("/api/users/password",
                     headers={"Authorization": f"Bearer {token}"},
                     json={"current_password": PW, "new_password": "Renew#2026"})
    assert res.status_code == 400
    body = res.get_json()
    assert body["code"] == "SOCIAL_ACCOUNT"
    assert body["field"] == "user_pw"


def test_local_account_can_still_change_password(client, monkeypatch):
    """소셜 가드를 넣다가 일반 사용자의 비밀번호 변경을 막지 않았는지 확인한다."""
    from conftest import _headers

    res = client.put("/api/users/password",
                     headers=_headers(1, "admin01", "ADMIN"),
                     json={"current_password": PW, "new_password": "Renew#2026"})
    assert res.status_code == 200


# ---------- state 계산 자체 ----------

def test_state_is_not_stored_anywhere(client):
    """저장하지 않고 계산해 대조한다 — 발급만 여러 번 해도 남는 것이 없어야 한다."""
    before = db.query_one("SELECT count(*) AS cnt FROM users")["cnt"]
    for _ in range(3):
        client.get("/api/auth/oauth/google/authorize")
    assert db.query_one("SELECT count(*) AS cnt FROM users")["cnt"] == before


def test_each_state_is_unique(client):
    """같은 시간 버킷 안에서도 매번 다른 값이어야 한다 (요청마다 난스를 섞는다)."""
    states = {client.get("/api/auth/oauth/google/authorize").get_json()["state"]
              for _ in range(5)}
    assert len(states) == 5


def test_state_survives_within_validity_window(client):
    """동의화면을 띄워 놓고 몇 분 뒤 돌아와도 통해야 한다."""
    state = oauth_provider.issue_state("GOOGLE", now=time.time() - 120)
    assert oauth_provider.verify_state("GOOGLE", state) is True
