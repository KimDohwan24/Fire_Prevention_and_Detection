"""텔레그램 연동코드 — 저장하지 않는 방식 (account_recovery 와 같은 계열).

계정 찾기 코드와 다른 점: 검증 시점에 user_no 를 모른다. 봇이 받는 것은
`/start <코드>` 한 줄뿐이라 코드 자체가 "누구인지"를 실어 날라야 한다.
그래서 코드는 `user_no-서명` 꼴이고, verify_code 는 bool 이 아니라 user_no 를 돌려준다.
"""
import pytest

from services import telegram_link


def test_issued_code_verifies_back_to_the_same_user():
    code = telegram_link.issue_code(7)

    assert telegram_link.verify_code(code) == 7


def test_code_for_another_user_does_not_verify_as_mine():
    mine = telegram_link.issue_code(7)
    yours = telegram_link.issue_code(8)

    assert telegram_link.verify_code(mine) == 7
    assert telegram_link.verify_code(yours) == 8


def test_swapping_the_user_number_breaks_the_signature():
    """앞자리만 남의 번호로 바꿔치기해도 서명이 맞지 않아야 한다."""
    code = telegram_link.issue_code(7)
    _, signature = code.split("-", 1)

    forged = f"8-{signature}"

    assert telegram_link.verify_code(forged) is None


def test_expired_code_does_not_verify():
    now = 1_800_000_000.0
    code = telegram_link.issue_code(7, now=now)

    # 유효 구간을 확실히 넘긴 시각에서 검증한다
    later = now + telegram_link.BUCKET_SEC * (telegram_link.VALID_BUCKETS + 1)

    assert telegram_link.verify_code(code, now=later) is None


def test_code_stays_valid_within_the_grace_window():
    now = 1_800_000_000.0
    code = telegram_link.issue_code(7, now=now)

    # 한 버킷 뒤 — 아직 유효 구간 안이다
    assert telegram_link.verify_code(code, now=now + telegram_link.BUCKET_SEC) == 7


@pytest.mark.parametrize("garbage", [None, "", "   ", "abc", "7", "7-", "-ABC",
                                     "x-ABCDEFGH", "7-ABCDEFGH-extra"])
def test_garbage_input_returns_none_without_raising(garbage):
    """봇 입력은 아무 문자열이나 들어온다 — 예외를 던져 워커를 죽이면 안 된다."""
    assert telegram_link.verify_code(garbage) is None


def test_code_is_safe_for_a_telegram_deep_link_payload():
    """딥링크(?start=) 페이로드는 A-Z a-z 0-9 _ - 만 허용한다."""
    import re

    for user_no in (1, 42, 1234567):
        code = telegram_link.issue_code(user_no)
        assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", code), code
