"""인증 API.

<<<<<<< Updated upstream
POST /api/auth/login                    로그인, JWT 발급
POST /api/auth/logout                   로그아웃 (토큰 폐기 + 활동이력 LOGOUT)
GET  /api/auth/me                       내 정보 (세션 복원용)
POST /api/auth/find-id                  아이디 찾기 (이름 + 이메일)
=======
POST /api/auth/login                  로그인, JWT 발급
GET  /api/auth/me                     내 정보 (세션 복원용)
POST /api/auth/find-id                아이디 찾기 (이름 + 이메일)
>>>>>>> Stashed changes
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
from services import account_recovery, activity_service, sms
from utils.validation import require_str, validate_password
import random
import smtplib
from email.mime.text import MIMEText

# 임시 저장소 (메모리 기반)
email_storage = {}      # {email: verification_code}
verified_emails = set()   # 인증 완료된 이메일 목록

# SMTP 설정
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "songjonghan96@gmail.com"
SENDER_PASSWORD = "geaexurrnrdegrnm"  # 구글 앱 비밀번호

def send_email_smtp(to_email: str, code: str):
    msg = MIMEText(f"[FireGuard] 회원가입 인증번호는 [{code}] 입니다. 5분 안에 입력해주세요.")
    msg["Subject"] = "[FireGuard] 회원가입 이메일 인증번호"
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
    except Exception as e:
        print(f"이메일 전송 실패: {e}")
        print(f"🚨 [상세 에러 발생]: {repr(e)}")
        raise ApiError(500, "EMAIL_SEND_FAILED", "이메일 전송에 실패했습니다.")

bp = Blueprint("auth", __name__)
logger = logging.getLogger("fireguard.auth")

# 재설정 요청의 고정 응답 — 정보가 맞든 틀리든 똑같이 나간다 (계정 존재 여부 은닉)
_RESET_ACCEPTED = {
    "message": "정보가 일치하면 등록된 연락처로 인증코드를 보냈습니다.",
    "expires_in_sec": account_recovery.BUCKET_SEC * account_recovery.VALID_BUCKETS,
}


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
        SELECT user_no, user_id, user_pw, user_name, user_role, user_status, user_provider
        FROM users WHERE user_id = %s
        """,
        (user_id,),
    )
    # 소셜 계정은 비밀번호가 없어서 어떤 값을 넣어도 통과할 수 없다. 균일하게
    # INVALID_CREDENTIALS 로 뭉개면 소셜 사용자가 영문도 모르고 갇히므로 따로 안내한다.
    # 대신 '그 아이디가 존재하고 소셜 계정'이라는 사실은 노출된다 — 닫힌 관제 시스템의
    # 지정된 운영자 계정이라 감수했다. 공개 가입형이 되면 재검토할 것.
    if user and user["user_provider"] != "LOCAL":
        raise ApiError(400, "SOCIAL_ACCOUNT",
                       "소셜 로그인으로 가입한 계정입니다. 해당 서비스로 로그인해주세요.")
    # user_pw 가 NULL 이면 .encode() 에서 터지므로 checkpw 앞에서 걸러낸다
    if not user or not user["user_pw"] \
            or not bcrypt.checkpw(user_pw.encode(), user["user_pw"].encode()):
        raise ApiError(401, "INVALID_CREDENTIALS", "아이디 또는 비밀번호가 일치하지 않습니다.")
    if user["user_status"] == "SUSPENDED":
        raise ApiError(403, "ACCOUNT_SUSPENDED", "정지된 계정입니다.")
    if user["user_status"] == "WITHDRAWN":
        raise ApiError(403, "ACCOUNT_WITHDRAWN", "탈퇴한 계정입니다.")

    activity_service.record(user["user_no"], activity_service.LOGIN)

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
    """토큰을 폐기하고 활동이력에 LOGOUT 을 남긴다. 두 가지를 다 한다.

    JWT 는 무상태라 이미 발급한 토큰을 회수할 수 없다. 그래서 폐기 목록을 두는
    대신 사용자마다 "이 시각 이전 발급분은 안 받는다"는 기준선을 세운다
    (users.user_token_valid_from, 검사는 auth._assert_not_revoked).

    **사용자 단위라서 그 사람의 다른 기기도 함께 끊긴다.** 토큰 하나만 죽이려면
    jti 별 폐기 목록이 필요한데, 매 요청 DB 조회가 드는 건 똑같으면서 표가 하나
    더 늘고 만료행 청소까지 따라온다. 관제 계정 규모에서는 기준선 하나가 낫다고 봤다.

    폐기와 기록은 별개다 — 토큰은 죽어도 "언제 나갔나"는 이력에 남아야 한다.
    다만 이 엔드포인트를 프론트가 불러줘야만 둘 다 일어난다. 브라우저를 그냥
    닫으면 토큰은 만료까지 살아있고 LOGOUT 행도 남지 않는다.
    """
    db.execute(
        "UPDATE users SET user_token_valid_from = now() WHERE user_no = %s",
        (g.user["user_no"],),
    )
    activity_service.record(g.user["user_no"], activity_service.LOGOUT)
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

    # user_pw IS NOT NULL 로 소셜 계정을 걸러낸다. 인증코드가 현재 비밀번호 해시를
    # HMAC 입력으로 쓰기 때문에(services/account_recovery.py) NULL 이면 코드 생성
    # 자체가 성립하지 않는다. 걸러진 계정은 '일치하는 계정 없음' 분기로 흘러가므로
    # 응답은 달라지지 않는다 — 계정 존재 여부를 숨기는 이 함수의 방침 그대로다.
    user = db.query_one(
        """
        SELECT user_no, user_pw, user_phone FROM users
        WHERE user_id = %s AND user_name = %s AND user_email = %s
          AND user_status = 'ACTIVE' AND user_pw IS NOT NULL
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

    # request 와 같은 이유로 소셜 계정을 제외한다 (비밀번호 해시가 인증코드의 입력이다)
    user = db.query_one(
        """
        SELECT user_no, user_pw FROM users
        WHERE user_id = %s AND user_status = 'ACTIVE' AND user_pw IS NOT NULL
        """,
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
    activity_service.record(user["user_no"], activity_service.PASSWORD_CHANGED,
                            detail="비밀번호 재설정")
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


@bp.post("/email/verify-request")
def email_verify_request():
    body = request.get_json(silent=True) or {}
    email = require_str(body, "email")
    
    code = str(random.randint(100000, 999999))  # 6자리 랜덤 숫자
    email_storage[email] = code
    
    print(f"[DEBUG] 이메일: {email}, 인증번호: {code}")
    send_email_smtp(email, code)
    
    return jsonify({"message": "인증번호가 발송되었습니다."})


@bp.post("/email/verify-confirm")
def email_verify_confirm():
    body = request.get_json(silent=True) or {}
    email = require_str(body, "email")
    code = require_str(body, "code")
    
    stored_code = email_storage.get(email)
    
    if not stored_code or stored_code != code:
        raise ApiError(400, "INVALID_VERIFY_CODE", "인증번호가 일치하지 않거나 만료되었습니다.")
    
    verified_emails.add(email)
    del email_storage[email]  # 사용된 인증번호 제거
    
    return jsonify({"message": "이메일 인증이 완료되었습니다.", "verified": True})