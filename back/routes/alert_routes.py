"""관리자 알림 API — 명세서 6번 섹션.

GET  /api/alerts                     내 알림 목록
POST /api/alerts/<alert_no>/respond  알림 응답 (READ 화재확인 / CANCEL 오탐취소)
"""
from flask import Blueprint, g, jsonify, request

import db
from auth import login_required
from services import alert_respond
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
               a.alert_channel, a.alert_status,
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
    """알림 응답. 본체는 services/alert_respond.py 에 있다 —
    텔레그램 알림의 인라인 버튼도 같은 처리를 부르기 때문이다."""
    body = request.get_json(silent=True) or {}
    row = alert_respond.respond(alert_no, g.user["user_no"], body.get("action"))
    return jsonify(row)
