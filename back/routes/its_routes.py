"""ITS OpenAPI CCTV catalogue endpoint."""
from flask import Blueprint, jsonify, request

from errors import ApiError
from services import its_cctv

bp = Blueprint("its", __name__)


def _to_public_item(item: dict) -> dict | None:
    """Convert the ITS OpenAPI field names to the frontend CCTV contract."""
    name = (item.get("cctvname") or "").strip()
    stream_url = (item.get("cctvurl") or "").strip()
    try:
        lat = float(item["coordy"])
        lng = float(item["coordx"])
    except (KeyError, TypeError, ValueError):
        return None

    # A camera without a name or a playable stream must not be selectable.
    if not name or not stream_url:
        return None

    return {
        "cctv_name": name,
        # 왼쪽 가지는 사실상 죽어 있다 — 2026-08-18 실측으로 ITS 개방 API 의
        # roadsectionid 는 전 건이 빈 문자열이다(고속도로 282건·국도 23건 모두).
        # 그래서 cctv_location 에는 항상 카메라 이름이 그대로 들어간다
        # ('[수도권제1순환선] 판교분기점'). 명세상 언제든 채워 보낼 수 있으니
        # 왼쪽은 남겨 둔다. 119 로 나가는 주소는 이 값이 아니라 좌표를
        # 역지오코딩해 등록 시 저장하는 cctv_address 다.
        "cctv_location": item.get("roadsectionid") or name,
        "cctv_lat": lat,
        "cctv_lng": lng,
        "cctv_type": item.get("cctvformat") or "ITS",
        "cctv_stream_url": stream_url,
    }


@bp.get("/cctvs")
def list_its_cctvs():
    """Return currently available ITS live CCTV streams for registration."""
    try:
        limit = int(request.args.get("limit", 10))
        offset = int(request.args.get("offset", 0))
    except ValueError as exc:
        raise ApiError(400, "BAD_REQUEST", "limit and offset must be integers.") from exc

    if not 1 <= limit <= 100 or offset < 0:
        raise ApiError(400, "BAD_REQUEST", "limit must be 1-100 and offset must be non-negative.")

    try:
        raw_items = its_cctv.fetch_its_cctvs()
    except Exception as exc:
        raise ApiError(503, "ITS_UNAVAILABLE", "ITS CCTV 목록을 조회할 수 없습니다.") from exc

    items = [mapped for item in raw_items if (mapped := _to_public_item(item))]
    return jsonify({"items": items[offset:offset + limit], "total": len(items)})
