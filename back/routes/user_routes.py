"""관리자 계정 API — 명세서 3번 섹션.

GET  /api/users                        목록 (ADMIN)
POST /api/users                        등록 (공개 — 가입 화면이 토큰 없이 부른다)
                                       ADMIN 토큰으로 부르면 user_role 을 지정할 수
                                       있고, 그 외에는 VIEWER 로 고정된다
PUT  /api/users/<user_no>              수정 · 정지 · 탈퇴 (ADMIN 전체 / 일반 사용자는 본인만)
PUT  /api/users/password               본인 비밀번호 변경 (로그인 필요)
GET  /api/users/<user_no>/activities   활동이력 (ADMIN 전체 / 일반 사용자는 본인만)
                                       본인 것만 필요하면 GET /api/me/activities 를 쓴다
"""
import bcrypt
from flask import Blueprint, g, jsonify, request

import db
from auth import admin_required, caller_role, login_required
from errors import ApiError
from services import activity_service
from utils.pagination import get_page_params, paged_response
from utils.validation import validate_password, validate_phone, validate_user_id, validate_user_name

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
# @admin_required
def create_user():
    body = request.get_json(silent=True) or {}
    for field in ("user_id", "user_pw", "user_name", "user_role"):
        if not body.get(field):
            raise ApiError(400, "BAD_REQUEST", f"{field} 는 필수입니다.", field=field)

    # 아이디·비밀번호 작성규칙 (명세서 3번) — 로그인에는 적용하지 않는다
    validate_user_id(body["user_id"])
    validate_password(body["user_pw"], user_id=body["user_id"])
    validate_phone(body, "user_phone")
    validate_user_name(body["user_name"])
    if db.query_one("SELECT 1 FROM users WHERE user_id = %s", (body["user_id"],)):
        raise ApiError(409, "DUPLICATE_USER_ID", "이미 사용 중인 아이디입니다.")

    # 권한은 요청자가 스스로 정할 수 없다.
    #
    # 이 엔드포인트는 원래 admin_required 였는데, 가입 화면이 토큰 없이 부르게 되면서
    # 데코레이터가 제거됐다. 그 상태로는 아무나 user_role='ADMIN' 을 실어 보내
    # **인증 없이 관리자 계정을 만들 수 있다** (2026-08-19 실측: 토큰 없이 201).
    # 인증을 다시 걸면 가입이 막히므로, 대신 관리자 토큰으로 부른 경우에만 본문의
    # user_role 을 받아들이고 그 외에는 VIEWER 로 고정한다.
    # 관리자가 남을 승격시키는 경로는 PUT /api/users/<user_no> 로 따로 있다.
    user_role = body["user_role"] if caller_role() == "ADMIN" else "VIEWER"

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
            body.get("user_email"), body.get("user_phone"), user_role,
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

    # 기준선(토큰 폐기) 판단과 비밀번호 규칙 검사가 둘 다 현재 행을 필요로 하므로
    # 한 번만 읽고 아래에서 재활용한다.
    target = db.query_one(
        "SELECT user_id, user_provider, user_role FROM users WHERE user_no = %s",
        (user_no,),
    )
    if not target:
        raise ApiError(404, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")

    # DB 의 role 을 바꿔도 이미 발급된 토큰의 클레임은 옛 값 그대로다(auth.admin_required
    # 가 보는 것이 그 클레임이다). 폐기 조건에서 쓰려고 여기서 판정해 둔다.
    role_changed = "user_role" in body and body["user_role"] != target["user_role"]

    sets = []
    params: list = []
    for col in UPDATABLE:
        if col in body:
            sets.append(f"{col} = %s")
            params.append(body[col])

    if "user_pw" in body:
        # 비밀번호 작성규칙 — 대상 사용자의 아이디 포함 여부는 위에서 읽은 행으로 확인한다
        # 소셜 계정에 비밀번호를 심으면 CK_USERS_LOCAL_PW 는 통과하지만 정작 로그인은
        # SOCIAL_ACCOUNT 로 계속 막힌다 — 아무 효과 없는 값만 남으므로 미리 거절한다
        if target["user_provider"] != "LOCAL":
            raise ApiError(400, "SOCIAL_ACCOUNT",
                           "소셜 로그인 계정에는 비밀번호를 설정할 수 없습니다.",
                           field="user_pw")
        validate_password(body["user_pw"], user_id=target["user_id"])
        sets.append("user_pw = %s")
        params.append(bcrypt.hashpw(body["user_pw"].encode(), bcrypt.gensalt()).decode())

    # 탈퇴 처리: WITHDRAWN 이 들어오면 탈퇴 일시를 함께 기록한다 (명세서 3번)
    if body.get("user_status") == "WITHDRAWN":
        sets.append("user_withdrawal_at = now()")

    # 정지·탈퇴는 즉시 효력을 가져야 한다. 이 줄이 없으면 관리자가 계정을 정지해도
    # 이미 로그인해 있던 사람은 토큰 만료(기본 12시간)까지 그대로 쓴다.
    # 권한 등급 변경도 같은 이유로 즉시 끊는다 — 강등당한 사람의 토큰에는 옛 ADMIN
    # 클레임이 그대로 남아 있어서, 폐기하지 않으면 만료까지 관리자 API 를 계속 쓴다.
    # 방향(강등/승격)은 따지지 않는다: 승격이면 옛 토큰으로 새 권한을 못 쓰니 살릴
    # 값어치가 없고, 방향 조건은 등급이 늘어나는 순간 구멍이 된다.
    # 비밀번호 변경도 마찬가지다 — 관리자가 유출 의심 계정의 비밀번호를 강제로
    # 바꿨는데 옛 세션이 살아 있으면 회수 의미가 없다.
    if (body.get("user_status") in ("SUSPENDED", "WITHDRAWN")
            or role_changed or "user_pw" in body):
        sets.append("user_token_valid_from = now()")

    if not sets:
        raise ApiError(400, "BAD_REQUEST", "수정할 필드가 없습니다.")

    sets.append("user_updated_at = now()")
    affected = db.execute(
        f"UPDATE users SET {', '.join(sets)} WHERE user_no = %s",
        tuple(params + [user_no]),
    )
    if affected == 0:
        raise ApiError(404, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")

    # 이력은 '누가 무엇을 바꿨나'로 남긴다 — 대상은 수정당한 계정(user_no),
    # 주체는 요청한 사람(g.user)이다. 관리자가 남의 계정을 고친 경우 둘이 다르다.
    changed = [col for col in UPDATABLE if col in body]
    if changed:
        activity_service.record(g.user["user_no"], activity_service.PROFILE_UPDATED,
                                target_no=user_no, detail=", ".join(changed))
    if "user_pw" in body:
        activity_service.record(g.user["user_no"], activity_service.PASSWORD_CHANGED,
                                target_no=user_no, detail="관리자 변경")
    return jsonify({"user_no": user_no})


@bp.put("/password")
@login_required
def change_password():
    body = request.get_json(silent=True) or {}
    current_password = body.get("current_password")
    new_password = body.get("new_password")

    if not current_password or not new_password:
        raise ApiError(400, "BAD_REQUEST", "현재 비밀번호와 새 비밀번호를 모두 입력해주세요.")

    # 현재 로그인된 사용자의 user_no 가져오기 (g.user 활용)
    user_no = g.user.get("user_no")

    # DB에서 현재 사용자의 아이디와 저장된 비밀번호 해시 조회
    user = db.query_one(
        "SELECT user_id, user_pw, user_provider FROM users WHERE user_no = %s",
        (user_no,),
    )
    if not user:
        raise ApiError(404, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")

    # 소셜 계정은 user_pw 가 NULL 이라 아래 .encode() 에서 그대로 터진다(500).
    # OAuth 로그인이 붙기 전에는 토큰을 못 얻어 도달 불가능한 경로였지만 이제는
    # 아니다. 바꿀 비밀번호가 애초에 없다는 사실을 400 으로 알려준다 —
    # PUT /api/users/{user_no} 의 user_pw 가드와 같은 code·field 를 쓴다.
    if user["user_provider"] != "LOCAL":
        raise ApiError(400, "SOCIAL_ACCOUNT",
                       "소셜 로그인 계정은 비밀번호를 변경할 수 없습니다.",
                       field="user_pw")

    # 1. 현재 비밀번호 검증 (bcrypt.checkpw 사용)
    if not bcrypt.checkpw(current_password.encode(), user["user_pw"].encode()):
        raise ApiError(400, "INVALID_CURRENT_PASSWORD", "현재 비밀번호가 일치하지 않습니다.")

    # 2. 새 비밀번호 작성규칙 검증 (기존 유틸 함수 활용)
    validate_password(new_password, user_id=user["user_id"])

    # 3. 새 비밀번호 해시화 및 DB 업데이트
    new_pw_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    # 비밀번호가 바뀌었으니 기존 세션을 전부 끊는다 — 도난당한 기기의 토큰도
    # 비밀번호 변경만으로는 회수되지 않는다. 요청한 이 기기 포함 로그아웃되므로,
    # 프론트는 직후 요청에서 401 TOKEN_REVOKED 를 받고 로그인 화면으로 돌아간다.
    db.execute(
        """
        UPDATE users
        SET user_pw = %s,
            user_updated_at = now(),
            user_token_valid_from = now()
        WHERE user_no = %s
        """,
        (new_pw_hash, user_no),
    )

    return jsonify({"message": "비밀번호가 성공적으로 변경되었습니다."})


@bp.get("/<int:user_no>/activities")
@login_required
def list_user_activities(user_no: int):
    """지정한 사용자의 활동이력을 최신순으로 돌려준다.

    권한은 PUT 과 같은 규칙이다 — ADMIN 은 전체, 일반 사용자는 본인 것만.
    활동 이력은 감사 자료라 아무나 남의 것을 들여다볼 수 있으면 안 된다.

    본인 이력만 필요하면 GET /api/me/activities 를 쓰는 편이 낫다 — 아래 두 검사가
    통째로 필요 없어진다. 이 경로는 관리자가 남의 이력을 볼 때를 위해 남겨 둔 것이다.
    """
    if g.user.get("user_role") != "ADMIN" and g.user.get("user_no") != user_no:
        raise ApiError(403, "FORBIDDEN", "본인 계정의 활동이력만 조회할 수 있습니다.")

    # 이력이 0건인 것과 사용자가 없는 것은 다르다 — 빈 배열로 뭉개면 프론트가
    # 오타 난 user_no 를 '활동 없음'으로 표시하게 된다
    if db.query_one("SELECT 1 FROM users WHERE user_no = %s", (user_no,)) is None:
        raise ApiError(404, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")

    page, size = get_page_params()
    return jsonify(activity_service.list_for_user(user_no, page, size))


#사용자가 마이페이지에 진입할 때 비밀번호를 확인하는 API
@bp.post("mypage-check-password")
@login_required
def mypage_pw_check():
    user_no = g.user.get("user_no") #로그인된 사용자의 유저 번호 가져옴
    # print("유저 번호: ", user_no)
    
    #프론트에서 보낸 JSON 형태의 데이터(Requset Body)를 파이썬 딕셔너리로 받아옴
    body = request.get_json(silent=True) or {}
    
    #사용자가 작성한 비밀번호를 current_password에 담기
    current_password = body.get("current_password")
    # print("Mypage에 접속하기 위해서 사용자가 입력한 비밀번호: ", current_password)

    #current_password에 빈 문자열이나 아예 안 들어왔을 때 발생
    if not current_password:
            return jsonify({"verified": False, "message": "비밀번호를 입력해주세요"}), 400
        
    #사용자의 유저 번호를 이용해 DB에서 사용자 정보 불러오기
    user = db.query_one(
            "SELECT  user_pw, user_provider FROM users WHERE user_no = %s",
            (user_no,),
    )
    if not user:
            raise ApiError(404, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")
        
    if not bcrypt.checkpw(current_password.encode(), user["user_pw"].encode()):
            return  jsonify({"verified": False, "message": "비밀번호가 일치하지 않습니다."}), 400
        
    #비밀번호가 일치할 경우    
    return jsonify({"verified": True})    
        