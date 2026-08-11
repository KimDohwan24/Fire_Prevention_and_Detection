"""계정 찾기 — 아이디 찾기 + 비밀번호 재설정 (인증코드 방식).

설계 요지: 인증코드를 **저장하지 않는다**. HMAC(JWT_SECRET, user_no|시간버킷|현재_비밀번호_해시)
를 그 자리에서 계산해 대조한다. 비밀번호가 바뀌면 bcrypt 해시가 달라져 같은 코드가
더 이상 재현되지 않으므로 **1회용이 별도 상태 없이 성립한다**.
"""
import time

import bcrypt
import pytest

import db
from services import account_recovery

FIND_ID = "/api/auth/find-id"
REQ = "/api/auth/password-reset/request"
CONFIRM = "/api/auth/password-reset/confirm"

NEW_PW = "Reset#2026x"


@pytest.fixture()
def sent_sms(monkeypatch):
    """sms.send_sms 를 가로채 (수신번호, 본문) 을 모은다."""
    box = []

    def fake(phone, message):
        box.append((phone, message))
        return True

    monkeypatch.setattr("services.sms.send_sms", fake)
    return box


def _pw_hash(user_id: str) -> str:
    return db.query_one(
        "SELECT user_pw FROM users WHERE user_id = %s", (user_id,)
    )["user_pw"]


def _issue(user_id: str) -> str:
    """현재 저장된 해시로 유효한 코드를 만든다 (SMS 로 받은 것과 같은 값)."""
    row = db.query_one(
        "SELECT user_no, user_pw FROM users WHERE user_id = %s", (user_id,)
    )
    return account_recovery.issue_code(row["user_no"], row["user_pw"])


# ---------- 아이디 찾기 ----------

def test_find_id_returns_masked_id(client):
    res = client.post(FIND_ID, json={"user_name": "관리자", "user_email": "admin@fg.kr"})
    assert res.status_code == 200
    masked = res.get_json()["user_id"]
    # 전체 노출 금지 — 일부는 가려져야 한다
    assert masked != "admin01"
    assert "*" in masked
    assert masked.startswith("adm")


def test_find_id_mismatch_is_404(client):
    res = client.post(FIND_ID, json={"user_name": "관리자", "user_email": "nobody@fg.kr"})
    assert res.status_code == 404


def test_find_id_requires_fields(client):
    res = client.post(FIND_ID, json={"user_name": "관리자"})
    assert res.status_code == 400
    assert res.get_json()["field"] == "user_email"


def test_find_id_skips_withdrawn_account(client):
    db.execute(
        "INSERT INTO users (user_id, user_pw, user_name, user_email, user_role, user_status)"
        " VALUES ('gone02', 'x', '탈퇴자둘', 'gone2@fg.kr', 'VIEWER', 'WITHDRAWN')"
    )
    res = client.post(FIND_ID, json={"user_name": "탈퇴자둘", "user_email": "gone2@fg.kr"})
    assert res.status_code == 404


# ---------- 재설정 요청 ----------

def test_request_sends_code_by_sms(client, sent_sms):
    res = client.post(REQ, json={"user_id": "admin01", "user_name": "관리자",
                                 "user_email": "admin@fg.kr"})
    assert res.status_code == 200
    assert len(sent_sms) == 1
    phone, message = sent_sms[0]
    assert phone == "01011111111"
    assert _issue("admin01") in message      # 실제 유효한 코드가 실려나간다


def test_request_never_returns_code_in_body(client, sent_sms):
    res = client.post(REQ, json={"user_id": "admin01", "user_name": "관리자",
                                 "user_email": "admin@fg.kr"})
    body = res.get_data(as_text=True)
    assert _issue("admin01") not in body     # 응답에 코드가 새면 인증이 무의미해진다


def test_request_mismatch_looks_identical_and_sends_nothing(client, sent_sms):
    ok = client.post(REQ, json={"user_id": "admin01", "user_name": "관리자",
                                "user_email": "admin@fg.kr"})
    bad = client.post(REQ, json={"user_id": "admin01", "user_name": "관리자",
                                 "user_email": "wrong@fg.kr"})
    # 계정 존재 여부를 흘리지 않는다 — 응답이 같아야 한다
    assert bad.status_code == ok.status_code == 200
    assert bad.get_json() == ok.get_json()
    assert len(sent_sms) == 1                # 틀린 쪽은 발송되지 않았다


def test_request_requires_fields(client, sent_sms):
    res = client.post(REQ, json={"user_id": "admin01", "user_name": "관리자"})
    assert res.status_code == 400
    assert not sent_sms


# ---------- 재설정 확정 ----------

def test_confirm_changes_password(client):
    code = _issue("admin01")
    res = client.post(CONFIRM, json={"user_id": "admin01", "code": code,
                                     "user_pw": NEW_PW})
    assert res.status_code == 200

    stored = _pw_hash("admin01")
    assert bcrypt.checkpw(NEW_PW.encode(), stored.encode())
    # 실제로 새 비밀번호로 로그인된다
    login = client.post("/api/auth/login", json={"user_id": "admin01", "user_pw": NEW_PW})
    assert login.status_code == 200


def test_confirm_rejects_wrong_code(client):
    res = client.post(CONFIRM, json={"user_id": "admin01", "code": "AAAAAAAAAA",
                                     "user_pw": NEW_PW})
    assert res.status_code == 400
    assert res.get_json()["code"] == "INVALID_RESET_CODE"


def test_confirm_rejects_expired_code(client, monkeypatch):
    row = db.query_one("SELECT user_no, user_pw FROM users WHERE user_id = 'admin01'")
    # 6분 전에 발급된 코드 (유효창 5분을 넘긴다)
    old = account_recovery.issue_code(row["user_no"], row["user_pw"],
                                      now=time.time() - 360)
    res = client.post(CONFIRM, json={"user_id": "admin01", "code": old,
                                     "user_pw": NEW_PW})
    assert res.status_code == 400


def test_code_is_single_use(client):
    """비밀번호가 바뀌면 해시가 달라져 같은 코드가 두 번 통하지 않는다."""
    code = _issue("admin01")
    first = client.post(CONFIRM, json={"user_id": "admin01", "code": code,
                                       "user_pw": NEW_PW})
    assert first.status_code == 200

    second = client.post(CONFIRM, json={"user_id": "admin01", "code": code,
                                        "user_pw": "Other#2026y"})
    assert second.status_code == 400


def test_confirm_enforces_password_rules(client):
    code = _issue("admin01")
    res = client.post(CONFIRM, json={"user_id": "admin01", "code": code,
                                     "user_pw": "1234"})
    assert res.status_code == 400
    assert res.get_json()["field"] == "user_pw"


def test_confirm_rejects_suspended_account(client):
    row = db.query_one("SELECT user_no, user_pw FROM users WHERE user_id = 'susp01'")
    code = account_recovery.issue_code(row["user_no"], row["user_pw"])
    res = client.post(CONFIRM, json={"user_id": "susp01", "code": code,
                                     "user_pw": NEW_PW})
    assert res.status_code == 400


def test_confirm_accepts_code_with_spaces_and_lowercase(client):
    """사용자가 문자로 받은 코드를 소문자·공백 섞어 넣어도 통과한다."""
    code = _issue("admin01")
    typed = code.lower()[:5] + " " + code.lower()[5:]
    res = client.post(CONFIRM, json={"user_id": "admin01", "code": typed,
                                     "user_pw": NEW_PW})
    assert res.status_code == 200


# ---------- 코드 생성기 자체 ----------

def test_code_shape_and_alphabet():
    code = account_recovery.issue_code(1, "somehash")
    assert len(code) == account_recovery.CODE_LEN
    # 혼동하기 쉬운 0·O·1·I 는 쓰지 않는다 (문자로 받아 손으로 입력한다)
    assert set(code) <= set(account_recovery.ALPHABET)
    assert not (set("01IO") & set(account_recovery.ALPHABET))


def test_code_differs_per_user_and_password():
    a = account_recovery.issue_code(1, "hash-a")
    b = account_recovery.issue_code(2, "hash-a")
    c = account_recovery.issue_code(1, "hash-b")
    assert a != b and a != c
