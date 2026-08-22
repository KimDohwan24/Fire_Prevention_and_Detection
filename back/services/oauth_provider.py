"""소셜 로그인 프로바이더 연동 — 구글·카카오·네이버.

**이 모듈은 DB 를 모른다.** 외부 HTTP 만 담당하고 결과를
`{provider, provider_id, email, name}` 로 정규화해 돌려준다. 계정을 찾거나 만드는
일은 routes/auth_routes.py 쪽이다.

세 프로바이더의 차이는 **URL·파라미터 이름·응답에서 값을 꺼내는 경로뿐**이고 흐름은
하나다 (동의화면 → code → 토큰 교환 → userinfo). 그래서 흐름은 함수로 한 번만 쓰고
프로바이더별 값은 아래 PROVIDERS 표에 둔다. if/elif 로 세 갈래를 복붙하면 나중에
프로바이더가 하나 늘 때마다 같은 로직을 네 번 고쳐야 한다.

⚠️ 네이버는 **실패해도 HTTP 200 을 주고 본문 resultcode 로 알린다.** 상태코드만
   보면 인증 실패를 성공으로 착각한다 — 표의 ok_path/ok_value 가 그것을 잡는다.

로그인 방식은 **리다이렉트 하나뿐이다.** 프로바이더는 브라우저를 언제나 백엔드
콜백(`/api/auth/{provider}/callback`)으로 되돌려보내므로 redirect_uri 도 하나다.
프론트가 code 를 받아 되돌려주던 SPA/JSON 방식은 걷어냈다 (필요하면 git 히스토리
e0d6ea6 에 있다).

state (CSRF 방지값)는 **저장하지 않는다.** account_recovery.py 의 인증코드와 같은
방식으로 HMAC 을 그때그때 계산해 대조한다 — 표를 새로 만들면 팀원 로컬 DB
마이그레이션까지 줄줄이 따라오는데, 왕복 한 번 쓰고 버릴 값에 치를 비용이 아니다.
만료도 같은 방식(시간 버킷)으로 준다.
"""
import hashlib
import hmac
import logging
import secrets
import time
from urllib.parse import urlencode

import requests

import config

logger = logging.getLogger("fireguard.oauth")

# 외부 호출 타임아웃(초). 로그인 응답을 오래 붙잡지 않도록 짧게 둔다.
# 119 신고(REPORT_HTTP_TIMEOUT_SEC)와 값을 공유하지 않는다 — 저쪽은 사람이 기다리지
# 않는 백그라운드 전송이라 조정 기준이 다르고, 한쪽을 줄이면 다른 쪽이 같이 줄어든다.
HTTP_TIMEOUT_SEC = config.OAUTH_HTTP_TIMEOUT_SEC

# state 1개의 유효 구간(초)과 검증 시 거슬러 확인할 버킷 수 (10 × 60초 ≈ 10분).
# 계정 찾기 코드(5분)보다 길게 잡은 이유: 사용자가 동의화면에서 프로바이더 계정에
# 새로 로그인하고 2단계 인증까지 거쳐 돌아오는 시간이 여기 통째로 들어간다.
STATE_BUCKET_SEC = 60
STATE_VALID_BUCKETS = 10


class OAuthProviderError(Exception):
    """프로바이더 쪽 문제 — 네트워크·상태코드·응답 형식·본문 오류코드 전부.

    라우트는 이것 하나만 잡아 502 OAUTH_PROVIDER_ERROR 로 바꾼다. 우리 잘못과
    저쪽 잘못을 응답에서 구분할 수 있어야 장애 때 어디를 볼지 정할 수 있다.
    """


# 프로바이더별로 다른 값만 모아 둔 표. 흐름은 아래 함수들이 공유한다.
#   *_path : 응답 dict 에서 값을 꺼내는 키 경로 (중첩 깊이가 제각각이라 튜플로 둔다)
#   ok_path/ok_value : 200 인데 본문으로 실패를 알리는 프로바이더용 (네이버)
#   state_in_token   : 토큰 교환에도 state 를 함께 보내야 하는 프로바이더용 (네이버)
PROVIDERS = {
    "GOOGLE": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v3/userinfo",
        # openid 를 넣어야 sub(계정 고유번호)가 안정적으로 내려온다
        "scope": "openid email profile",
        "id_path": ("sub",),
        "email_path": ("email",),
        "name_path": ("name",),
        "ok_path": None,
        "ok_value": None,
        "state_in_token": False,
    },
    "KAKAO": {
        "authorize_url": "https://kauth.kakao.com/oauth/authorize",
        "token_url": "https://kauth.kakao.com/oauth/token",
        "userinfo_url": "https://kapi.kakao.com/v2/user/me",
        # 동의항목은 카카오 개발자 콘솔에서 설정한다 — scope 를 보내면 콘솔 설정과
        # 어긋났을 때 동의화면 자체가 열리지 않아서 보내지 않는다
        "scope": None,
        # id 가 JSON 정수로 온다. user_provider_id 는 varchar 라 문자열로 바꿔 넣는다
        "id_path": ("id",),
        "email_path": ("kakao_account", "email"),
        "name_path": ("kakao_account", "profile", "nickname"),
        "ok_path": None,
        "ok_value": None,
        "state_in_token": False,
    },
    "NAVER": {
        "authorize_url": "https://nid.naver.com/oauth2.0/authorize",
        "token_url": "https://nid.naver.com/oauth2.0/token",
        "userinfo_url": "https://openapi.naver.com/v1/nid/me",
        "scope": None,
        "id_path": ("response", "id"),
        "email_path": ("response", "email"),
        "name_path": ("response", "name"),
        # 네이버만 200 + 본문 오류를 쓴다. "00" 이 아니면 전부 실패다
        "ok_path": ("resultcode",),
        "ok_value": "00",
        "state_in_token": True,
    },
}


def normalize_provider(raw) -> str | None:
    """경로로 받은 값을 표의 키(대문자)로 바꾼다. 미지원이면 None.

    경로는 소문자(`/api/auth/google`)로 쓰기로 했지만 대문자로 와도 받는다.
    DB 의 user_provider 는 항상 대문자다 (db/schema.sql '상태값 정의' 블록).
    """
    name = str(raw or "").strip().upper()
    return name if name in PROVIDERS else None


def credentials(provider: str) -> tuple[str, str]:
    """(client_id, client_secret). 미설정이면 빈 문자열이 그대로 나온다."""
    return (getattr(config, f"{provider}_CLIENT_ID", "") or "",
            getattr(config, f"{provider}_CLIENT_SECRET", "") or "")


def is_configured(provider: str) -> bool:
    """.env 에 그 프로바이더 키가 둘 다 들어와 있는가."""
    client_id, client_secret = credentials(provider)
    return bool(client_id and client_secret)


def redirect_uri(provider: str) -> str:
    """프로바이더가 브라우저를 되돌려보낼 곳 — **서버가 계산한다.**

    프론트가 자기 주소를 따로 들고 있으면 값이 두 곳에 생기고, 한쪽만 고쳐서
    프로바이더 콘솔에 등록한 값과 어긋나는 순간 redirect_uri_mismatch 가 난다.
    한 곳(config)에서만 정의한다.

    돌아오는 곳은 **백엔드 자신**이다 (프론트가 아니다). 그래서 프론트 주소인
    OAUTH_REDIRECT_BASE 가 아니라 OAUTH_CALLBACK_BASE 를 쓴다 — 두 변수의 역할
    차이는 config.py 주석에 적어 뒀다.
    """
    return (f"{config.OAUTH_CALLBACK_BASE.rstrip('/')}"
            f"/api/auth/{provider.lower()}/callback")


# ---------- state — 저장하지 않고 계산해 대조한다 ----------

def _bucket(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STATE_BUCKET_SEC)


def _sign(provider: str, nonce: str, bucket: int) -> str:
    """한 버킷에 대한 서명 (발급·검증이 같은 함수를 쓴다).

    provider 를 입력에 넣기 때문에 구글에서 받은 state 를 카카오 콜백에 밀어넣는
    식으로 돌려쓸 수 없다.
    """
    msg = f"{provider}|{bucket}|{nonce}".encode()
    return hmac.new(config.JWT_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def issue_state(provider: str, now: float | None = None) -> str:
    """`난스.서명` 형태의 state 를 만든다.

    account_recovery 의 인증코드와 달리 **난스를 섞는다.** 저기는 user_no 가 입력에
    들어가 사람마다 값이 갈리지만, 여기는 입력이 provider 와 시각뿐이라 난스가
    없으면 같은 분(分)에 로그인하는 모든 사용자가 똑같은 state 를 받는다. 그러면
    공격자가 자기 값으로 남의 콜백을 위조할 수 있어 CSRF 방지값 구실을 못 한다.
    """
    nonce = secrets.token_urlsafe(12)
    return f"{nonce}.{_sign(provider, nonce, _bucket(now))}"


def verify_state(provider: str, state, now: float | None = None) -> bool:
    """최근 STATE_VALID_BUCKETS 개 버킷 중 하나와 서명이 맞으면 True.

    맞는 버킷을 찾아도 중간에 빠져나가지 않는다 — 몇 번째에서 맞았는지가 응답
    시간으로 새어나가지 않게 하기 위해서다 (account_recovery.verify_code 와 동일).
    """
    nonce, _, signature = str(state or "").partition(".")
    if not nonce or not signature:
        return False

    current = _bucket(now)
    matched = False
    for back in range(STATE_VALID_BUCKETS):
        matched |= hmac.compare_digest(signature,
                                       _sign(provider, nonce, current - back))
    return matched


def authorize_url(provider: str, state: str) -> str:
    """사용자를 보낼 동의화면 주소.

    ⚠️ 여기 실리는 redirect_uri 와 _exchange_code 가 보내는 redirect_uri 는
       **글자 하나까지 같아야** 한다 (프로바이더가 대조한다). 그래서 두 곳 모두
       같은 redirect_uri() 를 부른다 — 한쪽만 다른 값을 만들면 동의화면은 열리는데
       토큰 교환에서만 실패하는, 원인 찾기 어려운 버그가 난다.
    """
    spec = PROVIDERS[provider]
    client_id, _ = credentials(provider)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri(provider),
        # 네이버는 필수, 나머지 둘은 선택 — 어차피 우리가 항상 검증하므로 전부 보낸다
        "state": state,
    }
    if spec["scope"]:
        params["scope"] = spec["scope"]
    return f"{spec['authorize_url']}?{urlencode(params)}"


# ---------- 외부 HTTP — 실제 통신은 이 두 함수에서만 나간다 (테스트 스텁 지점) ----------

def _post(url: str, data: dict) -> dict:
    """토큰 교환 (application/x-www-form-urlencoded)."""
    resp = requests.post(url, data=data, timeout=HTTP_TIMEOUT_SEC)
    resp.raise_for_status()
    return resp.json()


def _get(url: str, headers: dict) -> dict:
    """userinfo 조회."""
    resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SEC)
    resp.raise_for_status()
    return resp.json()


# ---------- 흐름 ----------

def _dig(payload, path):
    """중첩 dict 에서 키 경로를 따라 값을 꺼낸다. 중간이 끊기면 None."""
    current = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _exchange_code(provider: str, code: str, state: str) -> str:
    """authorization code → access token."""
    spec = PROVIDERS[provider]
    client_id, client_secret = credentials(provider)
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        # 동의화면에 보냈던 값과 **글자 하나까지 같아야** 한다 (프로바이더가 대조한다).
        # authorize_url 과 같은 함수를 부르는 것이 그 보장이다.
        "redirect_uri": redirect_uri(provider),
    }
    if spec["state_in_token"]:
        data["state"] = state

    try:
        payload = _post(spec["token_url"], data)
    except Exception as exc:
        raise OAuthProviderError(f"{provider} 토큰 교환 실패: {exc}") from exc

    token = _dig(payload, ("access_token",))
    if not token:
        # 만료·재사용된 code 는 여기서 걸린다 (구글은 invalid_grant 를 준다)
        raise OAuthProviderError(
            f"{provider} 토큰 응답에 access_token 이 없음 "
            f"(error={_dig(payload, ('error',))})"
        )
    return token


def _fetch_userinfo(provider: str, access_token: str) -> dict:
    spec = PROVIDERS[provider]
    try:
        payload = _get(spec["userinfo_url"],
                       {"Authorization": f"Bearer {access_token}"})
    except Exception as exc:
        raise OAuthProviderError(f"{provider} 사용자 정보 조회 실패: {exc}") from exc

    # 200 인데 본문으로 실패를 알리는 프로바이더(네이버) — 여기서 걸러내지 않으면
    # 아래 파싱이 전부 None 을 집어 '이름 없는 신규 계정'을 만들어 버린다
    if spec["ok_path"] and _dig(payload, spec["ok_path"]) != spec["ok_value"]:
        raise OAuthProviderError(
            f"{provider} 사용자 정보 응답 오류 "
            f"(resultcode={_dig(payload, spec['ok_path'])})"
        )
    return payload


def fetch_identity(provider: str, code: str, state: str = "") -> dict:
    """code 를 신원으로 바꾼다 — 이 모듈의 진입점.

    반환: {"provider": "GOOGLE", "provider_id": "...", "email": ..., "name": ...}
    email·name 은 없을 수 있다(사용자가 동의하지 않았거나 프로바이더가 안 준다).
    **provider_id 만은 없으면 안 된다** — 어느 계정인지 특정하는 유일한 값이라,
    빠진 채로 진행하면 서로 다른 사람이 같은 행에 묶인다.
    """
    spec = PROVIDERS[provider]
    payload = _fetch_userinfo(provider,
                              _exchange_code(provider, code, state))

    provider_id = _dig(payload, spec["id_path"])
    if provider_id is None or str(provider_id).strip() == "":
        raise OAuthProviderError(f"{provider} 응답에 계정 식별자가 없음")

    email = _dig(payload, spec["email_path"])
    name = _dig(payload, spec["name_path"])
    return {
        "provider": provider,
        # 카카오는 정수로 준다 — 컬럼이 varchar 라 여기서 문자열로 고정한다
        "provider_id": str(provider_id).strip(),
        "email": email or None,
        "name": name or None,
    }
