"""소방서 API 테스트 — 명세서 7번 섹션.

GET  /api/agencies               목록
POST /api/agencies               등록 (ADMIN)
PUT  /api/agencies/<agency_no>   수정 · 비활성화 (ADMIN)
"""

# 명세서가 문서화한 소방서 응답 키 — 이 집합에서 늘거나 줄면 명세 위반이다.
AGENCY_KEYS = {
    "agency_no", "agency_name", "agency_lat", "agency_lng",
    "agency_endpoint", "agency_is_active",
}

NEW_AGENCY = {
    "agency_name": "용산소방서",
    "agency_lat": 37.5326,
    "agency_lng": 126.9905,
    "agency_endpoint": "http://localhost:6000/report",
}


# ---------- GET /api/agencies ----------

def test_list_agencies_requires_token(client):
    """토큰 없이 호출하면 401."""
    r = client.get("/api/agencies")
    assert r.status_code == 401
    assert r.get_json()["code"] == "UNAUTHORIZED"


def test_list_agencies_returns_seed_rows(client, admin_headers):
    """기준 데이터 2건이 agency_no 순으로 내려온다. 좌표는 숫자, 기본 활성 상태."""
    r = client.get("/api/agencies", headers=admin_headers)
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert len(items) == 2
    assert [i["agency_no"] for i in items] == [1, 2]
    assert [i["agency_name"] for i in items] == ["종로소방서", "중부소방서"]

    first = items[0]
    assert first["agency_endpoint"] == "http://localhost:6000/report"
    assert first["agency_is_active"] is True
    # numeric 컬럼은 JSON 숫자로 직렬화된다 (문자열이면 안 됨)
    assert isinstance(first["agency_lat"], (int, float))
    assert abs(first["agency_lat"] - 37.5720) < 1e-6


def test_list_agencies_item_keys_are_exactly_documented(client, admin_headers):
    """목록 항목의 키 집합이 명세서와 정확히 일치한다 (누락도 초과도 없음)."""
    items = client.get("/api/agencies", headers=admin_headers).get_json()["items"]
    for it in items:
        assert set(it.keys()) == AGENCY_KEYS


# ---------- POST /api/agencies ----------

def test_create_agency_success(client, admin_headers):
    """등록 성공: 201 {"agency_no": 3}, 목록에서 3건 확인."""
    r = client.post("/api/agencies", headers=admin_headers, json=NEW_AGENCY)
    assert r.status_code == 201
    assert r.get_json() == {"agency_no": 3}

    r = client.get("/api/agencies", headers=admin_headers)
    items = r.get_json()["items"]
    assert len(items) == 3
    assert items[2]["agency_name"] == "용산소방서"


def test_create_agency_missing_endpoint_bad_request(client, admin_headers):
    """필수 필드 agency_endpoint 누락 시 400."""
    payload = {k: v for k, v in NEW_AGENCY.items() if k != "agency_endpoint"}
    r = client.post("/api/agencies", headers=admin_headers, json=payload)
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


# ---------- 등록: 빈 값 · 형식 오류 검증 ----------

def test_create_agency_empty_endpoint_returns_400(client, admin_headers):
    """필수 문자열 필드가 빈 문자열("")이면 400."""
    r = client.post("/api/agencies", headers=admin_headers,
                    json={**NEW_AGENCY, "agency_endpoint": ""})
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


def test_create_agency_non_numeric_lat_returns_400(client, admin_headers):
    """좌표에 숫자가 아닌 값("abc")이 오면 400."""
    r = client.post("/api/agencies", headers=admin_headers,
                    json={**NEW_AGENCY, "agency_lat": "abc"})
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


def test_create_agency_viewer_forbidden(client, viewer_headers):
    """VIEWER 는 등록 불가: 403."""
    r = client.post("/api/agencies", headers=viewer_headers, json=NEW_AGENCY)
    assert r.status_code == 403
    assert r.get_json()["code"] == "FORBIDDEN"


# ---------- PUT /api/agencies/<agency_no> ----------

def test_update_agency_deactivate(client, admin_headers):
    """agency_is_active=false 로 비활성화: 200 후 목록에서 반영 확인."""
    r = client.put("/api/agencies/1", headers=admin_headers,
                   json={"agency_is_active": False})
    assert r.status_code == 200
    assert r.get_json() == {"agency_no": 1}

    items = client.get("/api/agencies", headers=admin_headers).get_json()["items"]
    by_no = {i["agency_no"]: i for i in items}
    assert by_no[1]["agency_is_active"] is False
    assert by_no[2]["agency_is_active"] is True  # 다른 행은 영향 없음


def test_update_agency_unknown_not_found(client, admin_headers):
    """존재하지 않는 소방서: 404 AGENCY_NOT_FOUND.

    (빈 body 검사가 먼저이므로 유효한 필드를 하나 보낸다)
    """
    r = client.put("/api/agencies/999", headers=admin_headers,
                   json={"agency_is_active": False})
    assert r.status_code == 404
    assert r.get_json()["code"] == "AGENCY_NOT_FOUND"


def test_update_agency_empty_body_bad_request(client, admin_headers):
    """수정할 필드가 하나도 없으면 400."""
    r = client.put("/api/agencies/1", headers=admin_headers, json={})
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"
