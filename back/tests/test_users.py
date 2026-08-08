"""관리자 계정 API — 명세서 3번 섹션 (GET/POST /api/users, PUT /api/users/<user_no>)."""
import db
from conftest import PW

PAGED_KEYS = {"items", "page", "size", "total_count", "total_pages"}


def _login(client, user_id, user_pw):
    return client.post("/api/auth/login", json={"user_id": user_id, "user_pw": user_pw})


# ---------- GET /api/users ----------

def test_list_users_without_token(client):
    r = client.get("/api/users")
    assert r.status_code == 401


def test_list_users_viewer_forbidden(client, viewer_headers):
    r = client.get("/api/users", headers=viewer_headers)
    assert r.status_code == 403
    assert r.get_json()["code"] == "FORBIDDEN"


def test_list_users_admin(client, admin_headers):
    r = client.get("/api/users", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()

    # 페이징 공통 형식
    assert set(body.keys()) == PAGED_KEYS
    assert body["total_count"] == 4          # 기준 데이터 4명
    assert body["page"] == 1

    # user_no 오름차순 정렬
    nos = [item["user_no"] for item in body["items"]]
    assert nos == sorted(nos) == [1, 2, 3, 4]

    # 목록 항목에 비밀번호 해시가 노출되면 안 된다
    assert "user_pw" not in body["items"][0]


def test_list_users_filter_by_status(client, admin_headers):
    r = client.get("/api/users?user_status=ACTIVE", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["total_count"] == 2          # admin01, viewer01
    assert all(item["user_status"] == "ACTIVE" for item in body["items"])


def test_list_users_pagination(client, admin_headers):
    r = client.get("/api/users?page=1&size=2", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert len(body["items"]) == 2
    assert body["size"] == 2
    assert body["total_count"] == 4
    assert body["total_pages"] == 2


# ---------- POST /api/users ----------

def test_create_user_success(client, admin_headers):
    r = client.post("/api/users", headers=admin_headers, json={
        "user_id": "new01", "user_pw": "newpass1!",
        "user_name": "신규자", "user_role": "VIEWER",
    })
    assert r.status_code == 201
    assert r.get_json() == {"user_no": 5}    # 기준 4명 다음 번호

    # 등록한 비밀번호로 바로 로그인이 되어야 한다 (bcrypt 해시 저장 검증)
    r = _login(client, "new01", "newpass1!")
    assert r.status_code == 200
    assert r.get_json()["user"]["user_no"] == 5


def test_create_user_duplicate_id(client, admin_headers):
    r = client.post("/api/users", headers=admin_headers, json={
        "user_id": "admin01", "user_pw": "x", "user_name": "중복", "user_role": "ADMIN",
    })
    assert r.status_code == 409
    assert r.get_json()["code"] == "DUPLICATE_USER_ID"


def test_create_user_missing_required_field(client, admin_headers):
    # user_pw 누락
    r = client.post("/api/users", headers=admin_headers, json={
        "user_id": "new02", "user_name": "이름만", "user_role": "VIEWER",
    })
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


def test_create_user_viewer_forbidden(client, viewer_headers):
    r = client.post("/api/users", headers=viewer_headers, json={
        "user_id": "new03", "user_pw": "x", "user_name": "뷰어", "user_role": "VIEWER",
    })
    assert r.status_code == 403


# ---------- PUT /api/users/<user_no> ----------

def test_update_user_partial(client, admin_headers):
    # user_name 만 보내면 그 필드만 갱신된다
    r = client.put("/api/users/2", headers=admin_headers, json={"user_name": "개명자"})
    assert r.status_code == 200
    assert r.get_json() == {"user_no": 2}

    body = client.get("/api/users", headers=admin_headers).get_json()
    target = next(u for u in body["items"] if u["user_no"] == 2)
    assert target["user_name"] == "개명자"
    # 나머지 필드는 그대로
    assert target["user_id"] == "viewer01"
    assert target["user_role"] == "VIEWER"
    assert target["user_email"] == "viewer@fg.kr"
    assert target["user_status"] == "ACTIVE"


def test_update_user_password(client, admin_headers):
    r = client.put("/api/users/2", headers=admin_headers, json={"user_pw": "changed1!"})
    assert r.status_code == 200

    # 새 비밀번호로 로그인 성공
    assert _login(client, "viewer01", "changed1!").status_code == 200
    # 기존 비밀번호는 더 이상 안 된다
    assert _login(client, "viewer01", PW).status_code == 401


def test_update_user_withdrawn_records_timestamp(client, admin_headers):
    # 탈퇴 처리: WITHDRAWN 전송 시 서버가 user_withdrawal_at 을 함께 기록한다 (명세서 3번)
    r = client.put("/api/users/2", headers=admin_headers, json={"user_status": "WITHDRAWN"})
    assert r.status_code == 200

    row = db.query_one(
        "SELECT user_status, user_withdrawal_at FROM users WHERE user_no = %s", (2,)
    )
    assert row["user_status"] == "WITHDRAWN"
    assert row["user_withdrawal_at"] is not None


def test_update_user_not_found(client, admin_headers):
    r = client.put("/api/users/999", headers=admin_headers, json={"user_name": "유령"})
    assert r.status_code == 404
    assert r.get_json()["code"] == "USER_NOT_FOUND"


def test_update_user_empty_body(client, admin_headers):
    r = client.put("/api/users/2", headers=admin_headers, json={})
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


def test_update_user_viewer_forbidden(client, viewer_headers):
    # 일반 사용자가 다른 사용자를 수정하려 하면 403
    r = client.put("/api/users/1", headers=viewer_headers, json={"user_name": "불가"})
    assert r.status_code == 403
    assert r.get_json()["code"] == "FORBIDDEN"


# ---------- PUT /api/users/<user_no> — 본인 계정 수정 (일반 사용자) ----------

def test_update_self_name_by_viewer(client, viewer_headers):
    # 일반 사용자는 본인 계정의 기본 정보를 수정할 수 있다
    r = client.put("/api/users/2", headers=viewer_headers, json={"user_name": "셀프개명"})
    assert r.status_code == 200
    assert r.get_json() == {"user_no": 2}

    me = client.get("/api/auth/me", headers=viewer_headers).get_json()
    assert me["user_name"] == "셀프개명"


def test_update_self_password_by_viewer(client, viewer_headers):
    r = client.put("/api/users/2", headers=viewer_headers, json={"user_pw": "selfnew1!"})
    assert r.status_code == 200

    # 새 비밀번호로 로그인 성공, 기존 비밀번호는 실패
    assert _login(client, "viewer01", "selfnew1!").status_code == 200
    assert _login(client, "viewer01", PW).status_code == 401


def test_update_self_role_forbidden(client, viewer_headers):
    # 본인 계정이라도 user_role 변경은 관리자 전용
    r = client.put("/api/users/2", headers=viewer_headers, json={"user_role": "ADMIN"})
    assert r.status_code == 403
    assert r.get_json()["code"] == "FORBIDDEN"

    row = db.query_one("SELECT user_role FROM users WHERE user_no = %s", (2,))
    assert row["user_role"] == "VIEWER"


def test_update_self_status_forbidden(client, viewer_headers):
    # 본인 계정이라도 user_status 변경은 관리자 전용 (다른 필드와 섞여 있어도 전체 거부)
    r = client.put(
        "/api/users/2", headers=viewer_headers,
        json={"user_name": "몰래", "user_status": "WITHDRAWN"},
    )
    assert r.status_code == 403
    assert r.get_json()["code"] == "FORBIDDEN"

    row = db.query_one("SELECT user_name, user_status FROM users WHERE user_no = %s", (2,))
    assert row["user_status"] == "ACTIVE"
    assert row["user_name"] == "조회자"      # 아무것도 적용되지 않아야 한다


def test_update_user_role_by_admin_still_works(client, admin_headers):
    # 회귀 방지: 관리자는 여전히 다른 사용자의 user_role 을 변경할 수 있다
    r = client.put("/api/users/2", headers=admin_headers, json={"user_role": "ADMIN"})
    assert r.status_code == 200

    row = db.query_one("SELECT user_role FROM users WHERE user_no = %s", (2,))
    assert row["user_role"] == "ADMIN"
