"""400 에러가 '어느 입력' 때문인지 field 로 알려주는지 확인한다.

배경: 검증 실패는 전부 code=BAD_REQUEST 하나로 나간다. 그래서 프론트가
회원가입 폼에서 아이디 칸 아래에 띄울지 비밀번호 칸 아래에 띄울지 정하려면
message 한글 문구를 파싱하는 수밖에 없었다. 문구가 바뀌면 조용히 깨진다.

해결: 응답에 field 를 하나 더 싣는다. 기존 {code, message} 는 그대로 두고
키만 늘리므로 하위 호환이다. 입력 하나를 특정할 수 없는 400(예: "수정할
필드가 없습니다")과 400 이 아닌 에러에는 field 를 넣지 않는다.
"""
import config

INTERNAL = {"X-Internal-Key": config.INTERNAL_API_KEY}


def _err(res):
    """에러 본문을 (code, field) 로 줄인다. field 키가 없으면 None."""
    body = res.get_json()
    assert "code" in body and "message" in body, f"공통 형식이 깨졌다: {body}"
    return body["code"], body.get("field")


# ---------- 1. 필드를 특정할 수 있는 400 은 field 를 단다 ----------

def test_login_missing_user_id(client):
    res = client.post("/api/auth/login", json={"user_pw": "Guard#2026"})
    assert res.status_code == 400
    assert _err(res) == ("BAD_REQUEST", "user_id")


def test_login_missing_user_pw(client):
    res = client.post("/api/auth/login", json={"user_id": "admin01"})
    assert res.status_code == 400
    assert _err(res) == ("BAD_REQUEST", "user_pw")


def test_create_user_missing_required_field(client, admin_headers):
    res = client.post("/api/users", headers=admin_headers,
                      json={"user_id": "newuser01", "user_pw": "Guard#2026",
                            "user_role": "VIEWER"})
    assert res.status_code == 400
    assert _err(res) == ("BAD_REQUEST", "user_name")


def test_create_user_id_rule_violation(client, admin_headers):
    """아이디 작성규칙 위반 → 아이디 칸에 붙일 수 있어야 한다."""
    res = client.post("/api/users", headers=admin_headers,
                      json={"user_id": "1bad", "user_pw": "Guard#2026",
                            "user_name": "홍길동", "user_role": "VIEWER"})
    assert res.status_code == 400
    assert _err(res) == ("BAD_REQUEST", "user_id")


def test_create_user_password_rule_violation(client, admin_headers):
    res = client.post("/api/users", headers=admin_headers,
                      json={"user_id": "newuser01", "user_pw": "short",
                            "user_name": "홍길동", "user_role": "VIEWER"})
    assert res.status_code == 400
    assert _err(res) == ("BAD_REQUEST", "user_pw")


def test_create_user_phone_format(client, admin_headers):
    res = client.post("/api/users", headers=admin_headers,
                      json={"user_id": "newuser01", "user_pw": "Guard#2026",
                            "user_name": "홍길동", "user_role": "VIEWER",
                            "user_phone": "010-1234-5678"})
    assert res.status_code == 400
    assert _err(res) == ("BAD_REQUEST", "user_phone")


def test_update_user_password_rule_violation(client, admin_headers):
    res = client.put("/api/users/2", headers=admin_headers, json={"user_pw": "abcd1234!"})
    assert res.status_code == 400
    assert _err(res) == ("BAD_REQUEST", "user_pw")


def test_create_cctv_missing_required_field(client, admin_headers):
    res = client.post("/api/cctvs", headers=admin_headers,
                      json={"cctv_location": "본관", "cctv_lat": 37.5,
                            "cctv_lng": 127.0, "cctv_stream_url": "http://x/s.m3u8"})
    assert res.status_code == 400
    assert _err(res) == ("BAD_REQUEST", "cctv_name")


def test_create_cctv_coordinate_not_number(client, admin_headers):
    """숫자 문자열("37.5")도 거부 대상이고, 어느 좌표인지 알려줘야 한다."""
    res = client.post("/api/cctvs", headers=admin_headers,
                      json={"cctv_name": "정문", "cctv_location": "본관",
                            "cctv_lat": "37.5", "cctv_lng": 127.0,
                            "cctv_stream_url": "http://x/s.m3u8"})
    assert res.status_code == 400
    assert _err(res) == ("BAD_REQUEST", "cctv_lat")


def test_create_agency_missing_required_field(client, admin_headers):
    res = client.post("/api/agencies", headers=admin_headers,
                      json={"agency_lat": 37.5, "agency_lng": 127.0,
                            "agency_endpoint": "http://localhost:6000/report"})
    assert res.status_code == 400
    assert _err(res) == ("BAD_REQUEST", "agency_name")


def test_events_int_query_param(client, admin_headers):
    res = client.get("/api/events?cctv_no=abc", headers=admin_headers)
    assert res.status_code == 400
    assert _err(res) == ("BAD_REQUEST", "cctv_no")


def test_events_date_query_param(client, admin_headers):
    res = client.get("/api/events?date_from=2026-13-99", headers=admin_headers)
    assert res.status_code == 400
    assert _err(res) == ("BAD_REQUEST", "date_from")


def test_reports_int_query_param(client, admin_headers):
    res = client.get("/api/reports?event_no=abc", headers=admin_headers)
    assert res.status_code == 400
    assert _err(res) == ("BAD_REQUEST", "event_no")


def test_alert_respond_bad_action(client, admin_headers):
    res = client.post("/api/alerts/1/respond", headers=admin_headers,
                      json={"action": "MAYBE"})
    assert res.status_code == 400
    assert _err(res) == ("BAD_REQUEST", "action")


def test_detection_bad_cctv_no(client):
    res = client.post("/api/internal/detections", headers=INTERNAL,
                      json={"cctv_no": "1", "detections": []})
    assert res.status_code == 400
    assert _err(res) == ("BAD_REQUEST", "cctv_no")


def test_detection_bad_detections(client):
    res = client.post("/api/internal/detections", headers=INTERNAL,
                      json={"cctv_no": 1, "detections": "flame"})
    assert res.status_code == 400
    assert _err(res) == ("BAD_REQUEST", "detections")


def test_detection_bad_captured_at(client):
    res = client.post("/api/internal/detections", headers=INTERNAL,
                      json={"cctv_no": 1, "detections": [], "captured_at": "어제"})
    assert res.status_code == 400
    assert _err(res) == ("BAD_REQUEST", "captured_at")


# ---------- 2. 특정할 입력이 없으면 field 를 넣지 않는다 ----------

def test_no_field_when_whole_request_is_empty(client, admin_headers):
    """'수정할 필드가 없습니다' 는 특정 입력 탓이 아니다 — 폼 상단에 띄울 몫."""
    for path in ("/api/users/2", "/api/cctvs/1", "/api/agencies/1"):
        res = client.put(path, headers=admin_headers, json={})
        assert res.status_code == 400, path
        assert _err(res) == ("BAD_REQUEST", None), path


# ---------- 3. 400 이 아닌 에러는 형식이 그대로다 ----------

def test_non_400_errors_carry_no_field(client, admin_headers):
    cases = [
        (client.get("/api/auth/me"), 401, "UNAUTHORIZED"),
        (client.get("/api/users", headers=admin_headers), None, None),  # 자리 채움용
        (client.get("/api/cctvs/9999", headers=admin_headers), 404, "CCTV_NOT_FOUND"),
        (client.post("/api/internal/detections", json={}), 401, "INTERNAL_UNAUTHORIZED"),
    ]
    for res, status, code in cases:
        if status is None:
            continue
        assert res.status_code == status
        assert _err(res) == (code, None)


def test_viewer_forbidden_carries_no_field(client, viewer_headers):
    res = client.get("/api/users", headers=viewer_headers)
    assert res.status_code == 403
    assert _err(res) == ("FORBIDDEN", None)
