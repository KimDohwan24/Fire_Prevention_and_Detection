"""ITS 공공 CCTV 조회 API 테스트 — GET /api/its/cctvs.

카메라를 등록하려는 관리자가 "지금 연동 가능한 ITS 카메라"를 고르는 화면용이다.
DB 조회가 아니라 ITS 오픈 API 를 그때그때 조회해서, 우리 스키마 이름으로
정규화해 내려준다.

조회 API(GET /api/cctvs)와 실패 정책이 반대인 점이 이 파일의 핵심이다:
저장된 주소로 폴백할 수 있는 조회 API 는 외부가 죽어도 200 이지만,
이 엔드포인트는 폴백할 저장분이 없으므로 빈 목록으로 위장하지 않고 502 를 낸다.

이 파일의 어떤 테스트도 실제 HTTP 를 보내지 않는다 — conftest 의
`_no_real_its_http` 가 전역으로 `its_cctv._get` 을 막고, 개별 테스트는 자기
monkeypatch 로 그 스텁을 덮어쓴다 (모듈 TTL 캐시도 테스트마다 비워진다).
"""
import pytest

import config
from services import its_cctv

URL = "/api/its/cctvs"

STREAM = "http://cctvsec.example/1?wmsAuthSign=TOKEN-A"


def its_item(name, url=STREAM, lat=37.5665, lng=126.9780, fmt="HLS"):
    """ITS 응답 항목 1개 — 실제 응답과 같은 키 구성.

    coordx=경도, coordy=위도 다 (뒤집기 쉬운 지점이라 값을 크게 벌려 둔다).
    """
    return {
        "roadsectionid": "",
        "coordx": lng,
        "coordy": lat,
        "cctvresolution": "",
        "filecreatetime": "",
        "cctvtype": 1,
        "cctvformat": fmt,
        "cctvname": name,
        "cctvurl": url,
    }


def its_payload(*items):
    return {"response": {"coordtype": 1, "data": list(items)}}


EMPTY_PAYLOAD = {"response": {"coordtype": 1, "datacount": 0}}

AUTH_ERROR_PAYLOAD = {"header": {"resultCode": 4005,
                                 "resultMsg": "존재하지 않는 인증키입니다."},
                      "body": ""}


def stub_get(monkeypatch, payload, seen=None):
    """`its_cctv._get` 을 고정 응답으로 바꾼다. seen 을 주면 요청 파라미터를 모은다."""
    def _fake(params):
        if seen is not None:
            seen.append(params)
        if isinstance(payload, Exception):
            raise payload
        return payload
    monkeypatch.setattr(its_cctv, "_get", _fake)


@pytest.fixture(autouse=True)
def its_key(monkeypatch):
    """키가 있는 상태를 기본으로 고정한다 (팀원 로컬 .env 에 좌우되지 않게)."""
    monkeypatch.setattr(config, "CCTV_API_KEY", "TEST-ITS-KEY")
    monkeypatch.setattr(config, "ITS_ROAD_TYPES", ["ex"])
    yield


# ---------- 인증 ----------

def test_requires_login(client):
    """토큰 없이는 401."""
    r = client.get(URL)

    assert r.status_code == 401
    assert r.get_json()["code"] == "UNAUTHORIZED"


# ---------- 정규화 ----------

def test_items_are_normalized_to_our_field_names(client, admin_headers, monkeypatch):
    """ITS 원본 키가 아니라 우리 스키마 이름으로 내려간다."""
    stub_get(monkeypatch, its_payload(
        its_item("[경부선] 판교분기점", lat=37.3855, lng=127.1058)))

    r = client.get(URL, headers=admin_headers)

    assert r.status_code == 200
    items = r.get_json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["cctv_name"] == "[경부선] 판교분기점"
    assert item["cctv_stream_url"] == STREAM
    # ITS 원본 키는 응답에 남아 있으면 안 된다
    assert "cctvname" not in item
    assert "coordx" not in item
    # 프론트 모달이 문자열로 기대하는 필드 (undefined 면 .includes 에서 터진다)
    assert isinstance(item["cctv_location"], str)
    assert isinstance(item["cctv_type"], str)


def test_lat_lng_are_not_swapped(client, admin_headers, monkeypatch):
    """coordy=위도, coordx=경도 — 뒤집으면 지도에 엉뚱한 곳이 찍힌다."""
    stub_get(monkeypatch, its_payload(
        its_item("[경부선] 판교분기점", lat=37.3855, lng=127.1058)))

    item = client.get(URL, headers=admin_headers).get_json()["items"][0]

    assert item["cctv_lat"] == pytest.approx(37.3855)   # coordy
    assert item["cctv_lng"] == pytest.approx(127.1058)  # coordx


# ---------- q 필터 ----------

def test_q_filters_by_name(client, admin_headers, monkeypatch):
    """q 는 카메라 이름 부분 문자열 필터 — 서버에서 걸러 내려준다."""
    stub_get(monkeypatch, its_payload(
        its_item("[경부선] 판교분기점"),
        its_item("[서해안선] 금천IC"),
    ))

    items = client.get(f"{URL}?q=금천", headers=admin_headers).get_json()["items"]

    assert [it["cctv_name"] for it in items] == ["[서해안선] 금천IC"]


def test_q_is_case_insensitive(client, admin_headers, monkeypatch):
    """대소문자는 무시한다."""
    stub_get(monkeypatch, its_payload(
        its_item("[경부선] Pangyo JCT"),
        its_item("[서해안선] 금천IC"),
    ))

    items = client.get(f"{URL}?q=pangyo", headers=admin_headers).get_json()["items"]

    assert [it["cctv_name"] for it in items] == ["[경부선] Pangyo JCT"]


def test_q_matching_nothing_is_200_with_empty_items(client, admin_headers, monkeypatch):
    """검색 결과 0건도 정상이다 (200 + 빈 items)."""
    stub_get(monkeypatch, its_payload(its_item("[경부선] 판교분기점")))

    r = client.get(f"{URL}?q=없는이름", headers=admin_headers)

    assert r.status_code == 200
    assert r.get_json()["items"] == []


# ---------- 조회 박스 ----------

def test_bbox_is_passed_to_its(client, admin_headers, monkeypatch):
    """네 개를 다 주면 그 박스로 조회한다."""
    seen = []
    stub_get(monkeypatch, its_payload(), seen=seen)

    r = client.get(f"{URL}?min_x=126.8&max_x=127.2&min_y=37.4&max_y=37.6",
                   headers=admin_headers)

    assert r.status_code == 200
    assert len(seen) == 1
    p = seen[0]
    assert float(p["minX"]) == pytest.approx(126.8)
    assert float(p["maxX"]) == pytest.approx(127.2)
    assert float(p["minY"]) == pytest.approx(37.4)
    assert float(p["maxY"]) == pytest.approx(37.6)


def test_no_bbox_uses_korea_default(client, admin_headers, monkeypatch):
    """하나도 안 주면 대한민국 전역 기본 박스로 조회한다."""
    seen = []
    stub_get(monkeypatch, its_payload(), seen=seen)

    client.get(URL, headers=admin_headers)

    min_x, max_x, min_y, max_y = its_cctv.KOREA_BBOX
    p = seen[0]
    assert float(p["minX"]) == pytest.approx(min_x)
    assert float(p["maxX"]) == pytest.approx(max_x)
    assert float(p["minY"]) == pytest.approx(min_y)
    assert float(p["maxY"]) == pytest.approx(max_y)


@pytest.mark.parametrize("query", [
    "min_x=126.8",
    "min_x=126.8&max_x=127.2",
    "min_x=126.8&max_x=127.2&min_y=37.4",
    "max_y=37.6",
])
def test_partial_bbox_is_400(client, admin_headers, query):
    """네 개는 전부 있거나 전부 없어야 한다 — 일부만 주면 400."""
    r = client.get(f"{URL}?{query}", headers=admin_headers)

    assert r.status_code == 400
    assert r.get_json()["code"] == "BAD_REQUEST"


def test_non_numeric_bbox_is_400(client, admin_headers):
    """숫자가 아닌 좌표는 400 (어느 칸인지 field 로 알려준다)."""
    r = client.get(f"{URL}?min_x=서울&max_x=127.2&min_y=37.4&max_y=37.6",
                   headers=admin_headers)

    assert r.status_code == 400
    body = r.get_json()
    assert body["code"] == "BAD_REQUEST"
    assert body["field"] == "min_x"


# ---------- is_registered ----------

def test_is_registered_marks_already_registered_names(client, admin_headers, monkeypatch):
    """이미 cctv 테이블에 있는 이름은 True — 모달이 중복 등록을 막는 데 쓴다.

    시드 카메라는 '정문 카메라'(cctv_no 1) · '후문 카메라'(cctv_no 2) 두 대다.
    """
    stub_get(monkeypatch, its_payload(
        its_item("정문 카메라"),
        its_item("[경부선] 판교분기점"),
    ))

    items = client.get(URL, headers=admin_headers).get_json()["items"]

    by_name = {it["cctv_name"]: it["is_registered"] for it in items}
    assert by_name["정문 카메라"] is True
    assert by_name["[경부선] 판교분기점"] is False


def test_is_registered_queries_db_once(client, admin_headers, monkeypatch):
    """등록 이름 대조는 항목 수와 무관하게 쿼리 한 번이어야 한다."""
    import db

    stub_get(monkeypatch, its_payload(*[its_item(f"카메라{i}") for i in range(10)]))

    calls = []
    real_query = db.query
    monkeypatch.setattr(
        db, "query", lambda sql, params=(): calls.append(sql) or real_query(sql, params)
    )

    client.get(URL, headers=admin_headers)

    assert len(calls) == 1


# ---------- 결과 0건 ----------

def test_zero_result_is_200_with_empty_items(client, admin_headers, monkeypatch):
    """ITS 0건 응답(datacount 만 옴)은 실패가 아니라 빈 목록이다."""
    stub_get(monkeypatch, EMPTY_PAYLOAD)

    r = client.get(URL, headers=admin_headers)

    assert r.status_code == 200
    assert r.get_json()["items"] == []


# ---------- 실패는 실패로 알린다 (조회 API 와 정반대) ----------

def test_all_road_types_failing_is_502(client, admin_headers, monkeypatch):
    """ITS 가 전부 실패하면 빈 목록으로 위장하지 않고 502 를 낸다."""
    monkeypatch.setattr(config, "ITS_ROAD_TYPES", ["ex", "its"])
    stub_get(monkeypatch, ConnectionError("망 끊김"))

    r = client.get(URL, headers=admin_headers)

    assert r.status_code == 502
    assert r.get_json()["code"] == "ITS_UNAVAILABLE"


def test_auth_error_body_is_502(client, admin_headers, monkeypatch):
    """인증키 오류 본문(resultCode 4005)도 실패다."""
    stub_get(monkeypatch, AUTH_ERROR_PAYLOAD)

    r = client.get(URL, headers=admin_headers)

    assert r.status_code == 502
    assert r.get_json()["code"] == "ITS_UNAVAILABLE"


def test_one_road_type_failing_still_returns_the_other(client, admin_headers, monkeypatch):
    """한 유형만 죽으면 성공한 유형의 결과로 200 이다 (전부 실패해야 502)."""
    monkeypatch.setattr(config, "ITS_ROAD_TYPES", ["ex", "its"])

    def _fake(params):
        if params["type"] == "its":
            raise ConnectionError("국도 조회만 실패")
        return its_payload(its_item("[경부선] 판교분기점"))

    monkeypatch.setattr(its_cctv, "_get", _fake)

    r = client.get(URL, headers=admin_headers)

    assert r.status_code == 200
    assert [it["cctv_name"] for it in r.get_json()["items"]] == ["[경부선] 판교분기점"]


def test_missing_api_key_is_502(client, admin_headers, monkeypatch):
    """CCTV_API_KEY 가 없으면 호출도 하지 않고 502 로 이유를 알린다."""
    seen = []
    stub_get(monkeypatch, its_payload(its_item("[경부선] 판교분기점")), seen=seen)
    monkeypatch.setattr(config, "CCTV_API_KEY", "")

    r = client.get(URL, headers=admin_headers)

    assert r.status_code == 502
    body = r.get_json()
    assert body["code"] == "ITS_UNAVAILABLE"
    assert "인증키" in body["message"]
    assert seen == []
