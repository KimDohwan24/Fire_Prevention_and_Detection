"""공통 규칙 — 명세서 1번 섹션: 에러 형식, 헬스체크."""


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_404_returns_common_error_shape(client):
    r = client.get("/api/no-such-path")
    assert r.status_code == 404
    body = r.get_json()
    assert set(body.keys()) == {"code", "message"}
    assert body["code"] == "NOT_FOUND"


def test_405_returns_common_error_shape(client):
    # /api/auth/login 은 POST 전용
    r = client.get("/api/auth/login")
    assert r.status_code == 405
    body = r.get_json()
    assert body["code"] == "METHOD_NOT_ALLOWED"
