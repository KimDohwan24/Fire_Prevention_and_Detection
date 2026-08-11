"""PostGIS 공간 질의 — 최근접 소방서 탐색.

거리 계산과 정렬을 파이썬이 아니라 **DB 의 공간 연산**으로 한다.
좌표는 `numeric` 위경도가 원본이고, `*_geog` 는 거기서 파생되는 생성 컬럼이라
앱이 따로 채우지 않는다 (원본과 어긋날 수가 없다).
"""
import pytest

import db
from services import report_service

# 시드 좌표 (conftest 와 같은 값)
CCTV1 = (37.5665000, 126.9780000)      # 정문 카메라
AGENCY1 = (37.5720000, 126.9794000)    # 종로소방서 — 가깝다
AGENCY2 = (37.5610000, 126.9950000)    # 중부소방서 — 멀다


def test_postgis_extension_is_installed():
    """확장이 public 에 있어야 한다.

    fireguard 스키마 안에 있으면 schema.sql 의 DROP SCHEMA CASCADE 가
    확장까지 지워버린다 — 스키마를 다시 깔 때마다 PostGIS 가 사라진다.
    """
    row = db.query_one(
        """
        SELECT n.nspname AS schema_name
        FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
        WHERE e.extname = 'postgis'
        """
    )
    assert row is not None, "postgis 확장이 설치돼 있지 않다"
    assert row["schema_name"] == "public"


@pytest.mark.parametrize("table,col", [("agency", "agency_geog"), ("cctv", "cctv_geog")])
def test_geography_column_is_generated(table, col):
    """앱이 쓰지 않아도 위경도에서 자동으로 채워지는 생성 컬럼이어야 한다."""
    row = db.query_one(
        """
        SELECT is_generated, udt_name
        FROM information_schema.columns
        WHERE table_schema = 'fireguard' AND table_name = %s AND column_name = %s
        """,
        (table, col),
    )
    assert row is not None, f"{table}.{col} 컬럼이 없다"
    assert row["is_generated"] == "ALWAYS"
    assert row["udt_name"] == "geography"


@pytest.mark.parametrize("table,col", [("agency", "agency_geog"), ("cctv", "cctv_geog")])
def test_geography_column_has_gist_index(table, col):
    """KNN 정렬이 인덱스를 타려면 GiST 여야 한다."""
    row = db.query_one(
        """
        SELECT indexdef FROM pg_indexes
        WHERE schemaname = 'fireguard' AND tablename = %s AND indexdef LIKE %s
        """,
        (table, f"%gist%({col})%"),
    )
    assert row is not None, f"{table}.{col} 에 GiST 인덱스가 없다"


def test_generated_column_follows_lat_lng_updates():
    """위경도를 고치면 좌표점도 따라 바뀐다 (앱이 손대지 않아도)."""
    before = db.query_one(
        "SELECT public.ST_Y(agency_geog::public.geometry) AS lat FROM agency WHERE agency_no = 1"
    )["lat"]
    assert before == pytest.approx(AGENCY1[0], abs=1e-6)

    db.execute("UPDATE agency SET agency_lat = 38.0 WHERE agency_no = 1")
    after = db.query_one(
        "SELECT public.ST_Y(agency_geog::public.geometry) AS lat FROM agency WHERE agency_no = 1"
    )["lat"]
    assert after == pytest.approx(38.0, abs=1e-6)


def test_nearest_agencies_orders_by_distance():
    """가까운 기관이 먼저 나오고, 거리(km)가 상식 범위여야 한다."""
    rows = report_service.nearest_agencies(cctv_no=1)

    assert [r["agency_no"] for r in rows] == [1, 2]
    assert 0.4 < rows[0]["distance_km"] < 0.9      # 종로 ≈ 0.62km
    assert 1.2 < rows[1]["distance_km"] < 2.0      # 중부 ≈ 1.62km
    assert rows[0]["distance_km"] < rows[1]["distance_km"]
    # 승계에 필요한 값이 함께 나온다
    assert rows[0]["agency_name"] == "종로소방서"
    assert rows[0]["agency_endpoint"]


def test_nearest_agencies_excludes_inactive():
    db.execute("UPDATE agency SET agency_is_active = false WHERE agency_no = 1")
    rows = report_service.nearest_agencies(cctv_no=1)
    assert [r["agency_no"] for r in rows] == [2]


def test_nearest_agencies_skips_null_coordinates():
    """좌표 없는 기관은 거리를 잴 수 없다 — 승계 후보에서 뺀다.

    NULL 을 그냥 두면 정렬 맨 뒤에 붙어 '가장 먼 기관'처럼 취급되는데,
    거리를 모르는 것과 먼 것은 다르다. 신고 대상에서 아예 제외한다.
    """
    db.execute("UPDATE agency SET agency_lat = NULL, agency_lng = NULL WHERE agency_no = 1")
    rows = report_service.nearest_agencies(cctv_no=1)
    assert [r["agency_no"] for r in rows] == [2]


def test_nearest_agencies_empty_when_cctv_has_no_coordinates():
    db.execute("UPDATE cctv SET cctv_lat = NULL, cctv_lng = NULL WHERE cctv_no = 1")
    assert report_service.nearest_agencies(cctv_no=1) == []


def test_postgis_distance_matches_known_value():
    """타원체(WGS84) 기준 거리 — 구면 근사와 0.5% 안쪽에서 일치해야 한다.

    PostGIS geography 는 타원체로 재므로 하버사인(구면)보다 정확하다.
    값이 크게 어긋나면 좌표를 (경도, 위도) 순으로 잘못 넣은 것을 의심할 것.
    """
    row = db.query_one(
        """
        SELECT public.ST_Distance(
                 public.ST_SetSRID(public.ST_MakePoint(%s, %s), 4326)::public.geography,
                 public.ST_SetSRID(public.ST_MakePoint(%s, %s), 4326)::public.geography
               ) / 1000.0 AS km
        """,
        (CCTV1[1], CCTV1[0], AGENCY1[1], AGENCY1[0]),
    )
    assert row["km"] == pytest.approx(0.6228, rel=0.005)
