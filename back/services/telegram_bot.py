"""텔레그램 봇 워커 — 앱 의미를 아는 층.

전송 계층(services/telegram.py)은 텔레그램 API 만 알고, 여기가 우리 도메인을 안다.

하는 일은 둘이다.
  1) **연동**: 사용자가 마이페이지 딥링크로 보낸 `/start <코드>` 를 받아 chat_id 를
     사용자 행에 붙인다. 코드 검증은 services/telegram_link.py (저장 없는 HMAC).
  2) **응답**: 화재 알림에 붙인 인라인 버튼을 누르면 services/alert_respond.respond 를
     부른다 — 웹 화면의 POST /api/alerts/<no>/respond 와 **같은 함수**다.

**인증은 chat_id 로 한다.** 버튼을 누른 사람이 누구인지는 텔레그램이 알려주는
chat_id 로만 결정하고, 콜백 문자열에 실려 온 값은 믿지 않는다. 콜백에는 alert_no 가
들어 있지만 그건 '어떤 알림'일 뿐이고 '누구'가 아니다 — 소유자 검사는 respond 안에서
user_no 로 다시 한다. 그래서 남의 알림 번호를 눌러도 통하지 않는다
(tests/test_telegram_bot.py::test_press_on_someone_elses_alert_changes_nothing).

**한 업데이트의 실패가 폴링을 멈추면 안 된다.** 멈추면 그 뒤의 모든 버튼 응답이
사라지고, 사용자는 취소를 눌렀는데 119 가 나가는 상황이 된다. 그래서 각 업데이트를
개별 try/except 로 감싸고, 실패해도 오프셋은 넘긴다 (escalation.py 와 같은 판단).
"""
import logging
import threading
import time

import config
import db
from errors import ApiError
from services import alert_respond, telegram, telegram_link

logger = logging.getLogger("fireguard.telegram")

# 콜백 문자열 형식: "resp:<alert_no>:<ACTION>" (텔레그램 제한 64바이트 안)
CALLBACK_PREFIX = "resp"

# 다음에 받아올 업데이트 번호. 텔레그램은 offset 미만을 확인 처리한 것으로 보고
# 다시 주지 않는다 — 그래서 처리한 건 반드시 넘겨야 하고, 실패한 건도 넘겨야 한다
# (안 넘기면 같은 건에서 영영 막힌다).
_offset = 0


def reset_offset() -> None:
    """폴링 위치를 처음으로 되돌린다 (테스트에서 쓴다)."""
    global _offset
    _offset = 0


# ---------- 알림에 붙는 버튼 ----------

def build_alert_buttons(alert_no: int) -> list:
    """화재 알림에 붙일 인라인 키보드.

    두 버튼이 곧 유예(ALERT_DEADLINE_SEC) 안의 두 갈래다 — 확인하면 즉시 119 신고,
    오탐이면 취소. 아무것도 누르지 않으면 무응답으로 119 가 나간다.
    """
    return [[
        {"text": "🔥 화재 확인 — 119 신고", "callback_data": f"{CALLBACK_PREFIX}:{alert_no}:READ"},
        {"text": "✅ 오탐 — 신고 취소", "callback_data": f"{CALLBACK_PREFIX}:{alert_no}:CANCEL"},
    ]]


def _parse_callback(data) -> tuple[int, str] | None:
    """"resp:12:READ" → (12, "READ"). 형식이 어긋나면 None."""
    parts = str(data or "").split(":")
    if len(parts) != 3 or parts[0] != CALLBACK_PREFIX:
        return None
    try:
        alert_no = int(parts[1])
    except ValueError:
        return None
    if parts[2] not in alert_respond.ACTIONS:
        return None
    return alert_no, parts[2]


# ---------- 사용자 ↔ 대화방 ----------

def _user_by_chat(chat_id) -> int | None:
    """이 대화방에 연동된 활성 사용자. 미연동이거나 정지/탈퇴면 None."""
    row = db.query_one(
        "SELECT user_no FROM users "
        "WHERE user_telegram_chat_id = %s AND user_status = 'ACTIVE'",
        (chat_id,),
    )
    return row["user_no"] if row else None


def _link_chat(user_no: int, chat_id) -> dict | None:
    """대화방을 사용자에게 붙인다. 붙인 사용자 행, 대상이 없으면 None.

    같은 대화방이 다른 사용자에게 붙어 있으면 **떼어 와서** 붙인다. chat_id 는
    유니크라 그냥 넣으면 위반으로 터진다. 뺏기는 쪽이 위험해 보이지만, 그러려면
    상대의 마이페이지에서만 나오는 유효 코드가 필요하므로 남이 할 수 있는 일이 아니다.
    """
    user = db.query_one(
        "SELECT user_no, user_name FROM users "
        "WHERE user_no = %s AND user_status = 'ACTIVE'",
        (user_no,),
    )
    if not user:
        return None
    with db.get_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET user_telegram_chat_id = NULL "
                    "WHERE user_telegram_chat_id = %s", (chat_id,))
        cur.execute("UPDATE users SET user_telegram_chat_id = %s WHERE user_no = %s",
                    (chat_id, user_no))
    return dict(user)


def unlink_chat(chat_id) -> int:
    """대화방 연동을 푼다. 반환: 풀린 행 수."""
    return db.execute("UPDATE users SET user_telegram_chat_id = NULL "
                      "WHERE user_telegram_chat_id = %s", (chat_id,))


# ---------- 업데이트 처리 ----------

_HELP = ("파이어가드 화재 알림 봇입니다.\n\n"
         "연동하려면 웹 마이페이지의 '텔레그램 연동' 버튼을 눌러 주세요.\n"
         "연동을 끊으려면 /stop 을 보내세요.")


def _handle_message(message: dict) -> None:
    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()
    if chat_id is None:
        return

    if text == "/stop":
        unlink_chat(chat_id)
        telegram.send_message(chat_id, "연동을 끊었습니다. 이제 화재 알림이 가지 않습니다.")
        return

    if text.startswith("/start"):
        payload = text[len("/start"):].strip()
        user_no = telegram_link.verify_code(payload)
        user = _link_chat(user_no, chat_id) if user_no else None
        if user:
            telegram.send_message(
                chat_id,
                f"{user['user_name']}님, 연동됐습니다.\n"
                f"이제 화재가 확정되면 여기로 알림이 오고, 알림에 붙은 버튼으로 "
                f"바로 '화재 확인'이나 '오탐 취소'를 하실 수 있습니다.",
            )
        else:
            telegram.send_message(
                chat_id,
                "연동 코드가 유효하지 않거나 만료됐습니다(5분).\n"
                "마이페이지에서 연동 버튼을 다시 눌러 주세요.",
            )
        return

    telegram.send_message(chat_id, _HELP)


def _handle_callback(query: dict) -> None:
    query_id = query.get("id")
    message = query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")

    parsed = _parse_callback(query.get("data"))
    if parsed is None:
        telegram.answer_callback(query_id, "알 수 없는 버튼입니다.")
        return
    alert_no, action = parsed

    # 누른 사람은 chat_id 로만 정한다 — 콜백에 실려 온 값은 신원이 아니다
    user_no = _user_by_chat(chat_id)
    if user_no is None:
        telegram.answer_callback(query_id, "연동되지 않은 대화방입니다. 마이페이지에서 연동해 주세요.")
        return

    try:
        alert_respond.respond(alert_no, user_no, action)
    except ApiError as e:
        # 웹 화면과 같은 문구를 그대로 쓴다 (이미 응답함·유예 지남·남의 알림 등)
        telegram.answer_callback(query_id, e.message)
        return

    done = "화재로 확인했습니다 — 119 신고를 시작합니다." if action == "READ" \
        else "오탐으로 처리했습니다 — 119 신고를 취소했습니다."
    telegram.answer_callback(query_id, done)
    if message_id is not None:
        _show_outcome(chat_id, message_id, message, done)


def _show_outcome(chat_id, message_id, message: dict, done: str) -> None:
    """응답 결과를 원문 끝에 붙이고 버튼을 걷어낸다.

    **토스트만으로는 부족하다.** answer_callback 은 잠깐 떴다 사라져서 놓치기 쉽고,
    남아 있는 버튼이 "아직 아무 일도 안 일어났다"로 읽힌다. 그래서 메시지 자체를
    바꿔 흔적을 남긴다.

    갱신 방법이 메시지 종류마다 다르다. 사진으로 나간 알림은 본문이 caption 이라
    editMessageText 가 거절당하고(services/telegram.py 의 edit_message_caption 주석),
    거절당하면 버튼이 남아 사용자가 다시 누르게 된다. 그래서 caption 이 있으면
    캡션을, 없으면 본문을 고친다.
    """
    caption = message.get("caption")
    if caption is not None:
        telegram.edit_message_caption(chat_id, message_id, f"{caption}\n\n▶ {done}")
    else:
        telegram.edit_message_text(chat_id, message_id,
                                   f"{message.get('text', '')}\n\n▶ {done}")


def handle_update(update: dict) -> None:
    """업데이트 1건 처리. 우리가 모르는 종류는 조용히 흘린다."""
    if "message" in update:
        _handle_message(update["message"])
    elif "callback_query" in update:
        _handle_callback(update["callback_query"])


def run_telegram_tick(timeout_sec: int = 0) -> dict:
    """폴링 1회. timeout_sec 만큼 서버가 붙잡고 기다려 준다(롱폴링).

    반환: {"received": n, "failed": n}

    기본값 0(짧은 폴링)은 이 함수를 한 번만 불러 보고 싶은 호출부·테스트를 위한
    것이다. 실제 서버의 폴링 루프(_poll_loop)는 TELEGRAM_LONG_POLL_SEC 를 넘긴다.
    """
    global _offset
    summary = {"received": 0, "failed": 0}
    if not telegram.is_enabled():
        return summary

    for update in telegram.get_updates(_offset, timeout_sec):
        summary["received"] += 1
        # 오프셋을 **먼저** 넘긴다 — 처리에 실패해도 같은 건을 무한히 다시 받지 않게
        _offset = max(_offset, int(update.get("update_id", 0)) + 1)
        try:
            handle_update(update)
        except Exception:
            summary["failed"] += 1
            logger.exception("텔레그램 업데이트 처리 실패: %s", update.get("update_id"))

    if any(summary.values()):
        logger.info("텔레그램 폴링 틱: %s", summary)
    return summary


# ---------- 폴링 루프 (전용 스레드) ----------
#
# **왜 APScheduler 잡이 아니라 전용 스레드인가** (2026-08-22, 실측 후 교체).
#
# 원래는 run_telegram_tick 을 timeout=0 짧은 폴링으로 2초짜리 APScheduler 잡에
# 얹어 두었는데, 로그가 `skipped: maximum number of running instances reached (1)`
# 로 계속 더러웠다. 두 번 오진한 뒤(TLS 핸드셰이크 탓, 폴링 중복 기동 탓) 왕복
# 시간을 직접 재서 원인을 잡았다 — 아래 MIN_POLL_GAP_SEC 주석의 3초 바닥이다.
# **2초 주기는 서버가 허용하지 않는 값이라, 잡으로 두는 한 어떤 코드로도 못 맞춘다.**
#
# 남은 선택지는 둘이었다.
#   (가) 잡으로 두고 주기를 4초로 늘린다.
#        - 장점: 스레드 수명·종료 정리를 APScheduler 가 대신 해 준다. 배선이 그대로다.
#        - 버린 이유: 버튼 반응이 여전히 0~4초 늦고, 3초라는 바닥이 텔레그램의
#          문서화되지 않은 동작이라 저쪽이 값을 바꾸면 곧바로 같은 증상으로 돌아온다.
#          무엇보다 아무 일도 없는 동안 4초마다 요청을 계속 쏜다.
#   (나) 롱폴링(timeout=25)을 전용 데몬 스레드에서 돌린다. **택함.**
#        - 버튼 반응이 사실상 즉시가 되고, 유휴 시 요청이 2초당 1회 → 25초당 1회로
#          줄며, 3초 바닥을 아예 건드리지 않아 skipped 로그가 사라진다.
#        - 대가 1(스레드 수명): 아래 start_polling 의 '프로세스당 하나' 가드로 잡는다.
#          스케줄러 잡이 주던 중복 방지를 여기서 직접 하는 셈이다.
#        - 대가 2(종료 정리): daemon=True 라 프로세스가 끝나면 같이 죽는다.
#          stop_polling 주석 참고.
#        - 대가 3(테스트): 잡 등록 여부를 보던 테스트가 스레드를 봐야 한다.
#          run_telegram_tick 을 그대로 남겨 둔 덕에 처리 로직 테스트는 손대지 않았다.
#          루프는 스레드를 띄우지 않고 _poll_loop 를 직접 부르면 검증할 수 있다.
#
# 롱폴링 중에는 스레드가 소켓에서 블록돼 있을 뿐이라 CPU 를 쓰지 않는다. DB 커넥션도
# 업데이트를 실제로 처리할 때만 잡는다(db.py 는 ThreadedConnectionPool 이라 안전).

# 폴링 요청을 이 간격보다 촘촘하게 내보내지 않는다.
#
# 2026-08-22 실측(api.telegram.org, 왕복 235ms 고정): 같은 봇의 getUpdates 요청이
# **직전 요청으로부터 3.0초 안에 도착하면 서버가 그 요청을 정확히 3.000초 붙잡았다가**
# 빈 배열로 돌려준다. 호출 간격을 바꿔 가며 6회씩 재 보면 경계가 딱 떨어진다:
#     간격 2.24초 → 3/5 회 홀드   간격 2.74초 → 3/5 회 홀드   (번갈아 걸린다)
#     간격 3.04초 → 0/5 회        간격 3.24초 → 0/5 회        간격 4.24초 → 0/5 회
# timeout 값과는 무관한 바닥이다 — timeout=1 로 줘도 걸리는 회차는 3초를 채웠다.
#
# 정상 롱폴링은 25초를 기다렸다 오므로 이 바닥에 닿을 일이 없다. 이 값이 실제로
# 쓰이는 건 **호출이 즉시 실패로 되돌아오는 경우**뿐이다 — 토큰 폐기, Conflict,
# 망 단절 등. 그때 이 간격이 없으면 루프가 초당 수백 번 재시도하며 로그를 태운다.
MIN_POLL_GAP_SEC = 3.0

_poll_thread: threading.Thread | None = None
_poll_stop: threading.Event | None = None


def _poll_loop(stop: threading.Event) -> None:
    """중단 신호가 올 때까지 롱폴링을 반복한다."""
    logger.info("텔레그램 롱폴링 시작 (서버 대기 %s초)", config.TELEGRAM_LONG_POLL_SEC)
    while not stop.is_set():
        started = time.monotonic()
        try:
            summary = run_telegram_tick(config.TELEGRAM_LONG_POLL_SEC)
        except Exception:
            # 여기서 죽으면 이후 모든 버튼 응답이 사라진다 — 무엇이든 삼키고 계속 돈다.
            # (run_telegram_tick 이 이미 개별 업데이트를 감싸고 있어 여기까지 오는 건
            #  오프셋 계산처럼 루프 자체가 깨진 경우뿐이다.)
            logger.exception("텔레그램 폴링 루프 오류")
            summary = None

        if summary and summary["received"]:
            # 이 줄이 '롱폴링이 업데이트가 오는 즉시 풀리는가'의 증거다. 값이 매번
            # 25초에 붙어 있으면 서버가 안 깨워 주고 만료로만 돌아오는 것이므로
            # 폴링 방식을 다시 봐야 한다. (조사 시점엔 봇을 쓰는 사람이 없어
            #  업데이트를 만들 수 없었고, 이 한 가지만 실측하지 못했다.)
            logger.info("텔레그램 롱폴링 %.1f초 만에 %d건 수신",
                        time.monotonic() - started, summary["received"])
            # 받은 게 있으면 쉬지 않고 곧바로 다음 롱폴링으로 간다. 연속으로 누른
            # 버튼이 3초씩 밀리면 안 되고, 3초 바닥은 실측상 '빈 응답'에서만 걸렸다.
            continue

        # 빈 응답이나 실패로 돌아온 경우. 롱폴링이 정상이었다면 이미 25초가 지났으므로
        # 아래는 음수가 되어 그냥 지나간다 — 즉 이 대기가 실제로 걸리는 건 실패뿐이다.
        rest = MIN_POLL_GAP_SEC - (time.monotonic() - started)
        if rest > 0:
            stop.wait(rest)
    logger.info("텔레그램 롱폴링 종료")


def start_polling() -> bool:
    """폴링 스레드를 띄운다. **프로세스당 하나만.** 반환: 새로 띄웠으면 True.

    한 벌만 도는 것이 중요한 이유는 app.py 의 스케줄러 가드와 같다 — 텔레그램은
    getUpdates 를 한 소비자에게만 온전히 주므로, 두 벌이 돌면 업데이트가 둘로
    갈리거나 서로를 Conflict 로 끊는다. 그러면 유예 안에 '오탐 취소'를 못 받고,
    그건 오탐에도 119 가 나간다는 뜻이다.

    기준을 '이미 띄웠나'가 아니라 **'지금 살아 있나'**로 잡은 것도 같은 판단이다
    (app.py 의 _start_escalation_scheduler 참고). 죽은 스레드를 살아 있다고 보면
    폴링이 하나도 안 도는데 앱은 멀쩡해 보이는, 가장 나쁜 상태가 된다.
    """
    global _poll_thread, _poll_stop
    # 토큰이 없으면 아예 띄우지 않는다 — 돌려 봐야 매번 실패 로그만 쌓인다.
    # 이때 알림은 기존 모의 SMS 로만 나가고 나머지 경로는 그대로 산다.
    if not telegram.is_enabled():
        return False
    if _poll_thread is not None and _poll_thread.is_alive():
        return False

    _poll_stop = threading.Event()
    _poll_thread = threading.Thread(
        target=_poll_loop, args=(_poll_stop,),
        name="telegram-poll",
        # 데몬으로 두는 이유: 이 스레드는 대부분의 시간을 getUpdates 응답을 기다리며
        # 소켓에 블록된 채로 보낸다. 비데몬이면 인터프리터 종료가 그 대기만큼
        # 멈춰 서고, Ctrl+C 한 번으로 서버가 안 내려간다.
        daemon=True,
    )
    _poll_thread.start()
    return True


def stop_polling(join_sec: float = 0.2) -> None:
    """폴링 스레드에 중단을 알린다.

    **끝까지 기다리지 않는다.** 스레드는 지금 getUpdates 응답을 최대
    TELEGRAM_LONG_POLL_SEC(25초) 동안 기다리며 소켓에 블록돼 있어서, 다 끝나기를
    join 하면 서버 종료가 그만큼 멈춘다. daemon=True 라 프로세스가 끝나면 스레드도
    같이 죽고, 그때 소켓이 닫히면서 텔레그램 쪽 대기도 함께 풀린다.
    join_sec 은 '마침 쉬는 중이라 곧바로 빠져나올 수 있는' 경우만 거둬 주는 여유다.

    프로세스 종료 훅(atexit)에 걸지 않았다. 실제로 대기를 끊는 것은 소켓이 닫히는
    일이고 그건 OS 가 해 주므로, 훅을 걸어도 종료가 join_sec 만큼 늦어질 뿐 얻는 게
    없다. 이 함수는 테스트와 '앱을 띄웠다 내리는' 호출부를 위해 둔다.
    """
    global _poll_thread, _poll_stop
    if _poll_stop is not None:
        _poll_stop.set()
    if _poll_thread is not None:
        _poll_thread.join(timeout=join_sec)
        if not _poll_thread.is_alive():
            _poll_thread = None


def is_polling() -> bool:
    """폴링 스레드가 지금 살아 있나."""
    return _poll_thread is not None and _poll_thread.is_alive()
