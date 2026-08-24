"""요청 값 검증 공통 도구 — 형식 오류는 모두 400 BAD_REQUEST 로 통일한다.

쿼리스트링용:
    int_param("cctv_no")     정수 파라미터 (없으면 None)
    date_param("date_from")  YYYY-MM-DD 파라미터 (없으면 None)

JSON 본문용:
    require_str(body, "cctv_name")   빈 문자열("") · 공백 문자열 거부
    require_number(body, "cctv_lat") JSON 숫자(int/float)만 허용
                                     ("37.5" 같은 숫자 문자열도 거부)
    validate_phone(body, "user_phone") 하이픈 없이 숫자만 (키 없음 · null 은 통과)
    validate_user_id(value)          아이디 작성규칙 (POST /api/users)
    validate_password(value, user_id) 비밀번호 작성규칙 (POST · PUT /api/users)

아이디·비밀번호 작성규칙 근거:
    - user_id: 5~20자, 영문 소문자·숫자·특수기호(_, -), 시작은 영문 소문자
      (네이버 아이디 작성 규칙 참고)
    - user_pw: 「개인정보의 안전성 확보조치 기준」 및 KISA 「패스워드 선택 및
      이용 안내서」 권고를 바탕으로 영문자·숫자·특수문자 3종을 모두 포함해
      8자 이상(최대 64자). 여기에 동일 문자 3회 이상 반복, 연속 문자열
      (1234·abcd 등) 4자 이상, 키보드 배열 문자열(qwer·asdf 등),
      아이디 포함을 추가로 금지한다.
"""
import re
from datetime import datetime

from flask import request

from errors import ApiError

# 이름: 영문, 한글만 허용 (특수문자, 공백, 숫자 불가)
USER_NAME_RE = re.compile(r"^[a-zA-Z가-힣]+$")

def validate_user_name(value) -> str:
    """user_name 작성규칙 검증: 영문, 한글만 허용 (공백, 숫자, 특수문자 불가). 위반 시 400."""
    if not isinstance(value, str) or not USER_NAME_RE.fullmatch(value):
        raise ApiError(
            400, "BAD_REQUEST",
            "이름은 영문과 한글만 사용할 수 있습니다. (공백, 숫자, 특수문자 불가)",
            field="user_name",
        )
    return value

def int_param(name: str) -> int | None:
    """쿼리스트링에서 정수 파라미터를 읽는다. 없으면 None, 형식 오류면 400."""
    v = request.args.get(name)
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        raise ApiError(400, "BAD_REQUEST", f"{name} 는 정수여야 합니다.", field=name)


def date_param(name: str) -> str | None:
    """쿼리스트링에서 YYYY-MM-DD 파라미터를 읽는다. 없으면 None, 형식 오류면 400."""
    v = request.args.get(name)
    if not v:
        return None
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        raise ApiError(400, "BAD_REQUEST", f"{name} 는 YYYY-MM-DD 형식이어야 합니다.",
                       field=name)
    return v


def require_str(body: dict, field: str) -> str:
    """필수 문자열 필드: 누락 · 빈 문자열 · 공백뿐이면 400."""
    v = body.get(field)
    if not isinstance(v, str) or not v.strip():
        raise ApiError(400, "BAD_REQUEST", f"{field} 는 필수입니다.", field=field)
    return v


# 한국 휴대전화 번호 — 하이픈 없이 숫자만 (예: 01012345678)
PHONE_RE = re.compile(r"^01[016789][0-9]{7,8}$")


def validate_phone(body: dict, field: str = "user_phone") -> str | None:
    """선택 전화번호 필드: 키가 없거나 null 이면 통과, 값이 있으면 형식 검증.

    저장은 하이픈 없이 숫자만 한다 (표시 형식은 프론트엔드 몫).
    빈 문자열("")도 형식 오류로 400 — 지우려면 null 을 보낸다.
    """
    v = body.get(field)
    if v is None:
        return None
    if not isinstance(v, str) or not PHONE_RE.fullmatch(v):
        raise ApiError(
            400, "BAD_REQUEST",
            f"{field} 은 하이픈 없이 숫자만 입력해야 합니다. (예: 01012345678)",
            field=field,
        )
    return v


# ---------- user_id / user_pw 작성규칙 (명세서 3번) ----------

# 아이디: 5~20자, 영문 소문자·숫자·특수기호(_, -), 시작은 영문 소문자
USER_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{4,19}$")

# 비밀번호: 같은 문자 3회 이상 연속 (aaa, 111 등)
_REPEAT_RE = re.compile(r"(.)\1\1")

# 비밀번호: 키보드 배열 문자열 (부분 일치, 대소문자 무시)
_KEYBOARD_PATTERNS = (
    "qwer", "wert", "erty", "rtyu", "tyui", "yuio", "uiop",
    "asdf", "sdfg", "dfgh", "fghj", "ghjk", "hjkl",
    "zxcv", "xcvb", "cvbn", "vbnm",
)

PW_MIN_LEN = 8
PW_MAX_LEN = 21
_SEQ_RUN_LEN = 4        # 연속 문자열로 간주하는 최소 길이 (1234, abcd, dcba …)


def validate_user_id(value) -> str:
    """user_id 작성규칙 검증 (POST /api/users). 위반 시 400."""
    if not isinstance(value, str) or not USER_ID_RE.fullmatch(value):
        raise ApiError(
            400, "BAD_REQUEST",
            "아이디는 5~20자의 영문 소문자만 사용할 수 있으며, "
            "시작은 영문 소문자여야 합니다.",
            field="user_id",
        )
    return value


def _has_sequential_run(value: str, run_len: int = _SEQ_RUN_LEN) -> bool:
    """문자 코드가 1씩 오르거나 내리는 구간이 run_len 이상이면 True (1234, dcba 등)."""
    for i in range(len(value) - run_len + 1):
        seg = value[i:i + run_len]
        diffs = {ord(b) - ord(a) for a, b in zip(seg, seg[1:])}
        if diffs == {1} or diffs == {-1}:
            return True
    return False


# def validate_password(value, user_id: str | None = None) -> str:
#     """user_pw 작성규칙 검증 (POST, 그리고 user_pw 를 포함한 PUT). 위반 시 400.

#     user_id 를 넘기면 비밀번호에 아이디가 포함됐는지(대소문자 무시)도 검사한다.
#     PUT 에서는 대상 사용자의 user_id 를 DB 에서 조회해 넘긴다.
#     로그인은 형식 검증 없이 비교만 한다 (기존 계정 로그인 보장).
#     """
#     if not isinstance(value, str):
#         raise ApiError(400, "BAD_REQUEST", "user_pw 는 문자열이어야 합니다.", field="user_pw")
#     if len(value) > PW_MAX_LEN:
#         raise ApiError(400, "BAD_REQUEST", f"비밀번호는 최대 {PW_MAX_LEN}자까지 사용할 수 있습니다.",
#                        field="user_pw")

#     # 문자 종류: 영문자 / 숫자 / 특수문자(영문·숫자 외 전부) — 3종 모두 필수, 8자 이상
#     has_all_classes = (
#         re.search(r"[A-Za-z]", value)
#         and re.search(r"[0-9]", value)
#         and re.search(r"[^A-Za-z0-9]", value)
#     )
#     if not has_all_classes or len(value) < 8:
#         raise ApiError(
#             400, "BAD_REQUEST",
#             "비밀번호는 영문자·숫자·특수문자를 모두 포함해 8자 이상이어야 합니다.",
#             field="user_pw",
#         )

#     if _REPEAT_RE.search(value):
#         raise ApiError(
#             400, "BAD_REQUEST",
#             "비밀번호에 같은 문자를 3번 이상 연속(aaa, 111 등)으로 사용할 수 없습니다.",
#             field="user_pw",
#         )
#     if _has_sequential_run(value):
#         raise ApiError(
#             400, "BAD_REQUEST",
#             "비밀번호에 연속된 문자열(1234, abcd 등)은 사용할 수 없습니다.",
#             field="user_pw",
#         )

#     lowered = value.lower()
#     if any(p in lowered for p in _KEYBOARD_PATTERNS):
#         raise ApiError(
#             400, "BAD_REQUEST",
#             "비밀번호에 키보드 배열 문자열(qwer, asdf 등)은 사용할 수 없습니다.",
#             field="user_pw",
#         )
#     if user_id and user_id.lower() in lowered:
#         raise ApiError(400, "BAD_REQUEST", "비밀번호에 아이디를 포함할 수 없습니다.",
#                        field="user_pw")
#     return value

def validate_password(value, user_id: str | None = None) -> str:
    """user_pw 작성규칙 검증 (POST, 그리고 user_pw 를 포함한 PUT). 위반 시 400."""
    if not isinstance(value, str):
        raise ApiError(400, "BAD_REQUEST", "user_pw 는 문자열이어야 합니다.", field="user_pw")
    
    # 1. 길이 검증 (8자 이상 21자 이하)
    if not (PW_MIN_LEN <= len(value) <= PW_MAX_LEN):
        raise ApiError(
            400, "BAD_REQUEST",
            f"비밀번호는 {PW_MIN_LEN}자 이상, {PW_MAX_LEN}자 이하여야 합니다.",
            field="user_pw",
        )

    # 2. 영문, 숫자, 지정된 특수문자(!@#$%^&*~) 각각 1개 이상 필수 포함 검증
    has_english = re.search(r"[A-Za-z]", value)
    has_digit = re.search(r"[0-9]", value)
    has_special = re.search(r"[!@#$%^&*~]", value)

    if not (has_english and has_digit and has_special):
        raise ApiError(
            400, "BAD_REQUEST",
            "비밀번호는 영문, 숫자, 특수문자(!@#$%^&*~)를 각각 최소 1개 이상 포함해야 합니다.",
            field="user_pw",
        )

    # 3. 허용되지 않은 다른 문자나 특수문자가 들어왔는지 차단 (영문, 숫자, 지정된 특수문자 외 불가)
    if not re.fullmatch(r"^[a-zA-Z0-9!@#$%^&*~]+$", value):
        raise ApiError(
            400, "BAD_REQUEST",
            "비밀번호에 사용할 수 없는 문자가 포함되어 있습니다. (!@#$%^&*~ 만 허용)",
            field="user_pw",
        )

    if _REPEAT_RE.search(value):
        raise ApiError(
            400, "BAD_REQUEST",
            "비밀번호에 같은 문자를 3번 이상 연속(aaa, 111 등)으로 사용할 수 없습니다.",
            field="user_pw",
        )
    if _has_sequential_run(value):
        raise ApiError(
            400, "BAD_REQUEST",
            "비밀번호에 연속된 문자열(1234, abcd 등)은 사용할 수 없습니다.",
            field="user_pw",
        )

    lowered = value.lower()
    if any(p in lowered for p in _KEYBOARD_PATTERNS):
        raise ApiError(
            400, "BAD_REQUEST",
            "비밀번호에 키보드 배열 문자열(qwer, asdf 등)은 사용할 수 없습니다.",
            field="user_pw",
        )
    if user_id and user_id.lower() in lowered:
        raise ApiError(400, "BAD_REQUEST", "비밀번호에 아이디를 포함할 수 없습니다.",
                        field="user_pw")
    return value


def require_number(body: dict, field: str) -> int | float:
    """필수 숫자 필드: JSON 숫자(int/float)가 아니면 400 (bool · 숫자 문자열 거부)."""
    v = body.get(field)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ApiError(400, "BAD_REQUEST", f"{field} 는 숫자여야 합니다.", field=field)
    return v
