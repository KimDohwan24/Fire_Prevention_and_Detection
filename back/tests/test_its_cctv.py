"""ITS 실시간 스트림 주소 갱신 테스트 — services/its_cctv.py + 조회 API 연동.

국가교통정보센터(ITS)가 주는 cctvurl 에는 시간 제한 인증 토큰(wmsAuthSign)이
박혀 있어서 DB 에 저장된 주소는 시간이 지나면 재생되지 않는다. 그래서 카메라를
조회할 때마다 최신 주소를 받아 cctv_name 이 같은 행의 주소를 갈아끼운다.

이 파일의 어떤 테스트도 실제 HTTP 를 보내지 않는다 —
conftest 의 `_no_real_its_http` 가 전역으로 `its_cctv._get` 을 막고,
개별 테스트는 자기 monkeypatch 로 그 스텁을 덮어쓴다.
"""
import pytest

import config
import db
from services import its_cctv

# 시드 카메라: cctv_no 1 = '정문 카메라'(ACTIVE), cctv_no 2 = '후문 카메라'(INACTIVE)
SEED_URL_1 = "http://192.168.0.10:8080/live/cam1.m3u8"
SEED_URL_2 = "http://192.168.0.11:8080/live/cam2.m3u8"

# ITS 가 새로 발급해 준 주소 (토큰이 갱신된 형태)
FRESH_URL = "http://cctvsec.ktict.co.kr/9999/FRESH?wmsAuthSign=NEW-TOKEN-2026"


def its_item(name, url=FRESH_URL, lat=37.5665, lng=126.9780):
    """ITS 응답 항목 1개 — 실제 응답과 같은 키 구성."""
    return {
        "roadsectionid": "",
        "coordx": lng,
        "coordy": lat,
        "cctvresolution": "",
        "filecreatetime": "",
        "cctvtype": 1,
        "cctvformat": "HLS",
        "cctvname": name,
        "cctvurl": url,
    }


def its_payload(*items):
    """ITS 정상 응답 봉투: {"response": {"coordtype":1, "data":[...]}}"""
    return {"response": {"coordtype": 1, "data": list(items)}}


def stub_get(monkeypatch, payload, seen=None):
    """`its_cctv._get` 을 고정 응답으로 바꾼다. seen 을 주면 요청 파라미터를 모은다."""
    def _fake(params):
        if seen is not None:
            seen.append(params)
        if isinstance(payload, Exception):
            raise payload
        return payload
    monkeypatch.setattr(its_cctv, "_get", _fake)


def seed_rows():
    """DB 의 시드 카메라 2행을 조회 API 와 같은 형태로 읽어온다."""
    return db.query(
        """SELECT cctv_no, cctv_name, cctv_lat, cctv_lng, cctv_stream_url
           FROM cctv ORDER BY cctv_no"""
    )


def stored_url(cctv_no):
    return db.query_one(
        "SELECT cctv_stream_url FROM cctv WHERE cctv_no = %s", (cctv_no,)
    )["cctv_stream_url"]


@pytest.fixture(autouse=True)
def its_enabled(monkeypatch):
    """이 파일은 갱신 기능이 켜져 있고 키가 있는 상태를 기본으로 한다.

    (팀원 로컬 .env 에 실제 키가 있든 없든 테스트 결과가 흔들리지 않게 고정)
    """
    monkeypatch.setattr(config, "ITS_REFRESH_ENABLED", True)
    monkeypatch.setattr(config, "CCTV_API_KEY", "TEST-ITS-KEY")
    yield


def _key_headers():
    return {"X-Internal-Key": config.INTERNAL_API_KEY}


# ---------- ITS catalogue API ----------

def test_its_catalogue_returns_frontend_contract(client, monkeypatch):
    """The registration modal receives selectable ITS CCTV items."""
    monkeypatch.setattr(
        its_cctv,
        "fetch_its_cctvs",
        lambda: [its_item("[경부선] 양재IC", lat=37.472145, lng=127.042125)],
    )

    response = client.get("/api/its/cctvs")

    assert response.status_code == 200
    assert response.get_json() == {
        "items": [{
            "cctv_name": "[경부선] 양재IC",
            "cctv_location": "[경부선] 양재IC",
            "cctv_lat": 37.472145,
            "cctv_lng": 127.042125,
            "cctv_type": "HLS",
            "cctv_stream_url": FRESH_URL,
        }],
        "total": 1,
    }


def test_its_catalogue_skips_unusable_items(client, monkeypatch):
    monkeypatch.setattr(
        its_cctv,
        "fetch_its_cctvs",
        lambda: [
            its_item("usable"),
            {"cctvname": "missing coordinates", "cctvurl": FRESH_URL},
            its_item("missing stream", url=""),
        ],
    )

    response = client.get("/api/its/cctvs")

    assert response.status_code == 200
    assert [item["cctv_name"] for item in response.get_json()["items"]] == ["usable"]


def test_its_catalogue_returns_requested_page(client, monkeypatch):
    monkeypatch.setattr(
        its_cctv,
        "fetch_its_cctvs",
        lambda: [its_item(f"camera-{index}") for index in range(3)],
    )

    response = client.get("/api/its/cctvs?limit=1&offset=1")

    assert response.status_code == 200
    assert [item["cctv_name"] for item in response.get_json()["items"]] == ["camera-1"]
    assert response.get_json()["total"] == 3


def test_its_catalogue_returns_503_when_its_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(
        its_cctv,
        "fetch_its_cctvs",
        lambda: (_ for _ in ()).throw(ConnectionError("ITS unavailable")),
    )

    response = client.get("/api/its/cctvs")

    assert response.status_code == 503
    assert response.get_json()["code"] == "ITS_UNAVAILABLE"


# ---------- 이름 매칭 ----------

def test_matching_name_gets_fresh_url(monkeypatch):
    """cctvname 이 우리 cctv_name 과 정확히 같으면 주소가 갈아끼워진다."""
    stub_get(monkeypatch, its_payload(its_item("정문 카메라")))

    rows = its_cctv.refresh_stream_urls(seed_rows())

    assert rows[0]["cctv_name"] == "정문 카메라"
    assert rows[0]["cctv_stream_url"] == FRESH_URL


def test_unmatched_row_keeps_stored_url(monkeypatch):
    """ITS 에 없는 이름(수동 등록 카메라)은 저장된 주소를 그대로 유지한다."""
    stub_get(monkeypatch, its_payload(its_item("정문 카메라")))

    rows = its_cctv.refresh_stream_urls(seed_rows())

    assert rows[1]["cctv_name"] == "후문 카메라"
    assert rows[1]["cctv_stream_url"] == SEED_URL_2


# ---------- DB 반영 ----------

def test_db_row_updated_when_url_changed(monkeypatch):
    """주소가 바뀌면 DB 행도 갱신된다 (AI 모델 등 다른 소비자를 위해)."""
    stub_get(monkeypatch, its_payload(its_item("정문 카메라")))

    its_cctv.refresh_stream_urls(seed_rows())

    assert stored_url(1) == FRESH_URL
    assert stored_url(2) == SEED_URL_2  # 매칭 안 된 행은 그대로


def test_no_update_when_url_unchanged(monkeypatch):
    """ITS 주소가 저장된 값과 같으면 UPDATE 를 아예 보내지 않는다."""
    stub_get(monkeypatch, its_payload(its_item("정문 카메라", url=SEED_URL_1)))

    calls = []
    real_execute = db.execute
    monkeypatch.setattr(
        db, "execute", lambda sql, params=(): calls.append(sql) or real_execute(sql, params)
    )

    rows = its_cctv.refresh_stream_urls(seed_rows())

    assert calls == []
    assert rows[0]["cctv_stream_url"] == SEED_URL_1


# ---------- 바운딩 박스 ----------

def test_bbox_covers_all_rows_with_padding(monkeypatch):
    """모든 카메라를 덮는 박스 하나로 도로 유형별 1회씩만 호출한다."""
    seen = []
    stub_get(monkeypatch, its_payload(), seen=seen)
    monkeypatch.setattr(config, "ITS_ROAD_TYPES", ["ex", "its"])

    rows = [
        {"cctv_no": 1, "cctv_name": "A", "cctv_lat": 37.50, "cctv_lng": 126.90,
         "cctv_stream_url": "u1"},
        {"cctv_no": 2, "cctv_name": "B", "cctv_lat": 37.70, "cctv_lng": 127.10,
         "cctv_stream_url": "u2"},
    ]
    its_cctv.refresh_stream_urls(rows)

    assert len(seen) == 2                                   # 도로 유형 2종 × 1회
    assert {p["type"] for p in seen} == {"ex", "its"}
    p = seen[0]
    assert p["apiKey"] == "TEST-ITS-KEY"
    assert str(p["cctvType"]) == "1"                        # 실시간 HLS
    assert p["getType"] == "json"
    assert float(p["minY"]) == pytest.approx(37.45)         # 37.50 - 0.05
    assert float(p["maxY"]) == pytest.approx(37.75)         # 37.70 + 0.05
    assert float(p["minX"]) == pytest.approx(126.85)
    assert float(p["maxX"]) == pytest.approx(127.15)


def test_null_coords_row_does_not_crash(monkeypatch):
    """좌표가 NULL 인 행이 섞여 있어도 박스 계산이 깨지지 않는다."""
    stub_get(monkeypatch, its_payload(its_item("좌표없음")))

    rows = [
        {"cctv_no": 1, "cctv_name": "좌표없음", "cctv_lat": None, "cctv_lng": None,
         "cctv_stream_url": "u1"},
        {"cctv_no": 2, "cctv_name": "B", "cctv_lat": 37.70, "cctv_lng": 127.10,
         "cctv_stream_url": "u2"},
    ]
    out = its_cctv.refresh_stream_urls(rows)

    assert out[0]["cctv_stream_url"] == FRESH_URL
    assert out[1]["cctv_stream_url"] == "u2"


def test_all_null_coords_makes_no_http(monkeypatch):
    """좌표가 하나도 없으면 박스를 만들 수 없으니 호출하지 않고 그대로 반환한다."""
    seen = []
    stub_get(monkeypatch, its_payload(its_item("좌표없음")), seen=seen)

    rows = [{"cctv_no": 1, "cctv_name": "좌표없음", "cctv_lat": None,
             "cctv_lng": None, "cctv_stream_url": "u1"}]
    out = its_cctv.refresh_stream_urls(rows)

    assert seen == []
    assert out[0]["cctv_stream_url"] == "u1"


# ---------- TTL 캐시 ----------

def test_ttl_cache_reuses_result(monkeypatch):
    """TTL 안에서는 같은 박스에 대해 실제 호출이 한 번만 나간다."""
    seen = []
    stub_get(monkeypatch, its_payload(its_item("정문 카메라")), seen=seen)
    monkeypatch.setattr(config, "ITS_ROAD_TYPES", ["ex"])
    monkeypatch.setattr(config, "CCTV_URL_TTL_SEC", 300)

    its_cctv.refresh_stream_urls(seed_rows())
    its_cctv.refresh_stream_urls(seed_rows())

    assert len(seen) == 1


def test_clear_cache_forces_refetch(monkeypatch):
    """clear_cache() 후에는 다시 호출한다."""
    seen = []
    stub_get(monkeypatch, its_payload(its_item("정문 카메라")), seen=seen)
    monkeypatch.setattr(config, "ITS_ROAD_TYPES", ["ex"])

    its_cctv.refresh_stream_urls(seed_rows())
    its_cctv.clear_cache()
    its_cctv.refresh_stream_urls(seed_rows())

    assert len(seen) == 2


# ---------- 실패 내성 (절대 예외를 밖으로 내지 않는다) ----------

def test_network_error_returns_rows_unchanged(monkeypatch):
    """네트워크 예외가 나도 저장된 주소 그대로 돌려준다."""
    stub_get(monkeypatch, ConnectionError("네트워크 끊김"))

    rows = its_cctv.refresh_stream_urls(seed_rows())

    assert rows[0]["cctv_stream_url"] == SEED_URL_1
    assert stored_url(1) == SEED_URL_1


def test_auth_error_body_returns_rows_unchanged(monkeypatch):
    """인증키 오류 응답 본문(resultCode 4005)도 조용히 무시한다."""
    stub_get(monkeypatch, {"header": {"resultCode": 4005,
                                      "resultMsg": "존재하지 않는 인증키입니다."},
                           "body": ""})

    rows = its_cctv.refresh_stream_urls(seed_rows())

    assert rows[0]["cctv_stream_url"] == SEED_URL_1


def test_malformed_payload_returns_rows_unchanged(monkeypatch):
    """예상과 다른 모양의 본문이 와도 그대로 돌려준다."""
    stub_get(monkeypatch, {"response": "이건 객체가 아님"})

    rows = its_cctv.refresh_stream_urls(seed_rows())

    assert rows[0]["cctv_stream_url"] == SEED_URL_1


def test_disabled_makes_no_http(monkeypatch):
    """ITS_REFRESH_ENABLED=False 면 호출 자체를 하지 않는다."""
    seen = []
    stub_get(monkeypatch, its_payload(its_item("정문 카메라")), seen=seen)
    monkeypatch.setattr(config, "ITS_REFRESH_ENABLED", False)

    rows = its_cctv.refresh_stream_urls(seed_rows())

    assert seen == []
    assert rows[0]["cctv_stream_url"] == SEED_URL_1


def test_empty_api_key_makes_no_http(monkeypatch):
    """CCTV_API_KEY 가 비어 있으면 호출하지 않는다 (키 없는 팀원 로컬)."""
    seen = []
    stub_get(monkeypatch, its_payload(its_item("정문 카메라")), seen=seen)
    monkeypatch.setattr(config, "CCTV_API_KEY", "")

    rows = its_cctv.refresh_stream_urls(seed_rows())

    assert seen == []
    assert rows[0]["cctv_stream_url"] == SEED_URL_1


# ---------- 실제 응답에서 발견된 결함 (0건 응답 · 도로 유형별 격리) ----------

# 실제 ITS 응답: 결과가 0건이면 data 키가 아예 없고 datacount 만 온다.
# (type=its 로 좁은 영역을 조회하면 흔히 이 모양이 온다)
EMPTY_PAYLOAD = {"response": {"coordtype": 1, "datacount": 0}}

AUTH_ERROR_PAYLOAD = {"header": {"resultCode": 4005,
                                 "resultMsg": "존재하지 않는 인증키입니다."},
                      "body": ""}


def stub_get_by_type(monkeypatch, mapping, seen=None):
    """도로 유형(type 파라미터)별로 다른 응답을 돌려주는 스텁.

    mapping 값이 Exception 이면 그 유형 조회는 실패한다.
    """
    def _fake(params):
        if seen is not None:
            seen.append(params)
        result = mapping[params["type"]]
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(its_cctv, "_get", _fake)


def test_zero_result_shape_is_empty_not_error():
    """0건 응답(datacount 만 있고 data 없음)은 빈 목록이지 오류가 아니다."""
    assert its_cctv._extract_items(EMPTY_PAYLOAD) == []


def test_error_body_still_counts_as_failure():
    """인증키 오류 본문은 여전히 실패로 취급한다 (0건과 구분)."""
    with pytest.raises(ValueError):
        its_cctv._extract_items(AUTH_ERROR_PAYLOAD)


def test_zero_result_in_one_road_type_does_not_discard_the_other(monkeypatch):
    """한 유형이 0건이어도 성공한 유형의 결과는 살아남는다."""
    monkeypatch.setattr(config, "ITS_ROAD_TYPES", ["ex", "its"])
    stub_get_by_type(monkeypatch, {
        "ex": its_payload(its_item("정문 카메라")),
        "its": EMPTY_PAYLOAD,
    })

    rows = its_cctv.refresh_stream_urls(seed_rows())

    assert rows[0]["cctv_stream_url"] == FRESH_URL


def test_one_road_type_failure_does_not_discard_the_other(monkeypatch):
    """한 유형이 예외로 죽어도 성공한 유형의 결과로 갱신한다."""
    monkeypatch.setattr(config, "ITS_ROAD_TYPES", ["ex", "its"])
    stub_get_by_type(monkeypatch, {
        "ex": its_payload(its_item("정문 카메라")),
        "its": ConnectionError("국도 조회만 실패"),
    })

    rows = its_cctv.refresh_stream_urls(seed_rows())

    assert rows[0]["cctv_stream_url"] == FRESH_URL


def test_one_road_type_error_body_does_not_discard_the_other(monkeypatch):
    """한 유형이 오류 본문을 돌려줘도 성공한 유형의 결과로 갱신한다."""
    monkeypatch.setattr(config, "ITS_ROAD_TYPES", ["ex", "its"])
    stub_get_by_type(monkeypatch, {
        "ex": its_payload(its_item("정문 카메라")),
        "its": AUTH_ERROR_PAYLOAD,
    })

    rows = its_cctv.refresh_stream_urls(seed_rows())

    assert rows[0]["cctv_stream_url"] == FRESH_URL


def test_all_road_types_failing_falls_back(monkeypatch):
    """모든 유형이 실패해야만 저장된 주소로 폴백한다."""
    monkeypatch.setattr(config, "ITS_ROAD_TYPES", ["ex", "its"])
    stub_get_by_type(monkeypatch, {
        "ex": AUTH_ERROR_PAYLOAD,
        "its": ConnectionError("망 끊김"),
    })

    rows = its_cctv.refresh_stream_urls(seed_rows())

    assert rows[0]["cctv_stream_url"] == SEED_URL_1


def test_failed_fetch_is_not_cached(monkeypatch):
    """실패는 캐시하지 않는다 — 다음 호출에서 다시 시도해야 한다.

    (실패를 '0건 성공'으로 캐시하면 일시적 오류 한 번에 TTL 내내 갱신이 죽는다)
    """
    monkeypatch.setattr(config, "ITS_ROAD_TYPES", ["ex"])
    calls = []

    def _fake(params):
        calls.append(params)
        if len(calls) == 1:
            raise ConnectionError("첫 호출만 실패")
        return its_payload(its_item("정문 카메라"))

    monkeypatch.setattr(its_cctv, "_get", _fake)

    first = its_cctv.refresh_stream_urls(seed_rows())
    second = its_cctv.refresh_stream_urls(seed_rows())

    assert first[0]["cctv_stream_url"] == SEED_URL_1   # 실패 → 저장된 주소
    assert len(calls) == 2                             # 캐시 서빙이 아니라 재시도
    assert second[0]["cctv_stream_url"] == FRESH_URL   # 재시도 성공


def test_zero_result_is_not_cached_as_failure(monkeypatch):
    """반대로 정상 0건 응답은 성공이므로 TTL 안에서 캐시된다."""
    monkeypatch.setattr(config, "ITS_ROAD_TYPES", ["ex"])
    seen = []
    stub_get(monkeypatch, EMPTY_PAYLOAD, seen=seen)

    its_cctv.refresh_stream_urls(seed_rows())
    its_cctv.refresh_stream_urls(seed_rows())

    assert len(seen) == 1


# ---------- 공개 조회 API 연동 ----------

def test_list_cctvs_returns_refreshed_url(client, admin_headers, monkeypatch):
    """GET /api/cctvs 는 갱신된 주소를 내려준다."""
    stub_get(monkeypatch, its_payload(its_item("정문 카메라")))

    items = client.get("/api/cctvs", headers=admin_headers).get_json()["items"]

    assert items[0]["cctv_stream_url"] == FRESH_URL
    assert items[1]["cctv_stream_url"] == SEED_URL_2


def test_get_cctv_returns_refreshed_url(client, admin_headers, monkeypatch):
    """GET /api/cctvs/<no> 단건도 갱신된 주소를 내려준다."""
    stub_get(monkeypatch, its_payload(its_item("정문 카메라")))

    body = client.get("/api/cctvs/1", headers=admin_headers).get_json()

    assert body["cctv_stream_url"] == FRESH_URL


def test_list_cctvs_still_200_when_its_fails(client, admin_headers, monkeypatch):
    """외부 API 가 죽어도 카메라 조회는 200 + 저장된 주소."""
    stub_get(monkeypatch, ConnectionError("네트워크 끊김"))

    r = client.get("/api/cctvs", headers=admin_headers)

    assert r.status_code == 200
    assert r.get_json()["items"][0]["cctv_stream_url"] == SEED_URL_1


# ---------- 내부 조회 API (AI 모델용) ----------

def test_internal_cctvs_requires_key(client):
    """X-Internal-Key 없이는 401."""
    r = client.get("/api/internal/cctvs")
    assert r.status_code == 401
    assert r.get_json()["code"] == "INTERNAL_UNAUTHORIZED"


def test_internal_cctvs_returns_refreshed_items(client, monkeypatch):
    """내부 키로 조회하면 공개 목록과 같은 키 집합 + 갱신된 주소."""
    stub_get(monkeypatch, its_payload(its_item("정문 카메라")))

    r = client.get("/api/internal/cctvs", headers=_key_headers())

    assert r.status_code == 200
    items = r.get_json()["items"]
    assert len(items) == 2
    assert set(items[0].keys()) == {
        "cctv_no", "user_no", "cctv_name", "cctv_location", "cctv_lat", "cctv_lng",
        "cctv_stream_url", "cctv_width", "cctv_height", "cctv_status", "cctv_created_at",
    }
    assert items[0]["cctv_stream_url"] == FRESH_URL


def test_internal_cctvs_filters_by_status(client, monkeypatch):
    """?cctv_status=ACTIVE 면 가동 중인 카메라만 (AI 가 보통 쓰는 형태)."""
    stub_get(monkeypatch, its_payload(its_item("정문 카메라")))

    r = client.get("/api/internal/cctvs?cctv_status=ACTIVE", headers=_key_headers())

    assert r.status_code == 200
    items = r.get_json()["items"]
    assert [it["cctv_no"] for it in items] == [1]
    assert items[0]["cctv_stream_url"] == FRESH_URL
