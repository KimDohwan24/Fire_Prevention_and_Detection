-- =====================================================
-- 2026-08-21  소방서에 출처 고유번호 + 주소 + 전화 컬럼
--
-- 적용 대상: 이 날짜 이전에 db/schema.sql 로 만든 기존 개발 DB.
-- 새로 만드는 DB 는 db/schema.sql 하나면 되고 이 파일은 필요 없다.
--
-- 실행:
--   psql -U postgres -d fireguard -f db/migrations/008-2026-08-21-agency-source-address-phone.sql
--   (또는 pgAdmin Query Tool 에 통째로 붙여넣기)
--
-- 전체가 한 트랜잭션이다. 중간에 실패하면 아무것도 반영되지 않는다.
-- 재실행해도 안전하다 (IF NOT EXISTS).
--
-- 무엇이 바뀌나:
--   1) agency 에 컬럼 3개 — 출처 고유번호 / 주소 / 전화번호
--   2) 출처 고유번호에 부분 유니크 인덱스
--
-- 왜 필요한가 (2026-08-21 실측):
--   생활안전지도 소방시설 개방데이터(IF_0038)에서 전국 소방서 235건을 받아 보니
--   서로 다른 이름은 214개뿐이었다. 같은 이름의 소방서가 여러 지역에 실재한다 —
--     중부소방서 5곳 (대구·울산·인천·서울·부산)
--     서부소방서 5곳 (제주·대전·대구·인천·광주)
--     동부 5 · 북부 4 · 남부 3 · 강서 3 · 강북 2 · 고성 2
--   이름으로 대조해 적재하면 이 21건이 서로를 덮어써 사라진다. 기관을 가리키는
--   것은 이름이 아니라 출처의 고유번호(objt_id)여야 한다. 이름 앞에 시도명을
--   붙여 구분하는 방법도 있으나, 화면에 나가는 기관명을 우리가 가공하게 되고
--   출처가 이름을 바꾸면 대조가 다시 깨진다. 고유번호를 들고 있으면 개명이
--   일어나도 같은 행을 계속 따라간다.
--
--   주소·전화는 같은 응답에 이미 들어 있는데 담을 자리가 없어 버리고 있었다.
--   관리자 화면에서 '어느 지역 소방서인지' 구분하려면 주소가 사실상 필수다.
--
-- 부분 유니크(WHERE ... IS NOT NULL)인 이유:
--   손으로 등록한 기존 행(시연용 용산·종로·중부소방서)은 출처가 없어 NULL 이다.
--   보통의 유니크 인덱스도 NULL 은 서로 다르게 보지만, 의도를 분명히 남기고
--   '출처가 있는 행끼리만 유일하다'는 규칙을 인덱스에 새겨 둔다.
-- =====================================================
BEGIN;

SET search_path TO fireguard, public;

-- -----------------------------------------------------
-- 1) 컬럼 3개
--    agency_source_id 를 숫자가 아니라 varchar 로 두는 이유: 출처가 objt_id 를
--    '2.0' 처럼 소수점 붙은 문자열로 내려주는 경우가 있고, 앞으로 다른 출처
--    (공공데이터포털 등)를 섞게 되면 숫자가 아닐 수도 있다. 우리는 이 값으로
--    계산하지 않고 대조만 하므로 문자열이 안전하다.
-- -----------------------------------------------------
ALTER TABLE fireguard.agency
    ADD COLUMN IF NOT EXISTS agency_source_id varchar(40)  NULL,
    ADD COLUMN IF NOT EXISTS agency_address   varchar(255) NULL,
    ADD COLUMN IF NOT EXISTS agency_phone     varchar(30)  NULL;

COMMENT ON COLUMN fireguard.agency.agency_source_id
    IS '출처 고유번호 (생활안전지도 IF_0038 objt_id). 손으로 등록한 행은 NULL';
COMMENT ON COLUMN fireguard.agency.agency_address
    IS '주소 (도로명 우선, 없으면 지번)';
COMMENT ON COLUMN fireguard.agency.agency_phone
    IS '대표 전화번호';

-- -----------------------------------------------------
-- 2) 출처 고유번호는 기관을 가리키는 열쇠다 — 중복되면 적재가 어느 행을 고칠지
--    알 수 없어진다. 인덱스가 있으면 적재 스크립트의 조회도 순차 검색을 안 한다.
-- -----------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS UX_agency_source_id
    ON fireguard.agency (agency_source_id)
    WHERE agency_source_id IS NOT NULL;

COMMIT;
