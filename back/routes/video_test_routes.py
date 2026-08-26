"""Administrator UI endpoints for running videos from ai-model/samples."""

from flask import Blueprint, g, jsonify, request

from auth import admin_required
from errors import ApiError
from services import video_test_runner


bp = Blueprint("video_tests", __name__)


@bp.get("/samples")
@admin_required
def list_video_test_samples():
    return jsonify({"items": video_test_runner.list_samples()})


@bp.post("/run-sample")
@admin_required
def run_video_test_sample():
    body = request.get_json(silent=True) or {}
    sample_name = body.get("sample_name")
    cctv_no = body.get("cctv_no")
    live = body.get("live", False)

    if isinstance(cctv_no, bool) or not isinstance(cctv_no, int) or cctv_no < 1:
        raise ApiError(400, "BAD_REQUEST", "cctv_no는 1 이상의 정수여야 합니다.",
                       field="cctv_no")
    # live=true 면 모의 판정 대신 실전 파이프라인(run_video --send)으로 돈다 —
    # 실제 알림·119 신고가 나가는 스위치라 "true" 같은 어중간한 값은 받지 않는다.
    if not isinstance(live, bool):
        raise ApiError(400, "BAD_REQUEST", "live는 true 또는 false여야 합니다.",
                       field="live")

    job = video_test_runner.start_sample(sample_name, cctv_no, live=live)
    return jsonify(job), 202


@bp.get("/jobs/<job_id>")
@admin_required
def get_video_test_job(job_id: str):
    return jsonify(video_test_runner.get_job(job_id))


@bp.post("/jobs/<job_id>/decision")
@admin_required
def decide_video_test_job(job_id: str):
    body = request.get_json(silent=True) or {}
    decision = body.get("decision")
    reason = body.get("reason", "")
    result = video_test_runner.decide(
        job_id, decision, g.user["user_no"], reason
    )
    return jsonify(result)
