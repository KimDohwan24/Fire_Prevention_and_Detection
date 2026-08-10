"""소방서 API — 명세서 7번 섹션.

GET  /api/agencies               목록
POST /api/agencies               등록 (ADMIN)
PUT  /api/agencies/<agency_no>   수정 · 비활성화 (ADMIN)
"""
from flask import Blueprint, jsonify, request

import db
from auth import admin_required, login_required
from errors import ApiError
from utils.validation import require_number, require_str

bp = Blueprint("agencies", __name__)

UPDATABLE = ["agency_name", "agency_lat", "agency_lng", "agency_endpoint", "agency_is_active"]

# 응답에 내보내는 컬럼을 명시한다 — SELECT * 를 쓰면 나중에 컬럼이 추가될 때
# 의도치 않은 값이 조용히 API 응답에 섞여 나간다 (명세서 7번 섹션 기준)
COLUMNS = """agency_no, agency_name, agency_lat, agency_lng,
             agency_endpoint, agency_is_active"""


@bp.get("")
@login_required
def list_agencies():
    rows = db.query(f"SELECT {COLUMNS} FROM agency ORDER BY agency_no")
    return jsonify({"items": rows})


@bp.post("")
@admin_required
def create_agency():
    body = request.get_json(silent=True) or {}
    for field in ("agency_name", "agency_endpoint"):
        require_str(body, field)
    for field in ("agency_lat", "agency_lng"):
        require_number(body, field)

    row = db.execute_returning(
        """
        INSERT INTO agency (agency_name, agency_lat, agency_lng, agency_endpoint)
        VALUES (%s, %s, %s, %s)
        RETURNING agency_no
        """,
        (body["agency_name"], body["agency_lat"], body["agency_lng"], body["agency_endpoint"]),
    )
    return jsonify(row), 201


@bp.put("/<int:agency_no>")
@admin_required
def update_agency(agency_no: int):
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
        f"UPDATE agency SET {', '.join(sets)} WHERE agency_no = %s",
        tuple(params + [agency_no]),
    )
    if affected == 0:
        raise ApiError(404, "AGENCY_NOT_FOUND", "소방서를 찾을 수 없습니다.")
    return jsonify({"agency_no": agency_no})
