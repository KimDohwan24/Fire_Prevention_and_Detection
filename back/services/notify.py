"""화재 알림 전달 — 어느 채널로 내보낼지 정하는 한 곳.

호출부(services/alert_service.py)는 채널을 모른다. 이 함수 하나만 부르고, 여기서
텔레그램 → SMS 순으로 시도한다. 상용 전환으로 services/sms.py 가 실제 발송으로
바뀌어도 호출부는 그대로다.

**왜 텔레그램이 먼저인가**: 우리 알림은 유예 안에 '확인/취소'를 되받아야 의미가 있다
(무응답이면 119 로 넘어간다 — services/escalation.py). 문자는 회신을 받을 수 없어
사용자가 앱을 따로 열어야 하지만, 텔레그램은 알림에 붙은 버튼으로 그 자리에서 끝난다.
SMS 는 미연동 사용자를 위한 폴백이다. 자세한 배경은 config.py 의 TELEGRAM_* 주석에 있다.
같은 이유로 검출 이미지도 텔레그램에만 실린다 — 판단에 필요한 그림과 그 판단을 되돌려
보낼 버튼이 한 메시지에 있어야 유예 안에 끝난다. 문자로는 둘 다 보낼 수 없다.

**전달 실패는 알림 행 생성을 막지 않는다.** 어떤 채널이 터지든 예외를 밖으로
내보내지 않고, 실제로 나간 채널 이름만 돌려준다.
"""
import logging

from services import sms, telegram, telegram_bot

logger = logging.getLogger("fireguard.alert")


def _try_photo(chat_id, image: bytes, message: str, buttons: list, alert_no: int) -> bool:
    """사진으로 보내 본다. 실패면 False — 호출자가 텍스트로 내려간다.

    래퍼(services/telegram.py)가 이미 예외를 삼키지만 여기서 한 겹 더 막는다.
    사진은 곁들이는 것이라, 사진 경로에서 새는 예외 하나가 알림 자체를 통째로
    문자로 밀어내거나(최악의 경우 못 나가게) 만들면 안 된다.
    """
    if not image:
        return False
    try:
        return telegram.send_photo(chat_id, image, message, buttons=buttons)
    except Exception:
        logger.exception("텔레그램 사진 발송 중 예외 — 텍스트로 재시도 (alert_no=%s)",
                         alert_no)
        return False


def send_fire_alert(*, chat_id, phone, message: str, alert_no: int,
                    image: bytes | None = None) -> str:
    """화재 알림 1건을 내보낸다. 반환: 실제로 나간 채널 ("TELEGRAM"/"SMS"/"NONE").

    alert_no 는 텔레그램 버튼의 콜백에 실린다 — 그 버튼이 곧 응답 경로다.

    image 는 검출 상자를 그린 대표 프레임(services/event_frame.py)이다. 있으면
    사진에 문구를 캡션으로 달아 한 건으로 보낸다 — 사용자가 유예 안에 오탐 여부를
    가리려면 무엇이 찍혔는지 봐야 한다.

    **이미지는 곁들이고 알림이 본체다.** 이미지가 없거나 사진 발송이 실패하면
    같은 문구를 텍스트로 보내고, 그것도 안 되면 기존 SMS 폴백으로 내려간다.
    문자에는 이미지가 없다 — 모의 SMS 는 문자열 한 줄만 받는다.
    """
    if chat_id is not None:
        try:
            buttons = telegram_bot.build_alert_buttons(alert_no)
            if _try_photo(chat_id, image, message, buttons, alert_no):
                return "TELEGRAM"
            if telegram.send_message(chat_id, message, buttons=buttons):
                return "TELEGRAM"
            logger.warning("텔레그램 발송 실패 — SMS 로 폴백 (alert_no=%s)", alert_no)
        except Exception:
            # 래퍼가 이미 삼키지만, 여기서 새는 것이 있어도 폴백은 돌아야 한다
            logger.exception("텔레그램 발송 중 예외 — SMS 로 폴백 (alert_no=%s)", alert_no)

    return "SMS" if sms.send_sms(phone, message) else "NONE"
