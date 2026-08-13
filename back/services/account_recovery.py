"""계정 찾기 인증코드 — 저장하지 않는 방식.

코드를 DB 에 넣지 않고 **매번 계산해서 대조**한다.

    코드 = HMAC(JWT_SECRET, user_no | 시간버킷 | 현재_비밀번호_해시)

왜 저장하지 않나:
- 테이블(또는 users 컬럼)을 새로 만들면 스키마 변경 → 팀원 로컬 DB 마이그레이션까지
  줄줄이 따라온다. 일회성 코드 하나 때문에 치를 비용이 아니다.
- 저장한 코드는 평문이면 DB 를 본 사람이 곧바로 계정을 가져가고, 해시로 넣으면
  결국 여기서 하는 계산을 DB 왕복까지 더해 다시 하는 셈이다.

**1회용이 공짜로 따라온다.** 비밀번호 해시를 HMAC 입력에 섞었기 때문에, 비밀번호가
바뀌는 순간 bcrypt 해시가 달라져 같은 코드로는 더 이상 같은 서명이 나오지 않는다.
"사용됨" 플래그를 둘 필요가 없다. (Django 의 비밀번호 재설정 토큰이 쓰는 기법이다.)

**만료는 시간 버킷으로 한다.** 발급 시각을 코드에 실어 보내지 않아도 되도록,
검증할 때 최근 VALID_BUCKETS 개를 재계산해 하나라도 맞으면 통과시킨다.
그래서 실제 유효시간은 (VALID_BUCKETS-1)~VALID_BUCKETS × BUCKET_SEC 사이에서
발급 시점에 따라 조금 흔들린다 — 4분 30초~5분. 일회성 코드에 그 정도 오차는 무해하다.

**대가 하나**: 서버에 상태가 없으니 "N회 틀리면 잠금"을 걸 수 없다. 그래서 6자리 숫자가
아니라 32자 알파벳 10자리(=50비트)로 발급한다. 무제한으로 찔러도 뚫리지 않는 길이가
시도 횟수 제한을 대신한다.
"""
import hashlib
import hmac
import re
import time

import config

# 코드 1개의 유효 구간(초). 이 단위로 시각을 잘라 HMAC 입력에 넣는다
BUCKET_SEC = 30
# 검증 시 거슬러 올라가며 확인할 버킷 수 (10 × 30초 ≈ 5분)
VALID_BUCKETS = 10

# 혼동하기 쉬운 0·O·1·I 를 뺀 32자 — 문자로 받아 손으로 옮겨 적는 값이다
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LEN = 10

# 사용자가 넣은 코드에서 걷어낼 것 — 공백·하이픈 등 알파벳 밖 문자는 전부 무시한다
_NOISE = re.compile(r"[^A-Z0-9]")


def _bucket(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // BUCKET_SEC)


def _code_for(user_no: int, pw_hash: str, bucket: int) -> str:
    """한 버킷에 대한 코드를 만든다 (발급·검증이 같은 함수를 쓴다)."""
    msg = f"{user_no}|{bucket}|{pw_hash}".encode()
    digest = hmac.new(config.JWT_SECRET.encode(), msg, hashlib.sha256).digest()
    # 앞 8바이트(64비트)를 32진수로 펼쳐 10자리를 만든다 (10 × 5비트 = 50비트 사용)
    num = int.from_bytes(digest[:8], "big")
    out = []
    for _ in range(CODE_LEN):
        out.append(ALPHABET[num % len(ALPHABET)])
        num //= len(ALPHABET)
    return "".join(out)


def issue_code(user_no: int, pw_hash: str, now: float | None = None) -> str:
    """지금 시각 기준 인증코드. SMS 로 내보낼 값이다."""
    return _code_for(user_no, pw_hash, _bucket(now))


def normalize(code) -> str:
    """사용자 입력 정리 — 대문자로 올리고 공백·하이픈을 걷어낸다."""
    return _NOISE.sub("", str(code or "").upper())


def verify_code(user_no: int, pw_hash: str, code, now: float | None = None) -> bool:
    """최근 VALID_BUCKETS 개 버킷 중 하나와 맞으면 True.

    맞는 버킷을 찾아도 **중간에 빠져나가지 않는다** — 몇 번째 버킷에서 맞았는지가
    응답 시간으로 새어나가지 않게 하기 위해서다. 비교도 compare_digest 로 한다.
    """
    given = normalize(code)
    if len(given) != CODE_LEN:
        # 길이가 다르면 어차피 불일치다. compare_digest 는 길이를 숨겨주지 않는다
        return False

    current = _bucket(now)
    matched = False
    for back in range(VALID_BUCKETS):
        expected = _code_for(user_no, pw_hash, current - back)
        matched |= hmac.compare_digest(given, expected)
    return matched


def mask_user_id(user_id: str) -> str:
    """아이디 부분 마스킹 — 앞 3자만 남긴다 (`admin01` → `adm****`).

    이름과 이메일은 팀 안에서 대개 알려진 정보라, 아이디를 통째로 돌려주면
    그 조합을 아는 사람에게 계정 목록을 그대로 넘겨주는 셈이 된다.
    본인이라면 앞 3자로 충분히 알아본다.
    """
    if not user_id:
        return ""
    keep = min(3, len(user_id))
    return user_id[:keep] + "*" * (len(user_id) - keep)
