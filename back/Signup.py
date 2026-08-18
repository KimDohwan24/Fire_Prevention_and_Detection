import random
import smtplib
from email.mime.text import MIMEText
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from schemas import EmailRequest, EmailVerifyRequest, UserSignupRequest

app = FastAPI()

# CORS 설정 (프론트엔드 연동용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 비밀번호 암호화 설정
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 임시 저장소 (실제 프로젝트에서는 Redis나 DB 사용 권장)
email_storage = {}  # {email: verification_code}
verified_emails = set()  # 인증 완료된 이메일 목록

# SMTP 설정 (Gmail 예시)
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
        print(f"🚨 [상세 에러 발생]: {repr(e)}") # 에러 종류를 정확히 출력
        raise HTTPException(status_code=500, detail="이메일 전송에 실패했습니다.")


# 1. 이메일 인증번호 요청 API
@app.post("/api/email/verify-request")
def request_email_verification(data: EmailRequest):
    code = str(random.randint(100000, 999999))  # 6자리 랜덤 숫자
    email_storage[data.email] = code
    
    # 실제 이메일 전송 (테스트 시 콘솔 확인용으로 print도 함께 두면 편합니다)
    print(f"[DEBUG] 이메일: {data.email}, 인증번호: {code}")
    send_email_smtp(data.email, code)
    
    return {"message": "인증번호가 발송되었습니다."}


# 2. 이메일 인증번호 확인 API
@app.post("/api/email/verify-confirm")
def confirm_email_verification(data: EmailVerifyRequest):
    stored_code = email_storage.get(data.email)
    
    if not stored_code or stored_code != data.code:
        raise HTTPException(status_code=400, detail="인증번호가 일치하지 않거나 만료되었습니다.")
    
    # 인증 성공 처리
    verified_emails.add(data.email)
    del email_storage[data.email]  # 사용된 인증번호 제거
    return {"message": "이메일 인증이 완료되었습니다.", "verified": True}


# 3. 회원가입 API
@app.post("/api/users")
def signup(data: UserSignupRequest):
    # 이메일 인증 여부 확인
    if data.user_email not in verified_emails:
        raise HTTPException(status_code=400, detail="이메일 인증이 완료되지 않았습니다.")
    
    # 비밀번호 암호화
    hashed_password = pwd_context.hash(data.user_pw)
    
    # TODO: DB 저장 로직 구현 (예: SQLAlchemy를 사용해 데이터베이스에 insert)
    # db_user = User(user_id=data.user_id, user_pw=hashed_password, ...)
    # db.add(db_user); db.commit()
    
    # 가입 완료 후 인증 목록에서 제거
    verified_emails.remove(data.user_email)
    
    return {"message": "회원가입이 완료되었습니다."}