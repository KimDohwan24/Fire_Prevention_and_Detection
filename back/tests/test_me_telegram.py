"""마이페이지 텔레그램 연동 API.

GET    /api/me/telegram  연동 상태 + 딥링크
DELETE /api/me/telegram  연동 해제

연동 자체는 사용자가 딥링크를 눌러 텔레그램에서 끝낸다 — 서버가 하는 일은 코드를
실은 링크를 만들어 주는 것까지다. 코드를 저장하지 않으므로(services/telegram_link.py)
발급 API 가 DB 를 건드리지 않는다.
"""
import pytest

import config
import db
from services import telegram_link


@pytest.fixture()
def bot(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "12345:TESTTOKEN")
    monkeypatch.setattr(config, "TELEGRAM_BOT_USERNAME", "fireguard_test_bot")


def _chat_id_of(user_no):
    return db.query_one("SELECT user_telegram_chat_id AS c FROM users WHERE user_no = %s",
                        (user_no,))["c"]


def test_status_requires_login(client):
    assert client.get("/api/me/telegram").status_code == 401


def test_status_reports_not_linked_for_a_fresh_user(client, admin_headers, bot):
    body = client.get("/api/me/telegram", headers=admin_headers).get_json()

    assert body["linked"] is False


def test_status_reports_linked_after_the_chat_is_attached(client, admin_headers, bot):
    db.execute("UPDATE users SET user_telegram_chat_id = 555 WHERE user_no = 1")

    body = client.get("/api/me/telegram", headers=admin_headers).get_json()

    assert body["linked"] is True


def test_status_returns_a_deep_link_that_carries_my_code(client, admin_headers, bot):
    body = client.get("/api/me/telegram", headers=admin_headers).get_json()

    assert body["link_url"].startswith("https://t.me/fireguard_test_bot?start=")
    code = body["link_url"].split("start=", 1)[1]
    assert telegram_link.verify_code(code) == 1  # admin01 = user_no 1


def test_status_says_unconfigured_when_the_bot_token_is_missing(client, admin_headers,
                                                                monkeypatch):
    """토큰을 안 넣은 팀원 환경에서도 화면이 떠야 한다 — 링크만 없다."""
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "TELEGRAM_BOT_USERNAME", "")

    resp = client.get("/api/me/telegram", headers=admin_headers)

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["configured"] is False
    assert body["link_url"] is None


def test_issuing_a_link_does_not_touch_the_database(client, admin_headers, bot):
    """연동 코드는 저장하지 않는다 (HMAC 으로 매번 계산해 대조한다)."""
    client.get("/api/me/telegram", headers=admin_headers)

    assert _chat_id_of(1) is None


def test_delete_unlinks_my_chat(client, admin_headers, bot):
    db.execute("UPDATE users SET user_telegram_chat_id = 555 WHERE user_no = 1")

    resp = client.delete("/api/me/telegram", headers=admin_headers)

    assert resp.status_code == 200
    assert _chat_id_of(1) is None


def test_delete_only_unlinks_my_own_chat(client, admin_headers, bot):
    db.execute("UPDATE users SET user_telegram_chat_id = 555 WHERE user_no = 1")
    db.execute("UPDATE users SET user_telegram_chat_id = 777 WHERE user_no = 2")

    client.delete("/api/me/telegram", headers=admin_headers)

    assert _chat_id_of(2) == 777


def test_delete_is_idempotent(client, admin_headers, bot):
    assert client.delete("/api/me/telegram", headers=admin_headers).status_code == 200
    assert client.delete("/api/me/telegram", headers=admin_headers).status_code == 200
