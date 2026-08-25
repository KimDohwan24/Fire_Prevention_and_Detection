-- =====================================================
-- 2026-08-19  업로드 영상 AI 판정 이력
--
-- 적용 대상: 기존 개발 DB. 새 DB는 db/schema.sql만 실행하면 된다.
-- 실행:
--   psql -U postgres -d fireguard -f db/migrations/008-2026-08-19-video-test-events.sql
--
-- 재실행 가능하며 전체가 한 트랜잭션으로 적용된다.
-- =====================================================
BEGIN;

SET search_path TO fireguard, public;

ALTER TABLE fireguard.fire_event
    ADD COLUMN IF NOT EXISTS event_source_type varchar(20) NOT NULL DEFAULT 'CCTV_LIVE',
    ADD COLUMN IF NOT EXISTS event_source_metadata jsonb NULL,
    ADD COLUMN IF NOT EXISTS event_cctv_snapshot jsonb NULL,
    ADD COLUMN IF NOT EXISTS event_processed_frames integer NULL,
    ADD COLUMN IF NOT EXISTS event_first_detected_offset_sec numeric(12,3) NULL,
    ADD COLUMN IF NOT EXISTS event_confirmed_offset_sec numeric(12,3) NULL,
    ADD COLUMN IF NOT EXISTS event_test_started_at timestamp NULL,
    ADD COLUMN IF NOT EXISTS event_test_finished_at timestamp NULL;

ALTER TABLE fireguard.event_media
    ADD COLUMN IF NOT EXISTS media_is_first boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS media_is_confirmation boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS media_frame_index bigint NULL,
    ADD COLUMN IF NOT EXISTS media_source_offset_sec numeric(12,3) NULL;

COMMENT ON COLUMN fireguard.fire_event.event_source_type
    IS '이벤트 입력 종류 (CCTV_LIVE, VIDEO_TEST)';
COMMENT ON COLUMN fireguard.fire_event.event_source_metadata
    IS '영상·모델·판정 설정 메타데이터';
COMMENT ON COLUMN fireguard.fire_event.event_cctv_snapshot
    IS '테스트 당시 CCTV 정보 스냅샷';
COMMENT ON COLUMN fireguard.fire_event.event_processed_frames
    IS 'AI가 실제 추론한 전체 프레임 수';
COMMENT ON COLUMN fireguard.fire_event.event_first_detected_offset_sec
    IS '영상 내 최초 검출 위치(초)';
COMMENT ON COLUMN fireguard.fire_event.event_confirmed_offset_sec
    IS '영상 내 화재 확정 위치(초)';
COMMENT ON COLUMN fireguard.fire_event.event_test_started_at
    IS '영상 테스트 처리 시작 일시';
COMMENT ON COLUMN fireguard.fire_event.event_test_finished_at
    IS '영상 테스트 처리 종료 일시';
COMMENT ON COLUMN fireguard.event_media.media_is_first
    IS '최초 검출 증거 이미지 여부';
COMMENT ON COLUMN fireguard.event_media.media_is_confirmation
    IS '화재 확정 증거 이미지 여부';
COMMENT ON COLUMN fireguard.event_media.media_frame_index
    IS '원본 영상의 프레임 번호';
COMMENT ON COLUMN fireguard.event_media.media_source_offset_sec
    IS '원본 영상 내 위치(초)';

COMMIT;

SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'fireguard'
  AND table_name IN ('fire_event', 'event_media')
  AND column_name IN (
      'event_source_type', 'event_source_metadata', 'event_cctv_snapshot',
      'event_processed_frames', 'event_first_detected_offset_sec',
      'event_confirmed_offset_sec', 'event_test_started_at',
      'event_test_finished_at', 'media_is_first', 'media_is_confirmation',
      'media_frame_index', 'media_source_offset_sec'
  )
ORDER BY table_name, column_name;
