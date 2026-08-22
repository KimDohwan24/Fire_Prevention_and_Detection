"""화재 알림 전달 — 어느 채널로 내보낼지 정하는 한 곳.

호출부(services/alert_service.py)는 채널을 모른다. 이 함수 하나만 부르고, 여기서
텔레그램 → SMS 순으로 시도한다. 상용 전환으로 services/sms.py 가 실제 발송으로
바뀌어도 호출부는 그대로다.

**왜 텔레그램이 먼저인가**: 우리 알림은 유예 안에 '확인/취소'를 되받아야 의미가 있다
(무응답이면 119 로 넘어간다 — services/escalation.py). 문자는 회신을 받을 수 없어
사용자가 앱을 따로 열어야 하지만, 텔레그램은 알림에 붙은 버튼으로 그 자리에서 끝난다.
SMS 는 미연동 사용자를 위한 폴백이다. 자세한 배경은 config.py 의 TELEGRAM_* 주석에 있다.

**전달 실패는 알림 행 생성을 막지 않는다.** 어떤 채널이 터지든 예외를 밖으로
내보내지 않고, 실제로 나간 채널 이름만 돌려준다.
"""
import logging

from services import sms, telegram, telegram_bot

logger = logging.getLogger("fireguard.alert")


def send_fire_alert(*, chat_id, phone, message: str, alert_no: int) -> str:
    """화재 알림 1건을 내보낸다. 반환: 실제로 나간 채널 ("TELEGRAM"/"SMS"/"NONE").

    alert_no 는 텔레그램 버튼의 콜백에 실린다 — 그 버튼이 곧 응답 경로다.
    """
    if chat_id is not None:
        try:
            if telegram.send_message(chat_id, message,
                                     buttons=telegram_bot.build_alert_buttons(alert_no)):
                return "TELEGRAM"
            logger.warning("텔레그램 발송 실패 — SMS 로 폴백 (alert_no=%s)", alert_no)
        except Exception:
            # 래퍼가 이미 삼키지만, 여기서 새는 것이 있어도 폴백은 돌아야 한다
            logger.exception("텔레그램 발송 중 예외 — SMS 로 폴백 (alert_no=%s)", alert_no)

    return "SMS" if sms.send_sms(phone, message) else "NONE"
