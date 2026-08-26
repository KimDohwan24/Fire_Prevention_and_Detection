"""소방서 출동 통지 수신 — POST /api/reports/dispatch.

119 가 신고를 접수(ACCEPTED)한 뒤 실제로 배차하면 우리 callback_url 로 되쏜다.
그 신호를 받아 report_119 를 DISPATCHED 로 승격하는 경로의 테스트다.

인증은 JWT 가 아니라 공유 키(X-Agency-Key)다. 상대는 사람이 아니라 기관 서버다.
"""
from conftest import make_event, make_report

import config
import db
from services import report_service

URL = "/api/reports/dispatch"


def agency_headers(key=None):
    return {"X-Agency-Key": key or config.AGENCY_CALLBACK_KEY}


def dispatch_body(event_no, **overrides):
    """소방서가 보내는 출동 통지 본문."""
    body = {
        "report_uid": report_service.report_uid(event_no),
        "external_id": "R-TEST-001",
        "agency_name": "모의소방서 1",
        "dispatch_no": "D-R-TEST-001",
        "vehicles": 3,
        "crew": 12,
        "eta_sec": 240,
        "dispatched_at": "2026-08-18T14:32:10",
        "note": "펌프차 2 · 구급차 1 출동",
    }
    body.update(overrides)
    return body


def get_report(report_no):
    return db.query_one("SELECT * FROM report_119 WHERE report_no = %s", (report_no,))


# ---------- 인증 ----------

def test_rejects_without_key(client):
    """키가 없으면 401 — 아무나 신고 상태를 바꿀 수 없다."""
    event_no = make_event()
    make_report(event_no)

    r = client.post(URL, json=dispatch_body(event_no))

    assert r.status_code == 401
    assert r.get_json()["code"] == "AGENCY_UNAUTHORIZED"


def test_rejects_wrong_key(client):
    event_no = make_event()
    make_report(event_no)

    r = client.post(URL, headers=agency_headers(config.AGENCY_CALLBACK_KEY + "x"),
                    json=dispatch_body(event_no))

    assert r.status_code == 401
    assert r.get_json()["code"] == "AGENCY_UNAUTHORIZED"


# ---------- 입력 검증 ----------

def test_rejects_missing_report_uid(client):
    r = client.post(URL, headers=agency_headers(), json={"vehicles": 3})

    assert r.status_code == 400
    body = r.get_json()
    assert body["code"] == "BAD_REQUEST"
    assert body["field"] == "report_uid"


def test_rejects_malformed_report_uid(client):
    """'42' 처럼 형식이 다른 값은 400 이다 — 어느 화재인지 알 수 없다."""
    r = client.post(URL, headers=agency_headers(), json={"report_uid": "42"})

    assert r.status_code == 400
    assert r.get_json()["field"] == "report_uid"


# ---------- 대상 찾기 ----------

def test_returns_404_for_unknown_event(client):
    r = client.post(URL, headers=agency_headers(), json=dispatch_body(999999))

    assert r.status_code == 404
    assert r.get_json()["code"] == "REPORT_NOT_FOUND"


def test_returns_404_when_no_active_report(client):
    """NO_RESPONSE·FAILED 만 있는 이벤트는 진행 중인 신고가 아니다.

    그 기관은 이미 승계로 손을 뗐다. 뒤늦게 출동 통지가 와도 붙일 곳이 없다.
    """
    event_no = make_event()
    make_report(event_no, status="NO_RESPONSE")
    make_report(event_no, agency_no=2, sequence=2, status="FAILED")

    r = client.post(URL, headers=agency_headers(), json=dispatch_body(event_no))

    assert r.status_code == 404
    assert r.get_json()["code"] == "REPORT_NOT_FOUND"


# ---------- 정상 경로 ----------

def test_promotes_accepted_report_to_dispatched(client):
    """접수 확인된 신고에 출동이 붙는다."""
    event_no = make_event()
    report_no = make_report(event_no, status="ACCEPTED")

    r = client.post(URL, headers=agency_headers(), json=dispatch_body(event_no))

    assert r.status_code == 200
    body = r.get_json()
    assert body["report_no"] == report_no
    assert body["event_no"] == event_no
    assert body["report_status"] == "DISPATCHED"

    row = get_report(report_no)
    assert row["report_status"] == "DISPATCHED"
    assert row["report_dispatched_at"].isoformat() == "2026-08-18T14:32:10"
    assert row["report_dispatch"]["dispatch_no"] == "D-R-TEST-001"
    assert row["report_dispatch"]["vehicles"] == 3
    assert row["report_dispatch"]["agency_name"] == "모의소방서 1"
    assert row["report_dispatch"]["received_at"] is not None
    # report_uid 는 대상을 찾는 열쇠일 뿐이라 원문에 남기지 않는다
    assert "report_uid" not in row["report_dispatch"]


def test_promotes_sending_report_too(client):
    """SENDING 에서도 받는다.

    상대가 응답만 늦었을 뿐 접수는 했을 수 있다(mode=timeout 이 정확히 그 상황).
    그 신고에 출동이 붙는 것이 현실적으로 맞다.
    """
    event_no = make_event()
    report_no = make_report(event_no, status="SENDING")

    r = client.post(URL, headers=agency_headers(), json=dispatch_body(event_no))

    assert r.status_code == 200
    assert get_report(report_no)["report_status"] == "DISPATCHED"


def test_is_idempotent(client):
    """같은 통지가 두 번 와도 행이 늘지 않고 최신 값으로 덮인다."""
    event_no = make_event()
    make_report(event_no, status="ACCEPTED")

    client.post(URL, headers=agency_headers(), json=dispatch_body(event_no))
    r = client.post(URL, headers=agency_headers(),
                    json=dispatch_body(event_no, vehicles=5, note="증차"))

    assert r.status_code == 200
    rows = db.query("SELECT * FROM report_119 WHERE event_no = %s", (event_no,))
    assert len(rows) == 1
    assert rows[0]["report_dispatch"]["vehicles"] == 5
    assert rows[0]["report_dispatch"]["note"] == "증차"


def test_uses_receive_time_when_dispatched_at_is_unusable(client):
    """보낸 쪽 시각이 깨져 있어도 거절하지 않고 수신 시각으로 채운다.

    출동했다는 사실이 시각 형식보다 중요하다.
    """
    event_no = make_event()
    report_no = make_report(event_no, status="ACCEPTED")

    r = client.post(URL, headers=agency_headers(),
                    json=dispatch_body(event_no, dispatched_at="어제쯤"))

    assert r.status_code == 200
    assert get_report(report_no)["report_dispatched_at"] is not None


def test_accepts_mismatched_external_id(client):
    """접수번호가 어긋나도 통과시킨다 — 경고만 남긴다.

    mock-119 는 메모리라 재시작하면 접수번호가 1번부터 다시 발급된다. 그 불일치
    때문에 시연이 막히면 안 된다.
    """
    event_no = make_event()
    report_no = make_report(event_no, status="ACCEPTED")   # report_external_id = 'R-TEST-001'

    r = client.post(URL, headers=agency_headers(),
                    json=dispatch_body(event_no, external_id="R-999999"))

    assert r.status_code == 200
    assert get_report(report_no)["report_status"] == "DISPATCHED"


def test_keeps_unknown_fields(client):
    """모르는 키가 와도 버리지 않고 원문 그대로 보관한다."""
    event_no = make_event()
    report_no = make_report(event_no, status="ACCEPTED")

    client.post(URL, headers=agency_headers(),
                json=dispatch_body(event_no, ladder_truck=True, commander="김소방"))

    dispatch = get_report(report_no)["report_dispatch"]
    assert dispatch["ladder_truck"] is True
    assert dispatch["commander"] == "김소방"


# ---------- 영상 테스트 통지 ----------

def test_acknowledges_test_report_without_touching_db(client):
    """FG-TEST-<n> 은 영상 테스트의 모의 신고다 — 장부(report_119)에 없다.

    send_test_report 가 의도적으로 행을 만들지 않으므로 저장·승격할 대상이 없다.
    수신만 확인해 주고, 콘솔이 "출동 접수됨 · 시각"을 그릴 시각을 돌려준다.
    """
    event_no = make_event()
    report_no = make_report(event_no, status="ACCEPTED")
    before = db.query_one("SELECT count(*) AS cnt FROM report_119")["cnt"]

    r = client.post(URL, headers=agency_headers(),
                    json=dispatch_body(event_no,
                                       report_uid=f"FG-TEST-{event_no}"))

    assert r.status_code == 200
    body = r.get_json()
    assert body["test"] is True
    assert body["report_dispatched_at"] is not None

    # DB 는 일절 건드리지 않는다 — 행 수 그대로, 같은 이벤트의 실제 신고도 그대로
    after = db.query_one("SELECT count(*) AS cnt FROM report_119")["cnt"]
    assert after == before
    assert get_report(report_no)["report_status"] == "ACCEPTED"


def test_rejects_test_uid_with_non_numeric_tail(client):
    """'FG-TEST-abc' 는 테스트 통지도 실제 신고도 아니다 — 400."""
    r = client.post(URL, headers=agency_headers(),
                    json={"report_uid": "FG-TEST-abc"})

    assert r.status_code == 400
    assert r.get_json()["field"] == "report_uid"


# ---------- 진행 중 정의 ----------

def test_dispatched_report_blocks_new_report(monkeypatch):
    """출동 중인 화재에 신고가 또 나가지 않는다.

    ACTIVE_STATUSES 와 부분 유니크 인덱스가 어긋나면 여기서 드러난다.
    """
    event_no = make_event()
    make_report(event_no, status="ACCEPTED")
    db.execute("UPDATE report_119 SET report_status = 'DISPATCHED' WHERE event_no = %s",
               (event_no,))

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    rows = db.query("SELECT * FROM report_119 WHERE event_no = %s", (event_no,))
    assert len(rows) == 1
    assert result["report_status"] == "DISPATCHED"
