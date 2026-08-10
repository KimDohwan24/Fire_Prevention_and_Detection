"""인증 API — 명세서 2번 섹션.

POST /api/auth/login   로그인, JWT 발급
GET  /api/auth/me      내 정보 (세션 복원용)
"""
import bcrypt
from flask import Blueprint, g, jsonify, request

import db
from auth import issue_token, login_required
from errors import ApiError

bp = Blueprint("auth", __name__)


@bp.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    user_id = body.get("user_id")
    user_pw = body.get("user_pw")
    if not user_id or not user_pw:
        raise ApiError(400, "BAD_REQUEST", "user_id 와 user_pw 는 필수입니다.")

    # 필요한 컬럼만 읽는다 (SELECT * 면 주소·연락처 등 로그인에 불필요한 값까지 딸려온다)
    user = db.query_one(
        """
        SELECT user_no, user_id, user_pw, user_name, user_role, user_status
        FROM users WHERE user_id = %s
        """,
        (user_id,),
    )
    if not user or not bcrypt.checkpw(user_pw.encode(), user["user_pw"].encode()):
        raise ApiError(401, "INVALID_CREDENTIALS", "아이디 또는 비밀번호가 일치하지 않습니다.")
    if user["user_status"] == "SUSPENDED":
        raise ApiError(403, "ACCOUNT_SUSPENDED", "정지된 계정입니다.")
    if user["user_status"] == "WITHDRAWN":
        raise ApiError(403, "ACCOUNT_WITHDRAWN", "탈퇴한 계정입니다.")

    return jsonify({
        "access_token": issue_token(user),
        "user": {
            "user_no": user["user_no"],
            "user_id": user["user_id"],
            "user_name": user["user_name"],
            "user_role": user["user_role"],
        },
    })


@bp.get("/me")
@login_required
def me():
    user = db.query_one(
        """
        SELECT user_no, user_id, user_name, user_email,
               user_phone, user_role, user_status
        FROM users WHERE user_no = %s
        """,
        (g.user["user_no"],),
    )
    if not user:
        raise ApiError(404, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")
    return jsonify(user)
