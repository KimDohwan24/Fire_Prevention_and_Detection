"""알림 응답 처리 — 라우트에서 빼낸 본체.

왜 뺐나: 같은 처리를 두 입구가 부른다.
  1) POST /api/alerts/<no>/respond  — 웹 화면 (JWT 인증)
  2) 텔레그램 알림의 인라인 버튼      — 봇 워커 (chat_id 로 사용자를 찾는다)
Flask 의 g/request 에 기대면 2)에서 부를 수 없으므로 순수 함수로 둔다.
라우트 쪽 동작은 tests/test_alerts.py 가 계속 지킨다.
"""
import pytest

import db
from errors import ApiError
from services import alert_respond
from tests.conftest import make_alert, make_alert_pair, make_event


def _status(alert_no):
    return db.query_one("SELECT alert_status, alert_responded_at FROM alert "
                        "WHERE alert_no = %s", (alert_no,))


def test_read_marks_the_alert_read():
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1)

    row = alert_respond.respond(alert_no, user_no=1, action="READ")

    assert row["alert_status"] == "READ"
    assert row["alert_responded_at"] is not None


def test_cancel_marks_the_alert_canceled():
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1)

    row = alert_respond.respond(alert_no, user_no=1, action="CANCEL")

    assert row["alert_status"] == "CANCELED"


def test_responding_to_one_alert_closes_its_sibling():
    """확정 시 PUSH+SMS 두 행이 나간다 — 한쪽에 답하면 같은 이벤트의 나머지도 닫힌다."""
    event_no = make_event()
    push_no, sms_no = make_alert_pair(event_no, user_no=1)

    alert_respond.respond(push_no, user_no=1, action="CANCEL")

    assert _status(sms_no)["alert_status"] == "CANCELED"
    assert _status(sms_no)["alert_responded_at"] is not None


def test_unknown_action_is_rejected():
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1)

    with pytest.raises(ApiError) as exc:
        alert_respond.respond(alert_no, user_no=1, action="MAYBE")

    assert exc.value.code == "BAD_REQUEST"


def test_missing_alert_is_rejected():
    with pytest.raises(ApiError) as exc:
        alert_respond.respond(999999, user_no=1, action="READ")

    assert exc.value.code == "ALERT_NOT_FOUND"


def test_another_users_alert_is_rejected():
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1)

    with pytest.raises(ApiError) as exc:
        alert_respond.respond(alert_no, user_no=2, action="READ")

    assert exc.value.code == "NOT_YOUR_ALERT"


def test_responding_twice_is_rejected():
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1)
    alert_respond.respond(alert_no, user_no=1, action="READ")

    with pytest.raises(ApiError) as exc:
        alert_respond.respond(alert_no, user_no=1, action="READ")

    assert exc.value.code == "ALREADY_RESPONDED"


def test_cancel_after_the_deadline_is_rejected():
    """유예가 지나면 이미 119 신고 절차로 넘어갔으므로 취소할 수 없다."""
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1, deadline_offset_sec=-10)

    with pytest.raises(ApiError) as exc:
        alert_respond.respond(alert_no, user_no=1, action="CANCEL")

    assert exc.value.code == "DEADLINE_PASSED"


def test_late_read_keeps_the_no_response_history():
    """에스컬레이션이 이미 신고까지 보낸 알림은 READ 로 덮어쓰지 않는다."""
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1, status="NO_RESPONSE")

    row = alert_respond.respond(alert_no, user_no=1, action="READ")

    assert row["alert_status"] == "NO_RESPONSE"
    assert row["alert_responded_at"] is not None


def test_read_starts_the_119_report(monkeypatch):
    started = []
    monkeypatch.setattr("services.report_service.start_report",
                        lambda event_no, reason: started.append((event_no, reason)))
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1)

    alert_respond.respond(alert_no, user_no=1, action="READ")

    assert started == [(event_no, "USER_CONFIRMED")]


def test_cancel_does_not_start_a_report(monkeypatch):
    started = []
    monkeypatch.setattr("services.report_service.start_report",
                        lambda event_no, reason: started.append((event_no, reason)))
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1)

    alert_respond.respond(alert_no, user_no=1, action="CANCEL")

    assert started == []


def test_a_failing_report_does_not_break_the_response(monkeypatch):
    """신고가 터져도 '화재 확인' 자체는 기록돼야 한다."""
    def boom(event_no, reason):
        raise RuntimeError("119 unreachable")

    monkeypatch.setattr("services.report_service.start_report", boom)
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1)

    row = alert_respond.respond(alert_no, user_no=1, action="READ")

    assert row["alert_status"] == "READ"


def test_response_is_recorded_in_the_activity_log():
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1)

    alert_respond.respond(alert_no, user_no=1, action="READ")

    logged = db.query_one(
        "SELECT activity_type, activity_target_no FROM user_activity "
        "WHERE user_no = 1 ORDER BY activity_no DESC LIMIT 1"
    )
    assert logged["activity_target_no"] == event_no
