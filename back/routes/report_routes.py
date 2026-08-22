"""119 신고 API — 명세서 8번 섹션.

GET  /api/reports                     신고 이력 목록 (event_no 로 승계 이력 필터 가능)
GET  /api/reports/<report_no>/logs    그 신고의 119 송수신 로그 (전송 시도별)
POST /api/reports/dispatch            소방서가 보내는 출동 통지 수신 (X-Agency-Key)
"""
import json
import logging
import re
from datetime import datetime

from flask import Blueprint, jsonify, request

import db
from auth import agency_key_required, login_required
from errors import ApiError
from services.report_service import ACTIVE_STATUSES
from utils.pagination import get_page_params, paged_response
from utils.validation import int_param

bp = Blueprint("reports", __name__)

logger = logging.getLogger("fireguard.report")

# 신고 ID 형식 — report_service.report_uid() 가 만드는 "FG-{event_no}"
REPORT_UID_RE = re.compile(r"^FG-(\d+)$")


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
               r.report_attempt_count, r.reported_at, r.report_accepted_at,
               r.report_dispatched_at, r.report_dispatch
        FROM report_119 r
        JOIN agency ag ON ag.agency_no = r.agency_no
        {where}
        ORDER BY r.report_no DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [size, (page - 1) * size]),
    )
    return jsonify(paged_response(rows, page, size, total))


@bp.get("/<int:report_no>/logs")
@login_required
def list_report_logs(report_no: int):
    """신고 1건의 119 송수신 로그를 시도 순서대로 돌려준다.

    페이징하지 않는다 — 한 신고의 시도는 MAX_REPORT_ATTEMPTS(기본 4)건으로 묶여 있다.
    """
    if db.query_one("SELECT 1 FROM report_119 WHERE report_no = %s",
                    (report_no,)) is None:
        raise ApiError(404, "REPORT_NOT_FOUND", "신고를 찾을 수 없습니다.")

    rows = db.query(
        """
        SELECT log_no, report_no, log_attempt, log_endpoint, log_request,
               log_result, log_http_status, log_response, log_error,
               log_elapsed_ms, log_sent_at
        FROM report_log
        WHERE report_no = %s
        ORDER BY log_attempt, log_no
        """,
        (report_no,),
    )
    return jsonify({"items": rows})


@bp.post("/dispatch")
@agency_key_required
def receive_dispatch():
    """소방서가 실제로 배차했다는 통지를 받는다.

    2xx 응답(ACCEPTED)은 "신고를 받았다"까지다. 소방차가 나갔는지는 119 만 알고,
    이 엔드포인트로 알려준다. 받으면 그 신고를 DISPATCHED 로 승격한다.

    멱등하다 — 같은 통지가 여러 번 와도 행이 늘지 않고 최신 값으로 덮인다.
    소방서가 재전송할 수 있고, 그때마다 출동이 늘어나면 안 된다.
    """
    body = request.get_json(silent=True) or {}

    uid = body.get("report_uid")
    matched = REPORT_UID_RE.fullmatch(uid) if isinstance(uid, str) else None
    if matched is None:
        raise ApiError(400, "BAD_REQUEST",
                       "report_uid 는 'FG-<이벤트번호>' 형식이어야 합니다.",
                       field="report_uid")
    event_no = int(matched.group(1))

    report = db.query_one(
        """
        SELECT report_no, report_external_id FROM report_119
        WHERE event_no = %s AND report_status IN %s
        """,
        (event_no, ACTIVE_STATUSES),
    )
    if report is None:
        # 승계로 닫힌(NO_RESPONSE/FAILED) 신고뿐이면 붙일 곳이 없다
        raise ApiError(404, "REPORT_NOT_FOUND", "진행 중인 신고를 찾을 수 없습니다.")

    external_id = body.get("external_id")
    if external_id and report["report_external_id"] \
            and external_id != report["report_external_id"]:
        # 거절하지 않는다 — mock-119 를 재시작하면 접수번호가 1번부터 다시
        # 발급돼 어긋난다. 그것 때문에 출동 통지를 버리는 편이 더 나쁘다.
        logger.warning("출동 통지의 접수번호 불일치 — 그대로 진행 "
                       "(report_no=%s, 저장된=%s, 수신=%s)",
                       report["report_no"], report["report_external_id"], external_id)

    now = datetime.now()
    dispatched_at = now
    if raw := body.get("dispatched_at"):
        try:
            dispatched_at = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            # 출동했다는 사실이 시각 형식보다 중요하다 — 수신 시각으로 채운다
            logger.warning("출동 시각 형식 오류 — 수신 시각으로 대체 (report_no=%s, 값=%r)",
                           report["report_no"], raw)

    # 원문을 그대로 보관한다. 모르는 키가 와도 버리지 않는다 — 나중에 무엇이
    # 왔었는지 따질 근거가 여기밖에 없다. report_uid 는 대상을 찾는 열쇠일 뿐이라 뺀다.
    dispatch = {k: v for k, v in body.items() if k != "report_uid"}
    dispatch["received_at"] = now.isoformat(timespec="seconds")

    db.execute(
        """
        UPDATE report_119
        SET report_status = 'DISPATCHED', report_dispatched_at = %s,
            report_dispatch = %s::jsonb
        WHERE report_no = %s
        """,
        (dispatched_at, json.dumps(dispatch, ensure_ascii=False), report["report_no"]),
    )
    logger.info("소방서 출동 통지 수신 (report_no=%s, event_no=%s, 기관=%s)",
                report["report_no"], event_no, body.get("agency_name"))

    return jsonify({
        "report_no": report["report_no"],
        "event_no": event_no,
        "report_status": "DISPATCHED",
        "report_dispatched_at": dispatched_at,
    })
