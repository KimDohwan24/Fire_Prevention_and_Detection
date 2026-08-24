"""텔레그램 Bot API 래퍼 — 전송 계층만 본다.

이 모듈은 앱 의미(어떤 버튼을 붙일지, 콜백을 어떻게 해석할지)를 모른다.
그건 services/telegram_bot.py 몫이다. 여기서 지키려는 성질은 하나다:
**어떤 실패에서도 예외를 밖으로 흘리지 않는다.** 알림 발송 실패가 알림 행 생성을
막거나, 폴링 실패가 워커를 죽이면 안 되기 때문이다.
"""
import json

import pytest
import requests

import config
from services import telegram


@pytest.fixture()
def token(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "12345:TESTTOKEN")


@pytest.fixture()
def no_token(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")


@pytest.fixture()
def calls(monkeypatch):
    """_api 호출을 기록하고 성공 응답을 돌려주는 대역."""
    recorded = []

    def fake_api(method, payload):
        recorded.append((method, payload))
        return {"ok": True, "result": {"message_id": 555}}

    monkeypatch.setattr(telegram, "_api", fake_api)
    return recorded


# ---------- 스위치 ----------

def test_disabled_when_token_is_missing(no_token):
    assert telegram.is_enabled() is False


def test_enabled_when_token_is_set(token):
    assert telegram.is_enabled() is True


def test_send_message_makes_no_http_call_when_disabled(no_token, calls):
    assert telegram.send_message(999, "불이야") is False
    assert calls == []


# ---------- 발송 ----------

def test_send_message_posts_chat_id_and_text(token, calls):
    assert telegram.send_message(999, "불이야") is True

    method, payload = calls[0]
    assert method == "sendMessage"
    assert payload["chat_id"] == 999
    assert payload["text"] == "불이야"


def test_send_message_attaches_buttons_as_inline_keyboard(token, calls):
    buttons = [[{"text": "화재 확인", "callback_data": "resp:12:READ"}]]

    telegram.send_message(999, "불이야", buttons=buttons)

    _, payload = calls[0]
    assert payload["reply_markup"] == {"inline_keyboard": buttons}


def test_send_message_omits_reply_markup_when_no_buttons(token, calls):
    telegram.send_message(999, "불이야")

    _, payload = calls[0]
    assert "reply_markup" not in payload


def test_send_message_is_false_when_telegram_rejects_it(token, monkeypatch):
    monkeypatch.setattr(telegram, "_api",
                        lambda method, payload: {"ok": False, "description": "blocked"})

    assert telegram.send_message(999, "불이야") is False


def test_send_message_is_false_when_the_http_call_raises(token, monkeypatch):
    def boom(method, payload):
        raise requests.RequestException("network down")

    monkeypatch.setattr(telegram, "_api", boom)

    assert telegram.send_message(999, "불이야") is False


# ---------- 사진 발송 ----------
#
# sendPhoto 는 파일을 **multipart** 로 올린다 — 기존 _api 는 JSON body 라 같은 길로
# 갈 수 없다. 그래서 이 경로만 별도 seam(_api_multipart)을 둔다.

@pytest.fixture()
def photo_calls(monkeypatch):
    """_api_multipart 호출을 기록하고 성공 응답을 돌려주는 대역."""
    recorded = []

    def fake_api(method, data, files):
        recorded.append((method, data, files))
        return {"ok": True, "result": {"message_id": 777}}

    monkeypatch.setattr(telegram, "_api_multipart", fake_api)
    return recorded


def test_send_photo_posts_the_chat_id_and_caption(token, photo_calls):
    assert telegram.send_photo(999, b"\xff\xd8jpeg", "불이야") is True

    method, data, _ = photo_calls[0]
    assert method == "sendPhoto"
    assert data["chat_id"] == 999
    assert data["caption"] == "불이야"


def test_send_photo_uploads_the_bytes_as_a_file(token, photo_calls):
    """이미지는 form 필드가 아니라 파일로 올라가야 한다 (Bot API 규격)."""
    telegram.send_photo(999, b"\xff\xd8jpeg", "불이야")

    _, _, files = photo_calls[0]
    assert b"\xff\xd8jpeg" in files["photo"]


def test_send_photo_attaches_buttons_as_a_json_string(token, photo_calls):
    """multipart 는 form 필드가 전부 문자열이라 reply_markup 을 dict 로 실을 수 없다.

    JSON 으로 직렬화하지 않으면 텔레그램이 버튼을 못 읽고, 확인/취소 경로가 통째로
    사라진다 — 사진만 예쁘게 오고 응답은 못 하는 알림이 된다.
    """
    buttons = [[{"text": "화재 확인", "callback_data": "resp:12:READ"}]]

    telegram.send_photo(999, b"\xff\xd8jpeg", "불이야", buttons=buttons)

    _, data, _ = photo_calls[0]
    assert json.loads(data["reply_markup"]) == {"inline_keyboard": buttons}


def test_send_photo_omits_reply_markup_when_no_buttons(token, photo_calls):
    telegram.send_photo(999, b"\xff\xd8jpeg", "불이야")

    _, data, _ = photo_calls[0]
    assert "reply_markup" not in data


def test_send_photo_clips_the_caption_to_the_api_limit(token, photo_calls):
    """caption 은 1024자까지다 (본문 4096과 다르다).

    넘기면 텔레그램이 통째로 거절해서 **사진도 문구도 안 간다.** 잘라서라도 보낸다.
    """
    telegram.send_photo(999, b"\xff\xd8jpeg", "불" * 2000)

    _, data, _ = photo_calls[0]
    assert len(data["caption"]) <= 1024
    assert data["caption"].startswith("불불불")


def test_send_photo_leaves_a_short_caption_alone(token, photo_calls):
    telegram.send_photo(999, b"\xff\xd8jpeg", "불이야")

    _, data, _ = photo_calls[0]
    assert data["caption"] == "불이야"


def test_send_photo_makes_no_http_call_when_disabled(no_token, photo_calls):
    assert telegram.send_photo(999, b"\xff\xd8jpeg", "불이야") is False
    assert photo_calls == []


def test_send_photo_is_false_when_telegram_rejects_it(token, monkeypatch):
    monkeypatch.setattr(
        telegram, "_api_multipart",
        lambda method, data, files: {"ok": False, "description": "PHOTO_INVALID_DIMENSIONS"})

    assert telegram.send_photo(999, b"\xff\xd8jpeg", "불이야") is False


def test_send_photo_is_false_when_the_http_call_raises(token, monkeypatch):
    """이 모듈의 성질: 어떤 실패에서도 예외를 밖으로 흘리지 않는다."""
    def boom(method, data, files):
        raise requests.RequestException("network down")

    monkeypatch.setattr(telegram, "_api_multipart", boom)

    assert telegram.send_photo(999, b"\xff\xd8jpeg", "불이야") is False


def test_real_multipart_posts_through_the_session(token, monkeypatch):
    """seam 이 맞아도 실제 구현이 다른 길로 나가면 소용이 없다."""
    posted = {}

    def fake_post(url, data=None, files=None, timeout=None):
        posted["url"], posted["data"], posted["files"] = url, data, files
        raise requests.RequestException("stop here — 실제로 나가지 않게")

    monkeypatch.setattr(telegram, "_api_multipart", telegram._real_api_multipart)
    monkeypatch.setattr(telegram._session, "post", fake_post)

    telegram.send_photo(999, b"\xff\xd8jpeg", "불이야")   # 예외는 래퍼가 삼킨다

    assert posted["url"].endswith("/sendPhoto")
    assert posted["files"] is not None, "JSON 이 아니라 multipart 로 나가야 한다"


# ---------- 수신 ----------

def test_get_updates_passes_the_offset(token, monkeypatch):
    seen = {}

    def fake_api(method, payload):
        seen["method"], seen["payload"] = method, payload
        return {"ok": True, "result": [{"update_id": 7}]}

    monkeypatch.setattr(telegram, "_api", fake_api)

    assert telegram.get_updates(offset=100) == [{"update_id": 7}]
    assert seen["method"] == "getUpdates"
    assert seen["payload"]["offset"] == 100


def test_get_updates_sends_the_long_poll_timeout(token, monkeypatch):
    """timeout 은 **서버가 응답을 붙잡고 기다려 줄 시간**이다 (롱폴링)."""
    seen = {}

    def fake_api(method, payload):
        seen.update(payload)
        return {"ok": True, "result": []}

    monkeypatch.setattr(telegram, "_api", fake_api)

    telegram.get_updates(offset=5, timeout_sec=25)

    assert seen["timeout"] == 25


def test_get_updates_returns_empty_list_when_disabled(no_token, calls):
    assert telegram.get_updates(offset=0) == []
    assert calls == []


def test_get_updates_returns_empty_list_when_the_http_call_raises(token, monkeypatch):
    def boom(method, payload):
        raise requests.RequestException("network down")

    monkeypatch.setattr(telegram, "_api", boom)

    # 폴링 워커는 이 실패로 멈추면 안 된다
    assert telegram.get_updates(offset=0) == []


def test_get_updates_returns_empty_list_when_telegram_rejects_it(token, monkeypatch):
    monkeypatch.setattr(telegram, "_api",
                        lambda method, payload: {"ok": False, "description": "nope"})

    assert telegram.get_updates(offset=0) == []


# ---------- 버튼 응답 ----------

def test_answer_callback_posts_the_query_id(token, calls):
    telegram.answer_callback("q-1", "확인했습니다")

    method, payload = calls[0]
    assert method == "answerCallbackQuery"
    assert payload["callback_query_id"] == "q-1"
    assert payload["text"] == "확인했습니다"


def test_answer_callback_swallows_failures(token, monkeypatch):
    def boom(method, payload):
        raise requests.RequestException("network down")

    monkeypatch.setattr(telegram, "_api", boom)

    telegram.answer_callback("q-1", "확인했습니다")  # 예외가 나오면 실패


def test_edit_message_text_swallows_failures(token, monkeypatch):
    def boom(method, payload):
        raise requests.RequestException("network down")

    monkeypatch.setattr(telegram, "_api", boom)

    telegram.edit_message_text(999, 555, "처리됨")  # 예외가 나오면 실패


# ---------- HTTP 연결 재사용 ----------

def test_api_calls_go_through_one_reused_session():
    """매 호출마다 새로 붙으면 DNS+TLS 핸드셰이크를 계속 다시 문다.

    실측(2026-08-22, api.telegram.org): 첫 호출 733~767ms, 이후 234~247ms —
    차이 약 500ms 가 핸드셰이크다.

    ⚠️ 한때 이 재사용이 폴링 지연("maximum number of running instances reached")의
    해법이라고 적어 두었으나 **틀린 진단이었다.** 세션을 재사용해도 지연은 그대로였고,
    진짜 원인은 getUpdates 의 3초 서버 대기였다
    (services/telegram_bot.py 의 MIN_POLL_GAP_SEC 주석). 재사용은 500ms 를 아끼므로
    그대로 두지만, 지키는 이유가 다르다.
    """
    assert isinstance(telegram._session, requests.Session)


def test_real_api_posts_through_the_session(token, monkeypatch):
    posted = {}

    def fake_post(url, json=None, timeout=None):
        posted["url"] = url
        raise requests.RequestException("stop here — 실제로 나가지 않게")

    # conftest 전역 가드가 _api 를 대역으로 바꿔 두므로 실제 경로를 되돌린다.
    # 나가는 것은 _session.post 에서 막으므로 진짜 HTTP 는 여전히 없다.
    monkeypatch.setattr(telegram, "_api", telegram._real_api)
    monkeypatch.setattr(telegram._session, "post", fake_post)

    telegram.send_message(999, "불이야")  # 예외는 래퍼가 삼킨다

    assert posted["url"].endswith("/sendMessage")


# ---------- 롱폴링 클라이언트 타임아웃 ----------
# 롱폴링은 서버가 응답을 timeout 초 동안 붙잡고 있는 방식이다. 클라이언트 타임아웃이
# 그보다 짧으면 폴링이 매번 ReadTimeout 으로 끝나 업데이트를 영영 못 받는다 —
# 그것도 예외를 삼키는 _call 뒤에서 조용히. 아래 세 개가 그 조합을 막는다.

def test_short_poll_uses_the_plain_http_timeout(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_HTTP_TIMEOUT_SEC", 5.0)

    assert telegram._http_timeout({"chat_id": 1, "text": "불이야"}) == 5.0
    assert telegram._http_timeout({"offset": 1, "timeout": 0}) == 5.0


def test_long_poll_http_timeout_outlives_the_server_hold(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_HTTP_TIMEOUT_SEC", 5.0)

    assert telegram._http_timeout({"offset": 1, "timeout": 25}) > 25


def test_long_poll_gets_the_longer_timeout_all_the_way_down_to_the_socket(token, monkeypatch):
    """_http_timeout 이 맞아도 _real_api 가 안 쓰면 소용이 없다."""
    posted = {}

    def fake_post(url, json=None, timeout=None):
        posted["timeout"] = timeout
        raise requests.RequestException("stop here — 실제로 나가지 않게")

    monkeypatch.setattr(telegram, "_api", telegram._real_api)
    monkeypatch.setattr(telegram._session, "post", fake_post)

    telegram.get_updates(offset=1, timeout_sec=25)

    assert posted["timeout"] > 25
