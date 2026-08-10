"""모의 SMS 발송기.

실제 발송 API(쿨SMS 등) 로 교체하는 지점 — 지금은 로그만 남기고 성공으로 처리한다.
외부 HTTP 호출이 없으므로 테스트/개발 환경에서 그대로 사용해도 안전하다.
"""
import logging

logger = logging.getLogger("fireguard.sms")


def send_sms(phone: str | None, message: str) -> bool:
    """SMS 1건을 (모의) 발송한다.

    성공하면 True. 수신자 전화번호가 없으면 경고 로그만 남기고 False.
    (발송 실패가 알림 행 생성 자체를 막아서는 안 되므로 예외를 던지지 않는다)
    """
    if not phone:
        logger.warning("SMS 발송 생략 — 수신자 전화번호 없음: %s", message)
        return False
    logger.info("[모의 SMS] %s ← %s", phone, message)
    return True
