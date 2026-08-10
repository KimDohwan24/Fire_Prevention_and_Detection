"""엔드투엔드 파이프라인 시나리오 테스트.

AI 검출 수집(POST /api/internal/detections) → 이벤트 확정 → 알림 2건(PUSH+SMS)
→ 사용자 응답 또는 무응답 에스컬레이션 → 119 신고까지, 실제 HTTP 라우트를
통과시키며 한 흐름으로 검증한다. 서비스 함수를 직접 부르는 것은 API 가 없는
지점(에스컬레이션 스윕)뿐이다.

빠르게 확정시키기 위해 EVENT_THRESHOLD_FRAMES 를 2 로 낮춘다. 유예 마감은
sleep 대신 SQL 로 alert_deadline_at 을 과거로 당겨 흉내낸다.
119 전송은 conftest 의 autouse 스텁(`_no_real_report_http`)이 항상 2xx 로
받아주므로 실제 네트워크는 나가지 않는다.
"""
from datetime import datetime

import requests
from conftest import make_alert, make_event

import config
import db
from services import escalation

# conftest 시드: cctv 1(정문 카메라)의 소유자는 user_no 1(admin01)
OWNER_NO = 1

FLAME = {"cls": "flame", "conf": 0.91, "box": [0.238, 0.259, 0.047, 0.113]}


# ---------- 헬퍼 ----------

def _key_headers():
    """내부 API 인증 헤더 (JWT 아님)."""
    return {"X-Internal-Key": config.INTERNAL_API_KEY}


def post_frame(client, cctv_no=1, captured_at=None, media_url=None):
    """AI 모델이 보내는 검출 프레임 1장."""
    body = {"cctv_no": cctv_no, "detections": [FLAME]}
    if captured_at is not None:
        body["captured_at"] = captured_at
    if media_url is not None:
        body["media_url"] = media_url
    return client.post("/api/internal/detections", json=body, headers=_key_headers())


def confirm_event_via_api(client, cctv_no=1):
    """임계값(2프레임)까지 프레임을 보내 이벤트를 CONFIRMED 로 만든다.

    반환: 확정된 event_no. (monkeypatch 로 EVENT_THRESHOLD_FRAMES=2 인 상태 전제)
    """
    first = post_frame(client, cctv_no=cctv_no, captured_at="2026-08-08T14:30:00",
                       media_url="/media/events/raw/f001.jpg").get_json()
    assert first["event_status"] == "PENDING"

    second = post_frame(client, cctv_no=cctv_no, captured_at="2026-08-08T14:30:01",
                        media_url="/media/events/raw/f002.jpg").get_json()
    assert second["event_status"] == "CONFIRMED"
    assert second["event_no"] == first["event_no"]
    return second["event_no"]


def get_alerts(event_no):
    return db.query(
        "SELECT * FROM alert WHERE event_no = %s ORDER BY alert_no", (event_no,)
    )


def get_reports(event_no):
    return db.query(
        "SELECT * FROM report_119 WHERE event_no = %s ORDER BY report_no", (event_no,)
    )


def expire_deadline(event_no):
    """유예 마감을 과거로 당긴다 (sleep 대신 시간 경과를 흉내낸다)."""
    return db.execute(
        "UPDATE alert SET alert_deadline_at = now() - interval '1 minute' "
        "WHERE event_no = %s",
        (event_no,),
    )


def alert_of(event_no, channel):
    """이벤트의 특정 채널 알림 행을 집어온다."""
    return db.query_one(
        "SELECT * FROM alert WHERE event_no = %s AND alert_channel = %s",
        (event_no, channel),
    )


class _Accepted:
    """119 기관의 2xx 응답 대역."""
    status_code = 200

    def json(self):
        return {"external_id": "R-E2E-001"}


# ---------- 시나리오 1: 무응답 → 자동 신고 ----------

def test_no_response_timeout_triggers_automatic_report(client, admin_headers,
                                                       monkeypatch):
    """시나리오: 검출 누적 → 확정 → 알림 2건 → 무응답 유예 초과 → 119 자동 신고.

    프레임 수집부터 신고 조회까지 전부 공개/내부 API 로 확인한다.
    """
    monkeypatch.setattr(config, "EVENT_THRESHOLD_FRAMES", 2)

    event_no = confirm_event_via_api(client)

    # 확정 즉시 소유자 앞으로 PUSH·SMS 두 알림이 동시에 생성된다
    alerts = get_alerts(event_no)
    assert len(alerts) == 2
    assert [a["alert_channel"] for a in alerts] == ["PUSH", "SMS"]
    assert {a["alert_status"] for a in alerts} == {"SENT"}
    assert {a["user_no"] for a in alerts} == {OWNER_NO}
    assert {a["alert_level"] for a in alerts} == {1}          # 승격 개념 없음
    assert alerts[0]["alert_sent_at"] == alerts[1]["alert_sent_at"]
    assert alerts[0]["alert_deadline_at"] == alerts[1]["alert_deadline_at"]

    # 소유자의 알림 목록 API 에도 두 건 다 보인다
    listed = client.get("/api/alerts", headers=admin_headers).get_json()
    assert listed["total_count"] == 2
    assert {it["alert_channel"] for it in listed["items"]} == {"PUSH", "SMS"}

    # 유예 초과 → 에스컬레이션 스윕
    expire_deadline(event_no)
    summary = escalation.run_escalation_tick()
    assert summary["reported"] == 1

    # 두 알림 모두 무응답으로 닫히고, 신고가 하나 생성된다
    assert [a["alert_status"] for a in get_alerts(event_no)] == \
        ["NO_RESPONSE", "NO_RESPONSE"]
    (report,) = get_reports(event_no)
    assert report["report_status"] == "DISPATCHED"
    assert report["report_trigger_reason"] == "NO_RESPONSE_TIMEOUT"
    assert report["report_sequence"] == 1
    assert report["agency_no"] == 1              # 가장 가까운 종로소방서

    # 이벤트 상세에 알림·신고 이력이 함께 보인다
    detail = client.get(f"/api/events/{event_no}", headers=admin_headers).get_json()
    assert detail["event_status"] == "CONFIRMED"
    assert [a["alert_status"] for a in detail["alerts"]] == \
        ["NO_RESPONSE", "NO_RESPONSE"]
    assert [r["report_no"] for r in detail["reports"]] == [report["report_no"]]
    assert detail["reports"][0]["report_status"] == "DISPATCHED"

    # 신고 목록 API 에서 event_no 로 필터링된다
    r = client.get(f"/api/reports?event_no={event_no}", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["total_count"] == 1
    assert body["items"][0]["report_no"] == report["report_no"]
    assert body["items"][0]["report_trigger_reason"] == "NO_RESPONSE_TIMEOUT"


# ---------- 시나리오 2: 사용자 화재 확인 → 즉시 신고 ----------

def test_user_confirms_fire_reports_immediately(client, admin_headers, monkeypatch):
    """시나리오: 확정 → 사용자가 PUSH 알림에 READ → 즉시 119 신고, 이후 스윕은 무동작.

    형제(SMS) 알림도 같이 READ 로 닫히므로 에스컬레이션 대상에서 빠지고,
    나중에 스윕이 돌아도 두 번째 신고는 생기지 않는다.
    """
    monkeypatch.setattr(config, "EVENT_THRESHOLD_FRAMES", 2)

    event_no = confirm_event_via_api(client)
    push_no = alert_of(event_no, "PUSH")["alert_no"]

    r = client.post(f"/api/alerts/{push_no}/respond",
                    json={"action": "READ"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.get_json()["alert_status"] == "READ"

    # 응답은 이벤트 단위 — 형제 SMS 알림도 같은 상태·같은 시각으로 닫힌다
    alerts = get_alerts(event_no)
    assert [a["alert_status"] for a in alerts] == ["READ", "READ"]
    assert alerts[0]["alert_responded_at"] == alerts[1]["alert_responded_at"]

    (report,) = get_reports(event_no)
    assert report["report_status"] == "DISPATCHED"
    assert report["report_trigger_reason"] == "USER_CONFIRMED"

    # 이미 응답한 형제에 다시 응답하면 409
    sms_no = alert_of(event_no, "SMS")["alert_no"]
    dup = client.post(f"/api/alerts/{sms_no}/respond",
                      json={"action": "READ"}, headers=admin_headers)
    assert dup.status_code == 409
    assert dup.get_json()["code"] == "ALREADY_RESPONDED"

    # 마감이 지나고 스윕이 돌아도 두 번째 신고는 없다
    expire_deadline(event_no)
    summary = escalation.run_escalation_tick()
    assert summary["reported"] == 0
    assert [a["alert_status"] for a in get_alerts(event_no)] == ["READ", "READ"]
    assert len(get_reports(event_no)) == 1


# ---------- 시나리오 3: 오탐 취소 → 신고 없음 ----------

def test_user_cancels_false_alarm_never_reports(client, admin_headers, monkeypatch):
    """시나리오: 확정 → 사용자가 오탐으로 CANCEL → 신고는 영원히 생기지 않는다."""
    monkeypatch.setattr(config, "EVENT_THRESHOLD_FRAMES", 2)

    event_no = confirm_event_via_api(client)
    push_no = alert_of(event_no, "PUSH")["alert_no"]

    r = client.post(f"/api/alerts/{push_no}/respond",
                    json={"action": "CANCEL"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.get_json()["alert_status"] == "CANCELED"

    assert [a["alert_status"] for a in get_alerts(event_no)] == \
        ["CANCELED", "CANCELED"]
    assert get_reports(event_no) == []

    # 마감이 지나도 취소된 이벤트는 에스컬레이션 대상이 아니다
    expire_deadline(event_no)
    summary = escalation.run_escalation_tick()
    assert summary["reported"] == 0
    assert [a["alert_status"] for a in get_alerts(event_no)] == \
        ["CANCELED", "CANCELED"]
    assert get_reports(event_no) == []

    # 마감 이후의 CANCEL 시도는 409 DEADLINE_PASSED (별도 이벤트로 확인)
    late_event = make_event()
    late_alert = make_alert(late_event, user_no=OWNER_NO, deadline_offset_sec=-10)
    late = client.post(f"/api/alerts/{late_alert}/respond",
                       json={"action": "CANCEL"}, headers=admin_headers)
    assert late.status_code == 409
    assert late.get_json()["code"] == "DEADLINE_PASSED"


# ---------- 시나리오 4: 점검 모드 ----------

def test_test_mode_event_produces_no_alerts_and_no_reports(client, admin_headers):
    """시나리오: 점검 모드(event_is_test) 이벤트는 알림도 신고도 만들지 않는다.

    내부 검출 API 에는 점검 모드를 켜는 필드가 없다(운영 흐름상 AI 가 결정할 값이
    아니다). 그래서 점검 모드 PENDING 이벤트를 미리 만들어 두고, 그 카메라로
    실제 검출 프레임을 보내 API 경로 그대로 CONFIRMED 까지 밀어붙인다.
    (make_event 는 frames=32 / threshold=30 이므로 프레임 1장이면 확정된다)
    """
    now_iso = datetime.now().isoformat(timespec="seconds")
    event_no = make_event(status="PENDING", is_test=True,
                          detected_at=now_iso.replace("T", " "))

    body = post_frame(client, captured_at=now_iso).get_json()
    assert body["event_no"] == event_no
    assert body["event_status"] == "CONFIRMED"

    # 확정 훅이 돌았지만 알림이 하나도 만들어지지 않는다
    assert get_alerts(event_no) == []

    # 에스컬레이션 스윕도 점검 모드 이벤트를 건드리지 않는다
    summary = escalation.run_escalation_tick()
    assert summary["reported"] == 0
    assert get_reports(event_no) == []

    # 점검 이벤트는 기본 목록에서도 감춰진다 (include_test=true 로만 보인다)
    hidden = client.get("/api/events", headers=admin_headers).get_json()
    assert [it["event_no"] for it in hidden["items"]] == []
    shown = client.get("/api/events?include_test=true", headers=admin_headers).get_json()
    assert [it["event_no"] for it in shown["items"]] == [event_no]


# ---------- 시나리오 5: 기관 승계 ----------

def test_first_agency_exhausted_takes_over_to_second(client, monkeypatch):
    """시나리오: 무응답 자동 신고에서 1순위 기관이 전 회차 실패 → 2순위 기관으로 승계.

    1순위(종로소방서) endpoint 만 실패시키고 2순위(중부소방서)는 성공시킨다.
    """
    monkeypatch.setattr(config, "EVENT_THRESHOLD_FRAMES", 2)

    # 시드는 두 기관 endpoint 가 같으므로 기관별로 구분되게 바꾼다
    db.execute("UPDATE agency SET agency_endpoint = 'http://a1/report' "
               "WHERE agency_no = 1")
    db.execute("UPDATE agency SET agency_endpoint = 'http://a2/report' "
               "WHERE agency_no = 2")

    calls = []

    def fake_post(endpoint, payload):
        calls.append(endpoint)
        if endpoint == "http://a1/report":
            raise requests.exceptions.ConnectionError("1순위 기관 모의 접속 실패")
        return _Accepted()

    monkeypatch.setattr("services.report_service._post_report", fake_post)

    event_no = confirm_event_via_api(client)
    expire_deadline(event_no)
    summary = escalation.run_escalation_tick()
    assert summary["reported"] == 1

    first, second = get_reports(event_no)

    # 1순위: 시도 횟수 소진 후 무응답으로 승계
    assert first["agency_no"] == 1
    assert first["report_sequence"] == 1
    assert first["report_status"] == "NO_RESPONSE"
    assert first["report_attempt_count"] == config.MAX_REPORT_ATTEMPTS
    assert first["report_dispatched_at"] is None

    # 2순위: 승계받아 출동 접수
    assert second["agency_no"] == 2
    assert second["report_sequence"] == 2
    assert second["report_status"] == "DISPATCHED"
    assert second["report_trigger_reason"] == "NO_RESPONSE_TIMEOUT"
    assert second["report_external_id"] == "R-E2E-001"
    assert second["report_dispatched_at"] is not None

    # 1순위에 MAX_REPORT_ATTEMPTS 회, 2순위에 1회
    assert calls == ["http://a1/report"] * config.MAX_REPORT_ATTEMPTS \
        + ["http://a2/report"]

    # 거리 오름차순이므로 1순위가 더 가깝다
    assert float(first["report_distance_km"]) < float(second["report_distance_km"])

    # 진행 중(SENDING/DISPATCHED) 신고는 이벤트당 1건뿐
    active = [r for r in get_reports(event_no)
              if r["report_status"] in ("SENDING", "DISPATCHED")]
    assert len(active) == 1
    assert active[0]["report_no"] == second["report_no"]
