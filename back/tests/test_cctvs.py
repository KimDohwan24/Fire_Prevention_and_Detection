"""연동 카메라 API 테스트 — 명세서 4번 섹션.

시드 데이터: cctv_no 1 (정문 카메라, ACTIVE), cctv_no 2 (후문 카메라, INACTIVE).
"""
import pytest

import db

# 명세서가 문서화한 카메라 응답 키 — 이 집합에서 늘거나 줄면 명세 위반이다.
# (SELECT * 를 쓰면 나중에 컬럼이 추가될 때 조용히 응답에 섞여 들어간다)
CCTV_KEYS = {
    "cctv_no", "user_no", "cctv_name", "cctv_location", "cctv_lat", "cctv_lng",
    "cctv_stream_url", "cctv_width", "cctv_height", "cctv_status", "cctv_created_at",
}

NEW_CCTV = {
    "cctv_name": "옥상 카메라",
    "cctv_location": "본관 옥상",
    "cctv_lat": 37.5700,
    "cctv_lng": 126.9800,
    "cctv_stream_url": "http://192.168.0.12:8080/live/cam3.m3u8",
    "cctv_width": 1920,
    "cctv_height": 1080,
}


# ---------- 목록 ----------

def test_list_cctvs_requires_auth(client):
    """토큰 없이 목록 조회 시 401."""
    r = client.get("/api/cctvs")
    assert r.status_code == 401
    assert set(r.get_json().keys()) == {"code", "message"}


def test_list_cctvs_returns_seeded_cameras(client, admin_headers):
    """시드 카메라 2대가 cctv_no 오름차순으로 내려온다. 좌표는 JSON 숫자."""
    r = client.get("/api/cctvs", headers=admin_headers)
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert len(items) == 2
    assert [it["cctv_no"] for it in items] == [1, 2]

    first = items[0]
    assert first["cctv_name"] == "정문 카메라"
    assert first["cctv_location"] == "본관 정문 앞"
    assert first["cctv_status"] == "ACTIVE"
    assert first["cctv_stream_url"] == "http://192.168.0.10:8080/live/cam1.m3u8"
    assert first["cctv_width"] == 1920
    assert first["cctv_height"] == 1080
    # numeric 컬럼은 문자열이 아니라 JSON 숫자로 직렬화되어야 한다
    assert isinstance(first["cctv_lat"], float)
    assert first["cctv_lat"] == pytest.approx(37.5665)
    assert isinstance(first["cctv_lng"], float)
    assert first["cctv_lng"] == pytest.approx(126.978)


def test_list_cctvs_filter_by_status(client, admin_headers):
    """?cctv_status=ACTIVE 필터 시 ACTIVE 카메라 1대만."""
    r = client.get("/api/cctvs?cctv_status=ACTIVE", headers=admin_headers)
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert len(items) == 1
    assert items[0]["cctv_no"] == 1
    assert items[0]["cctv_status"] == "ACTIVE"


def _add_cctv_for_viewer(status="ACTIVE"):
    """user_no 2(viewer01)가 담당하는 카메라를 한 대 더 심는다.

    시드 카메라 2대가 모두 user_no 1 소유라, 소유자 필터를 검증하려면
    다른 소유자의 카메라가 최소 한 대는 있어야 한다 (없으면 필터가
    빠져 있어도 테스트가 통과해버린다).
    """
    row = db.execute_returning(
        """
        INSERT INTO cctv (user_no, cctv_name, cctv_location, cctv_lat, cctv_lng,
                          cctv_stream_url, cctv_width, cctv_height, cctv_status)
        VALUES (2, '별관 카메라', '별관 주차장', 37.5680000, 126.9800000,
                'http://192.168.0.20:8080/live/cam9.m3u8', 1920, 1080, %s)
        RETURNING cctv_no
        """,
        (status,),
    )
    return row["cctv_no"]


def test_list_cctvs_filter_by_user_no(client, admin_headers):
    """?user_no=N 필터 시 그 사용자가 담당하는 카메라만 내려온다."""
    other_no = _add_cctv_for_viewer()

    r = client.get("/api/cctvs?user_no=1", headers=admin_headers)
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert [it["cctv_no"] for it in items] == [1, 2]
    assert {it["user_no"] for it in items} == {1}

    r = client.get("/api/cctvs?user_no=2", headers=admin_headers)
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert [it["cctv_no"] for it in items] == [other_no]
    assert items[0]["user_no"] == 2


def test_list_cctvs_filter_by_user_no_and_status(client, admin_headers):
    """user_no 와 cctv_status 는 AND 로 함께 걸린다."""
    _add_cctv_for_viewer()      # user_no 2 · ACTIVE

    r = client.get("/api/cctvs?user_no=1&cctv_status=ACTIVE", headers=admin_headers)
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert [it["cctv_no"] for it in items] == [1]
    assert items[0]["user_no"] == 1
    assert items[0]["cctv_status"] == "ACTIVE"


def test_list_cctvs_filter_by_user_no_without_match_returns_empty(client, admin_headers):
    """담당 카메라가 없는 사용자는 200 + 빈 배열 (404 가 아니다)."""
    r = client.get("/api/cctvs?user_no=4", headers=admin_headers)
    assert r.status_code == 200
    assert r.get_json() == {"items": []}


def test_list_cctvs_invalid_user_no_returns_400(client, admin_headers):
    """user_no 가 정수가 아니면 400 — 어느 입력인지 field 로 알려준다."""
    r = client.get("/api/cctvs?user_no=abc", headers=admin_headers)
    assert r.status_code == 400
    body = r.get_json()
    assert body["code"] == "BAD_REQUEST"
    assert body["field"] == "user_no"


def test_list_cctvs_item_keys_are_exactly_documented(client, admin_headers):
    """목록 항목의 키 집합이 명세서와 정확히 일치한다 (누락도 초과도 없음)."""
    items = client.get("/api/cctvs", headers=admin_headers).get_json()["items"]
    for it in items:
        assert set(it.keys()) == CCTV_KEYS


# ---------- 단건 ----------

def test_get_cctv_keys_are_exactly_documented(client, admin_headers):
    """단건 조회도 목록 항목과 같은 키 집합을 돌려준다."""
    body = client.get("/api/cctvs/1", headers=admin_headers).get_json()
    assert set(body.keys()) == CCTV_KEYS


def test_get_cctv_detail(client, admin_headers):
    """단건 조회는 목록 항목과 동일한 형태의 단일 객체."""
    r = client.get("/api/cctvs/1", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["cctv_no"] == 1
    assert body["cctv_name"] == "정문 카메라"
    assert "items" not in body


def test_get_cctv_not_found(client, admin_headers):
    """없는 카메라 번호는 404 CCTV_NOT_FOUND."""
    r = client.get("/api/cctvs/999", headers=admin_headers)
    assert r.status_code == 404
    assert r.get_json()["code"] == "CCTV_NOT_FOUND"


# ---------- 등록 ----------

def test_create_cctv_success(client, admin_headers):
    """필수 필드를 모두 보내면 201, 새 cctv_no 반환.

    user_no 는 요청 본문이 아니라 관리자 토큰에서 가져오고,
    초기 상태는 ACTIVE 여야 한다.
    """
    r = client.post("/api/cctvs", json=NEW_CCTV, headers=admin_headers)
    assert r.status_code == 201
    assert r.get_json() == {"cctv_no": 3}

    r = client.get("/api/cctvs/3", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["user_no"] == 1          # admin01 (토큰의 user_no)
    assert body["cctv_status"] == "ACTIVE"
    assert body["cctv_name"] == "옥상 카메라"


def test_create_cctv_missing_lat_returns_400(client, admin_headers):
    """필수 필드 cctv_lat 누락 시 400 — 어느 입력인지 field 로 알려준다."""
    payload = {k: v for k, v in NEW_CCTV.items() if k != "cctv_lat"}
    r = client.post("/api/cctvs", json=payload, headers=admin_headers)
    assert r.status_code == 400
    body = r.get_json()
    assert set(body.keys()) == {"code", "message", "field"}
    assert body["field"] == "cctv_lat"


# ---------- 등록: 빈 값 · 형식 오류 검증 ----------

def test_create_cctv_empty_name_returns_400(client, admin_headers):
    """필수 문자열 필드가 빈 문자열("")이면 400."""
    r = client.post("/api/cctvs", json={**NEW_CCTV, "cctv_name": ""},
                    headers=admin_headers)
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


def test_create_cctv_empty_lat_returns_400(client, admin_headers):
    """필수 숫자 필드에 빈 문자열("")이 오면 400."""
    r = client.post("/api/cctvs", json={**NEW_CCTV, "cctv_lat": ""},
                    headers=admin_headers)
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


def test_create_cctv_string_lat_returns_400(client, admin_headers):
    """좌표는 JSON 숫자만 허용 — 숫자 형태 문자열("37.5")도 거부한다."""
    r = client.post("/api/cctvs", json={**NEW_CCTV, "cctv_lat": "37.5"},
                    headers=admin_headers)
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


def test_create_cctv_forbidden_for_viewer(client, viewer_headers):
    """VIEWER 권한으로 등록 시도 시 403."""
    r = client.post("/api/cctvs", json=NEW_CCTV, headers=viewer_headers)
    assert r.status_code == 403


# ---------- 수정 ----------

def test_update_cctv_status(client, admin_headers):
    """INACTIVE 카메라를 ACTIVE 로 변경하고 GET 으로 반영 확인."""
    r = client.put("/api/cctvs/2", json={"cctv_status": "ACTIVE"},
                   headers=admin_headers)
    assert r.status_code == 200
    assert r.get_json() == {"cctv_no": 2}

    r = client.get("/api/cctvs/2", headers=admin_headers)
    assert r.get_json()["cctv_status"] == "ACTIVE"


def test_update_cctv_not_found(client, admin_headers):
    """없는 카메라 수정 시 404."""
    r = client.put("/api/cctvs/999", json={"cctv_status": "ACTIVE"},
                   headers=admin_headers)
    assert r.status_code == 404
    assert r.get_json()["code"] == "CCTV_NOT_FOUND"


def test_update_cctv_empty_body_returns_400(client, admin_headers):
    """수정할 필드가 하나도 없으면 400."""
    r = client.put("/api/cctvs/2", json={}, headers=admin_headers)
    assert r.status_code == 400
