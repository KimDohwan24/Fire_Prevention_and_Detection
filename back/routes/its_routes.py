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
