"""관리자 계정 API — 명세서 3번 섹션.

GET  /api/users             목록 (ADMIN)
POST /api/users             등록 (ADMIN)
PUT  /api/users/<user_no>   수정 · 정지 · 탈퇴 (ADMIN 전체 / 일반 사용자는 본인만)
"""
import bcrypt
from flask import Blueprint, g, jsonify, request

import db
from auth import admin_required, login_required
from errors import ApiError
from utils.pagination import get_page_params, paged_response
from utils.validation import validate_password, validate_phone, validate_user_id

bp = Blueprint("users", __name__)

# PUT 에서 갱신을 허용하는 컬럼 (user_pw 는 해시 처리 때문에 따로 다룬다)
UPDATABLE = [
    "user_name", "user_email", "user_phone",
    "user_role", "user_status", "user_gender", "user_address",
]

# 일반 사용자가 본인 계정에서 수정할 수 없는 컬럼 (관리자 전용)
ADMIN_ONLY_FIELDS = ["user_role", "user_status"]


@bp.get("")
@admin_required
def list_users():
    page, size = get_page_params()
    where = ""
    params: list = []
    if status := request.args.get("user_status"):
        where = "WHERE user_status = %s"
        params.append(status)

    total = db.query_one(f"SELECT count(*) AS cnt FROM users {where}", tuple(params))["cnt"]
    rows = db.query(
        f"""
        SELECT user_no, user_id, user_name, user_email, user_phone,
               user_role, user_status, user_created_at
        FROM users {where}
        ORDER BY user_no
        LIMIT %s OFFSET %s
        """,
        tuple(params + [size, (page - 1) * size]),
    )
    return jsonify(paged_response(rows, page, size, total))


@bp.post("")
@admin_required
def create_user():
    body = request.get_json(silent=True) or {}
    for field in ("user_id", "user_pw", "user_name", "user_role"):
        if not body.get(field):
            raise ApiError(400, "BAD_REQUEST", f"{field} 는 필수입니다.")

    # 아이디·비밀번호 작성규칙 (명세서 3번) — 로그인에는 적용하지 않는다
    validate_user_id(body["user_id"])
    validate_password(body["user_pw"], user_id=body["user_id"])
    validate_phone(body, "user_phone")

    if db.query_one("SELECT 1 FROM users WHERE user_id = %s", (body["user_id"],)):
        raise ApiError(409, "DUPLICATE_USER_ID", "이미 사용 중인 아이디입니다.")

    pw_hash = bcrypt.hashpw(body["user_pw"].encode(), bcrypt.gensalt()).decode()
    row = db.execute_returning(
        """
        INSERT INTO users (user_id, user_pw, user_name, user_email, user_phone,
                           user_role, user_status, user_gender, user_address)
        VALUES (%s, %s, %s, %s, %s, %s, 'ACTIVE', %s, %s)
        RETURNING user_no
        """,
        (
            body["user_id"], pw_hash, body["user_name"],
            body.get("user_email"), body.get("user_phone"), body["user_role"],
            body.get("user_gender"), body.get("user_address"),
        ),
    )
    return jsonify(row), 201


@bp.put("/<int:user_no>")
@login_required
def update_user(user_no: int):
    body = request.get_json(silent=True) or {}

    # 권한 검사: ADMIN 은 전체, 일반 사용자는 본인 계정의 일부 필드만 (명세서 3번)
    if g.user.get("user_role") != "ADMIN":
        if g.user.get("user_no") != user_no:
            raise ApiError(403, "FORBIDDEN", "본인 계정만 수정할 수 있습니다.")
        # 하나라도 관리자 전용 필드가 있으면 요청 전체를 거부한다 (부분 적용 금지)
        if any(field in body for field in ADMIN_ONLY_FIELDS):
            raise ApiError(403, "FORBIDDEN", "권한 등급과 계정 상태는 관리자만 변경할 수 있습니다.")

    validate_phone(body, "user_phone")

    sets = []
    params: list = []
    for col in UPDATABLE:
        if col in body:
            sets.append(f"{col} = %s")
            params.append(body[col])

    if "user_pw" in body:
        # 비밀번호 작성규칙 — 대상 사용자의 아이디 포함 여부는 DB 조회로 확인한다
        target = db.query_one("SELECT user_id FROM users WHERE user_no = %s", (user_no,))
        if not target:
            raise ApiError(404, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")
        validate_password(body["user_pw"], user_id=target["user_id"])
        sets.append("user_pw = %s")
        params.append(bcrypt.hashpw(body["user_pw"].encode(), bcrypt.gensalt()).decode())

    # 탈퇴 처리: WITHDRAWN 이 들어오면 탈퇴 일시를 함께 기록한다 (명세서 3번)
    if body.get("user_status") == "WITHDRAWN":
        sets.append("user_withdrawal_at = now()")

    if not sets:
        raise ApiError(400, "BAD_REQUEST", "수정할 필드가 없습니다.")

    sets.append("user_updated_at = now()")
    affected = db.execute(
        f"UPDATE users SET {', '.join(sets)} WHERE user_no = %s",
        tuple(params + [user_no]),
    )
    if affected == 0:
        raise ApiError(404, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")
    return jsonify({"user_no": user_no})
