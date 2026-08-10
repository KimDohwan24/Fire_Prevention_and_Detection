"""내부 시스템 API — AI 모델 전용 (JWT 대신 X-Internal-Key 인증).

POST /api/internal/detections   프레임 1장의 검출 결과 수집
"""
from datetime import datetime

from flask import Blueprint, jsonify, request

import db
from auth import internal_key_required
from errors import ApiError
from services import event_service

bp = Blueprint("internal", __name__)


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
