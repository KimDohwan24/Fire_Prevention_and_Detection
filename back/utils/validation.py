"""요청 값 검증 공통 도구 — 형식 오류는 모두 400 BAD_REQUEST 로 통일한다.

쿼리스트링용:
    int_param("cctv_no")     정수 파라미터 (없으면 None)
    date_param("date_from")  YYYY-MM-DD 파라미터 (없으면 None)

JSON 본문용:
    require_str(body, "cctv_name")   빈 문자열("") · 공백 문자열 거부
    require_number(body, "cctv_lat") JSON 숫자(int/float)만 허용
                                     ("37.5" 같은 숫자 문자열도 거부)
"""
from datetime import datetime

from flask import request

from errors import ApiError


def int_param(name: str) -> int | None:
    """쿼리스트링에서 정수 파라미터를 읽는다. 없으면 None, 형식 오류면 400."""
    v = request.args.get(name)
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        raise ApiError(400, "BAD_REQUEST", f"{name} 는 정수여야 합니다.")


def date_param(name: str) -> str | None:
    """쿼리스트링에서 YYYY-MM-DD 파라미터를 읽는다. 없으면 None, 형식 오류면 400."""
    v = request.args.get(name)
    if not v:
        return None
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        raise ApiError(400, "BAD_REQUEST", f"{name} 는 YYYY-MM-DD 형식이어야 합니다.")
    return v


def require_str(body: dict, field: str) -> str:
    """필수 문자열 필드: 누락 · 빈 문자열 · 공백뿐이면 400."""
    v = body.get(field)
    if not isinstance(v, str) or not v.strip():
        raise ApiError(400, "BAD_REQUEST", f"{field} 는 필수입니다.")
    return v


def require_number(body: dict, field: str) -> int | float:
    """필수 숫자 필드: JSON 숫자(int/float)가 아니면 400 (bool · 숫자 문자열 거부)."""
    v = body.get(field)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ApiError(400, "BAD_REQUEST", f"{field} 는 숫자여야 합니다.")
    return v
