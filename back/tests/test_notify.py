"""알림 전달 채널 선택 — 텔레그램 우선, 안 되면 기존 모의 SMS.

호출부(services/alert_service.py)는 채널을 모르고 이 함수 하나만 부른다.
상용 전환으로 실제 SMS 가 붙어도 호출부는 바뀌지 않는다.
"""
import pytest

from services import notify, sms, telegram


@pytest.fixture()
def outbox(monkeypatch):
    """텔레그램·SMS 발송을 각각 기록한다."""
    box = {"telegram": [], "sms": []}
    monkeypatch.setattr(telegram, "send_message",
                        lambda chat_id, text, buttons=None:
                            box["telegram"].append((chat_id, text, buttons)) or True)
    monkeypatch.setattr(sms, "send_sms",
                        lambda phone, message: box["sms"].append((phone, message)) or True)
    return box


def test_uses_telegram_when_the_user_is_linked(outbox):
    channel = notify.send_fire_alert(chat_id=555, phone="01011111111",
                                     message="불이야", alert_no=12)

    assert channel == "TELEGRAM"
    assert outbox["telegram"] == [(555, "불이야", notify.telegram_bot.build_alert_buttons(12))]


def test_does_not_also_send_sms_when_telegram_worked(outbox):
    notify.send_fire_alert(chat_id=555, phone="01011111111", message="불이야", alert_no=12)

    assert outbox["sms"] == []


def test_falls_back_to_sms_when_the_user_is_not_linked(outbox):
    channel = notify.send_fire_alert(chat_id=None, phone="01011111111",
                                     message="불이야", alert_no=12)

    assert channel == "SMS"
    assert outbox["telegram"] == []
    assert outbox["sms"] == [("01011111111", "불이야")]


def test_falls_back_to_sms_when_telegram_delivery_fails(monkeypatch, outbox):
    monkeypatch.setattr(telegram, "send_message",
                        lambda chat_id, text, buttons=None: False)

    channel = notify.send_fire_alert(chat_id=555, phone="01011111111",
                                     message="불이야", alert_no=12)

    assert channel == "SMS"
    assert outbox["sms"] == [("01011111111", "불이야")]


def test_reports_none_when_no_channel_is_reachable(monkeypatch, outbox):
    monkeypatch.setattr(telegram, "send_message",
                        lambda chat_id, text, buttons=None: False)
    monkeypatch.setattr(sms, "send_sms", lambda phone, message: False)

    channel = notify.send_fire_alert(chat_id=None, phone=None,
                                     message="불이야", alert_no=12)

    assert channel == "NONE"


def test_a_raising_telegram_still_falls_back_to_sms(monkeypatch, outbox):
    """전달 실패가 알림 행 생성을 막아서는 안 된다 — 예외를 밖으로 내보내지 않는다."""
    def boom(chat_id, text, buttons=None):
        raise RuntimeError("telegram exploded")

    monkeypatch.setattr(telegram, "send_message", boom)

    channel = notify.send_fire_alert(chat_id=555, phone="01011111111",
                                     message="불이야", alert_no=12)

    assert channel == "SMS"
