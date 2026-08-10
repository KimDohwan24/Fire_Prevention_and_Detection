"""무응답 에스컬레이션 스윕 (동시 발송 확정 설계).

스케줄러(또는 테스트)가 run_escalation_tick 을 주기적으로 호출한다. 한 번의 틱은:
1) 오래된 PENDING 이벤트를 기준미달(DISMISSED) 처리 (event_service.sweep_stale_pending)
2) 유예 마감을 넘긴 무응답 이벤트를 찾아:
   - 그 이벤트의 미응답 알림(SENT, alert_responded_at IS NULL) 전부를 NO_RESPONSE 로 닫고
   - 곧바로 119 신고 (start_report, trigger 'NO_RESPONSE_TIMEOUT')

확정 시 PUSH/SMS 가 동시에 나가므로 단계 승격(1차→2차 SMS)은 존재하지 않는다.
유예는 한 번뿐이고, 그 다음은 신고다.

제외 규칙:
- 점검 모드(event_is_test) 이벤트는 대상이 아니다.
- CANCELED 알림이 하나라도 있는 이벤트는 절대 에스컬레이션하지 않는다 (사용자 취소).
- 응답된 알림은 responded_at 이 있으므로 애초에 걸리지 않는다
  (신고는 respond 라우트가 이미 시작했다 — 이중 신고 없음).

각 이벤트 처리는 개별 try/except 로 감싸서 한 건의 실패가 스윕 전체를 멈추지 않는다.
"""
import logging
from datetime import datetime

from services import event_service, report_service

import db

logger = logging.getLogger("fireguard.escalation")

# 유예 마감 초과 + 무응답 알림을 가진 이벤트 조회.
# now 파라미터가 NULL 이면 DB 의 now() 를 쓴다 (운영 경로), 테스트는 시각을 주입한다.
_OVERDUE_EVENTS_SQL = """
    SELECT DISTINCT a.event_no
    FROM alert a
    JOIN fire_event e ON e.event_no = a.event_no
    WHERE a.alert_status = 'SENT'
      AND a.alert_responded_at IS NULL
      AND a.alert_deadline_at < coalesce(%s::timestamp, now())
      AND NOT e.event_is_test
      AND NOT EXISTS (
          SELECT 1 FROM alert c
          WHERE c.event_no = a.event_no AND c.alert_status = 'CANCELED'
      )
    ORDER BY a.event_no
"""


def _mark_event_no_response(event_no: int) -> int:
    """이벤트의 미응답 알림을 모두 NO_RESPONSE 로 전환한다 (동시성 가드 포함).

    반환: 실제로 전환된 행 수. 0 이면 그 사이 응답/취소가 들어온 것이므로
    신고로 넘어가지 않는다.
    """
    return db.execute(
        "UPDATE alert SET alert_status = 'NO_RESPONSE' "
        "WHERE event_no = %s AND alert_status = 'SENT' "
        "  AND alert_responded_at IS NULL",
        (event_no,),
    )


def run_escalation_tick(now: datetime | None = None) -> dict:
    """에스컬레이션 스윕 1회. 스케줄러/테스트가 호출한다.

    - now: 테스트용 기준 시각. None 이면 DB now() 기준.
    - 반환: {"dismissed_pending": n, "reported": n}
    """
    summary = {"dismissed_pending": 0, "reported": 0}

    # 1) 검출이 끊긴 PENDING 이벤트 정리
    try:
        summary["dismissed_pending"] = event_service.sweep_stale_pending(now)
    except Exception:
        logger.exception("PENDING 스윕 실패 — 알림 에스컬레이션은 계속 진행")

    # 2) 유예 초과 이벤트 처리 (이벤트 번호 오름차순 = 결정적 순서)
    for row in db.query(_OVERDUE_EVENTS_SQL, (now,)):
        event_no = row["event_no"]
        try:
            if not _mark_event_no_response(event_no):
                continue  # 그 사이 응답/취소됨 — 건너뛴다
            # 무응답 확정 → 119 신고 (start_report 가 멱등/점검모드 처리)
            report_service.start_report(event_no, "NO_RESPONSE_TIMEOUT")
            summary["reported"] += 1
        except Exception:
            # 한 이벤트의 실패가 스윕 전체를 멈추지 않는다
            logger.exception("에스컬레이션 실패 (event_no=%s)", event_no)

    if any(summary.values()):
        logger.info("에스컬레이션 틱 완료: %s", summary)
    return summary
