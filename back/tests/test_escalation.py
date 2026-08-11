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


def test_create_app_start_scheduler_registers_interval_job():
    """create_app(start_scheduler=True) 는 ESCALATION_INTERVAL_SEC 간격 잡을 등록한다."""
    test_app = create_app(start_scheduler=True)
    scheduler = getattr(test_app, "escalation_scheduler", None)
    try:
        assert scheduler is not None
        assert scheduler.running
        jobs = scheduler.get_jobs()
        assert len(jobs) == 1
        job = jobs[0]
        assert job.func is escalation.run_escalation_tick
        assert job.trigger.interval.total_seconds() == config.ESCALATION_INTERVAL_SEC
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
