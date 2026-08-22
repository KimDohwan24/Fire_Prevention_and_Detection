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
# geocode 는 모듈째로 들고 온다 — reverse_geocode 를 이름으로 끌어오면 이 모듈에
# 별도 참조가 박혀서 테스트의 monkeypatch(services.geocode.reverse_geocode)가 안 먹는다.
from services import cctv_service, geocode
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

    # 주소는 등록 시점에 한 번만 구한다. 119 신고는 동기 경로라(요청 스레드에서
    # start_report 가 끝난다) 신고 순간에 외부 API 를 부르면 그 지연이 그대로 전송
    # 지연이 된다. 카메라 좌표는 변하지 않으니 여기서 한 번이면 충분하다.
    # 실패하면 None 이고, 그래도 등록은 성공해야 한다 — 주소 하나 때문에 카메라를
    # 못 붙이면 안 된다. 비어 있는 행은 backfill_cctv_address.py 로 나중에 메운다.
    cctv_address = geocode.reverse_geocode(body["cctv_lat"], body["cctv_lng"])

    row = db.execute_returning(
        """
        INSERT INTO cctv (user_no, cctv_name, cctv_location, cctv_address,
                          cctv_lat, cctv_lng,
                          cctv_stream_url, cctv_width, cctv_height, cctv_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE')
        RETURNING cctv_no
        """,
        (
            g.user["user_no"], body["cctv_name"], body["cctv_location"], cctv_address,
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
