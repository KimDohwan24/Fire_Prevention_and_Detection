"""ITS(국가교통정보센터) 공공 CCTV 조회 API.

GET /api/its/cctvs   연동 가능한 ITS 카메라 목록 (DB 가 아니라 외부 API 조회)

카메라를 등록하려는 관리자가 "지금 붙일 수 있는 카메라"를 고르는 화면용이다.
우리 DB 에 아직 없는 카메라를 보여주는 게 목적이라 저장분이 없고, 그래서
`/api/cctvs` 와 실패 정책이 정반대다:

- `/api/cctvs` 는 ITS 가 죽어도 **저장된 주소로 폴백**해 200 을 낸다.
- 여기는 폴백할 저장분이 없다. 실패를 빈 목록(0건)으로 위장하면 화면에는
  "조회 가능한 CCTV 가 없습니다"만 뜨고, 사용자는 정말 없는 건지 서버가
  고장난 건지 알 수 없다. 그래서 **실패는 502 로 실패라고 알린다**.
  (단 ITS 가 정상적으로 0건을 준 경우는 성공이므로 200 + 빈 items 다.)
"""
import logging

from flask import Blueprint, jsonify, request

import config
import db
from auth import login_required
from errors import ApiError
from services import its_cctv
from utils.validation import float_param

logger = logging.getLogger("fireguard.its")

bp = Blueprint("its", __name__)

# 조회 박스 파라미터 — 네 개는 전부 있거나 전부 없어야 한다
BBOX_PARAMS = ("min_x", "max_x", "min_y", "max_y")


def _bbox_from_query() -> tuple | None:
    """쿼리스트링에서 조회 박스를 읽는다. 없으면 None(=전국 기본 박스).

    일부만 주는 것은 400 이다 — 세 개만 받아 나머지를 기본값으로 채우면
    사용자가 의도한 영역과 전혀 다른 결과가 조용히 나간다.
    """
    values = {name: float_param(name) for name in BBOX_PARAMS}
    given = [name for name, v in values.items() if v is not None]
    if not given:
        return None
    if len(given) != len(BBOX_PARAMS):
        missing = [name for name in BBOX_PARAMS if values[name] is None]
        raise ApiError(
            400, "BAD_REQUEST",
            f"조회 영역은 {', '.join(BBOX_PARAMS)} 네 개를 모두 보내야 합니다. "
            f"(누락: {', '.join(missing)})",
            field=missing[0],
        )
    return (values["min_x"], values["max_x"], values["min_y"], values["max_y"])


def _to_float(value):
    """ITS 좌표를 float 으로. 값이 없거나 이상하면 None (한 항목 때문에 죽지 않게)."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize(item: dict, registered: set) -> dict:
    """ITS 원본 항목을 우리 스키마 이름으로 바꾼다.

    좌표는 **coordy=위도 · coordx=경도** 다 (뒤집으면 지도에 엉뚱한 곳이 찍힌다).

    cctv_location / cctv_type 은 ITS 원본에 대응 필드가 없다:
    - ITS 는 주소를 주지 않는다. 이름("[경부선] 판교분기점")이 노선+지점 표기라
      위치 설명을 겸하므로 그대로 넣는다.
    - cctv_type 은 스트림 형식(cctvformat, 예 HLS)을 쓴다.
    둘 다 **문자열을 보장한다** — 프론트 목록 화면이 이 값으로 검색(`.includes`)을
    돌려서 null 이면 화면이 통째로 터진다.
    """
    name = (item.get("cctvname") or "").strip()
    return {
        "cctv_name": name,
        "cctv_location": name,
        "cctv_type": item.get("cctvformat") or "",
        "cctv_lat": _to_float(item.get("coordy")),   # 위도
        "cctv_lng": _to_float(item.get("coordx")),   # 경도
        "cctv_stream_url": item.get("cctvurl"),
        "cctv_resolution": item.get("cctvresolution") or "",
        "is_registered": name in registered,
    }


def _registered_names() -> set:
    """이미 등록된 카메라 이름 집합 — 쿼리 한 번으로 받아 메모리에서 대조한다."""
    rows = db.query("SELECT cctv_name FROM cctv")
    return {(row["cctv_name"] or "").strip() for row in rows}


@bp.get("/cctvs")
@login_required
def list_its_cctvs():
    bbox = _bbox_from_query()
    q = (request.args.get("q") or "").strip().lower()

    if not config.CCTV_API_KEY:
        # 키가 없으면 조회 자체가 불가능하다. 0건으로 위장하지 않고 이유를 말한다.
        raise ApiError(502, "ITS_UNAVAILABLE",
                       "ITS 인증키가 설정되지 않았습니다. 서버의 CCTV_API_KEY 를 확인해주세요.")

    try:
        raw = its_cctv.fetch_its_cctvs(bbox)
    except Exception as exc:
        logger.warning("ITS 목록 조회 실패: %s", exc)
        raise ApiError(502, "ITS_UNAVAILABLE",
                       "ITS 오픈 API 조회에 실패했습니다. 잠시 후 다시 시도해주세요.")

    registered = _registered_names()
    items = [_normalize(item, registered) for item in raw]
    if q:
        items = [it for it in items if q in it["cctv_name"].lower()]
    return jsonify({"items": items})

