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
        "user_id": "admin01", "user_pw": "dup#Guard99", "user_name": "중복", "user_role": "ADMIN",
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


def test_create_user_is_public_for_signup(client):
    """가입 화면이 토큰 없이 부르는 경로다 — 인증을 걸지 않는다.

    원래 admin_required 였으나 자기 가입을 받으면서 공개로 바뀌었다. 그래서
    권한 상승을 막는 책임이 아래 세 테스트로 옮겨졌다.
    """
    r = client.post("/api/users", json={
        "user_id": "selfjoin", "user_pw": "no#Guard99x", "user_name": "가입자",
        "user_role": "VIEWER",
    })
    assert r.status_code == 201


def test_signup_cannot_grant_itself_admin(client):
    """토큰 없이 user_role='ADMIN' 을 보내도 VIEWER 로 만들어진다.

    이 방어가 없으면 아무나 관리자 계정을 만들 수 있다 — 2026-08-19 에 실제로
    그 상태였다(토큰 없이 ADMIN 생성이 201 로 통과했다).
    """
    r = client.post("/api/users", json={
        "user_id": "evil01", "user_pw": "Zx#9qWmb", "user_name": "침입자",
        "user_role": "ADMIN",
    })
    assert r.status_code == 201
    assert db.query_one(
        "SELECT user_role FROM users WHERE user_id = 'evil01'")["user_role"] == "VIEWER"


def test_viewer_token_cannot_grant_admin(client, viewer_headers):
    """로그인한 VIEWER 가 불러도 마찬가지다 — 관리자 토큰이라야 권한을 지정할 수 있다."""
    r = client.post("/api/users", headers=viewer_headers, json={
        "user_id": "new03", "user_pw": "no#Guard99x", "user_name": "뷰어", "user_role": "ADMIN",
    })
    assert r.status_code == 201
    assert db.query_one(
        "SELECT user_role FROM users WHERE user_id = 'new03'")["user_role"] == "VIEWER"


def test_admin_can_still_choose_role(client, admin_headers):
    """관리자 토큰으로 부르면 본문의 user_role 이 그대로 반영된다."""
    r = client.post("/api/users", headers=admin_headers, json={
        "user_id": "byadmin1", "user_pw": "no#Guard99x", "user_name": "관리자생성",
        "user_role": "ADMIN",
    })
    assert r.status_code == 201
    assert db.query_one(
        "SELECT user_role FROM users WHERE user_id = 'byadmin1'")["user_role"] == "ADMIN"


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


# ---------- user_phone 형식 검증 (하이픈 없이 숫자만, 명세서 3번) ----------

def test_create_user_phone_with_hyphens_rejected(client, admin_headers):
    # 하이픈이 섞인 전화번호는 400 (숫자만 저장한다)
    r = client.post("/api/users", headers=admin_headers, json={
        "user_id": "phone01", "user_pw": "fire#Guard7", "user_name": "폰검증",
        "user_role": "VIEWER", "user_phone": "010-1234-5678",
    })
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


def test_create_user_phone_digits_only_accepted(client, admin_headers):
    r = client.post("/api/users", headers=admin_headers, json={
        "user_id": "phone02", "user_pw": "fire#Guard7", "user_name": "폰정상",
        "user_role": "VIEWER", "user_phone": "01012345678",
    })
    assert r.status_code == 201

    row = db.query_one(
        "SELECT user_phone FROM users WHERE user_no = %s", (r.get_json()["user_no"],)
    )
    assert row["user_phone"] == "01012345678"


def test_create_user_without_phone_still_optional(client, admin_headers):
    # user_phone 은 여전히 선택 항목이다
    r = client.post("/api/users", headers=admin_headers, json={
        "user_id": "phone03", "user_pw": "fire#Guard7", "user_name": "폰없음", "user_role": "VIEWER",
    })
    assert r.status_code == 201


def test_update_user_phone_format_validated(client, viewer_headers):
    # 본인 수정에서도 하이픈 형식은 400, 숫자만은 200 후 그대로 저장된다
    r = client.put("/api/users/2", headers=viewer_headers, json={"user_phone": "010-9999-8888"})
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"

    r = client.put("/api/users/2", headers=viewer_headers, json={"user_phone": "01099998888"})
    assert r.status_code == 200

    row = db.query_one("SELECT user_phone FROM users WHERE user_no = %s", (2,))
    assert row["user_phone"] == "01099998888"


def test_update_user_phone_null_clears(client, admin_headers):
    # null 을 보내면 전화번호를 비운다 (검증 대상 아님)
    r = client.put("/api/users/2", headers=admin_headers, json={"user_phone": None})
    assert r.status_code == 200

    row = db.query_one("SELECT user_phone FROM users WHERE user_no = %s", (2,))
    assert row["user_phone"] is None


def test_update_user_role_by_admin_still_works(client, admin_headers):
    # 회귀 방지: 관리자는 여전히 다른 사용자의 user_role 을 변경할 수 있다
    r = client.put("/api/users/2", headers=admin_headers, json={"user_role": "ADMIN"})
    assert r.status_code == 200

    row = db.query_one("SELECT user_role FROM users WHERE user_no = %s", (2,))
    assert row["user_role"] == "ADMIN"


# ---------- user_id 작성규칙 (POST /api/users, 명세서 3번) ----------
# 규칙: 5~20자, 영문 소문자·숫자·특수기호(_, -), 시작은 영문 소문자 (네이버 아이디 규칙 참고)

def _post_user(client, headers, user_id, user_pw):
    return client.post("/api/users", headers=headers, json={
        "user_id": user_id, "user_pw": user_pw,
        "user_name": "규칙검증", "user_role": "VIEWER",
    })


def test_user_id_too_short_rejected(client, admin_headers):
    r = _post_user(client, admin_headers, "abc1", "fire#Guard7")
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


def test_user_id_uppercase_rejected(client, admin_headers):
    r = _post_user(client, admin_headers, "Admin99", "fire#Guard7")
    assert r.status_code == 400


def test_user_id_starting_with_digit_rejected(client, admin_headers):
    r = _post_user(client, admin_headers, "1admin", "fire#Guard7")
    assert r.status_code == 400


def test_user_id_starting_with_underscore_rejected(client, admin_headers):
    r = _post_user(client, admin_headers, "_wang01", "fire#Guard7")
    assert r.status_code == 400


def test_user_id_valid_with_underscore(client, admin_headers):
    r = _post_user(client, admin_headers, "wang_01", "fire#Guard7")
    assert r.status_code == 201


# ---------- user_pw 작성규칙 (POST /api/users, 명세서 3번) ----------
# 규칙: 영문자·숫자·특수문자 3종을 모두 포함해 8~64자 (KISA 권고 기반),
#       동일 문자 3연속·연속 문자열 4자 이상·키보드 배열·아이디 포함 금지

def test_password_single_class_rejected(client, admin_headers):
    # 영문만 (1종) — 길이가 충분해도 거부
    r = _post_user(client, admin_headers, "pwtest01", "bdfhjlnprtvz")
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


def test_password_two_classes_nine_chars_rejected(client, admin_headers):
    # 2종(영문+숫자) — 특수문자가 없으면 거부
    r = _post_user(client, admin_headers, "pwtest02", "guardwng9")
    assert r.status_code == 400


def test_password_two_classes_rejected_regardless_of_length(client, admin_headers):
    # 2종(영문+숫자) 11자 — 길이가 길어도 3종이 아니면 거부
    r = _post_user(client, admin_headers, "pwtest03", "guard2wang9")
    assert r.status_code == 400


def test_password_three_classes_eight_chars_accepted(client, admin_headers):
    # 3종(영문+숫자+특수) 8자 — 허용
    r = _post_user(client, admin_headers, "pwtest04", "gu2#wang")
    assert r.status_code == 201


def test_password_three_classes_seven_chars_rejected(client, admin_headers):
    # 3종 7자 — 8자 미만이라 거부
    r = _post_user(client, admin_headers, "pwtest05", "gu2#wan")
    assert r.status_code == 400


def test_password_over_64_chars_rejected(client, admin_headers):
    r = _post_user(client, admin_headers, "pwtest06", "aB1#" * 17)   # 68자
    assert r.status_code == 400


def test_password_repeated_char_rejected(client, admin_headers):
    # 같은 문자 3연속 ("aaa") — 조합·길이는 만족해도 거부
    r = _post_user(client, admin_headers, "pwtest07", "gua3aaa#x9")
    assert r.status_code == 400


def test_password_sequential_ascending_rejected(client, admin_headers):
    # 연속 문자열 4자 ("1234")
    r = _post_user(client, admin_headers, "pwtest08", "wang1234#")
    assert r.status_code == 400


def test_password_sequential_descending_rejected(client, admin_headers):
    # 역방향 연속 문자열 4자 ("dcba")
    r = _post_user(client, admin_headers, "pwtest09", "gu#9dcba7")
    assert r.status_code == 400


def test_password_keyboard_pattern_rejected(client, admin_headers):
    # 키보드 배열 문자열 ("qwer") — 대소문자 무시
    r = _post_user(client, admin_headers, "pwtest10", "qwerG#77x")
    assert r.status_code == 400


def test_password_containing_user_id_rejected(client, admin_headers):
    # 아이디 포함 금지 (대소문자 무시)
    r = _post_user(client, admin_headers, "wang_01", "Wang_01#99x")
    assert r.status_code == 400


# ---------- user_pw 작성규칙 (PUT /api/users/<user_no>) ----------

def test_update_password_weak_rejected(client, admin_headers):
    r = client.put("/api/users/2", headers=admin_headers, json={"user_pw": "abc12"})
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"

    # 기존 비밀번호가 그대로 유지되어야 한다
    assert _login(client, "viewer01", PW).status_code == 200


def test_update_password_containing_own_id_rejected(client, admin_headers):
    # PUT 은 대상 사용자의 아이디(DB 조회)와 비교한다 — user_no 2 는 viewer01
    r = client.put("/api/users/2", headers=admin_headers, json={"user_pw": "Viewer01#9x"})
    assert r.status_code == 400


def test_update_password_valid_roundtrip(client, admin_headers):
    r = client.put("/api/users/2", headers=admin_headers, json={"user_pw": "new#Guard77"})
    assert r.status_code == 200

    # 새 비밀번호로 로그인 성공, 기존 비밀번호는 실패
    assert _login(client, "viewer01", "new#Guard77").status_code == 200
    assert _login(client, "viewer01", PW).status_code == 401


def test_update_user_not_found_with_empty_body(client, admin_headers):
    """없는 사용자는 '고칠 것이 없다'보다 먼저 404 다 — 존재 확인이 UPDATE 앞에 있다."""
    r = client.put("/api/users/999", headers=admin_headers, json={})
    assert r.status_code == 404
    assert r.get_json()["code"] == "USER_NOT_FOUND"
