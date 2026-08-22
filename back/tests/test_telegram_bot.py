"""텔레그램 봇 워커 — 앱 의미를 아는 층.

여기가 하는 일은 둘이다.
  1) 연동: 사용자가 딥링크로 보낸 `/start <코드>` 를 받아 chat_id 를 사용자에 붙인다.
  2) 응답: 알림에 붙인 인라인 버튼을 누르면 alert_respond.respond 를 부른다.

지켜야 할 성질: **한 업데이트의 실패가 폴링 전체를 멈추면 안 된다.** 멈추면 그 뒤의
모든 버튼 응답이 사라지고, 사용자는 취소를 눌렀는데 119 가 나가는 상황이 된다.
"""
import threading
import time

import pytest

import config
import db
from services import telegram, telegram_bot, telegram_link
from tests.conftest import make_alert, make_event


@pytest.fixture()
def token(monkeypatch):
    import config
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "12345:TESTTOKEN")


@pytest.fixture()
def sent(monkeypatch):
    """봇이 내보낸 메시지·토스트를 기록한다."""
    outbox = []
    monkeypatch.setattr(telegram, "send_message",
                        lambda chat_id, text, buttons=None:
                            outbox.append(("send", chat_id, text, buttons)) or True)
    monkeypatch.setattr(telegram, "answer_callback",
                        lambda qid, text: outbox.append(("toast", qid, text, None)))
    monkeypatch.setattr(telegram, "edit_message_text",
                        lambda chat_id, mid, text: outbox.append(("edit", chat_id, text, None)))
    return outbox


def _chat_id_of(user_no):
    return db.query_one("SELECT user_telegram_chat_id AS c FROM users WHERE user_no = %s",
                        (user_no,))["c"]


def _link(user_no, chat_id):
    db.execute("UPDATE users SET user_telegram_chat_id = %s WHERE user_no = %s",
               (chat_id, user_no))


def _message(text, chat_id=555):
    return {"update_id": 1, "message": {"chat": {"id": chat_id}, "text": text}}


def _button_press(data, chat_id=555, qid="q-1"):
    return {"update_id": 2,
            "callback_query": {"id": qid, "data": data,
                               "message": {"chat": {"id": chat_id}, "message_id": 77}}}


# ---------- 알림에 붙는 버튼 ----------

def test_alert_buttons_carry_both_actions():
    buttons = telegram_bot.build_alert_buttons(12)

    data = [b["callback_data"] for row in buttons for b in row]
    assert "resp:12:READ" in data
    assert "resp:12:CANCEL" in data


def test_callback_data_fits_the_telegram_64_byte_limit():
    buttons = telegram_bot.build_alert_buttons(9_999_999_999)

    for row in buttons:
        for b in row:
            assert len(b["callback_data"].encode()) <= 64


# ---------- 연동 (/start) ----------

def test_start_with_a_valid_code_links_the_chat(sent):
    code = telegram_link.issue_code(1)

    telegram_bot.handle_update(_message(f"/start {code}", chat_id=555))

    assert _chat_id_of(1) == 555


def test_start_with_a_valid_code_confirms_to_the_user(sent):
    code = telegram_link.issue_code(1)

    telegram_bot.handle_update(_message(f"/start {code}", chat_id=555))

    assert any(kind == "send" and chat == 555 for kind, chat, _, _ in sent)


def test_start_with_a_bad_code_does_not_link(sent):
    telegram_bot.handle_update(_message("/start 1-BOGUSCODE", chat_id=555))

    assert _chat_id_of(1) is None
    assert sent, "안내 메시지는 보내야 한다"


def test_bare_start_does_not_link_and_explains(sent):
    telegram_bot.handle_update(_message("/start", chat_id=555))

    assert _chat_id_of(1) is None
    assert sent


def test_relinking_moves_the_chat_to_the_new_user(sent):
    """같은 텔레그램 계정을 다른 사용자로 다시 연동하면 이전 연결은 풀린다.

    chat_id 는 유니크다 — 옮기지 않고 그냥 넣으면 유니크 위반으로 터진다.
    """
    _link(1, 555)
    code = telegram_link.issue_code(2)

    telegram_bot.handle_update(_message(f"/start {code}", chat_id=555))

    assert _chat_id_of(1) is None
    assert _chat_id_of(2) == 555


def test_stop_unlinks_the_chat(sent):
    _link(1, 555)

    telegram_bot.handle_update(_message("/stop", chat_id=555))

    assert _chat_id_of(1) is None


# ---------- 버튼 응답 ----------

def test_pressing_confirm_marks_the_alert_read(sent):
    _link(1, 555)
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1)

    telegram_bot.handle_update(_button_press(f"resp:{alert_no}:READ", chat_id=555))

    row = db.query_one("SELECT alert_status FROM alert WHERE alert_no = %s", (alert_no,))
    assert row["alert_status"] == "READ"


def test_pressing_cancel_marks_the_alert_canceled(sent):
    _link(1, 555)
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1)

    telegram_bot.handle_update(_button_press(f"resp:{alert_no}:CANCEL", chat_id=555))

    row = db.query_one("SELECT alert_status FROM alert WHERE alert_no = %s", (alert_no,))
    assert row["alert_status"] == "CANCELED"


def test_press_from_an_unlinked_chat_changes_nothing(sent):
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1)

    telegram_bot.handle_update(_button_press(f"resp:{alert_no}:READ", chat_id=999))

    row = db.query_one("SELECT alert_status FROM alert WHERE alert_no = %s", (alert_no,))
    assert row["alert_status"] == "SENT"


def test_press_on_someone_elses_alert_changes_nothing(sent):
    """2번 사용자의 텔레그램에서 1번 사용자의 알림 번호를 눌러도 통하지 않아야 한다."""
    _link(2, 555)
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1)

    telegram_bot.handle_update(_button_press(f"resp:{alert_no}:READ", chat_id=555))

    row = db.query_one("SELECT alert_status FROM alert WHERE alert_no = %s", (alert_no,))
    assert row["alert_status"] == "SENT"


def test_press_reports_the_reason_back_as_a_toast(sent):
    """이미 응답한 알림을 또 누르면 이유가 사용자에게 보여야 한다."""
    _link(1, 555)
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1, responded=True)

    telegram_bot.handle_update(_button_press(f"resp:{alert_no}:READ", chat_id=555))

    toasts = [text for kind, _, text, _ in sent if kind == "toast"]
    assert any("이미 응답" in t for t in toasts)


@pytest.mark.parametrize("data", ["", "resp", "resp:x:READ", "resp:1", "nope:1:READ",
                                  "resp:1:DELETE", "resp:1:READ:extra"])
def test_malformed_callback_data_is_ignored_without_raising(sent, data):
    _link(1, 555)

    telegram_bot.handle_update(_button_press(data, chat_id=555))  # 예외가 나오면 실패


def test_unknown_update_shape_is_ignored_without_raising(sent):
    telegram_bot.handle_update({"update_id": 3, "edited_message": {"weird": True}})


# ---------- 폴링 틱 ----------

def test_tick_advances_the_offset_past_processed_updates(token, monkeypatch, sent):
    batches = [[{"update_id": 41, "message": {"chat": {"id": 555}, "text": "hi"}},
                {"update_id": 42, "message": {"chat": {"id": 555}, "text": "hi"}}],
               []]
    asked = []

    def fake_get_updates(offset, timeout_sec=0):
        asked.append(offset)
        return batches.pop(0) if batches else []

    monkeypatch.setattr(telegram, "get_updates", fake_get_updates)

    telegram_bot.run_telegram_tick()
    telegram_bot.run_telegram_tick()

    # 두 번째 틱은 마지막 update_id + 1 부터 물어봐야 한다 (같은 것을 또 받지 않게)
    assert asked[1] == 43


def test_tick_keeps_going_when_one_update_blows_up(token, monkeypatch, sent):
    """한 건이 터져도 오프셋은 넘어가야 한다 — 아니면 그 자리에서 영영 막힌다."""
    def boom(update):
        raise RuntimeError("bad update")

    monkeypatch.setattr(telegram_bot, "handle_update", boom)
    monkeypatch.setattr(telegram, "get_updates",
                        lambda offset, timeout_sec=0:
                            [{"update_id": 7}] if offset == 0 else [])

    summary = telegram_bot.run_telegram_tick()

    assert summary["failed"] == 1
    assert telegram_bot.run_telegram_tick()["received"] == 0


def test_tick_does_nothing_when_the_bot_is_not_configured(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    called = []
    monkeypatch.setattr(telegram, "get_updates",
                        lambda offset, timeout_sec=0: called.append(offset) or [])

    assert telegram_bot.run_telegram_tick() == {"received": 0, "failed": 0}
    assert called == []


def test_tick_hands_the_long_poll_timeout_to_the_api(token, monkeypatch, sent):
    """틱이 timeout 을 안 넘기면 짧은 폴링으로 돌아간다 — 3초 바닥에 다시 걸린다."""
    seen = {}

    def fake_get_updates(offset, timeout_sec=0):
        seen["timeout_sec"] = timeout_sec
        return []

    monkeypatch.setattr(telegram, "get_updates", fake_get_updates)

    telegram_bot.run_telegram_tick(25)

    assert seen["timeout_sec"] == 25


# ---------- 폴링 루프 ----------
# 텔레그램 폴링은 APScheduler 잡이 아니라 전용 데몬 스레드에서 롱폴링으로 돈다.
#
# **왜 바꿨나** (2026-08-22 실측). getUpdates 는 직전 요청과 3.0초 안에 붙으면
# 서버가 그 요청을 정확히 3.000초 붙잡았다가 빈 배열로 돌려준다 (간격 2.74초 →
# 두 번에 한 번 걸림, 3.04초 → 0/5회). 그래서 2초 간격 잡은 매 틱이 자기 주기를
# 넘겼고 APScheduler 가 `skipped: maximum number of running instances reached (1)`
# 를 계속 찍었다 — 주기를 어떻게 짜도 코드로는 못 맞추는 값이었다.
# 롱폴링은 이 바닥에 닿지 않는다 (timeout=25 연속 4회, 매번 정확히 25.00초).


def _run_loop(monkeypatch, summaries, gap=0.15):
    """_poll_loop 를 스레드 없이 그 자리에서 돌리고 각 틱의 시작 시각을 돌려준다.

    summaries 를 다 쓰면 중단 신호를 걸어 루프를 세운다.
    """
    monkeypatch.setattr(telegram_bot, "MIN_POLL_GAP_SEC", gap)
    stop = threading.Event()
    starts = []
    queue = list(summaries)

    def fake_tick(timeout_sec=0):
        starts.append(time.monotonic())
        if not queue:
            stop.set()
            return {"received": 0, "failed": 0}
        return queue.pop(0)

    monkeypatch.setattr(telegram_bot, "run_telegram_tick", fake_tick)
    telegram_bot._poll_loop(stop)
    return starts


def _gaps(starts):
    return [b - a for a, b in zip(starts, starts[1:])]


def test_loop_waits_the_floor_when_a_tick_comes_back_empty(monkeypatch):
    """즉시 빈손으로 돌아오면 최소 간격만큼 쉬어야 한다.

    정상 롱폴링은 25초를 기다렸다 오므로 여기 걸리지 않는다. 이 대기가 실제로
    쓰이는 건 Conflict·망 단절·토큰 폐기처럼 호출이 곧바로 실패로 되돌아오는
    경우고, 없으면 루프가 초당 수백 번 재시도하며 로그를 태운다.
    """
    starts = _run_loop(monkeypatch, [{"received": 0, "failed": 0}] * 2, gap=0.15)

    assert len(starts) == 3
    assert all(g >= 0.15 * 0.9 for g in _gaps(starts)), _gaps(starts)


def test_loop_does_not_wait_after_receiving_updates(monkeypatch):
    """받은 게 있으면 곧바로 다음 롱폴링으로 간다 — 연속으로 누른 버튼이 밀리면 안 된다."""
    starts = _run_loop(monkeypatch, [{"received": 2, "failed": 0}] * 2, gap=0.15)

    assert len(starts) == 3
    assert all(g < 0.15 * 0.5 for g in _gaps(starts)), _gaps(starts)


def test_loop_keeps_going_when_a_tick_raises(monkeypatch):
    """루프가 죽으면 그 뒤의 모든 버튼 응답이 사라진다 — 오탐에도 119 가 나간다."""
    monkeypatch.setattr(telegram_bot, "MIN_POLL_GAP_SEC", 0.01)
    stop = threading.Event()
    calls = []

    def boom(timeout_sec=0):
        calls.append(timeout_sec)
        if len(calls) >= 3:
            stop.set()
        raise RuntimeError("폴링이 통째로 터졌다")

    monkeypatch.setattr(telegram_bot, "run_telegram_tick", boom)

    telegram_bot._poll_loop(stop)  # 예외가 새어 나오면 실패

    assert len(calls) == 3


# ---------- 폴링 스레드 ----------

@pytest.fixture()
def idle_poller(monkeypatch):
    """폴링 스레드를 띄워도 밖으로 나가지 않게 만든다. 끝나면 반드시 세운다.

    세우지 않고 두면 monkeypatch 가 풀린 뒤 스레드가 진짜 api.telegram.org 로
    나가고, 뒤따르는 테스트와 getUpdates 소비권을 다툰다.
    """
    asked = []
    monkeypatch.setattr(telegram_bot, "run_telegram_tick",
                        lambda timeout_sec=0: asked.append(timeout_sec)
                        or {"received": 0, "failed": 0})
    monkeypatch.setattr(telegram_bot, "MIN_POLL_GAP_SEC", 0.02)
    yield asked
    telegram_bot.stop_polling()


def test_start_polling_runs_exactly_one_thread_per_process(token, idle_poller):
    """두 벌이 돌면 업데이트가 둘로 갈리거나 서로를 Conflict 로 끊는다.

    그러면 유예 안에 '오탐 취소'를 못 받고, 그건 오탐에도 119 가 나간다는 뜻이다.
    """
    assert telegram_bot.start_polling() is True
    thread = telegram_bot._poll_thread

    assert telegram_bot.start_polling() is False
    assert telegram_bot._poll_thread is thread
    assert telegram_bot.is_polling() is True


def test_start_polling_does_nothing_without_a_token(monkeypatch, idle_poller):
    """토큰이 없으면 아예 안 띄운다 — 돌려 봐야 실패 로그만 쌓인다."""
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")

    assert telegram_bot.start_polling() is False
    assert telegram_bot.is_polling() is False


def test_start_polling_starts_again_after_the_thread_stopped(token, idle_poller):
    """가드 기준이 '이미 띄웠나'면 죽은 스레드를 물려받아 폴링이 통째로 멎는다."""
    telegram_bot.start_polling()
    telegram_bot.stop_polling()
    assert telegram_bot.is_polling() is False

    assert telegram_bot.start_polling() is True


def test_the_polling_thread_is_a_daemon(token, idle_poller):
    """비데몬이면 종료가 롱폴링(최대 25초)만큼 멈춰 Ctrl+C 가 한 번에 안 먹는다."""
    telegram_bot.start_polling()

    assert telegram_bot._poll_thread.daemon is True


def test_the_polling_thread_uses_long_polling(token, idle_poller):
    telegram_bot.start_polling()

    deadline = time.monotonic() + 2.0
    while not idle_poller and time.monotonic() < deadline:
        time.sleep(0.01)

    assert idle_poller, "폴링 스레드가 틱을 한 번도 돌리지 않았다"
    assert idle_poller[0] == config.TELEGRAM_LONG_POLL_SEC
