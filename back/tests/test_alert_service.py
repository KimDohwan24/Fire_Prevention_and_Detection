"""알림 발송 서비스 테스트 — services/alert_service.py + services/sms.py.

알림 정책 (동시 발송 확정):
- 알림은 해당 CCTV 의 소유 사용자(cctv.user_no)에게만 간다. ADMIN 브로드캐스트 없음.
- 이벤트 확정 시 PUSH 와 SMS 를 **동시에** 한 트랜잭션으로 만든다 (단계 승격 없음).
  두 채널 모두 같은 사람의 같은 휴대폰으로 가므로 단계를 나누면 시간만 낭비된다.
- 두 행 모두 alert_status='SENT', alert_sent_at/alert_deadline_at 동일.
- alert_deadline_at = alert_sent_at + ALERT_DEADLINE_SEC 초. 유예는 이 한 번뿐이고,
  마감까지 무응답이면 에스컬레이션이 곧바로 119 신고로 넘어간다.
- 점검 모드(event_is_test) 이벤트는 알림을 만들지 않는다.
- 확정 훅(on_event_confirmed)은 두 알림을 만들고, 예외를 절대 밖으로 던지지 않는다.
"""
from datetime import timedelta

from conftest import make_event

import config
import db
from services import alert_service, hooks, sms


FLAME = {"cls": "flame", "conf": 0.91, "box": [0.238, 0.259, 0.047, 0.113]}


def post_frame(client, cctv_no=1, captured_at="2026-08-08T14:30:00"):
    """내부 검출 API 로 화재 프레임 1장을 보낸다 (훅 경로 테스트용)."""
    return client.post(
        "/api/internal/detections",
        json={"cctv_no": cctv_no, "detections": [FLAME], "captured_at": captured_at},
        headers={"X-Internal-Key": config.INTERNAL_API_KEY},
    )


def get_alert_rows(event_no=None):
    if event_no is None:
        return db.query("SELECT * FROM alert ORDER BY alert_no")
    return db.query(
        "SELECT * FROM alert WHERE event_no = %s ORDER BY alert_no", (event_no,)
    )


def spy_send_sms(monkeypatch):
    """sms.send_sms 를 기록용 스파이로 바꾼다."""
    calls = []
    monkeypatch.setattr("services.sms.send_sms",
                        lambda phone, message: calls.append((phone, message)) or True)
    return calls


# ---------- sms 모의 발송기 ----------

def test_send_sms_with_phone_returns_true():
    """전화번호가 있으면 (모의) 발송 성공 True."""
    assert sms.send_sms("01011111111", "테스트 메시지") is True


def test_send_sms_without_phone_returns_false():
    """전화번호가 None/빈 문자열이면 경고 로그 후 False (예외 없음)."""
    assert sms.send_sms(None, "테스트 메시지") is False
    assert sms.send_sms("", "테스트 메시지") is False


# ---------- send_alerts 기본 동작 ----------

def test_send_alerts_creates_push_and_sms_rows(monkeypatch):
    """확정 알림 = PUSH 1행 + SMS 1행. 둘 다 level 1 / SENT, 발송·마감 시각이 동일."""
    monkeypatch.setattr(config, "ALERT_DEADLINE_SEC", 45)
    spy_send_sms(monkeypatch)
    event_no = make_event(cctv_no=1)

    alert_nos = alert_service.send_alerts(event_no)

    rows = get_alert_rows(event_no)
    assert len(rows) == 2
    assert sorted(alert_nos) == [r["alert_no"] for r in rows]
    assert {r["alert_channel"] for r in rows} == {"PUSH", "SMS"}

    for a in rows:
        assert a["user_no"] == 1          # cctv 1 의 소유자
        assert "alert_level" not in a     # 승격 폐기 — 컬럼 자체를 삭제함
        assert a["alert_status"] == "SENT"
        assert a["alert_sent_at"] is not None
        assert a["alert_responded_at"] is None
        # 마감은 발송 시각 + 정확히 ALERT_DEADLINE_SEC 초
        assert a["alert_deadline_at"] - a["alert_sent_at"] == timedelta(seconds=45)

    # 두 행은 같은 트랜잭션에서 만들어지므로 시각이 완전히 같아야 한다
    push, sms_row = rows if rows[0]["alert_channel"] == "PUSH" else rows[::-1]
    assert push["alert_sent_at"] == sms_row["alert_sent_at"]
    assert push["alert_deadline_at"] == sms_row["alert_deadline_at"]


def test_deadline_supports_sub_minute_grace(monkeypatch):
    """유예를 1분 미만으로 잡을 수 있다 — 발표 슬라이드 11 의 타임라인이 30초다.

    분 단위 설정으로는 표현 자체가 불가능했던 값이라 회귀로 남긴다.
    """
    monkeypatch.setattr(config, "ALERT_DEADLINE_SEC", 30)
    spy_send_sms(monkeypatch)
    event_no = make_event(cctv_no=1)

    alert_service.send_alerts(event_no)

    for a in get_alert_rows(event_no):
        assert a["alert_deadline_at"] - a["alert_sent_at"] == timedelta(seconds=30)


def test_default_deadline_is_30_seconds():
    """기본 유예는 30초 (슬라이드 11 타임라인: 알림 02:14:08 → 신고 02:14:38)."""
    assert config.ALERT_DEADLINE_SEC == 30


def test_send_alerts_sends_sms_once_to_owner_phone(monkeypatch):
    """SMS 행에 대해서만 send_sms 를 1회 호출한다 (PUSH 는 프론트 폴링이 가져감)."""
    calls = spy_send_sms(monkeypatch)
    event_no = make_event(cctv_no=1)

    alert_service.send_alerts(event_no)

    assert len(calls) == 1
    phone, message = calls[0]
    assert phone == "01011111111"  # admin01 (user_no=1) 의 전화번호
    assert "정문 카메라" in message
    assert "본관 정문 앞" in message


# ---------- 멱등성 · 예외 상황 ----------

def test_send_alerts_idempotent_per_event(monkeypatch):
    """이벤트 단위 멱등: 두 번 호출해도 행은 2개뿐이고 SMS 재발송도 없다."""
    calls = spy_send_sms(monkeypatch)
    event_no = make_event()

    first = alert_service.send_alerts(event_no)
    second = alert_service.send_alerts(event_no)

    assert sorted(first) == sorted(second)
    assert len(get_alert_rows(event_no)) == 2
    assert len(calls) == 1  # SMS 는 최초 1회만


def test_send_alerts_owner_without_phone_still_creates_both_rows():
    """소유자 전화번호가 NULL 이어도 두 행 모두 생성된다 (send_sms 가 False 처리)."""
    db.execute("UPDATE users SET user_phone = NULL WHERE user_no = 1")
    event_no = make_event(cctv_no=1)

    alert_nos = alert_service.send_alerts(event_no)  # 실제 sms.send_sms 사용

    rows = get_alert_rows(event_no)
    assert len(rows) == 2
    assert sorted(alert_nos) == [r["alert_no"] for r in rows]
    assert {r["alert_channel"] for r in rows} == {"PUSH", "SMS"}


def test_send_alerts_unknown_event_returns_none():
    """존재하지 않는 이벤트(→ 소유자 조회 불가)는 경고 로그 후 None, 예외 없음."""
    assert alert_service.send_alerts(99999) is None
    assert get_alert_rows() == []


def test_send_alerts_test_event_skipped():
    """점검 모드(event_is_test) 이벤트는 알림을 만들지 않는다."""
    event_no = make_event(is_test=True, status="CONFIRMED")
    assert alert_service.send_alerts(event_no) is None
    assert get_alert_rows() == []


# ---------- 확정 훅 경로 ----------

def test_hook_creates_both_alerts_on_confirm(client, monkeypatch):
    """내부 검출 API 로 확정까지 가면 소유자(user_no=1) 앞 PUSH+SMS 알림이 생긴다."""
    monkeypatch.setattr(config, "EVENT_THRESHOLD_FRAMES", 2)
    calls = spy_send_sms(monkeypatch)

    post_frame(client, captured_at="2026-08-08T14:30:00")
    body = post_frame(client, captured_at="2026-08-08T14:30:01").get_json()
    assert body["event_status"] == "CONFIRMED"

    rows = get_alert_rows(body["event_no"])
    assert len(rows) == 2
    assert {r["alert_channel"] for r in rows} == {"PUSH", "SMS"}
    for a in rows:
        assert a["user_no"] == 1
        assert "alert_level" not in a
        assert a["alert_status"] == "SENT"
    assert len(calls) == 1


def test_hook_test_event_creates_no_alert():
    """점검 모드 이벤트가 확정돼도 훅은 아무 것도 만들지 않는다."""
    event_no = make_event(is_test=True, status="CONFIRMED")
    hooks.on_event_confirmed(event_no)
    assert get_alert_rows() == []


def test_hook_exception_does_not_break_detection_api(client, monkeypatch):
    """알림 발송이 죽어도 AI 의 검출 요청은 200 이어야 한다 (훅이 예외를 삼킨다)."""
    monkeypatch.setattr(config, "EVENT_THRESHOLD_FRAMES", 2)

    def boom(event_no):
        raise RuntimeError("알림 발송 실패 시뮬레이션")

    monkeypatch.setattr("services.alert_service.send_alerts", boom)

    post_frame(client, captured_at="2026-08-08T14:30:00")
    r = post_frame(client, captured_at="2026-08-08T14:30:01")
    assert r.status_code == 200
    body = r.get_json()
    assert body["event_status"] == "CONFIRMED"  # 확정 자체는 그대로
    assert get_alert_rows() == []


# ---------- 알림 목록 API 연동 (회귀) ----------

def test_sent_alerts_visible_in_owner_alert_list(client, admin_headers, monkeypatch):
    """send_alerts 로 만든 두 알림이 모두 소유자의 GET /api/alerts 목록에 보인다."""
    spy_send_sms(monkeypatch)
    event_no = make_event(cctv_no=1)
    alert_nos = alert_service.send_alerts(event_no)

    r = client.get("/api/alerts", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["total_count"] == 2
    assert sorted(i["alert_no"] for i in body["items"]) == sorted(alert_nos)
    assert {i["alert_channel"] for i in body["items"]} == {"PUSH", "SMS"}
    assert all(i["event_no"] == event_no for i in body["items"])
    assert all(i["cctv_name"] == "정문 카메라" for i in body["items"])
