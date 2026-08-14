"""인증 API.

POST /api/auth/login                    로그인, JWT 발급
POST /api/auth/logout                   로그아웃 (활동이력에 LOGOUT 을 남기려고 있다)
GET  /api/auth/me                       내 정보 (세션 복원용)
POST /api/auth/find-id                  아이디 찾기 (이름 + 이메일)
POST /api/auth/password-reset/request   재설정 인증코드 발급 → SMS
POST /api/auth/password-reset/confirm   인증코드 확인 후 비밀번호 변경

계정 찾기 세 개는 **비로그인 상태에서 부르는 공개 엔드포인트**다. 인증코드는 저장하지
않고 그때그때 계산해 대조한다 — 방식과 근거는 services/account_recovery.py 참고.
"""
import logging

import bcrypt
from flask import Blueprint, g, jsonify, request

import db
from auth import issue_token, login_required
from errors import ApiError
from services import account_recovery, sms
from utils.validation import require_str, validate_password

bp = Blueprint("auth", __name__)
logger = logging.getLogger("fireguard.auth")

# 재설정 요청의 고정 응답 — 정보가 맞든 틀리든 똑같이 나간다 (계정 존재 여부 은닉)
_RESET_ACCEPTED = {
    "message": "정보가 일치하면 등록된 연락처로 인증코드를 보냈습니다.",
    "expires_in_sec": account_recovery.BUCKET_SEC * account_recovery.VALID_BUCKETS,
}


def _record_activity(user_no: int, activity_type: str) -> None:
    """활동이력 1행을 남긴다 (LOGIN / LOGOUT).

    실패한 로그인은 부르지 않는다 — 침입 시도는 접속 이력과 다른 것이고,
    한 표에 섞이면 '이 사람이 언제 들어왔나'를 읽을 수 없게 된다.
    """
    db.execute(
        "INSERT INTO user_activity (user_no, activity_type) VALUES (%s, %s)",
        (user_no, activity_type),
    )


@bp.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    user_id = body.get("user_id")
    user_pw = body.get("user_pw")
    # 어느 칸이 비었는지 프론트가 알 수 있게 필드별로 나눠서 던진다
    for name, value in (("user_id", user_id), ("user_pw", user_pw)):
        if not value:
            raise ApiError(400, "BAD_REQUEST", f"{name} 는 필수입니다.", field=name)

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

    _record_activity(user["user_no"], "LOGIN")

    return jsonify({
        "access_token": issue_token(user),
        "user": {
            "user_no": user["user_no"],
            "user_id": user["user_id"],
            "user_name": user["user_name"],
            "user_role": user["user_role"],
        },
    })


@bp.post("/logout")
@login_required
def logout():
    """활동이력에 LOGOUT 을 남긴다. 토큰 자체는 무효화하지 않는다.

    JWT 는 무상태라 서버가 이미 발급한 토큰을 되돌릴 수 없다. 실제 로그아웃은
    프론트가 토큰을 지우는 것으로 끝나고(api.js 의 authApi.logout), 이 엔드포인트는
    "나갔다"는 사실을 서버가 알 수 있는 유일한 통로다. 프론트가 이걸 안 부르면
    LOGOUT 행은 영영 쌓이지 않는다.

    토큰을 진짜로 죽이려면 폐기 목록(blocklist)이 따로 필요한데, 지금 범위가 아니다.
    """
    _record_activity(g.user["user_no"], "LOGOUT")
    return jsonify({"message": "로그아웃되었습니다."})


@bp.post("/find-id")
def find_id():
    """이름 + 이메일이 맞으면 아이디를 부분 마스킹해 돌려준다.

    탈퇴·정지 계정은 대상이 아니다 — 되찾아 봐야 로그인이 막혀 있고,
    비활성 계정의 존재를 확인해 주는 것 자체가 불필요한 정보 노출이다.
    """
    body = request.get_json(silent=True) or {}
    user_name = require_str(body, "user_name")
    user_email = require_str(body, "user_email")

    user = db.query_one(
        """
        SELECT user_id FROM users
        WHERE user_name = %s AND user_email = %s AND user_status = 'ACTIVE'
        ORDER BY user_no
        """,
        (user_name, user_email),
    )
    if not user:
        raise ApiError(404, "USER_NOT_FOUND", "일치하는 계정을 찾을 수 없습니다.")
    return jsonify({"user_id": account_recovery.mask_user_id(user["user_id"])})


@bp.post("/password-reset/request")
def password_reset_request():
    """아이디+이름+이메일이 맞으면 인증코드를 만들어 SMS 로 보낸다.

    **일치하지 않아도 200 을 돌려준다.** 여기서 404 를 내면 아이디·이름·이메일 조합을
    바꿔가며 찔러 실재 계정을 골라낼 수 있다. 대신 오타를 낸 사용자는 오지 않는 문자를
    기다리게 되는데, 그 불편이 계정 목록 유출보다 낫다고 봤다.

    코드는 **응답 본문에 넣지 않는다** — 넣는 순간 인증 단계가 무의미해진다.
    개발 중에는 목 SMS 발송기가 서버 로그에 찍으므로 시연에 지장이 없다.
    """
    body = request.get_json(silent=True) or {}
    user_id = require_str(body, "user_id")
    user_name = require_str(body, "user_name")
    user_email = require_str(body, "user_email")

    user = db.query_one(
        """
        SELECT user_no, user_pw, user_phone FROM users
        WHERE user_id = %s AND user_name = %s AND user_email = %s
          AND user_status = 'ACTIVE'
        """,
        (user_id, user_name, user_email),
    )
    if user:
        code = account_recovery.issue_code(user["user_no"], user["user_pw"])
        sms.send_sms(
            user["user_phone"],
            f"[파이어가드] 비밀번호 재설정 인증코드: {code} "
            f"({_RESET_ACCEPTED['expires_in_sec'] // 60}분 안에 입력해주세요)",
        )
    else:
        # 감사 흔적은 남긴다 — 응답으로는 구분되지 않지만 로그로는 추적할 수 있어야 한다
        logger.info("비밀번호 재설정 요청 — 일치하는 계정 없음 (user_id=%s)", user_id)

    return jsonify(_RESET_ACCEPTED)


@bp.post("/password-reset/confirm")
def password_reset_confirm():
    """인증코드를 확인하고 새 비밀번호로 바꾼다.

    비밀번호 작성규칙은 가입할 때와 **같은 것을 그대로** 적용한다. 재설정 경로로
    규칙을 우회할 수 있으면 규칙을 둔 의미가 없다.
    """
    body = request.get_json(silent=True) or {}
    user_id = require_str(body, "user_id")
    code = require_str(body, "code")
    # 코드가 맞는지 보기 전에 규칙부터 검사한다 — 규칙 위반이면 어차피 못 바꾸고,
    # 사용자에게는 '코드가 틀렸다'가 아니라 '비밀번호가 규칙에 안 맞다'가 맞는 안내다
    new_pw = validate_password(body.get("user_pw"), user_id)

    user = db.query_one(
        "SELECT user_no, user_pw FROM users WHERE user_id = %s AND user_status = 'ACTIVE'",
        (user_id,),
    )
    # 계정이 없어도 코드가 틀린 것과 같은 응답을 준다 (아이디 존재 여부 은닉)
    if not user or not account_recovery.verify_code(user["user_no"], user["user_pw"], code):
        raise ApiError(400, "INVALID_RESET_CODE",
                       "인증코드가 올바르지 않거나 만료되었습니다.")

    pw_hash = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
    db.execute(
        "UPDATE users SET user_pw = %s, user_updated_at = now() WHERE user_no = %s",
        (pw_hash, user["user_no"]),
    )
    # 해시가 바뀌었으므로 방금 쓴 코드는 이 순간 자동으로 죽는다 (재사용 불가)
    logger.info("비밀번호 재설정 완료 (user_no=%s)", user["user_no"])
    return jsonify({"message": "비밀번호가 변경되었습니다. 새 비밀번호로 로그인해주세요."})


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
