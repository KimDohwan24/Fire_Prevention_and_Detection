"""이벤트 확정 후속 처리 훅."""
import logging

from services import alert_service

logger = logging.getLogger("fireguard.hooks")


def on_event_confirmed(event_no: int) -> None:
    """화재 이벤트가 CONFIRMED 로 전환된 직후 호출된다.

    호출 시점: 확정 트랜잭션 커밋 이후 (이벤트 행은 이미 CONFIRMED 상태).
    소유자 앞 PUSH·SMS 알림을 동시에 만든다 (단계 승격 없음).
    점검 모드 이벤트는 send_alerts 가 알아서 건너뛴다.

    주의: AI 검출 요청 처리 중에 호출되므로 예외가 밖으로 새어 나가면
    검출 API 가 500 이 된다 — 반드시 여기서 삼키고 로그만 남긴다.
    """
    try:
        alert_service.send_alerts(event_no)
    except Exception:
        logger.exception("확정 알림 발송 실패 (event_no=%s)", event_no)
