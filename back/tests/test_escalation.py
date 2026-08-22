"""무응답 에스컬레이션 스윕 테스트 — services/escalation.py + 스케줄러 배선.

에스컬레이션 정책 (동시 발송 확정 — 단계 승격 없음):
- 확정 시 PUSH/SMS 두 알림이 동시에 나가고 유예는 한 번뿐이다.
- 마감 초과 + 무응답(SENT, responded_at NULL) 알림이 하나라도 있는 이벤트는
  그 이벤트의 미응답 알림 **전부**를 NO_RESPONSE 로 닫고 곧바로 119 신고
  (start_report, trigger 'NO_RESPONSE_TIMEOUT') 로 넘어간다. 2차 SMS 발송 단계는 없다.
- 취소(CANCELED) 알림이 하나라도 있는 이벤트는 절대 에스컬레이션하지 않는다.
- 점검 모드(event_is_test) 이벤트 제외.
- 스윕은 오래된 PENDING 이벤트도 함께 기준미달(DISMISSED) 처리한다.
- 스케줄러는 create_app(start_scheduler=True) 일 때만 뜬다 (테스트 앱은 안 뜸).
"""
from datetime import datetime

from conftest import make_alert, make_alert_pair, make_event

import config
import db
from app import create_app
from services import escalation


def get_alerts(event_no):
    return db.query(
        "SELECT * FROM alert WHERE event_no = %s ORDER BY alert_no", (event_no,)
    )


def get_reports(event_no):
    return db.query(
        "SELECT * FROM report_119 WHERE event_no = %s ORDER BY report_no", (event_no,)
    )


def spy_start_report(monkeypatch):
    """report_service.start_report 를 기록용 스파이로 바꾼다."""
    calls = []
    monkeypatch.setattr(
        "services.report_service.start_report",
        lambda event_no, trigger_reason: calls.append((event_no, trigger_reason)),
    )
    return calls


# ---------- 마감 초과 → 전량 NO_RESPONSE + 119 신고 ----------

def test_overdue_event_marks_all_alerts_no_response_and_reports(monkeypatch):
    """마감 초과 이벤트: PUSH/SMS 두 알림 모두 NO_RESPONSE + 신고 1건 트리거."""
    calls = spy_start_report(monkeypatch)
    event_no = make_event()
    make_alert_pair(event_no, deadline_offset_sec=-10)

    summary = escalation.run_escalation_tick()

    rows = get_alerts(event_no)
    assert len(rows) == 2  # 새 알림을 더 만들지 않는다 (승격 없음)
    assert [r["alert_status"] for r in rows] == ["NO_RESPONSE", "NO_RESPONSE"]
    assert calls == [(event_no, "NO_RESPONSE_TIMEOUT")]
    assert summary["reported"] == 1
    assert "escalated_to_sms" not in summary  # 단계 승격 개념 제거


def test_overdue_event_reports_only_once_per_event(monkeypatch):
    """알림이 2건이어도 신고는 이벤트당 1회만 트리거된다."""
    calls = spy_start_report(monkeypatch)
    event_a = make_event(cctv_no=1)
    event_b = make_event(cctv_no=2)
    make_alert_pair(event_a, deadline_offset_sec=-10)
    make_alert_pair(event_b, deadline_offset_sec=-10)

    summary = escalation.run_escalation_tick()

    assert calls == [(event_a, "NO_RESPONSE_TIMEOUT"), (event_b, "NO_RESPONSE_TIMEOUT")]
    assert summary["reported"] == 2


def test_not_yet_due_alerts_untouched(monkeypatch):
    """마감 전 알림은 건드리지 않는다."""
    calls = spy_start_report(monkeypatch)
    event_no = make_event()
    make_alert_pair(event_no, deadline_offset_sec=180)

    summary = escalation.run_escalation_tick()

    assert [r["alert_status"] for r in get_alerts(event_no)] == ["SENT", "SENT"]
    assert calls == []
    assert summary["reported"] == 0


def test_responded_read_alerts_untouched_no_double_report(monkeypatch):
    """READ(화재 확인) 응답된 알림은 마감이 지났어도 에스컬레이션하지 않는다.

    READ 시점에 respond 라우트가 형제 알림까지 닫고 신고를 이미 시작했으므로,
    에스컬레이션이 또 신고를 트리거하면 안 된다.
    """
    calls = spy_start_report(monkeypatch)
    event_no = make_event()
    make_alert_pair(event_no, status="READ", deadline_offset_sec=-10, responded=True)

    summary = escalation.run_escalation_tick()

    assert [r["alert_status"] for r in get_alerts(event_no)] == ["READ", "READ"]
    assert calls == []  # 에스컬레이션발 신고 없음
    assert summary["reported"] == 0


def test_canceled_event_never_escalates(monkeypatch):
    """CANCELED 알림이 있는 이벤트는 마감 초과 SENT 가 있어도 전부 중단."""
    calls = spy_start_report(monkeypatch)
    event_no = make_event()
    push_no, _ = make_alert_pair(event_no, deadline_offset_sec=-10,
                                 sms_status="CANCELED")

    summary = escalation.run_escalation_tick()

    push = db.query_one("SELECT * FROM alert WHERE alert_no = %s", (push_no,))
    assert push["alert_status"] == "SENT"  # NO_RESPONSE 로 바뀌지 않는다
    assert calls == []
    assert get_reports(event_no) == []
    assert summary["reported"] == 0


def test_test_event_excluded(monkeypatch):
    """점검 모드(event_is_test) 이벤트의 알림은 마감 초과여도 건드리지 않는다."""
    calls = spy_start_report(monkeypatch)
    event_no = make_event(is_test=True)
    make_alert_pair(event_no, deadline_offset_sec=-10)

    summary = escalation.run_escalation_tick()

    assert [r["alert_status"] for r in get_alerts(event_no)] == ["SENT", "SENT"]
    assert calls == []
    assert summary["reported"] == 0


# ---------- 전체 사슬 · 스윕 부수 동작 ----------

def test_full_chain_alerts_to_report():
    """확정 알림 2건 → 유예 초과 → 두 알림 NO_RESPONSE + 119 신고(ACCEPTED)."""
    event_no = make_event()
    make_alert_pair(event_no, deadline_offset_sec=-10)

    summary = escalation.run_escalation_tick()

    rows = get_alerts(event_no)
    assert [r["alert_status"] for r in rows] == ["NO_RESPONSE", "NO_RESPONSE"]
    (report,) = get_reports(event_no)
    assert report["report_status"] == "ACCEPTED"  # conftest HTTP 스텁이 2xx 응답
    assert report["report_trigger_reason"] == "NO_RESPONSE_TIMEOUT"
    assert summary["reported"] == 1


def test_partially_responded_event_closes_remaining_alert(monkeypatch):
    """형제 중 하나만 응답된 이상 상태여도 남은 미응답 알림만 NO_RESPONSE 처리한다."""
    calls = spy_start_report(monkeypatch)
    event_no = make_event()
    push_no = make_alert(event_no, channel="PUSH", status="READ",
                         deadline_offset_sec=-10, responded=True)
    sms_no = make_alert(event_no, channel="SMS", deadline_offset_sec=-10)

    escalation.run_escalation_tick()

    push = db.query_one("SELECT * FROM alert WHERE alert_no = %s", (push_no,))
    sms_row = db.query_one("SELECT * FROM alert WHERE alert_no = %s", (sms_no,))
    assert push["alert_status"] == "READ"          # 이미 응답한 행은 보존
    assert sms_row["alert_status"] == "NO_RESPONSE"
    assert calls == [(event_no, "NO_RESPONSE_TIMEOUT")]


def test_stale_pending_dismissed_via_tick():
    """스윕이 오래된 PENDING 이벤트를 기준미달(DISMISSED) 처리한다."""
    event_no = make_event(status="PENDING", detected_at="2026-08-08 00:00:00")

    summary = escalation.run_escalation_tick(now=datetime(2026, 8, 8, 12, 0, 0))

    row = db.query_one(
        "SELECT event_status FROM fire_event WHERE event_no = %s", (event_no,)
    )
    assert row["event_status"] == "DISMISSED"
    assert summary["dismissed_pending"] == 1


def test_one_bad_event_does_not_break_sweep(monkeypatch):
    """한 이벤트 처리가 죽어도 나머지 이벤트는 계속 에스컬레이션된다."""
    event_a = make_event(cctv_no=1)
    event_b = make_event(cctv_no=2)
    make_alert_pair(event_a, deadline_offset_sec=-10)
    make_alert_pair(event_b, deadline_offset_sec=-10)

    calls = []

    def flaky_start_report(event_no, trigger_reason):
        if event_no == event_a:
            raise RuntimeError("신고 실패 시뮬레이션")
        calls.append((event_no, trigger_reason))

    monkeypatch.setattr("services.report_service.start_report", flaky_start_report)

    summary = escalation.run_escalation_tick()

    # event_a 는 실패했지만 event_b 는 신고까지 갔다
    assert calls == [(event_b, "NO_RESPONSE_TIMEOUT")]
    assert [r["alert_status"] for r in get_alerts(event_b)] == \
        ["NO_RESPONSE", "NO_RESPONSE"]
    assert summary["reported"] == 1


def test_tick_is_idempotent():
    """틱을 여러 번 돌려도 신고가 중복 생성되지 않는다."""
    event_no = make_event()
    make_alert_pair(event_no, deadline_offset_sec=-10)

    escalation.run_escalation_tick()
    second = escalation.run_escalation_tick()  # 이미 전부 NO_RESPONSE — 대상 없음

    assert len(get_alerts(event_no)) == 2
    assert second["reported"] == 0
    assert len(get_reports(event_no)) == 1  # 신고 행도 1건뿐


# ---------- 스케줄러 배선 ----------

def test_create_app_default_does_not_start_scheduler():
    """테스트/일반 create_app() 은 스케줄러를 띄우지 않는다."""
    test_app = create_app()
    assert getattr(test_app, "escalation_scheduler", None) is None


def test_create_app_start_scheduler_registers_interval_job(monkeypatch):
    """create_app(start_scheduler=True) 는 ESCALATION_INTERVAL_SEC 간격 잡을 등록한다."""
    # 토큰을 비워 폴링 스레드를 뺀다 — .env 에 진짜 토큰이 들어 있는 PC(시연 준비된
    # 환경이 그렇다)에서 이 테스트가 실제 텔레그램으로 나가지 않게.
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    test_app = create_app(start_scheduler=True)
    scheduler = getattr(test_app, "escalation_scheduler", None)
    try:
        assert scheduler is not None
        assert scheduler.running
        # 스케줄러에 얹는 잡은 이제 에스컬레이션 하나뿐이다 (아래 텔레그램 절 참고)
        jobs = scheduler.get_jobs()
        assert len(jobs) == 1
        job = jobs[0]
        assert job.func is escalation.run_escalation_tick
        assert job.trigger.interval.total_seconds() == config.ESCALATION_INTERVAL_SEC
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


# ---------- 텔레그램 폴링 배선 ----------
# 텔레그램만 스케줄러 밖의 **전용 데몬 스레드**에서 롱폴링으로 돈다 (2026-08-22 교체).
# 실측: getUpdates 는 직전 요청과 3.0초 안에 붙으면 서버가 정확히 3.000초 붙잡았다가
# 빈 배열을 준다. 그래서 2초 간격 잡은 매 틱이 자기 주기를 넘겨 APScheduler 가
# `skipped: maximum number of running instances reached (1)` 를 계속 찍었고, 이건
# 주기를 어떻게 짜도 코드로 맞출 수 있는 값이 아니었다. 25초를 붙잡는 롱폴링을 간격
# 잡에 얹으면 같은 병이 더 크게 재발하므로 잡으로는 둘 수 없다.
# 토큰이 없으면 아예 띄우지 않는다 — 돌려 봐야 실패 로그만 쌓인다.

def _stub_polling(monkeypatch):
    """폴링 스레드가 떠도 밖으로 나가지 않게 틱을 대역으로 바꾼다."""
    from services import telegram_bot

    monkeypatch.setattr(telegram_bot, "run_telegram_tick",
                        lambda timeout_sec=0: {"received": 0, "failed": 0})
    monkeypatch.setattr(telegram_bot, "MIN_POLL_GAP_SEC", 0.02)
    return telegram_bot


def test_scheduler_start_also_starts_the_telegram_poller_thread(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "12345:TESTTOKEN")
    # 에스컬레이션 주기를 길게 잡아 관찰 중에 실제 틱이 뜨지 않게 한다 —
    # 백그라운드 틱이 DB 커넥션을 물면 뒤따르는 테스트가 흔들린다.
    monkeypatch.setattr(config, "ESCALATION_INTERVAL_SEC", 3600)
    telegram_bot = _stub_polling(monkeypatch)

    test_app = create_app(start_scheduler=True)
    scheduler = getattr(test_app, "escalation_scheduler", None)
    try:
        assert telegram_bot.is_polling(), "폴링 스레드가 안 떴다"
        # 잡으로 되돌아가면 skipped 로그가 그대로 다시 시작된다
        assert scheduler.get_job("telegram_poll") is None
        assert len(scheduler.get_jobs()) == 1
    finally:
        telegram_bot.stop_polling()
        if scheduler is not None:
            scheduler.shutdown(wait=False)


def test_scheduler_skips_the_telegram_poller_without_a_token(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    telegram_bot = _stub_polling(monkeypatch)

    test_app = create_app(start_scheduler=True)
    scheduler = getattr(test_app, "escalation_scheduler", None)
    try:
        assert telegram_bot.is_polling() is False
        assert scheduler.get_job("escalation_tick") is not None, "신고 스윕은 그대로 돈다"
    finally:
        telegram_bot.stop_polling()
        if scheduler is not None:
            scheduler.shutdown(wait=False)


# ---------- 백그라운드 작업은 프로세스당 하나 ----------
# 이중 기동은 성능 문제가 아니라 **기능이 깨지는** 문제다.
#   - 텔레그램은 getUpdates 를 한 소비자에게만 온전히 준다. 두 벌이 돌면 업데이트가
#     둘로 갈리거나 서로를 Conflict 로 끊어 버튼 응답이 사라진다 — 유예 안에 '취소'를
#     못 받는다는 뜻이고, 그러면 오탐에도 119 가 나간다.
#   - 에스컬레이션 스윕도 두 벌이 같은 이벤트를 동시에 집는다.
# 그래서 '한 번만' 을 실행 방법(app.py 의 use_reloader=False)에만 기대지 않고
# 스케줄러는 _start_escalation_scheduler 가, 폴링 스레드는 telegram_bot.start_polling
# 이 각자 직접 건다. 아래 두 테스트가 그 가드를 잡는다.

def test_scheduler_starts_only_once_per_process(monkeypatch):
    """같은 프로세스에서 create_app(start_scheduler=True) 을 두 번 불러도 한 벌이다.

    앱 팩토리는 누구나 다시 부를 수 있다 — WSGI 진입점, 테스트, 실수로 끼어든
    임포트. 부를 때마다 폴링이 한 벌씩 늘어나면 안 된다.
    """
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "12345:TESTTOKEN")
    # 관찰 중에 실제 틱이 뜨지 않게 주기를 길게 잡는다 (위 테스트들과 같은 이유)
    monkeypatch.setattr(config, "ESCALATION_INTERVAL_SEC", 3600)
    telegram_bot = _stub_polling(monkeypatch)

    first = create_app(start_scheduler=True)
    poller = telegram_bot._poll_thread
    second = create_app(start_scheduler=True)
    schedulers = {id(a.escalation_scheduler): a.escalation_scheduler
                  for a in (first, second)}
    try:
        assert second.escalation_scheduler is first.escalation_scheduler
        assert len(first.escalation_scheduler.get_jobs()) == 1
        # 폴링 스레드도 한 벌뿐이어야 한다 — 두 벌이면 버튼 응답이 갈린다
        assert telegram_bot._poll_thread is poller
        assert telegram_bot.is_polling()
    finally:
        telegram_bot.stop_polling()
        # 가드가 없으면 스케줄러가 둘 뜬다 — 뒤따르는 테스트로 새지 않게 전부 내린다
        for scheduler in schedulers.values():
            if scheduler is not None and scheduler.running:
                scheduler.shutdown(wait=False)


def test_scheduler_starts_again_after_the_previous_one_stopped(monkeypatch):
    """앞서 뜬 스케줄러가 이미 내려갔으면 다음 create_app 은 새로 띄운다.

    가드를 '이 프로세스에서 한 번이라도 띄웠나'로 잡으면 내려간 스케줄러를 그대로
    물려주게 된다 — 잡이 하나도 돌지 않는데 앱은 멀쩡해 보이는 최악의 상태다.
    기준은 '지금 돌고 있나'여야 한다. 스케줄러를 띄웠다 내리는 이 파일의 다른
    테스트들이 서로를 오염시키지 않는 것도 같은 이유로 성립한다.
    """
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "ESCALATION_INTERVAL_SEC", 3600)

    first = create_app(start_scheduler=True).escalation_scheduler
    first.shutdown(wait=False)

    second = create_app(start_scheduler=True).escalation_scheduler
    try:
        assert second is not first
        assert second.running
        assert second.get_job("escalation_tick") is not None
    finally:
        if second is not None and second.running:
            second.shutdown(wait=False)
