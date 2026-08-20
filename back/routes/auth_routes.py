"""인증 API.

POST /api/auth/login                        로그인, JWT 발급
POST /api/auth/logout                       로그아웃 (토큰 폐기 + 활동이력 LOGOUT)
GET  /api/auth/me                           내 정보 (세션 복원용)
POST /api/auth/find-id                      아이디 찾기 (이름 + 이메일)
POST /api/auth/password-reset/request       재설정 인증코드 발급 → SMS
POST /api/auth/password-reset/confirm       인증코드 확인 후 비밀번호 변경
POST /api/auth/email/verify-request         회원가입 이메일 인증번호 발송
POST /api/auth/email/verify-confirm         회원가입 이메일 인증번호 확인
GET  /api/auth/<provider>                   소셜 동의화면으로 302
GET  /api/auth/<provider>/callback          프로바이더 콜백 → 프론트로 302 (토큰은 프래그먼트)

계정 찾기 세 개와 소셜 둘은 **비로그인 상태에서 부르는 공개 엔드포인트**다. 인증코드도
소셜 state 도 저장하지 않고 그때그때 계산해 대조한다 — 방식과 근거는
services/account_recovery.py, services/oauth_provider.py 참고.

소셜 로그인은 **리다이렉트 방식 하나뿐이다.** 프론트가 code 를 받아 백엔드에 POST 하던
SPA/JSON 방식(GET /api/auth/oauth/<provider>/authorize, POST /api/auth/oauth/<provider>)
은 프론트가 쓰지 않게 되어 걷어냈다 — 아무도 부르지 않는 로그인 경로를 남겨 두면 인증
표면만 넓어지고, 두 방식이 계정 로직을 공유하는 탓에 한쪽만 고치는 사고가 난다.
필요하면 git 히스토리(e0d6ea6)에서 꺼낼 수 있다.
"""
import logging
from urllib.parse import urlencode

import bcrypt
import psycopg2
from flask import Blueprint, abort, current_app, g, jsonify, redirect, request

import config
from flask import Blueprint, g, jsonify, request
import time
import db
from auth import issue_token, login_required
from errors import ApiError
from services import account_recovery, activity_service, oauth_provider, sms
from utils.validation import require_str, validate_password
import random
import smtplib
from email.mime.text import MIMEText
# 임시 저장소 (메모리 기반)
email_storage = {}      # {email: verification_code}
verified_emails = set()   # 인증 완료된 이메일 목록

import os
from dotenv import load_dotenv
# .env 파일 로드
load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
# 서버 메모리에 인증번호를 잠시 저장할 공간
verification_storage = {}

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
            verification_storage[to_email] = {"code": code, "expires_at": time.time() + 300};
    except Exception as e:
        print(f"이메일 전송 실패: {e}")
        print(f"🚨 [상세 에러 발생]: {repr(e)}")
        raise ApiError(500, "EMAIL_SEND_FAILED", "이메일 전송에 실패했습니다.")
    


bp = Blueprint("auth", __name__)
logger = logging.getLogger("fireguard.auth")

@bp.route("/verify-code", methods=["POST"])
def verify_code():
    data = request.get_json()
    email = data.get("email")
    user_code = data.get("code")

    if not email or not user_code:
        return jsonify({"error": "이메일과 인증번호를 모두 입력해주세요."}), 400

    record = verification_storage.get(email)

    if not record:
        return jsonify({"error": "인증번호가 요청되지 않았거나 만료된 이메일입니다."}), 400

    # 유효시간(5분) 경과 확인
    if time.time() > record["expires_at"]:
        del verification_storage[email]  # 만료된 데이터 삭제
        return jsonify({"error": "인증 시간이 만료되었습니다. 다시 요청해주세요."}), 400

    # 인증번호 일치 여부 확인
    if record["code"] != user_code:
        return jsonify({"error": "인증번호가 일치하지 않습니다."}), 400

    # 검증 성공 시 저장소에서 제거 (재사용 방지)
    del verification_storage[email]

    return jsonify({"message": "이메일 인증이 완료되었습니다."}), 200

# 재설정 요청의 고정 응답 — 정보가 맞든 틀리든 똑같이 나간다 (계정 존재 여부 은닉)
_RESET_ACCEPTED = {
    "message": "정보가 일치하면 등록된 연락처로 인증코드를 보냈습니다.",
    "expires_in_sec": account_recovery.BUCKET_SEC * account_recovery.VALID_BUCKETS,
}


# 계정 찾기·비밀번호 재설정이 대상으로 삼는 상태 — 지금 정상적으로 쓰이는 계정이다.
# PENDING(관리자 승격 승인 대기)은 권한만 기다릴 뿐 로그인도 되는 정상 계정이라 포함한다.
# 빼면 승인이 날 때까지 아이디 찾기도 비밀번호 재설정도 막혀, 승인 대기가 곧 계정 잠금이 된다.
# 정지·탈퇴는 되찾아 봐야 로그인이 막혀 있으므로 제외한다.
RECOVERABLE_STATUSES = ["ACTIVE", "PENDING"]


def _assert_account_usable(user: dict) -> None:
    """정지·탈퇴 계정을 막는다. 로그인 경로가 둘(일반·소셜)이라 한 곳에 모아 뒀다.

    비밀번호가 맞았는지(소셜이면 프로바이더 인증을 통과했는지) 확인한 **뒤에**
    부른다 — 순서를 바꾸면 아무나 아이디만 넣어보고 그 계정이 정지 상태인지
    알아낼 수 있다.
    """
    if user["user_status"] == "SUSPENDED":
        raise ApiError(403, "ACCOUNT_SUSPENDED", "정지된 계정입니다.")
    if user["user_status"] == "WITHDRAWN":
        raise ApiError(403, "ACCOUNT_WITHDRAWN", "탈퇴한 계정입니다.")


def _login_response(user: dict) -> dict:
    """로그인 성공 응답. 일반·소셜이 **완전히 같은 모양**이어야 한다.

    프론트가 두 버튼의 결과를 같은 코드로 받아 저장하게 하려는 것이다. 여기서
    갈라지면 소셜 로그인만 세션 복원이 안 되는 식의 버그가 나기 쉽다.
    """
    return {
        "access_token": issue_token(user),
        "user": {
            "user_no": user["user_no"],
            "user_id": user["user_id"],
            "user_name": user["user_name"],
            "user_role": user["user_role"],
        },
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
    _assert_account_usable(user)

    activity_service.record(user["user_no"], activity_service.LOGIN)
    return jsonify(_login_response(user))


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

    **소셜 계정도 이 경로 그대로다.** 기준선은 user_no 만 보고 토큰이 어떤 경로로
    발급됐는지는 따지지 않으므로, 소셜 로그인이 붙었다고 여기에 더할 일이 없다.

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
        WHERE user_name = %s AND user_email = %s AND user_status = ANY(%s)
        ORDER BY user_no
        """,
        (user_name, user_email, RECOVERABLE_STATUSES),
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
          AND user_status = ANY(%s) AND user_pw IS NOT NULL
        """,
        (user_id, user_name, user_email, RECOVERABLE_STATUSES),
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
        WHERE user_id = %s AND user_status = ANY(%s) AND user_pw IS NOT NULL
        """,
        (user_id, RECOVERABLE_STATUSES),
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


# ---------- 소셜 로그인 (구글·카카오·네이버) ----------

def _require_provider(raw: str) -> str:
    """경로의 provider 를 표의 키로 바꾸고, 쓸 수 있는 상태인지까지 확인한다.

    키 미설정을 500 이 아니라 503 으로 따로 내는 이유: 키 없이 배포된 상태에서
    500 이 나면 로그만 보고는 원인을 찾을 수 없다. 프론트도 "이 버튼은 아직 준비
    안 됨"으로 안내할 수 있다.
    """
    provider = oauth_provider.normalize_provider(raw)
    if provider is None:
        raise ApiError(400, "UNSUPPORTED_PROVIDER", "지원하지 않는 소셜 로그인입니다.")
    if not oauth_provider.is_configured(provider):
        raise ApiError(503, "OAUTH_NOT_CONFIGURED",
                       "해당 소셜 로그인이 서버에 설정되어 있지 않습니다.")
    return provider


def _find_or_create_social_user(provider: str, identity: dict) -> dict:
    """(user_provider, user_provider_id) 로 찾고, 없으면 새로 만든다.

    **이메일이 같은 일반(LOCAL) 계정과 자동으로 연결하지 않는다.** 프로바이더가 그
    이메일의 소유를 실제로 검증했는지 우리는 보장할 수 없어서다. 검증하지 않는
    프로바이더에 피해자의 이메일로 계정을 만들어 로그인하면 우리 쪽 계정을 그대로
    가져가게 된다 — 관리자 계정이면 시스템 전체가 넘어간다. 그래서 이메일이
    겹쳐도 별개 계정으로 만든다. 같은 사람의 계정 두 개를 합치는 일은 본인 확인을
    거친 별도 기능(로그인 상태에서 소셜 연결)으로 다뤄야 할 문제다.
    """
    select_sql = """
        SELECT user_no, user_id, user_name, user_role, user_status
        FROM users WHERE user_provider = %s AND user_provider_id = %s
    """
    user = db.query_one(select_sql, (provider, identity["provider_id"]))
    if user:
        return user

    # user_id 는 로그인에 쓰이지 않는 합성값이다 — 아이디 유니크 제약을 지키려고
    # 두는 것뿐이라 프로바이더 값에서 기계적으로 만든다 (컬럼이 varchar(50)).
    user_id = f"{provider.lower()}_{identity['provider_id']}"[:50]
    try:
        row = db.execute_returning(
            """
            INSERT INTO users (user_id, user_pw, user_name, user_email,
                               user_role, user_status, user_provider, user_provider_id)
            VALUES (%s, NULL, %s, %s, 'VIEWER', 'ACTIVE', %s, %s)
            RETURNING user_no, user_id, user_name, user_role, user_status
            """,
            # 컬럼 길이를 넘기면 DataError 로 로그인 전체가 실패한다. 프로바이더가
            # 주는 값의 길이를 우리가 정할 수 없으므로 잘라서 받는다.
            (user_id, (identity["name"] or None) and identity["name"][:50],
             (identity["email"] or None) and identity["email"][:100],
             provider, identity["provider_id"]),
        )
    except psycopg2.IntegrityError:
        # 같은 사람이 로그인 버튼을 두 번 눌러 요청이 겹치면 둘 다 '없음'을 보고
        # INSERT 하러 온다. 늦은 쪽은 UQ_USERS_PROVIDER 에 막히는데, 그때는 이미
        # 행이 있으므로 다시 읽어 그대로 진행하는 편이 사용자에게 옳다.
        user = db.query_one(select_sql, (provider, identity["provider_id"]))
        if user:
            return user
        # 여기까지 오면 막힌 것은 user_id 쪽이다 — 50자로 자르면서 다른 계정과
        # 겹쳤거나, 같은 이름의 일반 계정이 이미 있다. 자동으로 이름을 바꿔 만들면
        # 계정이 조용히 늘어나므로 사람이 보게 남긴다.
        logger.warning("소셜 계정 생성 실패 — user_id 충돌 (provider=%s, user_id=%s)",
                       provider, user_id)
        raise ApiError(409, "DUPLICATE_USER_ID", "이미 사용 중인 아이디입니다.")

    logger.info("소셜 계정 신규 생성 (provider=%s, user_no=%s)", provider, row["user_no"])
    return row


# ---------- 소셜 로그인 — 시작과 콜백 ----------
#
# 프로바이더가 브라우저를 **백엔드로 곧장** 되돌려보내고, 백엔드가 그 자리에서
# code 를 교환해 프론트로 302 한다 (front/src/api.js 의 startOAuthLogin 이 전제하는
# 모양). 프론트는 code 도 state 도 만지지 않는다.

def _front_redirect(**fragment_params):
    """프론트로 302 하되 값은 **프래그먼트(#)에** 싣는다.

    쿼리스트링(?)에 넣지 않는 이유가 이 방식의 핵심이다 — 쿼리는 웹서버·프록시
    접근로그에 그대로 쌓이고 다음 요청의 Referer 헤더에도 실려 나가지만,
    프래그먼트는 브라우저가 서버로 아예 보내지 않는다. 여기 실리는 것이 로그인
    토큰이라 그 차이가 곧 유출 여부다.

    오류 코드도 같은 자리에 실어서 프론트가 성공·실패를 한 곳에서 읽게 한다.
    """
    return redirect(f"{config.OAUTH_REDIRECT_BASE.rstrip('/')}/#{urlencode(fragment_params)}")


def _abort_if_shadowing_another_route() -> None:
    """이 규칙이 **다른 메서드 전용 엔드포인트를 가로챈** 요청이면 405 로 돌려보낸다.

    `/api/auth/<provider>` 는 `/api/auth/login`(POST 전용) 같은 경로와 모양이 겹친다.
    정적 규칙이 동적 규칙을 이기는 것은 **메서드까지 맞을 때** 이야기고, GET 으로
    /api/auth/login 을 부르면 Werkzeug 는 405 를 내기 전에 GET 을 받는 이 동적
    규칙을 찾아낸다. 그대로 두면 POST 전용 엔드포인트 전부가 GET 에
    "지원하지 않는 소셜 로그인" 302 를 돌려주게 되고, 공통 405 응답이 깨진다
    (회귀 테스트: tests/test_health_errors.py::test_405_returns_common_error_shape).

    같은 경로를 GET 아닌 메서드로 받는 규칙이 따로 있으면 그쪽이 주인이라고 본다.
    이름을 목록으로 적어 두지 않는 이유는, 그 목록이 곧 낡아서 다음에 추가되는
    POST 엔드포인트에서 같은 사고가 조용히 재발하기 때문이다.
    """
    others = set(current_app.url_map.bind("localhost").allowed_methods(request.path))
    if others - {"GET", "HEAD", "OPTIONS"}:
        abort(405)


# ⚠️ 이 규칙은 `/api/auth/me` 처럼 **한 조각짜리 GET 경로를 삼킬 수 있는 모양**이다.
#    Werkzeug 는 정적 규칙을 동적 규칙보다 먼저 맞추므로 실제로는 /me 가 이기고,
#    그 사실은 회귀 테스트로 못을 박아 뒀다 (tests/test_oauth_redirect_login.py::
#    test_me_route_is_not_swallowed_by_the_provider_rule). 다만 그 보호는 '더
#    구체적인 규칙이 이긴다'는 규칙 하나에만 기대고 있다 — /api/auth 아래에 **동적
#    세그먼트로 시작하는 GET 경로를 또 추가하면** 그 순간 서로 잡아먹는다.
@bp.get("/<provider>")
def oauth_redirect_start(provider: str):
    """소셜 로그인 시작 — 프로바이더 동의화면으로 302 한다 (비로그인 공개).

    프론트는 window.location.assign('/api/auth/kakao') 한 줄이면 된다. state 는
    여기서 발급해 URL 에 싣고 콜백에서 HMAC 으로 대조하므로, 프론트가 보관할 것도
    돌려줄 것도 없다.

    실패해도 JSON 을 주지 않는다 — 브라우저가 주소창째로 이동해 온 곳이라 JSON 을
    돌려주면 사용자 화면에 원시 JSON 이 그대로 뜬다. 콜백과 같은 자리(프래그먼트의
    oauth_error)로 알려서 프론트가 한 곳에서 읽게 한다.
    """
    _abort_if_shadowing_another_route()
    try:
        name = _require_provider(provider)
    except ApiError as exc:
        return _front_redirect(oauth_error=exc.code)

    state = oauth_provider.issue_state(name)
    return redirect(oauth_provider.authorize_url(name, state))


@bp.get("/<provider>/callback")
def oauth_redirect_callback(provider: str):
    """프로바이더가 브라우저를 되돌려보내는 곳 (비로그인 공개).

    **어떤 경우에도 302 다.** 사용자의 브라우저가 이 응답을 따라오는 중이라
    JSON 을 주면 화면에 원시 JSON 이 뜬다. 그래서 실패도 프론트로 돌려보내고
    프래그먼트의 oauth_error 로 알린다 (코드 문자열은 다른 API 의 error code 와 같은
    것을 쓴다 — 프론트가 안내 문구를 한 표에서 찾게 하려는 것이다).
    """
    # 지금은 `.../callback` 으로 끝나는 다른 경로가 없어 겹칠 일이 없지만, 시작
    # 라우트와 같은 위험을 안고 있으므로 같은 가드를 둔다 (판단 근거는 그 함수).
    _abort_if_shadowing_another_route()

    # 1. 사용자가 동의화면에서 취소했거나 프로바이더가 오류를 알려온 경우 — code 가
    #    없으므로 교환할 것이 없다. 취소는 오류가 아니라 사용자의 선택이라 저쪽
    #    장애와 구분한다. 뭉치면 프로바이더 장애를 "취소하셨습니다"로 안내하게 된다.
    provider_error = request.args.get("error")
    if provider_error:
        logger.info("소셜 로그인 콜백이 오류로 돌아옴 (provider=%s, error=%s)",
                    provider, provider_error)
        return _front_redirect(oauth_error="ACCESS_DENIED"
                               if provider_error == "access_denied"
                               else "OAUTH_PROVIDER_ERROR")

    # 2. 아래 헬퍼들은 일반 로그인과 공유하는 것들이라 ApiError 를 던진다 (저쪽은
    #    그대로 JSON 응답이 된다). 여기서는 한 번에 받아 code 만 꺼내 302 로 바꾼다.
    try:
        name = _require_provider(provider)

        # state 를 code 보다 먼저 본다 — 위조된 요청으로 프로바이더를 두드려 주면
        # 우리 서버가 남의 API 를 때리는 도구가 된다.
        state = request.args.get("state") or ""
        if not oauth_provider.verify_state(name, state):
            raise ApiError(400, "INVALID_OAUTH_STATE",
                           "인증 요청이 만료되었거나 올바르지 않습니다.")

        code = request.args.get("code")
        if not code:
            # error 도 code 도 없이 돌아오는 것은 프로바이더가 규약을 어긴 것이다.
            # 사용자가 고칠 수 있는 게 아니라 BAD_REQUEST 로 부르지 않는다.
            raise ApiError(502, "OAUTH_PROVIDER_ERROR",
                           "소셜 로그인 제공자의 응답이 올바르지 않습니다.")

        try:
            identity = oauth_provider.fetch_identity(name, code, state)
        except oauth_provider.OAuthProviderError as exc:
            logger.warning("소셜 로그인 실패 (provider=%s): %s", name, exc)
            raise ApiError(502, "OAUTH_PROVIDER_ERROR",
                           "소셜 로그인 제공자와 통신하지 못했습니다.") from exc

        user = _find_or_create_social_user(name, identity)
        _assert_account_usable(user)
    except ApiError as exc:
        return _front_redirect(oauth_error=exc.code)

    activity_service.record(user["user_no"], activity_service.LOGIN)
    # _login_response 를 쓰지 않고 토큰만 만든다 — 사용자 정보는 프론트가 이 토큰으로
    # GET /api/auth/me 를 부르면 되고, URL 에 개인정보를 실을 이유가 없다.
    return _front_redirect(access_token=issue_token(user))
