-- =====================================================
-- 2026-08-10 (2차)  안 쓰는 컬럼 제거 — media_type · alert_level
--
-- 적용 대상: 이 날짜 이전에 db/schema.sql 로 만든 기존 개발 DB.
-- 새로 만드는 DB 는 db/schema.sql 하나면 되고 이 파일은 필요 없다.
-- 001 (report-accepted-and-report-log) 을 먼저 돌릴 것 — 번호가 곧 실행 순서다.
--
-- 실행:
--   psql -U postgres -d fireguard -f db/migrations/002-2026-08-10-drop-media-type-and-alert-level.sql
--   (또는 pgAdmin Query Tool 에 통째로 붙여넣기)
--
-- 전체가 한 트랜잭션이고, IF EXISTS 라 재실행해도 안전하다.
--
-- 바뀌는 것 두 가지 (둘 다 항상 같은 값만 들어 있던 상수 컬럼)
--   1. event_media.media_type 제거
--      CLIP(영상 클립) 저장을 안 하기로 확정 → 값이 항상 'FRAME' 이라 구분이 무의미.
--   2. alert.alert_level 제거
--      알림 승격 단계 폐기(PUSH·SMS 동시 발송) → 값이 항상 1 이었다.
--      이 컬럼을 지우면 IX_alert_01(event_no, alert_level) 인덱스도 함께
--      사라지므로 (event_no) 단독으로 다시 만든다.
--   ※ 프론트는 두 필드 모두 사용하지 않음을 확인했다 (front/src 검색 기준).
-- =====================================================
BEGIN;

-- 1) event_media.media_type 제거
ALTER TABLE fireguard.event_media DROP COLUMN IF EXISTS media_type;

-- 2) alert.alert_level 제거 — 걸려 있던 IX_alert_01 도 같이 드롭된다
ALTER TABLE fireguard.alert DROP COLUMN IF EXISTS alert_level;

-- 3) 이벤트별 알림 조회 인덱스 재생성 (event_no 단독)
CREATE INDEX IF NOT EXISTS ix_alert_01 ON fireguard.alert (event_no);

COMMIT;

-- 확인:
--   SELECT column_name FROM information_schema.columns
--   WHERE table_schema='fireguard' AND table_name IN ('event_media','alert')
--   ORDER BY table_name, ordinal_position;
--   → media_type · alert_level 이 없어야 정상
