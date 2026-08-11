-- =====================================================
-- 2026-08-11  PostGIS 도입 — 최근접 소방서 탐색을 공간 질의로
--
-- 적용 대상: 이 날짜 이전에 db/schema.sql 로 만든 기존 개발 DB.
-- 새로 만드는 DB 는 db/schema.sql 하나면 되고 이 파일은 필요 없다.
--
-- 실행:
--   psql -U postgres -d fireguard -f db/migrations/003-2026-08-11-postgis-nearest-agency.sql
--   (또는 pgAdmin Query Tool 에 통째로 붙여넣기)
--
-- ⚠️ superuser 로 실행해야 한다 (CREATE EXTENSION / ALTER EXTENSION 권한).
-- 전체가 한 트랜잭션이다. 중간에 실패하면 아무것도 반영되지 않는다.
-- 재실행해도 안전하다 (IF NOT EXISTS / 조건부 분기).
--
-- 무엇이 바뀌나:
--   1) PostGIS 확장을 public 으로 옮기거나 새로 설치한다
--   2) cctv·agency 에 좌표점 생성 컬럼을 추가한다 (위경도에서 자동 파생)
--   3) 두 컬럼에 GiST 인덱스를 만든다
--
-- 왜 public 인가: fireguard 스키마 안에 있으면 schema.sql 의
-- DROP SCHEMA fireguard CASCADE 가 확장까지 지워버린다. 실제로 이 프로젝트의
-- 개발 DB 가 그 상태였다 — 스키마를 다시 깔면 PostGIS 가 사라졌을 것이다.
-- =====================================================
BEGIN;

-- -----------------------------------------------------
-- 1) 확장을 public 에 둔다
-- -----------------------------------------------------
-- ⚠️ PostGIS 는 **재배치가 안 되는 확장**이다. `ALTER EXTENSION postgis SET SCHEMA public`
--    은 "SET SCHEMA 구문을 지원하지 않음" 오류로 실패한다. 그래서 지우고 다시 만든다.
--
--    DROP ... CASCADE 는 그 확장에 의존하는 객체를 함께 지운다. 이 프로젝트에서는
--    이 마이그레이션 **전까지 PostGIS 를 쓰는 객체가 하나도 없어서** 잃을 것이 없다
--    (좌표점 컬럼은 아래 2)에서 지금 처음 만든다). 만약 직접 만든 공간 컬럼·인덱스가
--    이미 있다면 이 스크립트를 돌리기 전에 백업할 것.
DO $$
DECLARE
    current_schema_name text;
BEGIN
    SELECT n.nspname INTO current_schema_name
    FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
    WHERE e.extname = 'postgis';

    IF current_schema_name IS NULL THEN
        EXECUTE 'CREATE EXTENSION postgis SCHEMA public';
        RAISE NOTICE 'postgis 확장을 public 에 설치했습니다.';
    ELSIF current_schema_name <> 'public' THEN
        RAISE NOTICE 'postgis 가 % 스키마에 있습니다 — public 으로 다시 만듭니다.',
                     current_schema_name;
        EXECUTE 'DROP EXTENSION postgis CASCADE';
        EXECUTE 'CREATE EXTENSION postgis SCHEMA public';
    ELSE
        RAISE NOTICE 'postgis 가 이미 public 에 있습니다 — 그대로 둡니다.';
    END IF;
END $$;

-- -----------------------------------------------------
-- 2) 좌표점 생성 컬럼
--    앱이 채우지 않는다 — 위경도를 고치면 자동으로 따라 바뀐다.
--    ST_MakePoint 는 (경도, 위도) 순서다. 뒤집으면 엉뚱한 곳이 나온다.
-- -----------------------------------------------------
ALTER TABLE fireguard.cctv
    ADD COLUMN IF NOT EXISTS cctv_geog public.geography(Point,4326)
    GENERATED ALWAYS AS (
        public.ST_SetSRID(
            public.ST_MakePoint(cctv_lng::double precision,
                                cctv_lat::double precision), 4326
        )::public.geography
    ) STORED;

ALTER TABLE fireguard.agency
    ADD COLUMN IF NOT EXISTS agency_geog public.geography(Point,4326)
    GENERATED ALWAYS AS (
        public.ST_SetSRID(
            public.ST_MakePoint(agency_lng::double precision,
                                agency_lat::double precision), 4326
        )::public.geography
    ) STORED;

COMMENT ON COLUMN fireguard.cctv.cctv_geog     IS '좌표점 (위경도에서 자동 생성, 공간 질의용)';
COMMENT ON COLUMN fireguard.agency.agency_geog IS '좌표점 (위경도에서 자동 생성, 최근접 탐색용)';

-- -----------------------------------------------------
-- 3) 공간 인덱스 — `<->` KNN 정렬이 이걸 탄다
--    B-tree 로는 거리 정렬을 색인할 수 없어 GiST 를 쓴다.
-- -----------------------------------------------------
CREATE INDEX IF NOT EXISTS IX_agency_geog ON fireguard.agency USING GIST (agency_geog);
CREATE INDEX IF NOT EXISTS IX_cctv_geog   ON fireguard.cctv   USING GIST (cctv_geog);

COMMIT;

-- 확인용 (실행 후 따로 돌려보면 된다):
--   SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
--   WHERE e.extname = 'postgis';                          -- public 이어야 한다
--
--   SELECT a.agency_name,
--          public.ST_Distance(a.agency_geog, c.cctv_geog)/1000.0 AS km
--   FROM fireguard.agency a, fireguard.cctv c
--   WHERE c.cctv_no = 1 AND a.agency_is_active
--   ORDER BY a.agency_geog <-> c.cctv_geog;
