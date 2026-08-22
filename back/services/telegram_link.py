"""텔레그램 계정 연동코드 — 저장하지 않는 방식.

    코드 = "{user_no}-{HMAC(JWT_SECRET, 'tg'|user_no|시간버킷)}"

`services/account_recovery.py` 와 같은 계열이다. 저장하지 않는 이유(스키마를 늘리지
않는다·평문 저장 위험 없음·만료를 시간 버킷으로 처리)는 그쪽 모듈 주석에 적어 뒀다.

**다른 점 하나**: 계정 찾기는 "이 사용자가 맞나"를 묻지만(bool), 여기서는 검증 시점에
user_no 를 모른다. 봇이 받는 것은 `/start <코드>` 한 줄이 전부라, 코드 자체가 누구
것인지를 실어 날라야 한다. 그래서 앞자리에 user_no 를 그대로 붙이고 verify_code 는
user_no 를 돌려준다. user_no 가 드러나지만 이 값은 남이 알아도 할 수 있는 게 없다 —
뒤의 서명이 맞지 않으면 연동이 성립하지 않기 때문이다 (test_swapping_the_user_number).

**비밀번호 해시를 섞지 않는다.** 계정 찾기 코드는 그걸로 1회용을 얻지만, 여기서는
소셜 로그인 사용자(user_pw IS NULL)도 연동해야 하므로 입력으로 쓸 수 없다. 대신
유효 시간을 5분으로 짧게 두고, 연동이 이미 끝난 코드는 다시 써도 같은 사용자에게
같은 chat_id 를 덮어쓸 뿐이라 실질적인 재사용 위험이 없다.

출력 문자는 텔레그램 딥링크(`https://t.me/<봇>?start=<코드>`) 페이로드 규칙인
`A-Za-z0-9_-` 안에 있어야 한다 — 그래서 하이픈 하나 말고는 영숫자만 쓴다.
"""
import hashlib
import hmac
import time

import config

# 코드 1개의 유효 구간(초)
BUCKET_SEC = 60
# 검증 시 거슬러 올라가며 확인할 버킷 수 (5 × 60초 ≈ 4~5분)
VALID_BUCKETS = 5

# 혼동하기 쉬운 0·O·1·I 를 뺀 32자 (account_recovery 와 같은 표)
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
SIGNATURE_LEN = 10  # 10 × 5비트 = 50비트


def _bucket(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // BUCKET_SEC)


def _signature(user_no: int, bucket: int) -> str:
    """한 버킷에 대한 서명 (발급·검증이 같은 함수를 쓴다)."""
    msg = f"tg|{user_no}|{bucket}".encode()
    digest = hmac.new(config.JWT_SECRET.encode(), msg, hashlib.sha256).digest()
    num = int.from_bytes(digest[:8], "big")
    out = []
    for _ in range(SIGNATURE_LEN):
        out.append(ALPHABET[num % len(ALPHABET)])
        num //= len(ALPHABET)
    return "".join(out)


def issue_code(user_no: int, now: float | None = None) -> str:
    """지금 시각 기준 연동코드. 딥링크 payload 로 그대로 나간다."""
    return f"{user_no}-{_signature(user_no, _bucket(now))}"


def verify_code(code, now: float | None = None) -> int | None:
    """코드가 유효하면 그 주인의 user_no, 아니면 None.

    입력은 봇 대화창에서 오는 임의의 문자열이다. **어떤 입력에도 예외를 던지지
    않는다** — 여기서 터지면 폴링 워커가 통째로 멈춘다.
    """
    text = str(code or "").strip().upper()
    head, sep, signature = text.partition("-")
    if not sep or len(signature) != SIGNATURE_LEN:
        return None
    try:
        user_no = int(head)
    except ValueError:
        return None
    if user_no <= 0:
        return None

    # 맞는 버킷을 찾아도 중간에 빠져나가지 않는다 (account_recovery 와 같은 이유)
    current = _bucket(now)
    matched = False
    for back in range(VALID_BUCKETS):
        matched |= hmac.compare_digest(signature, _signature(user_no, current - back))
    return user_no if matched else None
