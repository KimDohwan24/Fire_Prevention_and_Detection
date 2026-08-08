"""관리자 알림 API — 명세서 6번 섹션.

GET  /api/alerts                     내 알림 목록
POST /api/alerts/<alert_no>/respond  알림 응답 (READ 화재확인 / CANCEL 오탐취소)
"""
from flask import Blueprint, g, jsonify, request

import db
from auth import login_required
from errors import ApiError
from utils.pagination import get_page_params, paged_response

bp = Blueprint("alerts", __name__)


@bp.get("")
@login_required
def list_alerts():
    page, size = get_page_params()

    conds = ["a.user_no = %s"]
    params: list = [g.user["user_no"]]
    if v := request.args.get("alert_status"):
        conds.append("a.alert_status = %s")
        params.append(v)
    where = f"WHERE {' AND '.join(conds)}"

    total = db.query_one(
        f"SELECT count(*) AS cnt FROM alert a {where}", tuple(params)
    )["cnt"]
    rows = db.query(
        f"""
        SELECT a.alert_no, a.event_no, e.event_class, c.cctv_name,
               a.alert_level, a.alert_channel, a.alert_status,
               a.alert_sent_at, a.alert_deadline_at, a.alert_responded_at
        FROM alert a
        JOIN fire_event e ON e.event_no = a.event_no
        JOIN cctv c ON c.cctv_no = e.cctv_no
        {where}
        ORDER BY a.alert_no DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [size, (page - 1) * size]),
    )
    return jsonify(paged_response(rows, page, size, total))


@bp.post("/<int:alert_no>/respond")
@login_required
def respond_alert(alert_no: int):
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    if action not in ("READ", "CANCEL"):
        raise ApiError(400, "BAD_REQUEST", "action 은 READ 또는 CANCEL 이어야 합니다.")

    alert = db.query_one("SELECT * FROM alert WHERE alert_no = %s", (alert_no,))
    if not alert:
        raise ApiError(404, "ALERT_NOT_FOUND", "알림을 찾을 수 없습니다.")
    if alert["user_no"] != g.user["user_no"]:
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
    row = db.execute_returning(
        """
        UPDATE alert
        SET alert_status = %s, alert_responded_at = now()
        WHERE alert_no = %s
        RETURNING alert_no, alert_status, alert_responded_at
        """,
        (new_status, alert_no),
    )
    return jsonify(row)
