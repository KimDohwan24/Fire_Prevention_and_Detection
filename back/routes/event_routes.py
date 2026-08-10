"""화재 이벤트 API — 명세서 5번 섹션.

GET /api/events              목록 (필터 + 페이징, 카메라 정보/대표 이미지 JOIN)
GET /api/events/<event_no>   상세 (카메라 + 미디어 + 알림 + 신고 이력 포함)
"""
from flask import Blueprint, jsonify, request

import db
from auth import login_required
from errors import ApiError
from utils.pagination import get_page_params, paged_response
from utils.validation import date_param, int_param

bp = Blueprint("events", __name__)


@bp.get("")
@login_required
def list_events():
    page, size = get_page_params()

    conds = []
    params: list = []
    if v := request.args.get("event_status"):
        conds.append("e.event_status = %s")
        params.append(v)
    if v := request.args.get("event_class"):
        conds.append("e.event_class = %s")
        params.append(v)
    if (v := int_param("cctv_no")) is not None:
        conds.append("e.cctv_no = %s")
        params.append(v)
    if v := date_param("date_from"):
        conds.append("e.event_detected_at >= %s")
        params.append(v)
    if v := date_param("date_to"):
        conds.append("e.event_detected_at < %s::date + 1")
        params.append(v)
    if request.args.get("include_test", "false").lower() != "true":
        conds.append("e.event_is_test = false")

    where = f"WHERE {' AND '.join(conds)}" if conds else ""

    total = db.query_one(
        f"SELECT count(*) AS cnt FROM fire_event e {where}", tuple(params)
    )["cnt"]
    rows = db.query(
        f"""
        SELECT e.event_no, e.cctv_no, c.cctv_name, c.cctv_location,
               e.event_status, e.event_class,
               e.event_first_detected_at, e.event_detected_at,
               e.event_confidence, e.event_is_test,
               -- 대표 이미지가 여러 장일 수 있으므로 정렬을 명시한다.
               -- (ORDER BY 없는 LIMIT 1 은 어떤 행이 뽑힐지 보장되지 않는다)
               -- 신뢰도가 가장 높은 것, 같으면 먼저 저장된 것(media_no 작은 쪽).
               (SELECT m.media_url FROM event_media m
                WHERE m.event_no = e.event_no AND m.media_is_primary
                ORDER BY m.media_confidence DESC NULLS LAST, m.media_no
                LIMIT 1) AS thumbnail_url
        FROM fire_event e
        JOIN cctv c ON c.cctv_no = e.cctv_no
        {where}
        ORDER BY e.event_no DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [size, (page - 1) * size]),
    )
    return jsonify(paged_response(rows, page, size, total))


@bp.get("/<int:event_no>")
@login_required
def get_event(event_no: int):
    event = db.query_one(
        """
        SELECT event_no, event_status, event_class,
               event_first_detected_at, event_detected_at,
               event_detected_frames, event_threshold_frames,
               event_confidence, event_is_test, cctv_no
        FROM fire_event WHERE event_no = %s
        """,
        (event_no,),
    )
    if not event:
        raise ApiError(404, "EVENT_NOT_FOUND", "이벤트를 찾을 수 없습니다.")

    cctv = db.query_one(
        """
        SELECT cctv_no, cctv_name, cctv_location, cctv_lat, cctv_lng
        FROM cctv WHERE cctv_no = %s
        """,
        (event.pop("cctv_no"),),
    )
    media = db.query(
        """
        SELECT media_no, media_type, media_url, media_confidence,
               media_captured_at, media_is_primary, media_detections
        FROM event_media WHERE event_no = %s
        ORDER BY media_is_primary DESC, media_no
        """,
        (event_no,),
    )
    alerts = db.query(
        """
        SELECT a.alert_no, a.user_no, u.user_name,
               a.alert_level, a.alert_channel, a.alert_status,
               a.alert_sent_at, a.alert_deadline_at, a.alert_responded_at
        FROM alert a
        JOIN users u ON u.user_no = a.user_no
        WHERE a.event_no = %s
        ORDER BY a.alert_level, a.alert_no
        """,
        (event_no,),
    )
    reports = db.query(
        """
        SELECT r.report_no, r.agency_no, ag.agency_name,
               r.report_sequence, r.report_status, r.report_distance_km,
               r.reported_at, r.report_accepted_at
        FROM report_119 r
        JOIN agency ag ON ag.agency_no = r.agency_no
        WHERE r.event_no = %s
        ORDER BY r.report_sequence, r.report_no
        """,
        (event_no,),
    )

    return jsonify({**event, "cctv": cctv, "media": media,
                    "alerts": alerts, "reports": reports})
