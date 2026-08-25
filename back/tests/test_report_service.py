"""119 신고 서비스 테스트 — services/report_service.py.

신고 정책 (D4 확정):
- 트리거: 사용자가 화재 확인(USER_CONFIRMED) 또는 무응답 에스컬레이션(NO_RESPONSE_TIMEOUT).
- 대상 기관: 활성(agency_is_active) 기관을 CCTV 좌표 기준 PostGIS 거리 오름차순으로 시도.
  (거리 계산·정렬은 DB 가 한다 — 최근접 탐색 자체의 검증은 test_geo_postgis.py)
- 안쪽 루프: 한 기관에 최대 MAX_REPORT_ATTEMPTS(운영 기본 1 = 재전송 없음)회
  전송(report_attempt_count). 테스트는 conftest 가 4 로 올려 루프 경로를 지킨다.
- 바깥 루프: 기관 승계(report_sequence 1, 2, ...). 소진된 기관 행은 NO_RESPONSE,
  마지막 기관까지 소진되면 그 행만 FAILED.
- DB 부분 유니크 인덱스(UX_report_119_active)로 이벤트당 진행 중 신고 1건 강제.
- 실제 HTTP 는 절대 나가지 않는다 — _post_report 를 monkeypatch 한다.
"""
import base64

import psycopg2
import pytest
import requests
from conftest import make_alert, make_alert_pair, make_event, make_media, make_report

import config
import db
from services import report_service

# conftest 시드 좌표
CCTV1 = (37.5665, 126.9780)      # cctv 1 (정문 카메라, '본관 정문 앞')
AGENCY1 = (37.5720, 126.9794)    # 종로소방서
AGENCY2 = (37.5610, 126.9950)    # 중부소방서


class FakeResponse:
    """requests.Response 대역 — status_code 와 json() 만 흉내낸다."""

    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("본문 없음")
        return self._body


def get_report_rows(event_no=None):
    if event_no is None:
        return db.query("SELECT * FROM report_119 ORDER BY report_no")
    return db.query(
        "SELECT * FROM report_119 WHERE event_no = %s ORDER BY report_no", (event_no,)
    )


def patch_post(monkeypatch, fn):
    """_post_report 를 대역으로 바꾸고 호출 기록 리스트를 돌려준다."""
    calls = []

    def wrapper(endpoint, payload):
        calls.append((endpoint, payload))
        return fn(endpoint, payload, len(calls))

    monkeypatch.setattr("services.report_service._post_report", wrapper)
    return calls


def set_distinct_endpoints():
    """시드는 두 기관이 같은 endpoint 라서, 기관별 구분이 필요한 테스트용."""
    db.execute("UPDATE agency SET agency_endpoint = 'http://a1/report' WHERE agency_no = 1")
    db.execute("UPDATE agency SET agency_endpoint = 'http://a2/report' WHERE agency_no = 2")


# ---------- 성공 경로 ----------

def test_start_report_success_first_try(monkeypatch):
    """첫 시도 성공: 가장 가까운 기관(1)으로 ACCEPTED 행 1개, 거리/주소/외부ID 저장."""
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-2026-0001"}))
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    rows = get_report_rows(event_no)
    assert len(rows) == 1
    r = rows[0]
    assert r["agency_no"] == 1
    assert r["report_sequence"] == 1
    assert r["report_status"] == "ACCEPTED"
    assert r["report_external_id"] == "R-2026-0001"
    assert r["report_trigger_reason"] == "USER_CONFIRMED"
    assert r["report_attempt_count"] == 1
    assert r["report_address"] == "서울특별시 중구 세종대로 110"  # cctv_address
    assert float(r["report_distance_km"]) == pytest.approx(
        report_service.nearest_agencies(1)[0]["distance_km"], abs=0.002)
    assert r["reported_at"] is not None
    assert r["report_accepted_at"] is not None

    assert result is not None
    assert result["report_no"] == r["report_no"]
    assert result["report_status"] == "ACCEPTED"
    assert result["agency_no"] == 1

    # 페이로드 계약 확인
    assert len(calls) == 1
    _, payload = calls[0]
    assert payload["event_no"] == event_no
    assert payload["address"] == "서울특별시 중구 세종대로 110"
    assert payload["place"] == "본관 정문 앞"
    assert payload["lat"] == pytest.approx(CCTV1[0])
    assert payload["lng"] == pytest.approx(CCTV1[1])
    assert payload["event_class"] == "FLAME"
    assert payload["confidence"] == pytest.approx(0.9123)
    assert payload["reported_at"] is not None


def test_payload_carries_first_detected_at(monkeypatch):
    """페이로드에 최초 검출 시각이 실린다 — 발화 시점 전달.

    유예 30초 + 승계가 겹치면 검출과 신고 사이가 1분 이상 벌어질 수 있다.
    reported_at(신고 시각)만으로는 소방이 발화 시점을 알 수 없다 (슬라이드 12 ①).
    """
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-FD"}))
    event_no = make_event()

    report_service.start_report(event_no, "USER_CONFIRMED")

    row = db.query_one(
        "SELECT event_first_detected_at FROM fire_event WHERE event_no = %s", (event_no,))
    _, payload = calls[0]
    assert payload["first_detected_at"] == \
        row["event_first_detected_at"].isoformat(timespec="seconds")


def test_start_report_retry_then_success(monkeypatch):
    """2번 실패(타임아웃/거절) 후 3번째 성공 → 같은 기관, attempt_count=3, ACCEPTED."""
    def fn(ep, pl, n):
        if n == 1:
            raise requests.exceptions.Timeout("모의 타임아웃")
        if n == 2:
            return FakeResponse(500)
        return FakeResponse(200, {"external_id": "R-RETRY-01"})

    calls = patch_post(monkeypatch, fn)
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    rows = get_report_rows(event_no)
    assert len(rows) == 1
    assert rows[0]["agency_no"] == 1
    assert rows[0]["report_status"] == "ACCEPTED"
    assert rows[0]["report_attempt_count"] == 3
    assert rows[0]["report_external_id"] == "R-RETRY-01"
    assert len(calls) == 3
    assert result["report_status"] == "ACCEPTED"


def test_start_report_accepts_2xx_without_body(monkeypatch):
    """본문 없는 2xx 도 성공으로 본다 (external_id 는 NULL)."""
    patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(204, None))
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    (r,) = get_report_rows(event_no)
    assert r["report_status"] == "ACCEPTED"
    assert r["report_external_id"] is None
    assert result["report_status"] == "ACCEPTED"


# ---------- bbox 이미지 전송 ----------
#
# 신고 페이로드에 대표 프레임 이미지(base64)와 검출 상자(bbox) 좌표를 실어 보낸다.
# 실제 119라면 외부에서 우리 서버 URL 에 접근할 수 없어 이미지 자체를 싣는다.
# 시연 대상이 모의 접수 서버라 가능한 결정 (2026-08-10, 슬라이드 12 ①).

def test_payload_carries_bbox_drawn_image(monkeypatch, tmp_path):
    """페이로드 이미지에는 검출 상자(bbox)가 그려져 있다 — DB 좌표로 그려서 보낸다.

    받는 쪽(119)이 좌표를 해석하지 않아도 발화 위치가 보이는 이미지를 받는다
    (슬라이드 12 ① "bbox 표시 화재 이미지"). 좌표 원본도 같이 실린다.
    """
    import io as _io

    from PIL import Image

    monkeypatch.setattr(config, "MEDIA_ROOT", str(tmp_path))
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-IMG"}))
    event_no = make_event()
    img_path = tmp_path / "events" / str(event_no) / "frame.jpg"
    img_path.parent.mkdir(parents=True)
    Image.new("RGB", (100, 100), (0, 0, 0)).save(img_path, "JPEG")
    make_media(event_no, is_primary=True, url=f"/media/events/{event_no}/frame.jpg")

    report_service.start_report(event_no, "USER_CONFIRMED")

    _, payload = calls[0]
    sent = Image.open(_io.BytesIO(base64.b64decode(payload["image_base64"]))).convert("RGB")
    # 검은 원본 위에 상자 선이 그려졌으면 붉은 픽셀이 존재한다
    reds = [px for px in sent.getdata() if px[0] > 150 and px[1] < 80 and px[2] < 80]
    assert reds, "페이로드 이미지에 bbox 선이 없다"
    assert payload["image_detections"] == [
        {"cls": "flame", "conf": 0.91, "box": [0.238, 0.259, 0.047, 0.113]}]


def test_payload_falls_back_to_raw_image_when_not_parseable(monkeypatch, tmp_path):
    """이미지로 못 여는 파일이면 그리기를 포기하고 원본 그대로 보낸다 — 신고가 우선."""
    monkeypatch.setattr(config, "MEDIA_ROOT", str(tmp_path))
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-RAW"}))
    event_no = make_event()
    img = tmp_path / "events" / str(event_no) / "frame.jpg"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"\xff\xd8fake-jpeg-bytes")
    make_media(event_no, is_primary=True, url=f"/media/events/{event_no}/frame.jpg")

    report_service.start_report(event_no, "USER_CONFIRMED")

    _, payload = calls[0]
    assert base64.b64decode(payload["image_base64"]) == b"\xff\xd8fake-jpeg-bytes"


def test_frame_ingested_from_the_model_carries_image(client, monkeypatch, tmp_path):
    """AI 모델이 보내는 경로 형태로 수집된 이벤트도 신고에 이미지가 실린다.

    다른 테스트들은 make_media 로 "/media/..." 를 직접 심어서, 실제 모델이
    보내는 값(MEDIA_ROOT 기준 상대경로)으로는 통과 여부가 검증된 적이 없었다.
    수집 시점에 정규화하지 않으면 _primary_frame 이 "/media/" 접두어를 못 찾고
    (None, None) 을 돌려줘서, 가장 확실하게 탐지한 프레임이 신고에서 통째로 빠진다.
    """
    from PIL import Image

    monkeypatch.setattr(config, "MEDIA_ROOT", str(tmp_path))
    calls = patch_post(monkeypatch,
                       lambda ep, pl, n: FakeResponse(200, {"external_id": "R-REL"}))

    img = tmp_path / "events" / "2026-08-13" / "1_143005_123456.jpg"
    img.parent.mkdir(parents=True)
    Image.new("RGB", (100, 100), (0, 0, 0)).save(img, "JPEG")

    flame = {"cls": "flame", "conf": 0.91, "box": [0.238, 0.259, 0.047, 0.113]}
    event_no = client.post(
        "/api/internal/detections",
        json={"cctv_no": 1, "captured_at": "2026-08-13T14:30:05",
              "media_url": "events/2026-08-13/1_143005_123456.jpg",   # 모델이 보내는 형태
              "detections": [flame]},
        headers={"X-Internal-Key": config.INTERNAL_API_KEY},
    ).get_json()["event_no"]

    report_service.start_report(event_no, "USER_CONFIRMED")

    _, payload = calls[0]
    assert payload["image_base64"] is not None, "대표 프레임이 신고에 실리지 않았다"
    assert payload["image_detections"] == [flame]


def test_report_goes_out_without_image_file(monkeypatch, tmp_path):
    """대표 프레임 파일이 디스크에 없어도 신고는 나간다 — 이미지가 신고를 막으면 안 된다."""
    monkeypatch.setattr(config, "MEDIA_ROOT", str(tmp_path))
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-NOIMG"}))
    event_no = make_event()
    make_media(event_no, is_primary=True, url=f"/media/events/{event_no}/ghost.jpg")

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    assert result["report_status"] == "ACCEPTED"
    _, payload = calls[0]
    assert payload["image_base64"] is None
    assert payload["image_detections"] is None


def test_log_request_omits_image_bytes(monkeypatch, tmp_path):
    """로그에는 이미지 원본을 남기지 않는다 — 크기 표시로 대체.

    이미지 파일은 디스크(MEDIA_ROOT)에 이미 있다. 로그 행마다 base64 를
    그대로 남기면 재전송 4회에 같은 이미지가 4번 DB 에 쌓인다.
    """
    monkeypatch.setattr(config, "MEDIA_ROOT", str(tmp_path))
    patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-LOGIMG"}))
    event_no = make_event()
    img = tmp_path / "events" / str(event_no) / "frame.jpg"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"\xff\xd8fake-jpeg-bytes")
    make_media(event_no, is_primary=True, url=f"/media/events/{event_no}/frame.jpg")

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    (log,) = db.query(
        "SELECT * FROM report_log WHERE report_no = %s", (result["report_no"],))
    logged = log["log_request"]["image_base64"]
    assert "생략" in logged                      # 원본 대신 표시 문자열
    assert len(logged) < 100                     # base64 원본이 아니다
    # 검출 좌표는 작고 승계 판단에 유용하므로 로그에 그대로 남는다
    assert log["log_request"]["image_detections"] == [
        {"cls": "flame", "conf": 0.91, "box": [0.238, 0.259, 0.047, 0.113]}]


# ---------- 신고 ID (멱등 키) ----------
#
# 재전송은 "상대가 못 받았다"가 아니라 "응답이 안 왔다"일 뿐이다. 같은 신고를
# 식별할 ID 가 없으면 119 쪽에서 같은 화재가 여러 건으로 접수된다.
# 발표 슬라이드 12: "동일 ID 로 최대 4회 재전송", "동일 신고 ID 유지로 중복 접수 방지".

def test_payload_carries_report_uid(monkeypatch):
    """페이로드에 신고 ID 가 실린다 — 이벤트에서 결정되는 값이라 재현 가능하다."""
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-1"}))
    event_no = make_event()

    report_service.start_report(event_no, "USER_CONFIRMED")

    _, payload = calls[0]
    assert payload["report_uid"] == report_service.report_uid(event_no)
    assert payload["report_uid"] == f"FG-{event_no}"


def test_report_uid_identical_across_retries(monkeypatch):
    """같은 기관에 재전송할 때 신고 ID 는 바뀌지 않는다."""
    def fn(ep, pl, n):
        if n < 3:
            raise requests.exceptions.Timeout("모의 타임아웃")
        return FakeResponse(200, {"external_id": "R-RETRY"})

    calls = patch_post(monkeypatch, fn)
    event_no = make_event()

    report_service.start_report(event_no, "USER_CONFIRMED")

    uids = {pl["report_uid"] for _, pl in calls}
    assert len(calls) == 3
    assert uids == {f"FG-{event_no}"}


def test_report_uid_survives_agency_takeover(monkeypatch):
    """기관을 승계해도 신고 ID 는 그대로다 — 다음 기관도 같은 화재임을 알 수 있다.

    report_119 행은 기관마다 새로 생기지만(순번 +1), 신고 ID 는 이벤트 단위다.
    """
    set_distinct_endpoints()

    def fn(ep, pl, n):
        if ep == "http://a1/report":
            raise requests.exceptions.ConnectionError("모의 연결 실패")
        return FakeResponse(200, {"external_id": "R-TAKEOVER"})

    calls = patch_post(monkeypatch, fn)
    event_no = make_event()

    report_service.start_report(event_no, "NO_RESPONSE_TIMEOUT")

    assert len(calls) == 2  # 연결 실패는 재시도하지 않는다 — 기관1에 1회 + 기관2에 1회
    assert {pl["report_uid"] for _, pl in calls} == {f"FG-{event_no}"}


def test_report_uid_differs_between_events():
    """다른 화재는 다른 신고 ID 를 받는다."""
    assert report_service.report_uid(11) != report_service.report_uid(12)


# ---------- 송수신 로그 ----------
#
# report_119 는 결과 요약만 남긴다. 전송 시도 하나하나가 무엇을 보내고 무엇을 받았는지는
# report_log 에 쌓인다 (발표 슬라이드 12 ⑤ "전 구간 송수신 로그 저장", 요구사항 N-04).

def get_log_rows(report_no=None):
    if report_no is None:
        return db.query("SELECT * FROM report_log ORDER BY log_no")
    return db.query(
        "SELECT * FROM report_log WHERE report_no = %s ORDER BY log_no", (report_no,)
    )


def test_success_is_logged_with_request_and_response(monkeypatch):
    """성공 1회 = 로그 1행. 보낸 본문과 받은 본문이 그대로 남는다."""
    patch_post(monkeypatch,
               lambda ep, pl, n: FakeResponse(200, {"external_id": "R-LOG-1"}))
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    (log,) = get_log_rows(result["report_no"])
    assert log["log_attempt"] == 1
    assert log["log_result"] == "ACCEPTED"
    assert log["log_http_status"] == 200
    assert log["log_request"]["report_uid"] == f"FG-{event_no}"
    assert log["log_request"]["address"] == "서울특별시 중구 세종대로 110"
    assert log["log_response"] == {"external_id": "R-LOG-1"}
    assert log["log_error"] is None
    assert log["log_sent_at"] is not None
    assert log["log_elapsed_ms"] >= 0


def test_every_attempt_is_logged_with_its_own_result(monkeypatch):
    """실패한 시도도 남는다 — 무응답과 거절은 뜻이 달라서 결과값으로 구분한다."""
    def fn(ep, pl, n):
        if n == 1:
            raise requests.exceptions.Timeout("모의 타임아웃")
        if n == 2:
            return FakeResponse(500, {"error": "system unavailable"})
        return FakeResponse(200, {"external_id": "R-LOG-3"})

    patch_post(monkeypatch, fn)
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    logs = get_log_rows(result["report_no"])
    assert [l["log_attempt"] for l in logs] == [1, 2, 3]
    assert [l["log_result"] for l in logs] == ["TIMEOUT", "REJECTED", "ACCEPTED"]
    assert [l["log_http_status"] for l in logs] == [None, 500, 200]
    # 타임아웃은 사유가 남고, 응답을 받은 시도는 사유가 없다
    assert "모의 타임아웃" in logs[0]["log_error"]
    assert logs[1]["log_error"] is None
    assert logs[1]["log_response"] == {"error": "system unavailable"}


def test_connection_failure_logged_as_error(monkeypatch):
    """연결 자체가 안 된 것(ERROR)과 응답이 없는 것(TIMEOUT)은 다르다.

    TIMEOUT 은 상대가 접수했을 수도 있다는 뜻이라 사후 판단이 달라진다.
    연결 실패는 재시도 값어치가 없어 기관당 한 줄만 남는다.
    """
    patch_post(monkeypatch, lambda ep, pl, n: (_ for _ in ()).throw(
        requests.exceptions.ConnectionError("모의 연결 실패")))
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    logs = get_log_rows(result["report_no"])
    assert len(logs) == 1
    assert {l["log_result"] for l in logs} == {"ERROR"}
    assert all(l["log_http_status"] is None for l in logs)


def test_logs_cover_every_agency_in_takeover(monkeypatch):
    """승계하면 기관마다 자기 신고 행에 로그가 붙는다 — 전 구간이 남는다."""
    set_distinct_endpoints()

    def fn(ep, pl, n):
        if ep == "http://a1/report":
            raise requests.exceptions.Timeout("모의 타임아웃")
        return FakeResponse(200, {"external_id": "R-LOG-TK"})

    patch_post(monkeypatch, fn)
    event_no = make_event()

    report_service.start_report(event_no, "NO_RESPONSE_TIMEOUT")

    first, second = get_report_rows(event_no)
    first_logs = get_log_rows(first["report_no"])
    second_logs = get_log_rows(second["report_no"])

    assert len(first_logs) == 4
    assert {l["log_result"] for l in first_logs} == {"TIMEOUT"}
    assert {l["log_endpoint"] for l in first_logs} == {"http://a1/report"}
    assert len(second_logs) == 1
    assert second_logs[0]["log_result"] == "ACCEPTED"
    assert second_logs[0]["log_endpoint"] == "http://a2/report"


def test_logging_failure_does_not_break_the_report(monkeypatch):
    """로그 기록이 실패해도 신고는 나간다 — 증거 남기려다 신고를 막으면 본말전도다."""
    patch_post(monkeypatch,
               lambda ep, pl, n: FakeResponse(200, {"external_id": "R-NOLOG"}))
    monkeypatch.setattr("services.report_service._log_attempt",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("로그 실패")))
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    assert result["report_status"] == "ACCEPTED"
    assert result["report_external_id"] == "R-NOLOG"


# ---------- 승계 (기관 교체) ----------

def test_takeover_to_second_agency(monkeypatch):
    """기관 1이 4회 모두 실패 → 그 행은 NO_RESPONSE(승계), 기관 2가 sequence 2 로 ACCEPTED.

    재시도를 다 쓰는 경로라 응답 타임아웃을 쓴다 (연결 실패는 1회에 승계한다).
    """
    set_distinct_endpoints()

    def fn(ep, pl, n):
        if ep == "http://a1/report":
            raise requests.exceptions.ReadTimeout("모의 응답 타임아웃")
        return FakeResponse(200, {"external_id": "R-TAKEOVER-02"})

    calls = patch_post(monkeypatch, fn)
    event_no = make_event()

    result = report_service.start_report(event_no, "NO_RESPONSE_TIMEOUT")

    rows = get_report_rows(event_no)
    assert len(rows) == 2
    first, second = rows
    assert first["agency_no"] == 1
    assert first["report_sequence"] == 1
    assert first["report_status"] == "NO_RESPONSE"
    assert first["report_attempt_count"] == 4
    assert first["report_accepted_at"] is None
    assert second["agency_no"] == 2
    assert second["report_sequence"] == 2
    assert second["report_status"] == "ACCEPTED"
    assert second["report_external_id"] == "R-TAKEOVER-02"
    assert float(second["report_distance_km"]) == pytest.approx(
        report_service.nearest_agencies(1)[1]["distance_km"], abs=0.002)

    # 기관 1에 4번, 기관 2에 1번
    assert [ep for ep, _ in calls] == ["http://a1/report"] * 4 + ["http://a2/report"]
    assert result["report_status"] == "ACCEPTED"
    assert result["agency_no"] == 2


# ---------- 운영 기본값: 가장 가까운 한 곳만 (승계 없음) ----------

def test_default_reports_only_to_nearest_agency(monkeypatch):
    """REPORT_MAX_AGENCIES=1(운영 기본값): 가장 가까운 기관 한 곳으로 끝난다."""
    monkeypatch.setattr(config, "REPORT_MAX_AGENCIES", 1)
    set_distinct_endpoints()
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-NEAREST"}))
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    rows = get_report_rows(event_no)
    assert len(rows) == 1
    assert rows[0]["agency_no"] == 1
    assert rows[0]["report_status"] == "ACCEPTED"
    assert result["report_external_id"] == "R-NEAREST"
    # 2순위 기관에는 아예 가지 않는다
    assert [ep for ep, _ in calls] == ["http://a1/report"]


def test_default_does_not_take_over_when_nearest_fails(monkeypatch):
    """REPORT_MAX_AGENCIES=1: 1순위가 소진돼도 2순위로 넘어가지 않는다.

    행은 하나뿐이고 상태는 NO_RESPONSE(승계 예정)가 아니라 FAILED 다 —
    넘어갈 다음 기관이 없으므로 '전송 실패'로 닫는 것이 맞다.
    """
    monkeypatch.setattr(config, "REPORT_MAX_AGENCIES", 1)
    set_distinct_endpoints()
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(503))
    event_no = make_event()

    result = report_service.start_report(event_no, "NO_RESPONSE_TIMEOUT")

    rows = get_report_rows(event_no)
    assert len(rows) == 1
    assert rows[0]["agency_no"] == 1
    assert rows[0]["report_status"] == "FAILED"
    assert rows[0]["report_attempt_count"] == config.MAX_REPORT_ATTEMPTS
    assert result["report_status"] == "FAILED"
    assert {ep for ep, _ in calls} == {"http://a1/report"}


def test_all_agencies_fail(monkeypatch):
    """모든 기관 소진 → 앞 기관은 NO_RESPONSE, 마지막 기관 행만 FAILED(전송실패)."""
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(503))
    event_no = make_event()

    result = report_service.start_report(event_no, "NO_RESPONSE_TIMEOUT")

    rows = get_report_rows(event_no)
    assert len(rows) == 2
    assert rows[0]["report_status"] == "NO_RESPONSE"
    assert rows[0]["report_attempt_count"] == 4
    assert rows[1]["report_status"] == "FAILED"
    assert rows[1]["report_attempt_count"] == 4
    assert rows[1]["report_sequence"] == 2
    assert len(calls) == 8  # 2개 기관 × 4회

    assert result is not None
    assert result["report_status"] == "FAILED"
    assert result["report_no"] == rows[1]["report_no"]


def test_max_attempts_configurable(monkeypatch):
    """MAX_REPORT_ATTEMPTS 를 줄이면 안쪽 루프 횟수도 줄어든다."""
    monkeypatch.setattr(config, "MAX_REPORT_ATTEMPTS", 2)
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(503))
    event_no = make_event()

    report_service.start_report(event_no, "USER_CONFIRMED")

    rows = get_report_rows(event_no)
    assert [r["report_attempt_count"] for r in rows] == [2, 2]
    assert len(calls) == 4  # 2개 기관 × 2회


# ---------- 운영 기본값: 한 기관에 한 번만 (재전송 없음) ----------

def test_default_sends_once_without_retrying(monkeypatch):
    """MAX_REPORT_ATTEMPTS=1(운영 기본값): 실패해도 같은 기관에 다시 보내지 않는다.

    2026-08-24 시연 단순화 — 119 와는 요청 한 번·응답 한 번으로 끝낸다.
    5xx 는 원래 '재시도할 값어치가 있는' 실패라 루프가 도는 경로인데, 그 경로에서도
    한 번으로 끝나는지를 봐야 기본값이 실제로 먹은 것이다.
    """
    monkeypatch.setattr(config, "MAX_REPORT_ATTEMPTS", 1)
    monkeypatch.setattr(config, "REPORT_MAX_AGENCIES", 1)
    set_distinct_endpoints()
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(503))
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    rows = get_report_rows(event_no)
    assert len(rows) == 1
    assert rows[0]["report_attempt_count"] == 1
    assert rows[0]["report_status"] == "FAILED"
    assert result["report_status"] == "FAILED"
    assert [ep for ep, _ in calls] == ["http://a1/report"]


def test_production_default_is_single_attempt():
    """config.py 에 적힌 기본값 자체가 1 이다 (conftest 가 테스트용으로 4 로 올린다).

    동작 테스트만 두면 기본값이 조용히 4 로 돌아가도 아무도 못 잡는다. 환경변수가
    아니라 파일에 적힌 리터럴을 본다 — config 를 reload 하면 다른 테스트가 쓰는
    모듈 상태까지 되돌아가므로 소스를 읽는 쪽이 안전하다.
    """
    import pathlib
    import re

    source = (pathlib.Path(config.__file__)).read_text(encoding="utf-8")
    match = re.search(
        r'^MAX_REPORT_ATTEMPTS = int\(os\.getenv\("MAX_REPORT_ATTEMPTS", "(\d+)"\)\)',
        source, re.M)
    assert match, "config.py 에서 MAX_REPORT_ATTEMPTS 기본값을 찾지 못했다"
    assert match.group(1) == "1"


# ---------- 실패 종류별 분기 (재시도할 값어치가 있는가) ----------

def test_connection_failure_takes_over_without_retrying(monkeypatch):
    """연결이 안 되면 같은 기관을 다시 두드리지 않고 곧장 다음 기관으로 간다.

    연결이 성립하지 않았다는 건 신고가 전달되지 않았다는 뜻이라, 원인(다운·방화벽)이
    그대로 남아 있는 같은 기관을 재시도해도 결과가 같다. 전달되지 않았으니 승계해도
    중복 접수 위험이 없다 — 타임아웃과 달리 승계가 공짜다.
    """
    set_distinct_endpoints()

    def fn(ep, pl, n):
        if ep == "http://a1/report":
            raise requests.exceptions.ConnectionError("모의 연결 실패")
        return FakeResponse(200, {"external_id": "R-FASTOVER"})

    calls = patch_post(monkeypatch, fn)
    event_no = make_event()

    result = report_service.start_report(event_no, "NO_RESPONSE_TIMEOUT")

    first, second = get_report_rows(event_no)
    assert first["report_attempt_count"] == 1
    assert first["report_status"] == "NO_RESPONSE"
    assert second["report_status"] == "ACCEPTED"
    assert [ep for ep, _ in calls] == ["http://a1/report", "http://a2/report"]
    assert result["agency_no"] == 2


def test_connect_timeout_counts_as_connection_failure(monkeypatch):
    """연결 타임아웃은 Timeout 이기도 하지만 '전달 안 됨'이다 — ERROR 로 남고 재시도 없다.

    requests 의 ConnectTimeout 은 ConnectionError 와 Timeout 을 모두 상속한다.
    Timeout 으로 먼저 잡히면 '상대가 접수했을 수도 있다'로 잘못 기록된다.
    """
    patch_post(monkeypatch, lambda ep, pl, n: (_ for _ in ()).throw(
        requests.exceptions.ConnectTimeout("모의 연결 타임아웃")))
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    logs = get_log_rows(result["report_no"])
    assert len(logs) == 1
    assert logs[0]["log_result"] == "ERROR"


def test_read_timeout_still_retries_same_agency(monkeypatch):
    """응답 타임아웃은 상대가 접수했을 수 있으므로 같은 기관에 재확인을 다 쓴다."""
    set_distinct_endpoints()

    def fn(ep, pl, n):
        if ep == "http://a1/report":
            raise requests.exceptions.ReadTimeout("모의 응답 타임아웃")
        return FakeResponse(200, {"external_id": "R-READTO"})

    calls = patch_post(monkeypatch, fn)
    event_no = make_event()

    report_service.start_report(event_no, "NO_RESPONSE_TIMEOUT")

    first, _ = get_report_rows(event_no)
    assert first["report_attempt_count"] == config.MAX_REPORT_ATTEMPTS
    assert [ep for ep, _ in calls] == \
        ["http://a1/report"] * config.MAX_REPORT_ATTEMPTS + ["http://a2/report"]


def test_client_rejection_takes_over_without_retrying(monkeypatch):
    """4xx 는 우리 요청이 규격에 안 맞는다는 뜻 — 같은 걸 다시 보내도 같은 답이 온다.

    다만 다른 기관도 거절하리라는 보장은 없으므로 승계는 계속한다.
    화재에서는 중복 접수보다 미출동이 훨씬 위험하다.
    """
    set_distinct_endpoints()

    def fn(ep, pl, n):
        if ep == "http://a1/report":
            return FakeResponse(400, {"error": "invalid report"})
        return FakeResponse(200, {"external_id": "R-AFTER400"})

    calls = patch_post(monkeypatch, fn)
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    first, second = get_report_rows(event_no)
    assert first["report_attempt_count"] == 1
    assert [ep for ep, _ in calls] == ["http://a1/report", "http://a2/report"]
    assert second["report_status"] == "ACCEPTED"
    assert result["agency_no"] == 2

    logs = get_log_rows(first["report_no"])
    assert len(logs) == 1
    assert logs[0]["log_result"] == "REJECTED"
    assert logs[0]["log_http_status"] == 400


def test_server_error_still_retries_same_agency(monkeypatch):
    """5xx 는 일시 장애일 수 있으므로 재시도 값어치가 있다 — 4xx 와 다르게 다룬다."""
    set_distinct_endpoints()

    def fn(ep, pl, n):
        if ep == "http://a1/report":
            return FakeResponse(503)
        return FakeResponse(200, {"external_id": "R-AFTER503"})

    calls = patch_post(monkeypatch, fn)
    event_no = make_event()

    report_service.start_report(event_no, "USER_CONFIRMED")

    first, _ = get_report_rows(event_no)
    assert first["report_attempt_count"] == config.MAX_REPORT_ATTEMPTS
    assert len(calls) == config.MAX_REPORT_ATTEMPTS + 1


# ---------- 기관 필터링 ----------

def test_inactive_agency_excluded(monkeypatch):
    """비활성 기관은 후보에서 빠진다 — 기관 1 비활성 → 곧장 기관 2, sequence 1."""
    db.execute("UPDATE agency SET agency_is_active = false WHERE agency_no = 1")
    patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-A2"}))
    event_no = make_event()

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    rows = get_report_rows(event_no)
    assert len(rows) == 1
    assert rows[0]["agency_no"] == 2
    assert rows[0]["report_sequence"] == 1
    assert rows[0]["report_status"] == "ACCEPTED"
    assert result["agency_no"] == 2


def test_no_active_agencies_returns_none(monkeypatch):
    """활성 기관이 하나도 없으면 None, 행도 HTTP 호출도 없다."""
    db.execute("UPDATE agency SET agency_is_active = false")
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200))
    event_no = make_event()

    assert report_service.start_report(event_no, "USER_CONFIRMED") is None
    assert get_report_rows() == []
    assert calls == []


# ---------- 멱등성 · 동시성 가드 ----------

def test_start_report_idempotent_existing_active(monkeypatch):
    """이미 진행 중(ACCEPTED) 신고가 있으면 그 정보를 돌려주고 아무 것도 안 한다."""
    event_no = make_event()
    existing_no = make_report(event_no, agency_no=1, status="ACCEPTED")
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200))

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    assert result is not None
    assert result["report_no"] == existing_no
    assert result["report_status"] == "ACCEPTED"
    assert len(get_report_rows(event_no)) == 1  # 새 행 없음
    assert calls == []                          # HTTP 호출 없음


def test_start_report_test_event_skipped(monkeypatch):
    """점검 모드(event_is_test) 이벤트는 신고하지 않는다."""
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200))
    event_no = make_event(is_test=True)

    assert report_service.start_report(event_no, "USER_CONFIRMED") is None
    assert get_report_rows() == []
    assert calls == []


def test_unique_violation_guard_returns_existing(monkeypatch):
    """행 INSERT 시점에 다른 활성 신고가 끼어들면(23505) 죽지 않고 기존 신고를 돌려준다.

    사전 체크(_find_active_report)를 무력화해서 INSERT 까지 진행시키고,
    부분 유니크 인덱스(UX_report_119_active) 위반을 실제 DB 에서 일으킨다.
    """
    event_no = make_event()
    existing_no = make_report(event_no, agency_no=1, status="SENDING")
    monkeypatch.setattr("services.report_service._find_active_report", lambda e: None)
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200))

    result = report_service.start_report(event_no, "USER_CONFIRMED")

    assert result is not None
    assert result["report_no"] == existing_no
    assert len(get_report_rows(event_no)) == 1
    assert calls == []  # INSERT 가 막혔으므로 전송 자체가 없다


# ---------- 알림 응답(READ) 연동 — D4: 사용자가 화재 확인 시 즉시 신고 ----------

def test_read_on_sent_alert_triggers_report(client, admin_headers, monkeypatch):
    """SENT 알림에 READ 응답 → USER_CONFIRMED 사유로 신고가 만들어진다."""
    patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-READ-01"}))
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1, status="SENT")

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    json={"action": "READ"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.get_json()["alert_status"] == "READ"

    rows = get_report_rows(event_no)
    assert len(rows) == 1
    assert rows[0]["report_trigger_reason"] == "USER_CONFIRMED"
    assert rows[0]["report_status"] == "ACCEPTED"


def test_read_on_one_of_paired_alerts_reports_once(client, admin_headers, monkeypatch):
    """PUSH/SMS 두 알림 중 하나만 READ 해도 신고는 1건 (형제 종료 + 멱등 가드)."""
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-PAIR"}))
    event_no = make_event()
    push_no, _ = make_alert_pair(event_no)

    r = client.post(f"/api/alerts/{push_no}/respond",
                    json={"action": "READ"}, headers=admin_headers)
    assert r.status_code == 200

    rows = get_report_rows(event_no)
    assert len(rows) == 1
    assert rows[0]["report_trigger_reason"] == "USER_CONFIRMED"
    assert len(calls) == 1


def test_read_on_no_response_alert_does_not_report(client, admin_headers, monkeypatch):
    """NO_RESPONSE 알림에 대한 늦은 READ 는 신고를 만들지 않는다 (에스컬레이션이 이미 처리)."""
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200))
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1, status="NO_RESPONSE")

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    json={"action": "READ"}, headers=admin_headers)
    assert r.status_code == 200

    assert get_report_rows() == []
    assert calls == []


def test_cancel_does_not_report(client, admin_headers, monkeypatch):
    """CANCEL(오탐 취소)은 신고를 만들지 않는다."""
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200))
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1, status="SENT")

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    json={"action": "CANCEL"}, headers=admin_headers)
    assert r.status_code == 200

    assert get_report_rows() == []
    assert calls == []


def test_report_failure_does_not_break_respond_api(client, admin_headers, monkeypatch):
    """신고 로직이 죽어도 알림 응답 API 는 200 이어야 한다 (try/except 로 삼킨다)."""
    def boom(event_no, trigger_reason):
        raise RuntimeError("신고 실패 시뮬레이션")

    monkeypatch.setattr("services.report_service.start_report", boom)
    event_no = make_event()
    alert_no = make_alert(event_no, user_no=1, status="SENT")

    r = client.post(f"/api/alerts/{alert_no}/respond",
                    json={"action": "READ"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.get_json()["alert_status"] == "READ"  # 알림 갱신 자체는 성공


# ---------- 페이로드 v2 (주소 · CCTV 정보 · 콜백) ----------

def test_payload_uses_cctv_address_as_address(monkeypatch):
    """address 는 역지오코딩한 주소다. 설치 위치 설명은 place 로 따로 간다.

    소방서가 출동해야 하는 값과 사람이 붙인 위치 설명은 다른 것이다.
    """
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-A"}))
    event_no = make_event()

    report_service.start_report(event_no, "USER_CONFIRMED")

    _, payload = calls[0]
    assert payload["address"] == "서울특별시 중구 세종대로 110"
    assert payload["place"] == "본관 정문 앞"


def test_payload_falls_back_to_coordinates_without_cctv_address(monkeypatch):
    """주소가 없으면 좌표 문자열로 떨어진다 — 가짜 주소보다 안전하고 빈 칸보다 쓸모 있다.

    시드 2번 카메라(후문)는 cctv_address 가 NULL 이다.
    """
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-B"}))
    event_no = make_event(cctv_no=2)

    report_service.start_report(event_no, "USER_CONFIRMED")

    _, payload = calls[0]
    assert payload["address"] == "위도 37.567, 경도 126.979 (본관 후문)"
    assert payload["place"] == "본관 후문"


def test_payload_carries_cctv_block(monkeypatch):
    """CCTV 각종 정보를 함께 보낸다 — 접수자가 카메라를 특정하고 화면을 띄울 수 있게."""
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-C"}))
    event_no = make_event()

    report_service.start_report(event_no, "USER_CONFIRMED")

    _, payload = calls[0]
    assert payload["cctv"] == {
        "cctv_no": 1,
        "name": "정문 카메라",
        "location": "본관 정문 앞",
        "address": "서울특별시 중구 세종대로 110",
        "lat": pytest.approx(CCTV1[0]),
        "lng": pytest.approx(CCTV1[1]),
        "stream_url": "http://192.168.0.10:8080/live/cam1.m3u8",
        "width": 1920,
        "height": 1080,
        "status": "ACTIVE",
    }


def test_payload_carries_callback_url(monkeypatch):
    """소방서가 출동을 되쏠 주소를 페이로드에 실어 준다.

    받는 쪽이 우리 주소를 미리 설정해 두지 않아도 되게 한다.
    """
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-D"}))
    event_no = make_event()

    report_service.start_report(event_no, "USER_CONFIRMED")

    _, payload = calls[0]
    assert payload["callback_url"] == f"{config.PUBLIC_BASE_URL}/api/reports/dispatch"


def test_payload_carries_detection_and_agency(monkeypatch):
    """검출 근거(프레임 수)와 수신 기관을 함께 보낸다."""
    calls = patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-E"}))
    event_no = make_event()

    report_service.start_report(event_no, "USER_CONFIRMED")

    _, payload = calls[0]
    assert payload["detection"] == {"frames": 32, "threshold_frames": 30}
    assert payload["agency"]["name"] == "종로소방서"
    assert payload["agency"]["distance_km"] == pytest.approx(
        report_service.nearest_agencies(1)[0]["distance_km"], abs=0.002)


def test_report_path_never_calls_geocoding(monkeypatch):
    """신고 경로에서 역지오코딩을 부르지 않는다.

    119 신고는 동기다 — 여기서 외부 API 를 부르면 그 지연이 그대로 신고 지연이
    되고, 카카오가 죽으면 신고가 늦어진다. 주소는 등록 시점에 이미 채워져 있다.
    """
    called = []
    monkeypatch.setattr("services.geocode.reverse_geocode",
                        lambda lat, lng: called.append((lat, lng)))
    patch_post(monkeypatch, lambda ep, pl, n: FakeResponse(200, {"external_id": "R-F"}))
    event_no = make_event()

    report_service.start_report(event_no, "USER_CONFIRMED")

    assert called == []
