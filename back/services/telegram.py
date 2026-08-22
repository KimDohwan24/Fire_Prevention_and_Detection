"""텔레그램 Bot API 래퍼 — 전송 계층.

여기는 **앱 의미를 모른다.** 어떤 버튼을 붙일지, 콜백 문자열을 어떻게 해석할지는
services/telegram_bot.py 몫이다. 이 모듈이 지키는 성질은 하나다:

    어떤 실패에서도 예외를 밖으로 흘리지 않는다.

알림 발송 실패가 알림 행 생성을 막으면 안 되고(services/alert_service.py),
폴링 실패가 워커를 죽이면 그 뒤의 모든 버튼 응답이 사라지기 때문이다.
실패는 전부 반환값(False / [])과 로그로만 알린다.

토큰이 비어 있으면 모든 함수가 HTTP 없이 즉시 실패값을 돌려준다 — 토큰을 넣지 않은
팀원 환경에서도 서버는 그대로 뜨고 알림은 기존 모의 SMS 로만 나간다.
"""
import logging

import requests

import config

logger = logging.getLogger("fireguard.telegram")

API_BASE = "https://api.telegram.org"

# 연결을 재사용한다. 2026-08-22 실측(api.telegram.org): 첫 호출은 733~767ms 인데
# 그 뒤로는 234~247ms 로 안정적이다 — 차이 약 500ms 가 DNS+TLS 핸드셰이크 값이다.
# 매 호출마다 새로 붙으면 그만큼을 계속 다시 문다.
#
# ⚠️ 한때 이 재사용이 폴링 지연(APScheduler 의 "maximum number of running instances
#    reached")의 해법이라고 적어 두었으나 **틀린 진단이었다.** 세션을 재사용해도
#    지연은 그대로였고, 진짜 원인은 getUpdates 쪽의 서버 대기였다
#    (services/telegram_bot.py 의 MIN_POLL_GAP_SEC 주석에 실측값이 있다).
#    재사용 자체는 500ms 를 아끼므로 그대로 두지만, 이유를 바꿔 적는다.
#
# 여러 스레드가 같이 쓴다 — requests.Session 은 이 용도로 안전하다.
_session = requests.Session()


def is_enabled() -> bool:
    """봇 토큰이 설정돼 있나. 매번 config 를 다시 본다 (테스트가 갈아끼운다)."""
    return bool(config.TELEGRAM_BOT_TOKEN)


def _http_timeout(payload: dict) -> float:
    """이 호출에 줄 클라이언트 타임아웃(초).

    getUpdates 의 payload["timeout"] 은 **텔레그램 서버가 응답을 붙잡고 기다려 주는
    시간**이다(롱폴링). 클라이언트 타임아웃이 그보다 짧으면 폴링이 매번 ReadTimeout
    으로 끝나 업데이트를 영영 못 받는다 — 그것도 조용히, 예외를 삼키는 _call 뒤에서.
    그래서 롱폴링일 때는 서버 대기시간에 여유분을 얹는다.

    여유분으로 TELEGRAM_HTTP_TIMEOUT_SEC 를 그대로 쓴다. 그 값의 뜻이 원래
    '망이 이 정도까지 느려지는 건 봐준다'이고, 여기서 필요한 것도 정확히 그 값이기
    때문이다 (실측 왕복은 235ms 라 5초면 20배 여유다).
    payload 에 timeout 을 싣는 메서드는 getUpdates 뿐이라 다른 호출에는 영향이 없다.
    """
    server_hold = float(payload.get("timeout") or 0)
    if server_hold <= 0:
        return config.TELEGRAM_HTTP_TIMEOUT_SEC
    return server_hold + config.TELEGRAM_HTTP_TIMEOUT_SEC


def _real_api(method: str, payload: dict) -> dict | None:
    resp = _session.post(
        f"{API_BASE}/bot{config.TELEGRAM_BOT_TOKEN}/{method}",
        json=payload,
        timeout=_http_timeout(payload),
    )
    return resp.json()


def _api(method: str, payload: dict) -> dict | None:
    """Bot API 호출 1회. 테스트에서 monkeypatch 하는 지점."""
    return _real_api(method, payload)


def _call(method: str, payload: dict) -> dict | None:
    """_api 를 부르되 실패를 전부 삼키고 성공 응답의 result 만 돌려준다.

    반환: 성공이면 result(어떤 타입이든), 실패면 None.
    """
    if not is_enabled():
        return None
    try:
        body = _api(method, payload)
    except Exception:
        # 망 단절·타임아웃·JSON 파싱 실패 등 — 무엇이든 여기서 끝낸다
        logger.warning("텔레그램 %s 호출 실패", method, exc_info=True)
        return None

    if not isinstance(body, dict) or not body.get("ok"):
        # 봇 차단·잘못된 chat_id 등. 텔레그램이 이유를 description 에 담아 준다
        desc = body.get("description") if isinstance(body, dict) else body
        logger.warning("텔레그램 %s 거부됨: %s", method, desc)
        return None
    return body.get("result")


def send_message(chat_id, text: str, buttons: list | None = None) -> bool:
    """메시지 1건 발송. buttons 를 주면 인라인 키보드로 붙인다.

    buttons 는 텔레그램 inline_keyboard 형식 그대로 — 행의 리스트, 각 행은 버튼의
    리스트다. 예: [[{"text": "화재 확인", "callback_data": "resp:12:READ"}]]
    """
    payload = {"chat_id": chat_id, "text": text}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    return _call("sendMessage", payload) is not None


def get_updates(offset: int, timeout_sec: int = 0) -> list[dict]:
    """offset 이후의 업데이트를 받아온다. 실패하면 빈 리스트.

    **offset 은 '어디부터 줘'가 아니라 확인응답이다.** 텔레그램은 offset 미만의
    업데이트를 처리 완료로 보고 다시 주지 않는다. 그래서 처리한 건은 반드시 넘겨야
    하고(안 넘기면 같은 건을 영원히 다시 받는다), 넘기면 되돌릴 수 없다.
    오프셋을 관리하는 쪽은 services/telegram_bot.py 다.

    timeout_sec 은 **서버가 응답을 붙잡고 기다려 줄 시간**이다.
      - 0  = 즉시 반환(짧은 폴링). ⚠️ 겉보기와 달리 '항상 즉시'가 아니다 —
             직전 요청과 3초 안에 붙으면 서버가 정확히 3초를 붙잡는다(실측).
             그래서 짧은 폴링으로는 3초보다 촘촘하게 돌 수 없다.
      - >0 = 롱폴링. 업데이트가 생길 때까지 서버가 붙잡고 있다가 돌려준다.
    실측값과 그 선택의 근거는 services/telegram_bot.py 의 MIN_POLL_GAP_SEC 주석에 있다.

    기본값이 0 인 것은 이 함수만 따로 부르는 호출부·테스트를 위한 것이고,
    실제 폴링 루프는 config.TELEGRAM_LONG_POLL_SEC 를 넘겨 롱폴링으로 쓴다.
    """
    result = _call("getUpdates", {"offset": offset, "timeout": timeout_sec})
    return result if isinstance(result, list) else []


def answer_callback(callback_query_id: str, text: str) -> None:
    """버튼을 누른 사용자에게 짧은 토스트를 띄운다.

    이걸 보내지 않으면 텔레그램 클라이언트에 로딩 표시가 한동안 남는다.
    실패해도 본 처리(응답 기록)는 이미 끝난 뒤라 무시한다.
    """
    _call("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})


def edit_message_text(chat_id, message_id, text: str) -> None:
    """이미 보낸 메시지의 본문을 갈아끼운다 (버튼도 같이 사라진다).

    버튼을 누른 뒤 "처리됨"으로 바꿔 두면 같은 알림을 두 번 누르는 일이 줄어든다.
    실패해도 본 처리에는 영향이 없다.
    """
    _call("editMessageText",
          {"chat_id": chat_id, "message_id": message_id, "text": text})
