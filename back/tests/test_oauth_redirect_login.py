"""소셜 로그인(OAuth) — 구글·카카오·네이버.

GET /api/auth/<provider>            302 → 프로바이더 동의화면
GET /api/auth/<provider>/callback   302 → 프론트 (#access_token 또는 #oauth_error)

로그인 방식은 **이것 하나뿐이다.** 프론트가 code 를 받아 POST 로 되돌려주던
SPA/JSON 방식(옛 test_oauth_login.py)은 걷어냈고, 거기서만 보던 동작은 전부 이 파일로
옮겨 리다이렉트 방식으로 다시 썼다.

응답은 **전부 302 다** — 브라우저가 따라오는 중이라 JSON 을 주면 사용자 화면에 원시
JSON 이 그대로 뜬다. 그래서 실패도 상태코드가 아니라 프래그먼트의 oauth_error 로
확인한다.

**실제 네트워크는 한 번도 타지 않는다.** oauth_provider 의 HTTP 진입점(_post/_get)을
테스트마다 monkeypatch 로 갈아끼운다 — conftest 의 _no_real_report_http /
_no_real_its_http 와 같은 방식이다. 다만 여기서는 전역 스텁을 두지 않았다. 프로바이더
응답 모양이 테스트마다 다르고, 스텁을 깜빡한 테스트는 키 미설정이나 연결 오류로
곧바로 드러난다.
"""
import time
from urllib.parse import parse_qs, urlparse

import pytest

import config
import db
from conftest import PW, _headers, make_social_user
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

USERINFO = {
    "google": GOOGLE_USERINFO,
    "kakao": KAKAO_USERINFO,
    "naver": NAVER_USERINFO,
}

# 위 응답에서 뽑혀 나와야 하는 (provider_id, email, name)
EXPECTED = {
    "google": ("108127319", "gu@fg.kr", "구글사용자"),
    "kakao": ("3312244556", "ka@fg.kr", "카카오사용자"),
    "naver": ("naver-8821", "na@fg.kr", "네이버사용자"),
}

# 프로바이더별 동의화면 호스트 — 리다이렉트가 실제로 저쪽으로 나가는지 확인용
CONSENT_HOST = {
    "google": "accounts.google.com",
    "kakao": "kauth.kakao.com",
    "naver": "nid.naver.com",
}

FRONT = "http://localhost:5173"
BACKEND = "http://localhost:5000"


@pytest.fixture(autouse=True)
def oauth_keys(monkeypatch):
    """세 프로바이더 키 + 프론트/백엔드 주소를 고정한다.

    실제 .env 값에 기대면 개발자마다 결과가 달라진다. '키 미설정' 시나리오만
    자기 monkeypatch 로 다시 비운다.
    """
    for provider in ("GOOGLE", "KAKAO", "NAVER"):
        monkeypatch.setattr(config, f"{provider}_CLIENT_ID", f"{provider.lower()}-cid")
        monkeypatch.setattr(config, f"{provider}_CLIENT_SECRET", f"{provider.lower()}-sec")
    monkeypatch.setattr(config, "OAUTH_REDIRECT_BASE", FRONT)
    monkeypatch.setattr(config, "OAUTH_CALLBACK_BASE", BACKEND)
    yield


def stub_http(monkeypatch, userinfo, token=None, spy=None):
    """토큰 교환·userinfo 두 번의 외부 호출을 스텁으로 갈아끼운다.

    spy 를 주면 토큰 교환에 실제로 나간 폼 데이터를 그 dict 에 담아 둔다
    (동의화면과 토큰 교환의 redirect_uri 대조에 쓴다).
    """
    def fake_post(url, data):
        if spy is not None:
            spy.update(data)
        return token if token is not None else {"access_token": "provider-access-token"}

    monkeypatch.setattr("services.oauth_provider._post", fake_post)
    monkeypatch.setattr("services.oauth_provider._get", lambda url, headers: userinfo)


def start(client, provider="google"):
    """로그인 버튼 = 브라우저를 백엔드로 보내는 것 (front/src/api.js startOAuthLogin)."""
    return client.get(f"/api/auth/{provider}")


def consent_params(res) -> dict:
    """동의화면 리다이렉트의 쿼리 파라미터를 {키: 값} 으로 펴서 돌려준다."""
    return {k: v[0] for k, v in parse_qs(urlparse(res.headers["Location"]).query).items()}


def issued_state(client, provider="google") -> str:
    """실제 시작 라우트가 발급한 state (직접 만들지 않고 라우트에서 받아 쓴다)."""
    return consent_params(start(client, provider))["state"]


def callback(client, provider="google", **params):
    """프로바이더가 브라우저를 되돌려보내는 요청."""
    query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    return client.get(f"/api/auth/{provider}/callback?{query}")


def login(client, monkeypatch, provider="google", userinfo=None):
    """시작 → 콜백 한 번. 로그인이 끝난 콜백 응답(302)을 돌려준다.

    성공 경로를 보는 테스트가 대부분이라 스텁·state 발급까지 여기서 묶는다.
    실패 주입이 필요한 테스트는 stub_http/callback 을 직접 부른다.
    """
    stub_http(monkeypatch, USERINFO[provider] if userinfo is None else userinfo)
    return callback(client, provider, code="auth-code",
                    state=issued_state(client, provider))


def fragment(res) -> dict:
    """콜백 응답 Location 의 **프래그먼트**를 {키: 값} 으로 편다."""
    return {k: v[0]
            for k, v in parse_qs(urlparse(res.headers["Location"]).fragment).items()}


def error_code(res) -> str:
    return fragment(res).get("oauth_error")


def me(client, token) -> dict:
    """발급된 토큰으로 내 정보를 읽는다.

    콜백은 프래그먼트에 토큰만 싣는다 (URL 에 개인정보를 넣지 않는다). 그래서 어떤
    계정으로 로그인됐는지는 이 경로로만 확인할 수 있다.
    """
    return client.get("/api/auth/me",
                      headers={"Authorization": f"Bearer {token}"}).get_json()


# ---------- 시작: GET /api/auth/<provider> ----------

@pytest.mark.parametrize("provider", ["google", "kakao", "naver"])
def test_start_redirects_to_provider_consent_screen(client, provider):
    res = start(client, provider)
    assert res.status_code == 302

    location = urlparse(res.headers["Location"])
    assert location.netloc == CONSENT_HOST[provider]

    params = consent_params(res)
    assert params["response_type"] == "code"
    assert params["client_id"] == f"{provider}-cid"
    assert params["state"]


def test_start_needs_no_token(client):
    """로그인 화면에서 누르는 버튼이다 — 토큰이 있을 리 없다."""
    assert start(client).status_code == 302


@pytest.mark.parametrize("provider", ["google", "kakao", "naver"])
def test_start_redirect_uri_points_at_backend_callback(client, provider):
    """콜백은 **프론트가 아니라 백엔드**다 (브라우저가 여기로 온다).

    프론트 주소(OAUTH_REDIRECT_BASE)를 여기에 잘못 쓰면 증상이 프로바이더의
    redirect_uri_mismatch 로만 나타나 원인을 찾기 아주 어렵다.
    """
    params = consent_params(start(client, provider))
    assert params["redirect_uri"] == f"{BACKEND}/api/auth/{provider}/callback"


def test_start_asks_google_for_openid_scope(client):
    """구글은 openid 를 넣어야 sub(계정 고유번호)가 안정적으로 내려온다."""
    assert consent_params(start(client))["scope"] == "openid email profile"


def test_start_state_is_unique_per_request(client):
    """같은 시간 버킷 안에서도 매번 다른 값이어야 한다 (요청마다 난스를 섞는다)."""
    assert len({issued_state(client) for _ in range(5)}) == 5


def test_start_reports_unsupported_provider_without_raw_json(client):
    """브라우저가 따라오는 중이라 여기서도 JSON 을 주면 안 된다."""
    res = start(client, "facebook")
    assert res.status_code == 302
    assert res.headers["Location"].startswith(f"{FRONT}/#")
    assert error_code(res) == "UNSUPPORTED_PROVIDER"


def test_start_reports_missing_keys(client, monkeypatch):
    """키 없이 배포된 상태에서 빈 client_id 가 박힌 동의화면으로 보내면 안 된다."""
    monkeypatch.setattr(config, "NAVER_CLIENT_ID", "")
    res = start(client, "naver")
    assert res.status_code == 302
    assert error_code(res) == "OAUTH_NOT_CONFIGURED"


# ---------- 라우트 충돌: /api/auth/<provider> 가 기존 GET 경로를 삼키지 않는다 ----------

def test_me_route_is_not_swallowed_by_the_provider_rule(client):
    """`/api/auth/<provider>` 는 `/api/auth/me` 와 모양이 겹친다.

    Werkzeug 가 정적 규칙을 동적 규칙보다 먼저 맞추므로 실제로는 /me 가 이긴다.
    그 사실이 깨지면 세션 복원이 통째로 죽으므로 여기서 못을 박아 둔다.
    """
    res = client.get("/api/auth/me")
    assert res.status_code == 401                 # 토큰이 없어서 401 — 302 가 아니다
    assert res.get_json()["code"] != "UNSUPPORTED_PROVIDER"


def test_post_only_routes_still_answer_405_to_get(client):
    """정적 규칙이 이기는 것은 **메서드까지 맞을 때**다.

    GET /api/auth/login 은 원래 405 인데, 그 405 를 내기 전에 Werkzeug 가 GET 을
    받는 동적 규칙(/api/auth/<provider>)을 찾아낸다. 가드가 없으면 POST 전용
    엔드포인트 전부가 GET 에 "지원하지 않는 소셜 로그인" 302 를 돌려주게 된다.
    """
    for path in ("/api/auth/login", "/api/auth/logout", "/api/auth/find-id"):
        res = client.get(path)
        assert res.status_code == 405, path
        assert res.get_json()["code"] == "METHOD_NOT_ALLOWED"


def test_me_route_still_returns_the_user_with_a_token(client, monkeypatch):
    token = fragment(login(client, monkeypatch))["access_token"]
    assert me(client, token)["user_id"] == "google_108127319"


# ---------- 콜백 성공 ----------

def test_callback_redirects_to_front_with_token_in_fragment(client, monkeypatch):
    res = login(client, monkeypatch)

    assert res.status_code == 302
    assert res.headers["Location"].startswith(f"{FRONT}/#")
    assert fragment(res)["access_token"]


def test_token_in_the_fragment_actually_works(client, monkeypatch):
    """모양만 맞고 쓸 수 없는 토큰이면 의미가 없다 — 보호된 경로로 직접 확인한다."""
    token = fragment(login(client, monkeypatch))["access_token"]

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200


def test_token_never_appears_in_the_query_string(client, monkeypatch):
    """쿼리는 서버 접근로그와 Referer 헤더에 남지만 프래그먼트는 서버로 가지 않는다.

    이 한 줄이 이 방식의 핵심이다 — 여기가 깨지면 JWT 가 로그에 평문으로 쌓인다.
    """
    location = login(client, monkeypatch).headers["Location"]

    assert urlparse(location).query == ""
    assert "access_token" not in location.split("#")[0]
    assert "access_token" in urlparse(location).fragment


def test_callback_carries_no_personal_information(client, monkeypatch):
    """토큰만 싣는다 — 사용자 정보는 프론트가 GET /api/auth/me 로 받아가면 된다."""
    assert set(fragment(login(client, monkeypatch))) == {"access_token"}


@pytest.mark.parametrize("provider", ["google", "kakao", "naver"])
def test_callback_creates_the_account_for_each_provider(client, monkeypatch, provider):
    res = login(client, monkeypatch, provider)

    assert fragment(res).get("access_token")
    row = db.query_one(
        """
        SELECT user_pw, user_role, user_status
        FROM users WHERE user_provider = %s
        """,
        (provider.upper(),),
    )
    assert row["user_pw"] is None          # 소셜 계정은 비밀번호를 갖지 않는다
    assert row["user_role"] == "VIEWER"    # 관제 권한은 관리자가 따로 올려준다
    assert row["user_status"] == "ACTIVE"


@pytest.mark.parametrize("provider", ["google", "kakao", "naver"])
def test_each_provider_response_is_normalized(client, monkeypatch, provider):
    """세 프로바이더가 값을 담아 주는 키 경로가 전부 다르다 — 표 하나로 흡수한다.

    카카오만 id 를 정수로 주는 것도 여기서 걸린다 (user_provider_id 는 varchar 다).
    """
    provider_id, email, name = EXPECTED[provider]
    login(client, monkeypatch, provider)

    row = db.query_one(
        """
        SELECT user_id, user_name, user_email, user_provider_id
        FROM users WHERE user_provider = %s
        """,
        (provider.upper(),),
    )
    assert row["user_provider_id"] == provider_id
    assert row["user_email"] == email
    assert row["user_name"] == name
    # user_id 는 로그인에 쓰이지 않는 합성값이다 (아이디 유니크 제약을 지키려고 둘 뿐)
    assert row["user_id"] == f"{provider}_{provider_id}"


def test_provider_path_is_case_insensitive(client, monkeypatch):
    """경로는 소문자로 받되 대문자로 와도 받아준다. DB 에는 항상 대문자로 저장한다."""
    stub_http(monkeypatch, KAKAO_USERINFO)
    res = callback(client, "KAKAO", code="c", state=issued_state(client, "KAKAO"))

    assert fragment(res).get("access_token")
    assert db.query_one(
        "SELECT count(*) AS cnt FROM users WHERE user_provider = 'KAKAO'"
    )["cnt"] == 1


def test_second_login_reuses_the_same_account(client, monkeypatch):
    """같은 프로바이더 계정으로 다시 들어오면 계정이 늘지 않는다."""
    stub_http(monkeypatch, GOOGLE_USERINFO)
    callback(client, code="c", state=issued_state(client))
    callback(client, code="c", state=issued_state(client))

    assert db.query_one(
        "SELECT count(*) AS cnt FROM users WHERE user_provider = 'GOOGLE'"
    )["cnt"] == 1


def test_existing_social_account_is_matched_by_provider_id(client, monkeypatch):
    """user_id 가 아니라 (provider, provider_id) 로 찾는다 — user_id 는 합성값일 뿐이다."""
    user_no = make_social_user(user_id="legacy_google_user", provider="GOOGLE",
                               provider_id="108127319", name="기존사용자")
    token = fragment(login(client, monkeypatch))["access_token"]

    body = me(client, token)
    assert body["user_no"] == user_no
    assert body["user_id"] == "legacy_google_user"


def test_callback_records_login_activity(client, monkeypatch):
    login(client, monkeypatch)

    user_no = db.query_one(
        "SELECT user_no FROM users WHERE user_provider = 'GOOGLE'"
    )["user_no"]
    rows = db.query("SELECT activity_type FROM user_activity WHERE user_no = %s",
                    (user_no,))
    assert [r["activity_type"] for r in rows] == ["LOGIN"]


def test_second_login_records_another_activity_row(client, monkeypatch):
    """재로그인은 계정을 늘리지 않지만 **이력은 늘어야** 한다."""
    stub_http(monkeypatch, GOOGLE_USERINFO)
    callback(client, code="c", state=issued_state(client))
    callback(client, code="c", state=issued_state(client))

    user_no = db.query_one(
        "SELECT user_no FROM users WHERE user_provider = 'GOOGLE'"
    )["user_no"]
    assert db.query_one(
        "SELECT count(*) AS cnt FROM user_activity WHERE user_no = %s", (user_no,)
    )["cnt"] == 2


# ---------- 이메일이 같은 일반 계정과 자동 연결하지 않는다 ----------

def test_matching_local_email_does_not_link_accounts(client, monkeypatch):
    """프로바이더가 이메일을 검증했다는 보장이 없어 계정 탈취 경로가 된다.

    시드의 admin01 이 admin@fg.kr 을 쓰고 있는데 같은 이메일로 소셜 로그인이
    들어오면, 자동 연결하는 구현에서는 그 사람이 ADMIN 계정을 통째로 가져간다.
    """
    res = login(client, monkeypatch,
                userinfo={**GOOGLE_USERINFO, "email": "admin@fg.kr"})

    body = me(client, fragment(res)["access_token"])
    assert body["user_no"] != 1
    assert body["user_role"] == "VIEWER"         # ADMIN 을 물려받지 않는다
    assert body["user_id"] == "google_108127319"

    # 원래 admin01 은 그대로 LOCAL 계정으로 남아 있어야 한다
    admin = db.query_one("SELECT user_provider, user_role FROM users WHERE user_no = 1")
    assert admin["user_provider"] == "LOCAL"
    assert admin["user_role"] == "ADMIN"


# ---------- 제일 깨지기 쉬운 지점: 두 redirect_uri 가 같아야 한다 ----------

@pytest.mark.parametrize("provider", ["google", "kakao", "naver"])
def test_consent_and_token_exchange_send_the_same_redirect_uri(client, monkeypatch,
                                                               provider):
    """다르면 프로바이더가 redirect_uri_mismatch 로 거절한다.

    동의화면 URL 과 토큰 교환 폼을 각각 뜯어 **실제로 나간 값끼리** 비교한다 —
    양쪽이 같은 함수를 부르는지 보는 것만으로는 한쪽이 다른 값을 만들어 내는 것을
    못 잡는다.
    """
    sent = {}
    stub_http(monkeypatch, USERINFO[provider], spy=sent)

    consent = consent_params(start(client, provider))
    callback(client, provider, code="c", state=consent["state"])

    assert sent["redirect_uri"] == consent["redirect_uri"]
    assert sent["redirect_uri"] == f"{BACKEND}/api/auth/{provider}/callback"


# ---------- state — 저장하지 않고 계산해 대조한다 ----------

def test_forged_state_is_rejected(client, monkeypatch):
    stub_http(monkeypatch, GOOGLE_USERINFO)
    res = callback(client, code="c", state="deadbeef.0123456789abcdef")
    assert error_code(res) == "INVALID_OAUTH_STATE"


def test_expired_state_is_rejected(client, monkeypatch):
    stub_http(monkeypatch, GOOGLE_USERINFO)
    stale = oauth_provider.issue_state("GOOGLE", now=time.time() - 3600)

    res = callback(client, code="c", state=stale)
    assert error_code(res) == "INVALID_OAUTH_STATE"


def test_state_survives_within_validity_window(client):
    """동의화면을 띄워 놓고 몇 분 뒤 돌아와도 통해야 한다."""
    state = oauth_provider.issue_state("GOOGLE", now=time.time() - 120)
    assert oauth_provider.verify_state("GOOGLE", state) is True


def test_state_of_another_provider_is_rejected(client, monkeypatch):
    """provider 를 HMAC 입력에 넣었기 때문에 다른 프로바이더의 state 는 통하지 않는다."""
    stub_http(monkeypatch, KAKAO_USERINFO)
    res = callback(client, "kakao", code="c", state=issued_state(client, "google"))
    assert error_code(res) == "INVALID_OAUTH_STATE"


def test_state_is_not_stored_anywhere(client):
    """저장하지 않고 계산해 대조한다 — 발급만 여러 번 해도 남는 것이 없어야 한다."""
    before = db.query_one("SELECT count(*) AS cnt FROM users")["cnt"]
    for _ in range(3):
        start(client)
    assert db.query_one("SELECT count(*) AS cnt FROM users")["cnt"] == before


def test_state_check_happens_before_any_external_call(client, monkeypatch):
    """위조된 state 로는 프로바이더를 두드리지도 않는다 (남의 서버 대신 맞아주지 않게)."""
    def boom(*args, **kwargs):
        raise AssertionError("state 검증 전에 외부 호출이 나갔다")

    monkeypatch.setattr("services.oauth_provider._post", boom)
    monkeypatch.setattr("services.oauth_provider._get", boom)

    res = callback(client, code="c", state="deadbeef.0123456789abcdef")
    assert res.status_code == 302
    assert error_code(res) == "INVALID_OAUTH_STATE"


# ---------- 콜백 실패 경로 — 전부 302 다 ----------

def test_user_denied_consent(client, monkeypatch):
    """동의화면에서 '취소'를 누른 경우. 오류가 아니라 사용자의 선택이다."""
    stub_http(monkeypatch, GOOGLE_USERINFO)
    res = callback(client, error="access_denied", state=issued_state(client))

    assert res.status_code == 302
    assert error_code(res) == "ACCESS_DENIED"
    assert db.query("SELECT 1 FROM users WHERE user_provider = 'GOOGLE'") == []


def test_provider_side_error_is_not_reported_as_user_denial(client):
    """저쪽 장애(server_error 등)를 '사용자가 취소함'으로 안내하면 안내가 틀린다."""
    res = callback(client, error="server_error", state="whatever")
    assert error_code(res) == "OAUTH_PROVIDER_ERROR"


def test_callback_without_code_is_a_provider_error(client, monkeypatch):
    """code 도 error 도 없이 돌아오는 것은 프로바이더가 규약을 어긴 것이다."""
    stub_http(monkeypatch, GOOGLE_USERINFO)
    res = callback(client, state=issued_state(client))
    assert error_code(res) == "OAUTH_PROVIDER_ERROR"


def test_token_exchange_failure(client, monkeypatch):
    state = issued_state(client)

    def boom(url, data):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("services.oauth_provider._post", boom)
    res = callback(client, code="c", state=state)
    assert error_code(res) == "OAUTH_PROVIDER_ERROR"


def test_token_response_without_access_token_is_a_provider_error(client, monkeypatch):
    """만료·재사용된 code 가 여기서 걸린다 (구글은 invalid_grant 를 준다)."""
    state = issued_state(client)
    stub_http(monkeypatch, GOOGLE_USERINFO, token={"error": "invalid_grant"})

    res = callback(client, code="c", state=state)
    assert error_code(res) == "OAUTH_PROVIDER_ERROR"


def test_userinfo_failure_is_a_provider_error(client, monkeypatch):
    """토큰 교환은 됐는데 userinfo 조회에서 터지는 경우도 저쪽 문제로 분류한다."""
    state = issued_state(client)

    def boom(url, headers):
        raise RuntimeError("500 from provider")

    monkeypatch.setattr("services.oauth_provider._post",
                        lambda url, data: {"access_token": "AT"})
    monkeypatch.setattr("services.oauth_provider._get", boom)

    res = callback(client, code="c", state=state)
    assert error_code(res) == "OAUTH_PROVIDER_ERROR"


def test_userinfo_without_provider_id_is_a_provider_error(client, monkeypatch):
    """provider_id 가 없으면 어느 계정인지 특정할 수 없다 — 임의로 만들면 안 된다."""
    state = issued_state(client)
    stub_http(monkeypatch, {"email": "gu@fg.kr", "name": "구글사용자"})

    res = callback(client, code="c", state=state)
    assert error_code(res) == "OAUTH_PROVIDER_ERROR"
    assert db.query("SELECT 1 FROM users WHERE user_provider = 'GOOGLE'") == []


def test_naver_failure_body_is_treated_as_error(client, monkeypatch):
    """네이버는 실패해도 HTTP 200 이다 — resultcode 를 안 보면 성공으로 착각한다."""
    stub_http(monkeypatch, {"resultcode": "024", "message": "Authentication failed"})
    res = callback(client, "naver", code="c", state=issued_state(client, "naver"))

    assert error_code(res) == "OAUTH_PROVIDER_ERROR"
    assert db.query("SELECT 1 FROM users WHERE user_provider = 'NAVER'") == []


def test_callback_rejects_unsupported_provider(client):
    res = callback(client, "facebook", code="c", state="s")
    assert res.status_code == 302
    assert error_code(res) == "UNSUPPORTED_PROVIDER"


def test_callback_reports_missing_keys(client, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_CLIENT_SECRET", "")
    res = callback(client, code="c", state="s")
    assert error_code(res) == "OAUTH_NOT_CONFIGURED"


def test_user_id_collision_is_reported_not_worked_around(client, monkeypatch):
    """합성한 user_id 가 이미 쓰이고 있으면 이름을 바꿔 만들지 않고 그대로 알린다.

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

    res = login(client, monkeypatch)
    assert error_code(res) == "DUPLICATE_USER_ID"
    # 절반만 만들어진 계정이 남으면 안 된다
    assert db.query("SELECT 1 FROM users WHERE user_provider = 'GOOGLE'") == []


# ---------- 계정 상태 ----------

def test_suspended_account_cannot_log_in(client, monkeypatch):
    make_social_user(user_id="google_108127319", provider="GOOGLE",
                     provider_id="108127319", status="SUSPENDED")

    res = login(client, monkeypatch)
    assert error_code(res) == "ACCOUNT_SUSPENDED"
    assert "access_token" not in fragment(res)


def test_withdrawn_account_cannot_log_in(client, monkeypatch):
    make_social_user(user_id="google_108127319", provider="GOOGLE",
                     provider_id="108127319", status="WITHDRAWN")

    res = login(client, monkeypatch)
    assert error_code(res) == "ACCOUNT_WITHDRAWN"


def test_blocked_account_records_no_activity(client, monkeypatch):
    user_no = make_social_user(user_id="google_108127319", provider="GOOGLE",
                               provider_id="108127319", status="SUSPENDED")
    login(client, monkeypatch)

    assert db.query("SELECT 1 FROM user_activity WHERE user_no = %s", (user_no,)) == []


# ---------- 로그아웃은 그대로 동작한다 ----------

def test_social_token_can_be_revoked_by_logout(client, monkeypatch):
    """폐기 기준선은 user_no 만 본다 — 소셜 계정이라고 따로 손댈 것이 없다.

    폐기 해상도가 1초라 로그인과 로그아웃 사이를 1초 이상 벌려야 한다
    (근거는 auth._assert_not_revoked, test_token_revocation.py 와 같은 사정이다).
    """
    token = fragment(login(client, monkeypatch))["access_token"]
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
    token = fragment(login(client, monkeypatch))["access_token"]

    res = client.put("/api/users/password",
                     headers={"Authorization": f"Bearer {token}"},
                     json={"current_password": PW, "new_password": "Renew#2026"})
    assert res.status_code == 400
    body = res.get_json()
    assert body["code"] == "SOCIAL_ACCOUNT"
    assert body["field"] == "user_pw"


def test_local_account_can_still_change_password(client):
    """소셜 가드를 넣다가 일반 사용자의 비밀번호 변경을 막지 않았는지 확인한다."""
    res = client.put("/api/users/password",
                     headers=_headers(1, "admin01", "ADMIN"),
                     json={"current_password": PW, "new_password": "Renew#2026"})
    assert res.status_code == 200
