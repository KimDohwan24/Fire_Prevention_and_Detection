"""내부 시스템 API — AI 모델 전용 (JWT 대신 X-Internal-Key 인증).

POST /api/internal/detections   프레임 1장의 검출 결과 수집
POST /api/internal/video-tests  업로드 영상의 최종 판정과 증거 이미지 저장
GET  /api/internal/cctvs        감시 대상 카메라 목록 (스트림 주소 최신화)
"""
import json
from datetime import datetime

from flask import Blueprint, jsonify, request

import db
from auth import internal_key_required
from errors import ApiError
from services import cctv_service, event_service, video_test_runner, video_test_service

bp = Blueprint("internal", __name__)


@bp.get("/cctvs")
@internal_key_required
def list_cctvs_for_ai():
    """AI 모델이 읽어 갈 카메라 목록 — 공개 목록과 같은 컬럼 + 최신 스트림 주소.

    ITS 스트림 주소에 박힌 토큰이 만료되면 재생이 끊긴다. 그때 AI 가 이 엔드포인트를
    다시 호출해 새 주소를 받아 재접속하면 된다. 보통은 ?cctv_status=ACTIVE 로
    가동 중인 카메라만 받아 간다.
    """
    rows = cctv_service.list_cctvs(cctv_status=request.args.get("cctv_status"))
    return jsonify({"items": rows})


@bp.post("/detections")
@internal_key_required
def ingest_detection():
    body = request.get_json(silent=True) or {}

    cctv_no = body.get("cctv_no")
    if isinstance(cctv_no, bool) or not isinstance(cctv_no, int):
        raise ApiError(400, "BAD_REQUEST", "cctv_no 는 필수 정수입니다.", field="cctv_no")

    detections = body.get("detections")
    if not isinstance(detections, list):
        raise ApiError(400, "BAD_REQUEST", "detections 는 리스트여야 합니다.",
                       field="detections")

    if not db.query_one("SELECT cctv_no FROM cctv WHERE cctv_no = %s", (cctv_no,)):
        raise ApiError(404, "CCTV_NOT_FOUND", "카메라를 찾을 수 없습니다.")

    # captured_at 은 선택 — 없으면 서버 수신 시각
    captured_at = datetime.now()
    if raw := body.get("captured_at"):
        try:
            captured_at = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            raise ApiError(400, "BAD_REQUEST", "captured_at 은 ISO 8601 형식이어야 합니다.",
                          field="captured_at")

    result = event_service.process_detection(
        cctv_no=cctv_no,
        captured_at=captured_at,
        media_url=body.get("media_url"),
        detections=detections,
    )
    return jsonify(result)


@bp.post("/video-tests")
@internal_key_required
def ingest_video_test():
    """영상 전체 판정 결과와 원본 증거 JPEG 최대 3장을 한 번에 저장한다."""
    raw_manifest = request.form.get("manifest")
    if raw_manifest is None:
        raise ApiError(400, "BAD_REQUEST", "manifest 는 필수 JSON 문자열입니다.",
                       field="manifest")
    try:
        manifest = json.loads(raw_manifest)
    except (TypeError, json.JSONDecodeError):
        raise ApiError(400, "BAD_REQUEST", "manifest 는 올바른 JSON이어야 합니다.",
                       field="manifest")

    result = video_test_service.create_video_test(manifest, request.files)
    return jsonify(result), 201


@bp.post("/video-tests/<job_id>/progress")
@internal_key_required
def ingest_video_test_progress(job_id: str):
    """백그라운드 AI가 최초 감지·화재 확정 순간에 보내는 진행상황."""
    raw_progress = request.form.get("progress")
    if raw_progress is None:
        progress = request.get_json(silent=True)
        image = None
    else:
        try:
            progress = json.loads(raw_progress)
        except (TypeError, json.JSONDecodeError):
            raise ApiError(400, "BAD_REQUEST", "progress는 올바른 JSON이어야 합니다.",
                           field="progress")
        image_file = request.files.get("image")
        image = image_file.read() if image_file else None

    return jsonify(video_test_runner.update_progress(job_id, progress, image))
