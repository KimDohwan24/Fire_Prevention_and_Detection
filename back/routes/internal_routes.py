"""내부 시스템 API — AI 모델 전용 (JWT 대신 X-Internal-Key 인증).

POST /api/internal/detections   프레임 1장의 검출 결과 수집
GET  /api/internal/cctvs        감시 대상 카메라 목록 (스트림 주소 최신화)
"""
from datetime import datetime

from flask import Blueprint, jsonify, request

import db
from auth import internal_key_required
from errors import ApiError
from routes.cctv_routes import COLUMNS as CCTV_COLUMNS
from services import event_service, its_cctv

bp = Blueprint("internal", __name__)


@bp.get("/cctvs")
@internal_key_required
def list_cctvs_for_ai():
    """AI 모델이 읽어 갈 카메라 목록 — 공개 목록과 같은 컬럼 + 최신 스트림 주소.

    ITS 스트림 주소에 박힌 토큰이 만료되면 재생이 끊긴다. 그때 AI 가 이 엔드포인트를
    다시 호출해 새 주소를 받아 재접속하면 된다. 보통은 ?cctv_status=ACTIVE 로
    가동 중인 카메라만 받아 간다.
    """
    where = ""
    params: list = []
    if status := request.args.get("cctv_status"):
        where = "WHERE cctv_status = %s"
        params.append(status)

    rows = db.query(
        f"SELECT {CCTV_COLUMNS} FROM cctv {where} ORDER BY cctv_no", tuple(params)
    )
    return jsonify({"items": its_cctv.refresh_stream_urls(rows)})


@bp.post("/detections")
@internal_key_required
def ingest_detection():
    body = request.get_json(silent=True) or {}

    cctv_no = body.get("cctv_no")
    if isinstance(cctv_no, bool) or not isinstance(cctv_no, int):
        raise ApiError(400, "BAD_REQUEST", "cctv_no 는 필수 정수입니다.")

    detections = body.get("detections")
    if not isinstance(detections, list):
        raise ApiError(400, "BAD_REQUEST", "detections 는 리스트여야 합니다.")

    if not db.query_one("SELECT cctv_no FROM cctv WHERE cctv_no = %s", (cctv_no,)):
        raise ApiError(404, "CCTV_NOT_FOUND", "카메라를 찾을 수 없습니다.")

    # captured_at 은 선택 — 없으면 서버 수신 시각
    captured_at = datetime.now()
    if raw := body.get("captured_at"):
        try:
            captured_at = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            raise ApiError(400, "BAD_REQUEST", "captured_at 은 ISO 8601 형식이어야 합니다.")

    result = event_service.process_detection(
        cctv_no=cctv_no,
        captured_at=captured_at,
        media_url=body.get("media_url"),
        detections=detections,
    )
    return jsonify(result)
