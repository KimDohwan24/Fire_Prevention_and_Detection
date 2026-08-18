"""연동 카메라 API — 명세서 4번 섹션.

GET  /api/cctvs             목록
GET  /api/cctvs/<cctv_no>   단건
POST /api/cctvs             등록 (ADMIN)
PUT  /api/cctvs/<cctv_no>   수정 · 중지 (ADMIN)
"""
from flask import Blueprint, g, jsonify, request

import db
from auth import admin_required, login_required
from errors import ApiError
from services import cctv_service
from utils.validation import int_param, require_number, require_str

bp = Blueprint("cctvs", __name__)

UPDATABLE = [
    "cctv_name", "cctv_location", "cctv_lat", "cctv_lng",
    "cctv_stream_url", "cctv_width", "cctv_height", "cctv_status",
]


@bp.get("")
@login_required
def list_cctvs():
    # user_no: 특정 사용자가 담당(소유)하는 카메라만 — 관리자 화면에서 쓴다.
    # 없으면 필터 없이 전체 (기존 호출자 동작 그대로)
    rows = cctv_service.list_cctvs(
        cctv_status=request.args.get("cctv_status"),
        user_no=int_param("user_no"),
    )
    return jsonify({"items": rows})


@bp.get("/<int:cctv_no>")
@login_required
def get_cctv(cctv_no: int):
    row = cctv_service.get_cctv(cctv_no)
    if not row:
        raise ApiError(404, "CCTV_NOT_FOUND", "카메라를 찾을 수 없습니다.")
    return jsonify(row)


@bp.post("")
@admin_required
def create_cctv():
    body = request.get_json(silent=True) or {}
    for field in ("cctv_name", "cctv_location", "cctv_stream_url"):
        require_str(body, field)
    for field in ("cctv_lat", "cctv_lng"):
        require_number(body, field)

    row = db.execute_returning(
        """
        INSERT INTO cctv (user_no, cctv_name, cctv_location, cctv_lat, cctv_lng,
                          cctv_stream_url, cctv_width, cctv_height, cctv_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE')
        RETURNING cctv_no
        """,
        (
            g.user["user_no"], body["cctv_name"], body["cctv_location"],
            body["cctv_lat"], body["cctv_lng"], body["cctv_stream_url"],
            body.get("cctv_width"), body.get("cctv_height"),
        ),
    )
    return jsonify(row), 201


@bp.put("/<int:cctv_no>")
@admin_required
def update_cctv(cctv_no: int):
    body = request.get_json(silent=True) or {}

    sets = []
    params: list = []
    for col in UPDATABLE:
        if col in body:
            sets.append(f"{col} = %s")
            params.append(body[col])

    if not sets:
        raise ApiError(400, "BAD_REQUEST", "수정할 필드가 없습니다.")

    affected = db.execute(
        f"UPDATE cctv SET {', '.join(sets)} WHERE cctv_no = %s",
        tuple(params + [cctv_no]),
    )
    if affected == 0:
        raise ApiError(404, "CCTV_NOT_FOUND", "카메라를 찾을 수 없습니다.")
    return jsonify({"cctv_no": cctv_no})
