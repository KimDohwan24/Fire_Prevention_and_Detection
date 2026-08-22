"""알림 응답 처리 (READ 화재확인 / CANCEL 오탐취소).

**입구가 둘이라 라우트에서 빼냈다.**
  1) POST /api/alerts/<no>/respond — 웹 화면. JWT 로 사용자를 안다.
  2) 텔레그램 알림의 인라인 버튼    — 봇 워커. chat_id 로 사용자를 찾는다.
Flask 의 g/request 에 기대면 2)에서 부를 수 없다. 그래서 user_no 를 인자로 받는
순수 함수로 두고, 두 입구가 같은 규칙(소유자 검사·중복 응답·유예 마감)을 지나게 한다.

실패는 ApiError 로 던진다 — 라우트는 등록된 핸들러가 HTTP 로 바꿔 주고(errors.py),
봇 워커는 message 를 그대로 토스트로 띄운다. 두 입구가 같은 문구를 쓰게 된다.
"""
import logging

import db
from errors import ApiError
from services import activity_service, report_service

logger = logging.getLogger("fireguard.alerts")

ACTIONS = ("READ", "CANCEL")


def respond(alert_no: int, user_no: int, action: str) -> dict:
    """알림 1건에 응답한다. 반환: 갱신된 alert 행(alert_no/status/responded_at).

    응답은 **이벤트 단위**로 적용된다 — 같은 이벤트의 미응답 형제 알림도 함께 닫힌다.
    """
    if action not in ACTIONS:
        raise ApiError(400, "BAD_REQUEST", "action 은 READ 또는 CANCEL 이어야 합니다.",
                       field="action")

    # cctv_name 은 활동이력 요약 문구에 쓴다 — 어차피 한 번 읽는 김에 조인해 둔다
    # (list_alerts 가 쓰는 것과 같은 조인이다)
    alert = db.query_one(
        """
        SELECT a.alert_no, a.event_no, a.user_no, a.alert_status, a.alert_responded_at,
               c.cctv_name
        FROM alert a
        JOIN fire_event e ON e.event_no = a.event_no
        JOIN cctv c ON c.cctv_no = e.cctv_no
        WHERE a.alert_no = %s
        """,
        (alert_no,),
    )
    if not alert:
        raise ApiError(404, "ALERT_NOT_FOUND", "알림을 찾을 수 없습니다.")
    if alert["user_no"] != user_no:
        raise ApiError(403, "NOT_YOUR_ALERT", "다른 사용자의 알림입니다.")
    if alert["alert_responded_at"] is not None:
        raise ApiError(409, "ALREADY_RESPONDED", "이미 응답한 알림입니다.")

    if action == "CANCEL":
        # 유예 마감이 지났으면 취소 불가 (이미 119 신고 절차로 넘어감)
        deadline_ok = db.query_one(
            "SELECT alert_deadline_at > now() AS ok FROM alert WHERE alert_no = %s",
            (alert_no,),
        )["ok"]
        if not deadline_ok:
            raise ApiError(409, "DEADLINE_PASSED", "취소 유예 시간이 지났습니다.")

    if action == "READ" and alert["alert_status"] == "NO_RESPONSE":
        # 에스컬레이션이 이미 NO_RESPONSE 처리(119 신고 트리거)한 알림에 대한 늦은 READ.
        # 상태를 READ 로 덮어쓰면 '무응답으로 신고까지 갔다'는 이력이 사라지므로
        # alert_status 는 NO_RESPONSE 그대로 보존하고 alert_responded_at 만 기록한다.
        new_status = "NO_RESPONSE"
    else:
        new_status = "READ" if action == "READ" else "CANCELED"

    # 응답은 '이벤트 단위'로 적용된다.
    # 확정 시 PUSH/SMS 두 알림이 동시에 나가는데 둘 다 같은 사람의 같은 화재 건이므로,
    # 한쪽에 응답하면 같은 이벤트의 나머지 미응답 알림도 같은 상태·같은 시각으로 닫는다.
    # (NO_RESPONSE 형제는 신고 이력 보존을 위해 상태를 유지하고 응답 시각만 기록)
    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE alert
            SET alert_status = %s, alert_responded_at = now()
            WHERE alert_no = %s
            RETURNING alert_no, alert_status, alert_responded_at
            """,
            (new_status, alert_no),
        )
        row = dict(cur.fetchone())
        cur.execute(
            """
            UPDATE alert
            SET alert_status = CASE WHEN alert_status = 'NO_RESPONSE'
                                    THEN 'NO_RESPONSE' ELSE %s END,
                alert_responded_at = %s
            WHERE event_no = %s
              AND alert_no <> %s
              AND alert_responded_at IS NULL
              AND alert_status IN ('SENT', 'NO_RESPONSE')
            """,
            (new_status, row["alert_responded_at"], alert["event_no"], alert_no),
        )

    # 관제 조치 이력 — 종류만 남기면 "화재를 확인했다"가 전부 똑같이 보이므로
    # 대상 이벤트 번호와 카메라 이름까지 같이 남긴다.
    if action == "READ":
        activity_service.record(
            user_no, activity_service.FIRE_CONFIRMED,
            target_no=alert["event_no"], detail=f"{alert['cctv_name']} 화재 확인",
        )
    else:
        activity_service.record(
            user_no, activity_service.FIRE_DISMISSED,
            target_no=alert["event_no"], detail=f"{alert['cctv_name']} 오탐 취소",
        )

    if action == "READ" and alert["alert_status"] == "SENT":
        # D4: 사용자가 화재를 확인하면 즉시 119 신고를 시작한다.
        # (NO_RESPONSE 알림의 늦은 READ 는 제외 — 에스컬레이션이 이미 신고를 처리했다)
        # 신고 로직이 실패해도 알림 응답 자체는 성공해야 하므로 예외는 삼킨다.
        try:
            report_service.start_report(alert["event_no"], "USER_CONFIRMED")
        except Exception:
            logger.exception("화재 확인 신고 시작 실패 (alert_no=%s, event_no=%s)",
                             alert_no, alert["event_no"])

    return row
