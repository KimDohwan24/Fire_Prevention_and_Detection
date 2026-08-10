"""119 신고 API — 명세서 8번 섹션.

GET /api/reports   신고 이력 목록 (event_no 로 승계 이력 필터 가능)
"""
from flask import Blueprint, jsonify, request

import db
from auth import login_required
from utils.pagination import get_page_params, paged_response
from utils.validation import int_param

bp = Blueprint("reports", __name__)


@bp.get("")
@login_required
def list_reports():
    page, size = get_page_params()

    conds = []
    params: list = []
    if v := request.args.get("report_status"):
        conds.append("r.report_status = %s")
        params.append(v)
    if (v := int_param("event_no")) is not None:
        conds.append("r.event_no = %s")
        params.append(v)
    where = f"WHERE {' AND '.join(conds)}" if conds else ""

    total = db.query_one(
        f"SELECT count(*) AS cnt FROM report_119 r {where}", tuple(params)
    )["cnt"]
    rows = db.query(
        f"""
        SELECT r.report_no, r.event_no, r.agency_no, ag.agency_name,
               r.report_sequence, r.report_external_id, r.report_trigger_reason,
               r.report_status, r.report_address, r.report_distance_km,
               r.report_attempt_count, r.reported_at, r.report_accepted_at
        FROM report_119 r
        JOIN agency ag ON ag.agency_no = r.agency_no
        {where}
        ORDER BY r.report_no DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [size, (page - 1) * size]),
    )
    return jsonify(paged_response(rows, page, size, total))
