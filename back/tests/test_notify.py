"""알림 전달 채널 선택 — 텔레그램 우선, 안 되면 기존 모의 SMS.

호출부(services/alert_service.py)는 채널을 모르고 이 함수 하나만 부른다.
상용 전환으로 실제 SMS 가 붙어도 호출부는 바뀌지 않는다.
"""
import pytest

from services import notify, sms, telegram


@pytest.fixture()
def outbox(monkeypatch):
    """텔레그램(본문·사진)·SMS 발송을 각각 기록한다."""
    box = {"telegram": [], "photo": [], "sms": []}
    monkeypatch.setattr(telegram, "send_message",
                        lambda chat_id, text, buttons=None:
                            box["telegram"].append((chat_id, text, buttons)) or True)
    monkeypatch.setattr(telegram, "send_photo",
                        lambda chat_id, image, caption, buttons=None:
                            box["photo"].append((chat_id, image, caption, buttons)) or True)
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


# ---------- 검출 이미지 동봉 ----------
#
# 사용자가 유예 안에 '확인/취소'를 판단하려면 무엇이 찍혔는지 봐야 한다. 문구만으로는
# 앱을 열어야 알 수 있고, 그 왕복이 유예를 다 먹는다. 그래서 대표 프레임(검출 상자를
# 그린 그림)을 알림에 그대로 붙인다.

IMAGE = b"\xff\xd8jpeg-bytes"


def test_sends_the_photo_with_the_message_as_its_caption(outbox):
    channel = notify.send_fire_alert(chat_id=555, phone="01011111111",
                                     message="불이야", alert_no=12, image=IMAGE)

    assert channel == "TELEGRAM"
    assert outbox["photo"] == [
        (555, IMAGE, "불이야", notify.telegram_bot.build_alert_buttons(12))]
    assert outbox["telegram"] == [], "사진이 나갔으면 같은 내용을 또 보내지 않는다"


def test_sends_plain_text_when_there_is_no_image(outbox):
    """이미지는 곁들이고 알림이 본체다 — 못 구했다고 알림을 거르지 않는다."""
    channel = notify.send_fire_alert(chat_id=555, phone="01011111111",
                                     message="불이야", alert_no=12, image=None)

    assert channel == "TELEGRAM"
    assert outbox["photo"] == []
    assert len(outbox["telegram"]) == 1


def test_falls_back_to_text_when_the_photo_send_fails(monkeypatch, outbox):
    """사진이 거절돼도(용량·형식) 알림 자체는 나가야 한다 — 문자로 내려가지도 않는다."""
    monkeypatch.setattr(telegram, "send_photo",
                        lambda chat_id, image, caption, buttons=None: False)

    channel = notify.send_fire_alert(chat_id=555, phone="01011111111",
                                     message="불이야", alert_no=12, image=IMAGE)

    assert channel == "TELEGRAM"
    assert len(outbox["telegram"]) == 1
    assert outbox["sms"] == []


def test_falls_back_to_text_when_the_photo_send_raises(monkeypatch, outbox):
    def boom(chat_id, image, caption, buttons=None):
        raise RuntimeError("photo exploded")

    monkeypatch.setattr(telegram, "send_photo", boom)

    channel = notify.send_fire_alert(chat_id=555, phone="01011111111",
                                     message="불이야", alert_no=12, image=IMAGE)

    assert channel == "TELEGRAM"
    assert len(outbox["telegram"]) == 1


def test_falls_back_to_sms_when_neither_photo_nor_text_gets_through(monkeypatch, outbox):
    monkeypatch.setattr(telegram, "send_photo",
                        lambda chat_id, image, caption, buttons=None: False)
    monkeypatch.setattr(telegram, "send_message",
                        lambda chat_id, text, buttons=None: False)

    channel = notify.send_fire_alert(chat_id=555, phone="01011111111",
                                     message="불이야", alert_no=12, image=IMAGE)

    assert channel == "SMS"
    assert outbox["sms"] == [("01011111111", "불이야")]


def test_sms_fallback_carries_the_text_only(outbox):
    """문자에는 이미지가 없다 — 모의 SMS 는 문자열 한 줄만 받는다."""
    channel = notify.send_fire_alert(chat_id=None, phone="01011111111",
                                     message="불이야", alert_no=12, image=IMAGE)

    assert channel == "SMS"
    assert outbox["photo"] == []
    assert outbox["sms"] == [("01011111111", "불이야")]
