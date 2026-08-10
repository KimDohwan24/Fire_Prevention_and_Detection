"""내부 검출 수집 API 테스트 — POST /api/internal/detections.

AI 모델이 프레임 1장의 검출 결과를 보낼 때마다:
- X-Internal-Key 헤더로 인증 (JWT 아님)
- 화재(flame/smoke) 검출이 있으면 PENDING 이벤트에 프레임을 누적
- 임계 프레임 수에 도달하면 CONFIRMED 로 확정 + 확정 훅 호출
- 윈도우(EVENT_WINDOW_SEC) 를 넘겨 끊긴 PENDING 은 DISMISSED 처리
"""
from datetime import datetime, timedelta

import pytest

import config
import db
from services import event_service


# ---------- 요청 헬퍼 ----------

FLAME = {"cls": "flame", "conf": 0.91, "box": [0.238, 0.259, 0.047, 0.113]}
SMOKE = {"cls": "smoke", "conf": 0.55, "box": [0.412, 0.688, 0.031, 0.142]}
PERSON = {"cls": "person", "conf": 0.77, "box": [0.512, 0.388, 0.131, 0.242]}


def _key_headers():
    """올바른 내부 키 헤더."""
    return {"X-Internal-Key": config.INTERNAL_API_KEY}


def post_frame(client, cctv_no=1, detections=None, captured_at=None,
               media_url=None, headers=None):
    """검출 프레임 1장을 전송한다. detections 기본값은 flame 1개."""
    body = {"cctv_no": cctv_no,
            "detections": [FLAME] if detections is None else detections}
    if captured_at is not None:
        body["captured_at"] = captured_at
    if media_url is not None:
        body["media_url"] = media_url
    return client.post("/api/internal/detections", json=body,
                       headers=_key_headers() if headers is None else headers)


def get_event_row(event_no):
    return db.query_one("SELECT * FROM fire_event WHERE event_no = %s", (event_no,))


def get_media_rows(event_no):
    return db.query(
        "SELECT * FROM event_media WHERE event_no = %s ORDER BY media_no", (event_no,)
    )


# ---------- 인증 ----------

def test_missing_internal_key_401(client):
    """X-Internal-Key 헤더가 없으면 401 INTERNAL_UNAUTHORIZED."""
    r = post_frame(client, headers={})
    assert r.status_code == 401
    assert r.get_json()["code"] == "INTERNAL_UNAUTHORIZED"


def test_wrong_internal_key_401(client):
    """키 값이 다르면 401 INTERNAL_UNAUTHORIZED."""
    r = post_frame(client, headers={"X-Internal-Key": config.INTERNAL_API_KEY + "x"})
    assert r.status_code == 401
    assert r.get_json()["code"] == "INTERNAL_UNAUTHORIZED"


# ---------- 검증 ----------

def test_unknown_cctv_404(client):
    """존재하지 않는 카메라 번호면 404 CCTV_NOT_FOUND."""
    r = post_frame(client, cctv_no=999)
    assert r.status_code == 404
    assert r.get_json()["code"] == "CCTV_NOT_FOUND"


def test_missing_cctv_no_400(client):
    """cctv_no 누락(또는 정수 아님)이면 400 BAD_REQUEST."""
    r = client.post("/api/internal/detections",
                    json={"detections": [FLAME]}, headers=_key_headers())
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


def test_detections_not_a_list_400(client):
    """detections 가 리스트가 아니면 400 BAD_REQUEST."""
    r = client.post("/api/internal/detections",
                    json={"cctv_no": 1, "detections": "flame"},
                    headers=_key_headers())
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


# ---------- 첫 프레임 · 무시 케이스 ----------

def test_first_fire_frame_creates_pending_event(client):
    """첫 화재 프레임: PENDING 이벤트 생성 + 미디어 1건(대표) 저장."""
    r = post_frame(client, detections=[FLAME, PERSON],
                   captured_at="2026-08-08T14:30:00",
                   media_url="/media/events/raw/f001.jpg")
    assert r.status_code == 200
    body = r.get_json()
    assert body["event_no"] is not None
    assert body["event_status"] == "PENDING"
    assert body["event_detected_frames"] == 1
    assert body["event_threshold_frames"] == config.EVENT_THRESHOLD_FRAMES

    ev = get_event_row(body["event_no"])
    assert ev["event_status"] == "PENDING"
    assert ev["event_class"] == "FLAME"
    assert ev["event_detected_frames"] == 1
    assert float(ev["event_confidence"]) == pytest.approx(0.91)
    assert ev["event_first_detected_at"].isoformat().startswith("2026-08-08T14:30:00")
    assert ev["event_detected_at"] is None  # 아직 확정 전

    media = get_media_rows(body["event_no"])
    assert len(media) == 1
    m = media[0]
    assert m["media_type"] == "FRAME"
    assert m["media_url"] == "/media/events/raw/f001.jpg"
    assert m["media_is_primary"] is True
    assert float(m["media_confidence"]) == pytest.approx(0.91)
    # person 검출도 원본 그대로 media_detections 에 저장된다
    assert m["media_detections"] == [FLAME, PERSON]


def test_non_fire_frame_without_open_event_is_ignored(client):
    """화재 검출이 없고 열린 이벤트도 없으면 event_no null + ignored."""
    r = post_frame(client, detections=[PERSON])
    assert r.status_code == 200
    body = r.get_json()
    assert body["event_no"] is None
    assert body["ignored"] is True
    # 이벤트도 미디어도 만들어지지 않는다
    assert db.query_one("SELECT count(*) AS cnt FROM fire_event")["cnt"] == 0


def test_non_fire_frame_with_open_event_does_not_increment(client):
    """열린 이벤트가 있어도 비화재 프레임은 누적/저장하지 않고 현재 상태만 반환."""
    ev_no = post_frame(client, captured_at="2026-08-08T14:30:00").get_json()["event_no"]

    r = post_frame(client, detections=[PERSON], captured_at="2026-08-08T14:30:01")
    assert r.status_code == 200
    body = r.get_json()
    assert body["event_no"] == ev_no
    assert body["event_status"] == "PENDING"
    assert body["event_detected_frames"] == 1  # 그대로

    assert get_event_row(ev_no)["event_detected_frames"] == 1
    assert len(get_media_rows(ev_no)) == 1  # 비화재 프레임 미디어는 저장 안 함


# ---------- 누적 · 확정 ----------

def test_accumulate_to_threshold_confirms(client, monkeypatch):
    """임계 프레임 수 도달 시 CONFIRMED + event_detected_at 기록."""
    monkeypatch.setattr(config, "EVENT_THRESHOLD_FRAMES", 3)

    r1 = post_frame(client, captured_at="2026-08-08T14:30:00")
    assert r1.get_json()["event_status"] == "PENDING"
    r2 = post_frame(client, captured_at="2026-08-08T14:30:01")
    assert r2.get_json()["event_status"] == "PENDING"
    r3 = post_frame(client, captured_at="2026-08-08T14:30:02")

    body = r3.get_json()
    assert body["event_status"] == "CONFIRMED"
    assert body["event_detected_frames"] == 3
    assert body["event_threshold_frames"] == 3

    ev = get_event_row(body["event_no"])
    assert ev["event_status"] == "CONFIRMED"
    assert ev["event_detected_at"] is not None


def test_confirmed_event_is_closed_for_new_frames(client, monkeypatch):
    """확정된 이벤트는 더 이상 열린 이벤트가 아니다 — 다음 화재 프레임은 새 이벤트."""
    monkeypatch.setattr(config, "EVENT_THRESHOLD_FRAMES", 2)
    post_frame(client, captured_at="2026-08-08T14:30:00")
    confirmed = post_frame(client, captured_at="2026-08-08T14:30:01").get_json()
    assert confirmed["event_status"] == "CONFIRMED"

    r = post_frame(client, captured_at="2026-08-08T14:30:02")
    body = r.get_json()
    assert body["event_no"] != confirmed["event_no"]
    assert body["event_status"] == "PENDING"
    assert body["event_detected_frames"] == 1


def test_class_merge_flame_then_smoke(client):
    """FLAME 이벤트에 SMOKE 프레임이 오면 FLAME_SMOKE 로 병합."""
    ev_no = post_frame(client, detections=[FLAME],
                       captured_at="2026-08-08T14:30:00").get_json()["event_no"]
    assert get_event_row(ev_no)["event_class"] == "FLAME"

    post_frame(client, detections=[SMOKE], captured_at="2026-08-08T14:30:01")
    assert get_event_row(ev_no)["event_class"] == "FLAME_SMOKE"


def test_confidence_takes_max(client):
    """event_confidence 는 지금까지 프레임 중 최고 화재 신뢰도."""
    low = {"cls": "flame", "conf": 0.5, "box": [0.1, 0.1, 0.1, 0.1]}
    high = {"cls": "flame", "conf": 0.93, "box": [0.1, 0.1, 0.1, 0.1]}
    mid = {"cls": "flame", "conf": 0.7, "box": [0.1, 0.1, 0.1, 0.1]}

    ev_no = post_frame(client, detections=[low],
                       captured_at="2026-08-08T14:30:00").get_json()["event_no"]
    post_frame(client, detections=[high], captured_at="2026-08-08T14:30:01")
    post_frame(client, detections=[mid], captured_at="2026-08-08T14:30:02")

    assert float(get_event_row(ev_no)["event_confidence"]) == pytest.approx(0.93)


def test_higher_confidence_frame_steals_primary(client):
    """더 높은 신뢰도의 프레임이 오면 대표 이미지가 교체된다 (항상 1건만 대표)."""
    low = {"cls": "flame", "conf": 0.5, "box": [0.1, 0.1, 0.1, 0.1]}
    high = {"cls": "flame", "conf": 0.93, "box": [0.1, 0.1, 0.1, 0.1]}
    mid = {"cls": "flame", "conf": 0.7, "box": [0.1, 0.1, 0.1, 0.1]}

    ev_no = post_frame(client, detections=[low], media_url="/m/f1.jpg",
                       captured_at="2026-08-08T14:30:00").get_json()["event_no"]
    post_frame(client, detections=[high], media_url="/m/f2.jpg",
               captured_at="2026-08-08T14:30:01")
    post_frame(client, detections=[mid], media_url="/m/f3.jpg",
               captured_at="2026-08-08T14:30:02")

    media = get_media_rows(ev_no)
    assert len(media) == 3
    primaries = [m for m in media if m["media_is_primary"]]
    assert len(primaries) == 1
    assert primaries[0]["media_url"] == "/m/f2.jpg"


# ---------- 윈도우 초과 · 정리 ----------

def test_stale_pending_dismissed_and_new_event_started(client):
    """마지막 활동에서 윈도우(60초)를 넘긴 프레임은 기존 PENDING 을 기준미달 처리하고 새 이벤트를 연다."""
    old_no = post_frame(client, captured_at="2026-08-08T14:30:00").get_json()["event_no"]

    r = post_frame(client, captured_at="2026-08-08T14:31:01")  # 61초 뒤
    body = r.get_json()
    assert body["event_no"] != old_no
    assert body["event_status"] == "PENDING"
    assert body["event_detected_frames"] == 1

    assert get_event_row(old_no)["event_status"] == "DISMISSED"


def test_sweep_stale_pending(client):
    """sweep_stale_pending: 윈도우를 넘긴 PENDING 만 일괄 DISMISSED, 건수 반환."""
    stale_at = (datetime.now() - timedelta(seconds=config.EVENT_WINDOW_SEC + 30))
    fresh_at = datetime.now()
    stale_no = post_frame(client, captured_at=stale_at.isoformat()).get_json()["event_no"]
    fresh_no = post_frame(client, cctv_no=2,
                          captured_at=fresh_at.isoformat()).get_json()["event_no"]

    count = event_service.sweep_stale_pending()
    assert count == 1
    assert get_event_row(stale_no)["event_status"] == "DISMISSED"
    assert get_event_row(fresh_no)["event_status"] == "PENDING"


# ---------- 확정 훅 ----------

def test_hook_called_on_confirm(client, monkeypatch):
    """CONFIRMED 전환 시 services.hooks.on_event_confirmed(event_no) 가 호출된다."""
    monkeypatch.setattr(config, "EVENT_THRESHOLD_FRAMES", 2)
    calls = []
    monkeypatch.setattr("services.hooks.on_event_confirmed",
                        lambda event_no: calls.append(event_no))

    post_frame(client, captured_at="2026-08-08T14:30:00")
    assert calls == []  # 아직 확정 전

    body = post_frame(client, captured_at="2026-08-08T14:30:01").get_json()
    assert body["event_status"] == "CONFIRMED"
    assert calls == [body["event_no"]]


# ---------- 공개 목록과의 연동 ----------

def test_pending_event_visible_in_public_list(client, admin_headers):
    """PENDING 이벤트도 GET /api/events 목록에 그대로 보인다."""
    ev_no = post_frame(client, captured_at="2026-08-08T14:30:00").get_json()["event_no"]

    r = client.get("/api/events", headers=admin_headers)
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert [it["event_no"] for it in items] == [ev_no]
    assert items[0]["event_status"] == "PENDING"
