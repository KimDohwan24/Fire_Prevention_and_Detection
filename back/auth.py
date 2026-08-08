"""JWT 발급/검증 + 인증 데코레이터.

사용 예:
    @bp.get("/me")
    @login_required
    def me():
        g.user  # 토큰에서 복원한 사용자 정보

    @bp.post("")
    @admin_required
    def create():
        ...
"""
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import g, request

import config
from errors import ApiError


def issue_token(user: dict) -> str:
    """로그인 성공 시 JWT 를 발급한다."""
    payload = {
        "user_no": user["user_no"],
        "user_id": user["user_id"],
        "user_role": user["user_role"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=config.JWT_EXPIRES_HOURS),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def _decode_token() -> dict:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise ApiError(401, "UNAUTHORIZED", "인증 토큰이 필요합니다.")
    token = header.removeprefix("Bearer ")
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "TOKEN_EXPIRED", "토큰이 만료되었습니다. 다시 로그인해주세요.")
    except jwt.InvalidTokenError:
        raise ApiError(401, "INVALID_TOKEN", "유효하지 않은 토큰입니다.")


def login_required(f):
    """토큰 검증 후 g.user 에 payload 를 넣는다."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        g.user = _decode_token()
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    """ADMIN 권한까지 요구한다."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        g.user = _decode_token()
        if g.user.get("user_role") != "ADMIN":
            raise ApiError(403, "FORBIDDEN", "관리자 권한이 필요합니다.")
        return f(*args, **kwargs)
    return wrapper
