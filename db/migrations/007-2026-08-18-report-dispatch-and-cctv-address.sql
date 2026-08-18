-- =====================================================
-- 2026-08-18  소방서 출동 통지 수신 + CCTV 주소 컬럼
--
-- 적용 대상: 이 날짜 이전에 db/schema.sql 로 만든 기존 개발 DB.
-- 새로 만드는 DB 는 db/schema.sql 하나면 되고 이 파일은 필요 없다.
--
-- 실행:
--   psql -U postgres -d fireguard -f db/migrations/007-2026-08-18-report-dispatch-and-cctv-address.sql
--   (또는 pgAdmin Query Tool 에 통째로 붙여넣기)
--
-- 전체가 한 트랜잭션이다. 중간에 실패하면 아무것도 반영되지 않는다.
-- 재실행해도 안전하다 (IF NOT EXISTS).
--
-- 무엇이 바뀌나:
--   1) report_119 에 출동 통지 컬럼 2개 (수신 시각 + 원문 jsonb)
--   2) cctv 에 역지오코딩 주소 컬럼 1개
--   3) 부분 유니크 인덱스의 '진행 중' 정의에 DISPATCHED 를 넣는다
--
-- 왜 필요한가:
--   2xx 응답(ACCEPTED)은 '신고를 받았다'까지고, 소방차가 실제로 나갔는지는
--   119 만 알았다. 이제 119 가 콜백으로 알려주므로 받아 적을 자리가 필요하다.
--   cctv_address 는 그 신고에 실어 보낼 주소다 — 지금 나가는 값(cctv_location)은
--   설치 위치 설명이거나 ITS 카메라 이름이라 소방 지령에 쓸 수 없다.
--
-- ⚠️ DISPATCHED 이름 재사용 주의
--   001-2026-08-10 은 **정확히 반대 방향**의 변경을 했다: 당시의 DISPATCHED 를
--   ACCEPTED 로 바꾸고 report_dispatched_at 을 report_accepted_at 으로 rename 했다.
--   이 파일은 그때 폐기한 이름을 **다른 뜻으로** 되살린다.
--     001 의 DISPATCHED = '119 서버가 신고를 받았다'  → 지금의 ACCEPTED
--     007 의 DISPATCHED = '소방차가 실제로 출동했다'  (119 가 콜백으로 알려준다)
--   되돌리는 것이 아니다. 두 값은 이제 서로 다른 뜻으로 공존한다.
-- =====================================================
BEGIN;

SET search_path TO fireguard, public;

-- -----------------------------------------------------
-- 1) 출동 통지 컬럼
--    report_dispatch 는 스키마를 고정하지 않는다 — 기관마다 보내는 키가 다르고,
--    모르는 키가 왔을 때 버리면 사후에 무엇이 왔었는지 따질 근거가 사라진다.
-- -----------------------------------------------------
ALTER TABLE fireguard.report_119
    ADD COLUMN IF NOT EXISTS report_dispatched_at timestamp NULL,
    ADD COLUMN IF NOT EXISTS report_dispatch      jsonb     NULL;

COMMENT ON COLUMN fireguard.report_119.report_dispatched_at
    IS '소방서 출동 통지 수신 일시';
COMMENT ON COLUMN fireguard.report_119.report_dispatch
    IS '소방서가 보낸 출동 정보 원문 (지령번호·차량·ETA)';

-- -----------------------------------------------------
-- 2) CCTV 주소 컬럼
--    등록 시점에 좌표를 역지오코딩해 채운다. 기존 행은 NULL 이므로
--    back/scripts/backfill_cctv_address.py 를 한 번 돌려 메운다.
-- -----------------------------------------------------
ALTER TABLE fireguard.cctv
    ADD COLUMN IF NOT EXISTS cctv_address varchar(255) NULL;

COMMENT ON COLUMN fireguard.cctv.cctv_address
    IS '좌표를 역지오코딩한 주소 (119 신고에 싣는 값)';

-- -----------------------------------------------------
-- 3) '진행 중' 정의 갱신
--    인덱스 조건에 상태 문자열이 직접 박혀 있어 다시 만드는 수밖에 없다.
--    이 집합은 services/report_service.py 의 ACTIVE_STATUSES 와 같아야 한다.
-- -----------------------------------------------------
DROP INDEX IF EXISTS fireguard.UX_report_119_active;
CREATE UNIQUE INDEX UX_report_119_active ON fireguard.report_119 (event_no)
    WHERE report_status IN ('SENDING', 'ACCEPTED', 'DISPATCHED');

COMMIT;

-- =====================================================
-- 구축 확인
-- =====================================================
-- 컬럼 3행이 나와야 한다
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'fireguard'
  AND (table_name, column_name) IN
      (('report_119', 'report_dispatched_at'), ('report_119', 'report_dispatch'),
       ('cctv', 'cctv_address'))
ORDER BY table_name, column_name;

-- 인덱스 조건에 DISPATCHED 가 보여야 한다
SELECT indexdef FROM pg_indexes
WHERE schemaname = 'fireguard' AND indexname = 'ux_report_119_active';
