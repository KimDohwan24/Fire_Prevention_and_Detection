# import random
# import smtplib
# from email.mime.text import MIMEText
# from fastapi import FastAPI, HTTPException, status, Query
# from fastapi.middleware.cors import CORSMiddleware
# from passlib.context import CryptContext
# from schemas import EmailRequest, EmailVerifyRequest, UserSignupRequest
# from db import query_one, execute


# app = FastAPI(redirect_slashes=False)

# # CORS 설정 (프론트엔드 연동용)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # 비밀번호 암호화 설정
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# # 임시 저장소 (실제 프로젝트에서는 Redis나 DB 사용 권장)
# email_storage = {}  # {email: verification_code}
# verified_emails = set()  # 인증 완료된 이메일 목록

# # SMTP 설정 (Gmail 예시)
# SMTP_SERVER = "smtp.gmail.com"
# SMTP_PORT = 587
# SENDER_EMAIL = "songjonghan96@gmail.com"
# SENDER_PASSWORD = "geaexurrnrdegrnm"  # 구글 앱 비밀번호

# def send_email_smtp(to_email: str, code: str):
#     msg = MIMEText(f"[FireGuard] 회원가입 인증번호는 [{code}] 입니다. 5분 안에 입력해주세요.")
#     msg["Subject"] = "[FireGuard] 회원가입 이메일 인증번호"
#     msg["From"] = SENDER_EMAIL
#     msg["To"] = to_email

#     try:
#         with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
#             server.starttls()
#             server.login(SENDER_EMAIL, SENDER_PASSWORD)
#             server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
#     except Exception as e:
#         print(f"이메일 전송 실패: {e}")
#         print(f"🚨 [상세 에러 발생]: {repr(e)}") # 에러 종류를 정확히 출력
#         raise HTTPException(status_code=500, detail="이메일 전송에 실패했습니다.")

# # 0. 아이디 중복 확인 API (실제 PostgreSQL 연동)
# @app.get("/api/auth/check-id", strict_slashes=False)
# def check_id(user_id: str = Query(..., description="중복 확인할 아이디")):
#     if not user_id.strip():
#         raise HTTPException(status_code=400, detail="아이디를 입력해주세요.")
    
#     # db.py의 query_one을 사용해 데이터베이스 조회
#     # (search_path가 fireguard로 설정되어 있으므로 users 테이블 직접 조회 가능)
#     user = query_one("SELECT * FROM users WHERE user_id = %s", (user_id,))
    
#     is_duplicated = user is not None

#     return {
#         "user_id": user_id,
#         "available": not is_duplicated
#     }

# # 1. 이메일 인증번호 요청 API
# @app.post("/api/email/verify-request")
# def request_email_verification(data: EmailRequest):
#     code = str(random.randint(100000, 999999))  # 6자리 랜덤 숫자
#     email_storage[data.email] = code
    
#     # 실제 이메일 전송 (테스트 시 콘솔 확인용으로 print도 함께 두면 편합니다)
#     print(f"[DEBUG] 이메일: {data.email}, 인증번호: {code}")
#     send_email_smtp(data.email, code)
    
#     return {"message": "인증번호가 발송되었습니다."}


# # 2. 이메일 인증번호 확인 API
# @app.post("/api/email/verify-confirm")
# def confirm_email_verification(data: EmailVerifyRequest):
#     stored_code = email_storage.get(data.email)
    
#     if not stored_code or stored_code != data.code:
#         raise HTTPException(status_code=400, detail="인증번호가 일치하지 않거나 만료되었습니다.")
    
#     # 인증 성공 처리
#     verified_emails.add(data.email)
#     del email_storage[data.email]  # 사용된 인증번호 제거
#     return {"message": "이메일 인증이 완료되었습니다.", "verified": True}


# # 3. 회원가입 API
# @app.post("/api/users")
# def signup(data: UserSignupRequest):
#     # 이메일 인증 여부 확인
#     if data.user_email not in verified_emails:
#         raise HTTPException(status_code=400, detail="이메일 인증이 완료되지 않았습니다.")
    
#     # 비밀번호 암호화
#     hashed_password = pwd_context.hash(data.user_pw)
    
#     # TODO: DB 저장 로직 구현 (예: SQLAlchemy를 사용해 데이터베이스에 insert)
#     # db_user = User(user_id=data.user_id, user_pw=hashed_password, ...)
#     # db.add(db_user); db.commit()
    
#     # 가입 완료 후 인증 목록에서 제거
#     verified_emails.remove(data.user_email)
    
#     return {"message": "회원가입이 완료되었습니다."}


import re
import random
import smtplib
from utils.validation import validate_user_name, validate_user_id, validate_password
from email.mime.text import MIMEText
from flask import Blueprint, request, jsonify
from passlib.context import CryptContext
from db import query_one, execute

# Flask Blueprint 생성 (FastAPI의 APIRouter 역할)
# url_prefix를 '/api'로 설정하여 아래 라우트들은 자동으로 /api로 시작함
signup_bp = Blueprint('signup', __name__, url_prefix='/api')

# 비밀번호 암호화 설정
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 임시 저장소
email_storage = {}  
verified_emails = set()  

# SMTP 설정
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "songjonghan96@gmail.com"
SENDER_PASSWORD = "geaexurrnrdegrnm" 

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
        # Flask에서는 HTTP 에러를 튜플 형태로 반환하거나 abort() 사용
        raise RuntimeError("이메일 전송에 실패했습니다.")


# 0. 아이디 중복 및 형식 확인 API (중복확인 버튼 클릭 시 호출)
@signup_bp.route("/auth/check-id", methods=["GET"], strict_slashes=False)
def check_id():
    user_id = request.args.get("user_id")
    
    # 1. 빈 값 체크
    if not user_id or not user_id.strip():
        return jsonify({"detail": "아이디를 입력해주세요."}), 400
    
    # 2. 아이디 유효성 검사 (영문과 숫자만 허용)
    if not re.match(r"^[a-zA-Z0-9]+$", user_id):
        print("🚨 [디버깅] 정규식 차단 작동함 (한글/특수문자 감지)")  # 👈 정규식 통과 실패 시 찍힘
        return jsonify({"detail": "아이디는 영문과 숫자만 사용할 수 있습니다."}), 400
    
    # 3. 데이터베이스 중복 조회
    user = query_one("SELECT * FROM users WHERE user_id = %s", (user_id,))
    if user:
        return jsonify({"detail": "이미 존재하는 아이디입니다."}), 400

    return jsonify({
        "message": "사용 가능한 아이디입니다.",
        "available": True
    })


# 1. 이메일 인증번호 요청 API
@signup_bp.route("/email/verify-request", methods=["POST"], strict_slashes=False)
def request_email_verification():
    data = request.get_json()
    email = data.get("email")
    
    code = str(random.randint(100000, 999999))
    email_storage[email] = code
    
    print(f"[DEBUG] 이메일: {email}, 인증번호: {code}")
    send_email_smtp(email, code)
    
    return jsonify({"message": "인증번호가 발송되었습니다."})


# 2. 이메일 인증번호 확인 API
@signup_bp.route("/email/verify-confirm", methods=["POST"], strict_slashes=False)
def confirm_email_verification():
    data = request.get_json()
    email = data.get("email")
    code = data.get("code")
    
    stored_code = email_storage.get(email)
    
    if not stored_code or stored_code != code:
        return jsonify({"detail": "인증번호가 일치하지 않거나 만료되었습니다."}), 400
    
    # 인증 성공 처리
    verified_emails.add(email)
    del email_storage[email]
    return jsonify({"message": "이메일 인증이 완료되었습니다.", "verified": True})


# 3. 회원가입 API
@signup_bp.route("/users", methods=["POST"], strict_slashes=False)
def signup():
    data = request.get_json()
    print("🚨 [확인용] 진짜 signup 함수 진입함! 받은 데이터:", data)
    
    # 1. 공통 도구함에서 가져온 함수들로 안전하게 검증 및 데이터 추출
    user_name = validate_user_name(data.get("user_name"))
    user_id = validate_user_id(data.get("user_id"))
    user_pw = validate_password(data.get("user_pw"), user_id)
    user_email = data.get("user_email")
    user_address = data.get("user_address")
    user_gender = data.get("user_gender")

    # 2. 성별 유효성 검사 (남성, 여성, 선택안함 중 하나인지 확인)
    allowed_genders = ["남성", "여성", "선택안함"]
    if not user_gender or user_gender not in allowed_genders:
        return jsonify({"detail": "올바른 성별을 선택해주세요."}), 400
    
    # 3. 주소 빈칸(공백 포함) 검증
    if not user_address or not str(user_address).strip():
        return jsonify({"detail": "주소를 입력해주세요."}), 400
    
    # 4. 이메일 인증 여부 확인
    if user_email not in verified_emails:
        return jsonify({"detail": "이메일 인증이 완료되지 않았습니다."}), 400
    
    # 5. 아이디 중복 최종 확인 (방어 로직)
    existing_user = query_one("SELECT * FROM users WHERE user_id = %s", (user_id,))
    if existing_user:
        return jsonify({"detail": "이미 존재하는 아이디입니다."}), 400
    
    # 6. 비밀번호 암호화
    hashed_password = pwd_context.hash(user_pw)
    
    # 7. DB 저장 (💡 누락되었던 user_name 컬럼과 값 추가 완료!)
    execute(
        "INSERT INTO users (user_id, user_pw, user_email, user_address, user_gender, user_name) VALUES (%s, %s, %s, %s, %s, %s)",
        (user_id, hashed_password, user_email, user_address.strip(), user_gender, user_name)
    )
    
    # 8. 가입 완료 후 인증 목록에서 제거
    verified_emails.remove(user_email)
    
    return jsonify({"message": "회원가입이 완료되었습니다."})