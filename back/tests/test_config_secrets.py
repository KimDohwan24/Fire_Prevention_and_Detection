"""시크릿 가드 — 개발용 기본값으로는 서버가 뜨지 않는다.

**왜 이 테스트가 있나** (2026-08-24):
`config.py` 는 시크릿을 `os.getenv(name, "dev-...")` 로 읽었다. `.env` 에 값이
없으면 아무 경고 없이 그 문자열로 돌아간다 — 에러도, 로그도 없다. 그런데 이 값
하나가 로그인 JWT 서명(auth.py:38)·OAuth state HMAC(oauth_provider.py:157)·
계정찾기 인증코드(account_recovery.py:53)·텔레그램 연동코드(telegram_link.py:45)를
전부 떠받친다. 소스코드에 적힌 공개 문자열이 키가 되는 순간 누구나 자기 노트북에서
`user_role: ADMIN` 짜리 토큰을 만들어 넣을 수 있고, 서버는 서명이 맞으니 통과시킨다.

그래서 **조용한 기본값을 시끄러운 실패로 바꾼다.** 잘못 뜬 서버보다 안 뜨는 서버가
낫다 — 안 뜨면 사람이 알아채지만, 잘못 뜬 것은 아무도 모른다.
"""
import pytest

import config
from app import create_app


def _values(**overrides):
    """검사 대상 값 묶음. 지정하지 않은 시크릿은 안전한 값으로 채운다."""
    base = {name: f"real-{name.lower()}-9f3a2b" for name in config.INSECURE_DEFAULTS}
    base.update(overrides)
    return base


# ---------- 무엇을 '설정되지 않음' 으로 볼 것인가 ----------

def test_하드코딩된_개발용_기본값은_미설정으로_본다():
    for name, default in config.INSECURE_DEFAULTS.items():
        assert config.insecure_secret_names(_values(**{name: default})) == [name]


def test_빈_문자열은_미설정이다():
    """`.env.example` 을 복사해 만든 `.env` 는 `JWT_SECRET=` 처럼 빈 값이다.

    python-dotenv 가 빈 문자열을 환경변수로 심으면 os.getenv 는 그것을 '값 있음'
    으로 보고 기본값을 쓰지 않는다 — 서명 키가 "" 가 된다. 게다가 내부 키가 "" 면
    `X-Internal-Key:` 를 빈 값으로 보낸 요청이 그대로 통과한다(auth.py:156).
    """
    assert config.insecure_secret_names(_values(JWT_SECRET="")) == ["JWT_SECRET"]


def test_공백뿐인_값도_미설정이다():
    assert config.insecure_secret_names(_values(JWT_SECRET="   ")) == ["JWT_SECRET"]


def test_값이_아예_없어도_미설정이다():
    values = _values()
    del values["INTERNAL_API_KEY"]
    assert config.insecure_secret_names(values) == ["INTERNAL_API_KEY"]


def test_제대로_된_값이면_아무것도_잡히지_않는다():
    assert config.insecure_secret_names(_values()) == []


# ---------- 어떻게 알릴 것인가 ----------

def test_문제가_여럿이면_한_번에_전부_알린다():
    """하나 고쳐 재기동, 또 하나 고쳐 재기동을 반복하게 만들지 않는다."""
    bad = config.insecure_secret_names(_values(JWT_SECRET="", INTERNAL_API_KEY=""))
    assert bad == ["JWT_SECRET", "INTERNAL_API_KEY"]


def test_에러_메시지가_문제_변수_이름을_담는다():
    with pytest.raises(RuntimeError) as exc:
        config.assert_secrets_configured(_values(AGENCY_CALLBACK_KEY=""))
    assert "AGENCY_CALLBACK_KEY" in str(exc.value)


def test_정상이면_예외가_없다():
    config.assert_secrets_configured(_values())


# ---------- 실제로 부팅이 막히는가 ----------

def test_기본값이면_앱이_뜨지_않는다(monkeypatch):
    """가드가 config 안에만 있으면 소용없다 — create_app 이 불러야 부팅이 막힌다.

    `python app.py` 뿐 아니라 WSGI 서버로 띄우는 경우까지 덮으려고 __main__ 이
    아니라 앱 팩토리에 둔다.
    """
    monkeypatch.setattr(config, "JWT_SECRET", config.INSECURE_DEFAULTS["JWT_SECRET"])
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        create_app()


def test_현재_설정으로는_앱이_뜬다():
    """회귀 방지 — 테스트 환경(conftest)이 가드를 통과하는 값을 심는지 확인한다."""
    assert config.insecure_secret_names() == []
    assert create_app() is not None
