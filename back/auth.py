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
import hmac

import jwt
from flask import g, request

import config
import db
from errors import ApiError


def issue_token(user: dict) -> str:
    """로그인 성공 시 JWT 를 발급한다."""
    payload = {
        "user_no": user["user_no"],
        "user_id": user["user_id"],
        "user_role": user["user_role"],
        "user_status": user.get("user_status", "ACTIVE"),  # 계정 상태(user_status) 추가
        "exp": datetime.now(timezone.utc) + timedelta(hours=config.JWT_EXPIRES_HOURS),
        # 발급 시각 — 토큰 폐기(_assert_not_revoked)가 이 값을 기준선과 대조한다.
        # exp 다음에 둔 것은 순서에 뜻이 있어서가 아니라, 바로 위 user_status 줄이
        # 다른 사람이 쓴 줄이라 붙여 쓰면 병합 충돌이 나기 쉬워서다.
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def _decode_token() -> dict:
    """Authorization 헤더의 JWT 를 검증해 payload 를 돌려준다.

    **토큰이 없는 것과 틀린 것을 구분한다.** 헤더가 아예 없으면 UNAUTHORIZED,
    있는데 검증에 실패하면 INVALID_TOKEN 이다. 이 구분이 사라지면 프론트가
    "로그인하러 보내야 하는 상황"과 "토큰이 상해서 다시 받아야 하는 상황"을
    가릴 수 없고, 명세서(401 UNAUTHORIZED)와도 어긋난다.

    따옴표를 벗기는 것은 프론트가 토큰을 `Bearer "eyJ..."` 처럼 따옴표째 실어
    보낸 적이 있어서다 — 값 자체는 멀쩡하므로 받아준다.

    (이전 구현은 토큰 전체 길이로 base64 패딩을 맞추는 코드를 갖고 있었는데,
     JWT 의 패딩은 header.payload.signature 조각별이라 전체 길이로 계산하는 것은
     의미가 없고 PyJWT 가 조각마다 알아서 처리한다. 유효 토큰 200개로 확인했다.)
    """
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise ApiError(401, "UNAUTHORIZED", "인증 토큰이 필요합니다.")
    token = header.removeprefix("Bearer ").strip().strip('"').strip("'")

    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "TOKEN_EXPIRED", "토큰이 만료되었습니다.")
    except jwt.InvalidTokenError:
        raise ApiError(401, "INVALID_TOKEN", "유효하지 않은 토큰입니다.")

def _assert_not_revoked(payload: dict) -> None:
    """로그아웃·정지 이후에 발급된 토큰인지 확인한다.

    JWT 는 무상태라 이미 내보낸 토큰을 회수할 수 없다. 그래서 사용자마다
    "이 시각 이전 발급분은 안 받는다"는 기준선(users.user_token_valid_from)을
    두고 매 요청 대조한다. 로그아웃과 계정 정지·탈퇴가 그 값을 세운다.

    검사가 _decode_token 이 아니라 여기 있는 이유는 관심사가 다르기 때문이다 —
    저쪽은 "이 토큰이 진짜인가", 이쪽은 "아직 살아있는가".

    **비교를 SQL 에서 하는 것이 중요하다.** 시간 컬럼은 타임존 없는 timestamp 이고
    now() 는 DB 서버 로컬 시각을 넣는데, iat 는 UTC epoch 초다. 파이썬에서
    naive datetime 을 .timestamp() 하면 클라이언트 로컬 시각으로 해석해서
    DB 서버 타임존이 UTC 가 아니면 몇 시간씩 어긋난다.

    date_trunc('second') 도 필수다. iat 는 정수 초인데 now() 는 마이크로초까지
    있어서, 자르지 않으면 로그아웃 직후 같은 초에 재로그인했을 때 방금 받은
    새 토큰이 즉시 거부된다(iat=100 < 컷오프 100.7). 자르면 폐기가 최대 1초
    늦게 걸리는 대신 그 자물쇠가 사라진다.
    """
    row = db.query_one(
        """
        SELECT date_trunc('second', user_token_valid_from) > to_timestamp(%s)::timestamp
               AS revoked
        FROM users WHERE user_no = %s
        """,
        # iat 가 없는 배포 이전 토큰은 0(1970년)으로 본다 — 기준선이 있으면 거부된다
        (payload.get("iat", 0), payload["user_no"]),
    )
    if row is None:
        # 토큰은 유효한데 사용자 행이 사라진 경우 (삭제된 계정)
        raise ApiError(401, "INVALID_TOKEN", "유효하지 않은 토큰입니다.")
    if row["revoked"]:  # 기준선이 NULL 이면 비교 결과도 NULL → 거짓으로 취급된다
        raise ApiError(401, "TOKEN_REVOKED",
                       "로그아웃되었거나 무효화된 토큰입니다. 다시 로그인해주세요.")


def caller_role() -> str | None:
    """요청자의 권한 등급을 돌려준다. 판별할 수 없으면 None — **예외를 던지지 않는다.**

    인증을 걸 수 없는 공개 엔드포인트가 "그래도 관리자가 부른 것이라면 다르게
    처리"해야 할 때 쓴다. 지금은 회원가입(POST /api/users)이 그렇다 — 가입 화면이
    토큰 없이 부르는 경로라 admin_required 를 걸 수 없는데, 그렇다고 본문의
    user_role 을 그대로 믿으면 누구나 관리자 계정을 만들 수 있다.

    토큰이 없거나·깨졌거나·폐기됐으면 전부 None 이다. 인증 실패를 오류로 알리는
    자리가 아니라 '누가 불렀는지 아는가'만 판별하는 자리이므로 조용히 넘긴다.
    """
    try:
        payload = _decode_token()
        _assert_not_revoked(payload)
    except ApiError:
        return None
    return payload.get("user_role")


def login_required(f):
    """토큰 검증 후 g.user 에 payload 를 넣는다."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        g.user = _decode_token()
        _assert_not_revoked(g.user)
        return f(*args, **kwargs)
    wrapper._auth = "bearer"  # openapi.yaml 의 security 선언과 대조된다 (test_openapi.py)
    return wrapper


def admin_required(f):
    """ADMIN 권한까지 요구한다."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        g.user = _decode_token()
        _assert_not_revoked(g.user)
        if g.user.get("user_role") != "ADMIN":
            raise ApiError(403, "FORBIDDEN", "관리자 권한이 필요합니다.")
        return f(*args, **kwargs)
    wrapper._auth = "bearer"
    return wrapper


def _key_matches(header_name: str, expected: str) -> bool:
    """헤더 값을 상수 시간에 대조한다.

    문자열 != 는 첫 불일치에서 비교를 멈추므로 '접두어가 몇 글자 맞았는지'가
    응답 시간으로 새어 나간다(타이밍 어택). compare_digest 는 결과와 무관하게
    같은 시간에 끝난다. str 이 아니라 bytes 로 비교하는 것은 compare_digest 가
    ASCII 밖의 str 을 TypeError 로 거절하기 때문이다 — 이상한 인코딩 헤더로
    500 이 나는 것까지 막는다.
    """
    supplied = request.headers.get(header_name) or ""
    return hmac.compare_digest(supplied.encode(), expected.encode())


def internal_key_required(f):
    """내부 시스템(AI 모델) 전용 인증 — X-Internal-Key 헤더를 비교한다.

    JWT 와 무관하며, 키가 없거나 다르면 401 INTERNAL_UNAUTHORIZED.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not _key_matches("X-Internal-Key", config.INTERNAL_API_KEY):
            raise ApiError(401, "INTERNAL_UNAUTHORIZED", "내부 API 키가 올바르지 않습니다.")
        return f(*args, **kwargs)
    wrapper._auth = "internal"
    return wrapper


def agency_key_required(f):
    """소방서(119) 전용 인증 — X-Agency-Key 헤더를 비교한다.

    출동 통지를 되쏘는 상대는 사람이 아니라 기관 서버라 JWT 를 쓸 수 없다.
    내부 키(X-Internal-Key)와 나눠 쓴다 — 하나가 새더라도 AI 검출 수집
    경로까지 함께 열리지는 않게 한다.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not _key_matches("X-Agency-Key", config.AGENCY_CALLBACK_KEY):
            raise ApiError(401, "AGENCY_UNAUTHORIZED", "기관 인증 키가 올바르지 않습니다.")
        return f(*args, **kwargs)
    wrapper._auth = "agency"
    return wrapper