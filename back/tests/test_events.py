"""화재 이벤트 API 테스트 — 명세서 5번 섹션.

각 테스트는 conftest 의 make_event / make_media / make_alert / make_report 로
필요한 데이터를 직접 만든다. (시드에는 이벤트가 없음)
"""
import pytest

from conftest import make_alert, make_event, make_media, make_report


# ---------- 목록: 기본 ----------

def test_list_events_requires_auth(client):
    """토큰 없이 목록 조회 시 401."""
    r = client.get("/api/events")
    assert r.status_code == 401
    assert set(r.get_json().keys()) == {"code", "message"}


def test_list_events_empty(client, admin_headers):
    """이벤트가 없으면 빈 items 와 total_count 0 (페이징 공통 형식)."""
    r = client.get("/api/events", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["items"] == []
    assert body["total_count"] == 0
    assert body["page"] == 1
    assert set(body.keys()) == {"items", "page", "size", "total_count", "total_pages"}


def test_list_events_includes_joined_fields(client, admin_headers):
    """목록 항목에 카메라 정보와 대표 이미지가 JOIN 되어 내려온다."""
    ev = make_event(cctv_no=1)
    make_media(ev, is_primary=True, url="/media/events/1/primary.jpg")

    r = client.get("/api/events", headers=admin_headers)
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert len(items) == 1

    item = items[0]
    assert item["event_no"] == ev
    assert item["cctv_no"] == 1
    assert item["cctv_name"] == "정문 카메라"
    assert item["cctv_location"] == "본관 정문 앞"
    assert item["thumbnail_url"] == "/media/events/1/primary.jpg"
    # confidence 는 문자열이 아니라 JSON 숫자
    assert isinstance(item["event_confidence"], float)
    assert item["event_confidence"] == pytest.approx(0.9123)
    assert item["event_is_test"] is False


def test_list_events_thumbnail_picks_highest_confidence_primary(client, admin_headers):
    """대표 이미지가 여러 장이면 media_confidence 가 가장 높은 것을 고른다.

    ORDER BY 없는 LIMIT 1 은 어떤 행이 나올지 보장되지 않는다(플랜에 따라 바뀜).
    일부러 낮은 신뢰도 행을 먼저 넣어 '먼저 들어온 행'이 뽑히면 실패하게 만든다.
    """
    ev = make_event(cctv_no=1)
    make_media(ev, is_primary=True, url="/media/events/1/low.jpg", confidence=0.5000)
    make_media(ev, is_primary=True, url="/media/events/1/high.jpg", confidence=0.9900)
    # 대표가 아닌 행은 신뢰도가 더 높아도 후보가 아니다
    make_media(ev, is_primary=False, url="/media/events/1/not_primary.jpg",
               confidence=0.9999)

    for _ in range(3):  # 여러 번 불러도 같은 값이어야 한다
        items = client.get("/api/events", headers=admin_headers).get_json()["items"]
        assert items[0]["thumbnail_url"] == "/media/events/1/high.jpg"


def test_list_events_thumbnail_tiebreak_is_lowest_media_no(client, admin_headers):
    """신뢰도가 같으면 media_no 가 작은(먼저 저장된) 대표 이미지를 쓴다."""
    ev = make_event(cctv_no=1)
    first = make_media(ev, is_primary=True, url="/media/events/1/a.jpg",
                       confidence=0.7000)
    second = make_media(ev, is_primary=True, url="/media/events/1/b.jpg",
                        confidence=0.7000)
    assert first < second

    items = client.get("/api/events", headers=admin_headers).get_json()["items"]
    assert items[0]["thumbnail_url"] == "/media/events/1/a.jpg"


def test_list_events_excludes_test_events_by_default(client, admin_headers):
    """점검 모드(is_test) 이벤트는 기본 제외, include_test=true 면 포함."""
    normal = make_event(is_test=False)
    make_event(is_test=True)

    r = client.get("/api/events", headers=admin_headers)
    items = r.get_json()["items"]
    assert [it["event_no"] for it in items] == [normal]

    r = client.get("/api/events?include_test=true", headers=admin_headers)
    assert len(r.get_json()["items"]) == 2


# ---------- 목록: 필터 ----------

def test_list_events_filter_by_event_status(client, admin_headers):
    """event_status 필터: CONFIRMED / DISMISSED 각각 해당 건만."""
    confirmed = make_event(status="CONFIRMED")
    dismissed = make_event(status="DISMISSED")

    r = client.get("/api/events?event_status=CONFIRMED", headers=admin_headers)
    items = r.get_json()["items"]
    assert [it["event_no"] for it in items] == [confirmed]

    r = client.get("/api/events?event_status=DISMISSED", headers=admin_headers)
    items = r.get_json()["items"]
    assert [it["event_no"] for it in items] == [dismissed]


def test_list_events_filter_by_event_class(client, admin_headers):
    """event_class 필터: 일치하는 클래스만 반환."""
    flame = make_event(event_class="FLAME")
    make_event(event_class="SMOKE")

    r = client.get("/api/events?event_class=FLAME", headers=admin_headers)
    items = r.get_json()["items"]
    assert [it["event_no"] for it in items] == [flame]


def test_list_events_filter_by_cctv_no(client, admin_headers):
    """cctv_no 필터: 해당 카메라의 이벤트만 반환."""
    on_cam1 = make_event(cctv_no=1)
    make_event(cctv_no=2)

    r = client.get("/api/events?cctv_no=1", headers=admin_headers)
    items = r.get_json()["items"]
    assert [it["event_no"] for it in items] == [on_cam1]


def test_list_events_date_from(client, admin_headers):
    """date_from: 시작일 이후(당일 포함) 이벤트만."""
    make_event(detected_at="2026-08-01 10:00:00")
    later = make_event(detected_at="2026-08-08 14:30:00")

    r = client.get("/api/events?date_from=2026-08-05", headers=admin_headers)
    items = r.get_json()["items"]
    assert [it["event_no"] for it in items] == [later]


def test_list_events_date_to(client, admin_headers):
    """date_to: 종료일 이전 이벤트만."""
    earlier = make_event(detected_at="2026-08-01 10:00:00")
    make_event(detected_at="2026-08-08 14:30:00")

    r = client.get("/api/events?date_to=2026-08-05", headers=admin_headers)
    items = r.get_json()["items"]
    assert [it["event_no"] for it in items] == [earlier]


def test_list_events_date_to_includes_whole_day(client, admin_headers):
    """date_to 는 그 날 하루 전체 포함 (2026-08-08 14:30 이벤트가 date_to=2026-08-08 에 포함)."""
    make_event(detected_at="2026-08-01 10:00:00")
    make_event(detected_at="2026-08-08 14:30:00")

    r = client.get("/api/events?date_to=2026-08-08", headers=admin_headers)
    assert r.get_json()["total_count"] == 2

    # date_from 도 당일 00:00 부터 포함
    r = client.get("/api/events?date_from=2026-08-01", headers=admin_headers)
    assert r.get_json()["total_count"] == 2


# ---------- 목록: 잘못된 필터 값 (형식 오류 → 400) ----------

def test_list_events_invalid_cctv_no_returns_400(client, admin_headers):
    """cctv_no 에 숫자가 아닌 값이 오면 500 이 아니라 400 BAD_REQUEST."""
    r = client.get("/api/events?cctv_no=abc", headers=admin_headers)
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


def test_list_events_invalid_date_from_returns_400(client, admin_headers):
    """date_from 이 날짜 형식이 아니면 400 BAD_REQUEST."""
    r = client.get("/api/events?date_from=abc", headers=admin_headers)
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


def test_list_events_out_of_range_date_returns_400(client, admin_headers):
    """존재하지 않는 날짜(2026-13-99)도 400 BAD_REQUEST."""
    r = client.get("/api/events?date_from=2026-13-99", headers=admin_headers)
    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"

    r = client.get("/api/events?date_to=2026-13-99", headers=admin_headers)
    assert r.status_code == 400


def test_list_events_valid_date_filter_still_works(client, admin_headers):
    """정상 YYYY-MM-DD 날짜는 그대로 200."""
    make_event(detected_at="2026-08-08 14:30:00")
    r = client.get("/api/events?date_from=2026-08-01", headers=admin_headers)
    assert r.status_code == 200
    assert r.get_json()["total_count"] == 1


# ---------- 목록: 정렬 · 페이징 ----------

def test_list_events_ordered_newest_first(client, admin_headers):
    """최신순 정렬 — event_no 가 큰 것이 먼저."""
    first = make_event()
    second = make_event()
    third = make_event()

    r = client.get("/api/events", headers=admin_headers)
    items = r.get_json()["items"]
    assert [it["event_no"] for it in items] == [third, second, first]


def test_list_events_pagination(client, admin_headers):
    """size=2 로 3건 조회: 1페이지 2건 + 2페이지 1건, total 은 그대로."""
    for _ in range(3):
        make_event()

    r = client.get("/api/events?page=1&size=2", headers=admin_headers)
    body = r.get_json()
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["size"] == 2
    assert body["total_count"] == 3
    assert body["total_pages"] == 2

    r = client.get("/api/events?page=2&size=2", headers=admin_headers)
    body = r.get_json()
    assert len(body["items"]) == 1
    assert body["page"] == 2
    assert body["total_count"] == 3


# ---------- 상세 ----------

def test_event_detail_full_payload(client, admin_headers):
    """상세: 이벤트 + 카메라 + 미디어(대표 먼저) + 알림 + 신고 이력을 한 번에."""
    ev = make_event(cctv_no=1)
    extra_no = make_media(ev, media_type="FRAME", is_primary=False,
                          url=f"/media/events/{ev}/frame_002.jpg")
    frame_no = make_media(ev, media_type="FRAME", is_primary=True,
                          url=f"/media/events/{ev}/frame.jpg")
    alert_no = make_alert(ev, user_no=1)
    report_no = make_report(ev, agency_no=1)

    r = client.get(f"/api/events/{ev}", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()

    # 이벤트 본문
    assert body["event_no"] == ev
    assert body["event_status"] == "CONFIRMED"
    assert body["event_class"] == "FLAME"
    assert body["event_detected_frames"] == 32
    assert body["event_threshold_frames"] == 30
    assert body["event_confidence"] == pytest.approx(0.9123)

    # 카메라 객체
    cctv = body["cctv"]
    assert cctv["cctv_no"] == 1
    assert cctv["cctv_name"] == "정문 카메라"
    assert cctv["cctv_location"] == "본관 정문 앞"
    assert cctv["cctv_lat"] == pytest.approx(37.5665)
    assert cctv["cctv_lng"] == pytest.approx(126.978)

    # 미디어: 대표(FRAME)가 먼저, jsonb 는 리스트로 역직렬화
    media = body["media"]
    assert len(media) == 2
    assert media[0]["media_no"] == frame_no
    assert media[0]["media_is_primary"] is True
    assert media[0]["media_type"] == "FRAME"
    assert media[1]["media_no"] == extra_no
    detections = media[0]["media_detections"]
    assert isinstance(detections, list)
    assert isinstance(detections[0], dict)
    assert detections[0]["cls"] == "flame"

    # 알림: 사용자 이름 JOIN
    alerts = body["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["alert_no"] == alert_no
    assert alerts[0]["user_name"] == "관리자"

    # 신고: 기관 이름 JOIN
    reports = body["reports"]
    assert len(reports) == 1
    assert reports[0]["report_no"] == report_no
    assert reports[0]["agency_name"] == "종로소방서"


def test_event_detail_not_found(client, admin_headers):
    """없는 이벤트 번호는 404 EVENT_NOT_FOUND."""
    r = client.get("/api/events/999", headers=admin_headers)
    assert r.status_code == 404
    assert r.get_json()["code"] == "EVENT_NOT_FOUND"


def test_event_dates_are_iso_strings(client, admin_headers):
    """날짜 필드는 'T' 가 들어간 ISO 8601 문자열로 직렬화된다."""
    ev = make_event(detected_at="2026-08-08 14:30:00")

    r = client.get("/api/events", headers=admin_headers)
    item = r.get_json()["items"][0]
    assert isinstance(item["event_detected_at"], str)
    assert "T" in item["event_detected_at"]
    assert item["event_detected_at"].startswith("2026-08-08T14:30:00")

    r = client.get(f"/api/events/{ev}", headers=admin_headers)
    body = r.get_json()
    assert "T" in body["event_detected_at"]
    assert "T" in body["event_first_detected_at"]
