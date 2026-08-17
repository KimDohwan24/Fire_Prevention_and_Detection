-- =====================================================
-- 2026-08-17  활동이력 상세 · 토큰 폐기 · 소셜 로그인 대비
--
-- 적용 대상: 005 까지 적용된 기존 개발 DB
-- 새로 만드는 DB 는 db/schema.sql 하나면 되고 이 파일은 필요 없다.
--
-- 실행:
--   psql -U postgres -d fireguard -f db/migrations/006-2026-08-17-activity-detail-and-social.sql
--   (또는 pgAdmin Query Tool 에 통째로 붙여넣기)
--
-- 전체가 한 트랜잭션이다. 중간에 실패하면 아무것도 반영되지 않는다.
-- 이미 적용한 DB 에 다시 돌리면 ADD COLUMN 에서 오류가 나며 전부 롤백된다 — 안전하다.
--
-- 바뀌는 것 세 가지
--
-- (1) user_activity 에 대상·요약 컬럼
--     지금은 종류와 시각뿐이라 관제 조치 이력이 전부 똑같이 보인다. "화재를 확인했다"는
--     남지만 언제 어느 카메라 건이었는지는 답할 수가 없다. target 은 대상 행의 번호,
--     detail 은 화면에 그대로 띄울 한 줄 요약이다.
--     기존 행은 둘 다 NULL 로 남는다 — 소급해 채울 근거가 없다.
--
--     활동 종류도 넷 늘어난다 (컬럼 변경 없이 값만):
--       PASSWORD_CHANGED  PROFILE_UPDATED  FIRE_CONFIRMED  FIRE_DISMISSED
--     activity_type 은 varchar(20) 이고 넷 다 그 안에 들어간다.
--
-- (2) users.user_token_valid_from — 토큰 폐기 기준선
--     JWT 는 무상태라 이미 발급한 토큰을 회수할 수 없다. 그래서 사용자마다
--     "이 시각 이전에 발급된 것은 안 받는다"는 기준선을 두고 매 요청 대조한다.
--     로그아웃과 계정 정지·탈퇴가 이 값을 now() 로 세운다.
--     NULL = 폐기 이력 없음. 기존 사용자는 전부 NULL 이라 지금 살아있는 토큰은
--     그대로 유지된다 — 배포하자마자 전원 로그아웃되지는 않는다.
--
--     ⚠️ 다만 이 배포 이전에 발급된 토큰에는 iat(발급시각) 클레임이 없다. 그 사용자가
--        한 번이라도 로그아웃하면 이후 그 구 토큰은 iat=0 으로 취급돼 거부된다.
--        의도한 동작이다.
--
-- (3) 소셜 로그인 대비 — user_pw 를 NULL 허용으로, provider 컬럼 신설
--     지금은 user_pw 가 NOT NULL 이라 비밀번호 없는 계정은 INSERT 자체가 안 된다.
--     제약을 푸는 대신 CK_USERS_LOCAL_PW 로 "일반 계정이면 비밀번호 필수"를 지킨다.
--     즉 느슨해지는 게 아니라 조건이 붙는 것이다.
--
--     소셜 계정의 user_id 는 '{provider소문자}_{provider_id}' 를 50자로 자른
--     합성값으로 채운다. user_id 유니크 제약을 그대로 두기 위한 규칙이다.
--
--     이 마이그레이션은 스키마와 방어 코드까지만이다. 실제 프로바이더 연동
--     엔드포인트(POST /api/auth/oauth/{provider})는 아직 없다.
-- =====================================================
BEGIN;

-- ----- (1) 활동이력 상세 -----
ALTER TABLE fireguard.user_activity
    ADD COLUMN activity_target_no bigint       NULL,
    ADD COLUMN activity_detail    varchar(255) NULL;

COMMENT ON COLUMN fireguard.user_activity.activity_target_no IS '대상 번호 (화재 이벤트·사용자)';
COMMENT ON COLUMN fireguard.user_activity.activity_detail    IS '활동 요약';

-- ----- (2) 토큰 폐기 기준선 -----
ALTER TABLE fireguard.users ADD COLUMN user_token_valid_from timestamp NULL;

COMMENT ON COLUMN fireguard.users.user_token_valid_from IS '이 시각 이전 발급 토큰 폐기';

-- ----- (3) 소셜 로그인 대비 -----
ALTER TABLE fireguard.users ALTER COLUMN user_pw DROP NOT NULL;

ALTER TABLE fireguard.users
    ADD COLUMN user_provider    varchar(20)  NOT NULL  DEFAULT 'LOCAL',
    ADD COLUMN user_provider_id varchar(191) NULL;

COMMENT ON COLUMN fireguard.users.user_provider    IS '가입 경로';
COMMENT ON COLUMN fireguard.users.user_provider_id IS '소셜 제공자가 준 고유 식별자';

-- 일반 계정은 비밀번호가 반드시 있어야 한다 (NOT NULL 을 푼 대가를 여기서 되받는다)
ALTER TABLE fireguard.users ADD CONSTRAINT CK_USERS_LOCAL_PW
    CHECK (user_provider <> 'LOCAL' OR user_pw IS NOT NULL);

-- 같은 소셜 계정이 두 번 들어오지 않게. 일반 계정은 provider_id 가 NULL 이라
-- 이 인덱스의 대상이 아니다 — 그래서 부분 인덱스여야 한다 (NULL 이 여럿이어도 무방).
CREATE UNIQUE INDEX UQ_USERS_PROVIDER ON fireguard.users (user_provider, user_provider_id)
    WHERE user_provider_id IS NOT NULL;

COMMIT;


-- =====================================================
-- 적용 확인 (선택)
-- =====================================================
-- SELECT column_name, is_nullable, column_default
--   FROM information_schema.columns
--  WHERE table_schema='fireguard' AND table_name='users'
--    AND column_name IN ('user_pw','user_provider','user_provider_id','user_token_valid_from')
--  ORDER BY column_name;
--   → user_pw 는 YES(널 허용), user_provider 는 NO + 기본값 'LOCAL'
--
-- SELECT conname FROM pg_constraint WHERE conname = 'ck_users_local_pw';
--   → 1행
--
-- INSERT INTO fireguard.users (user_id, user_name, user_role, user_status)
-- VALUES ('제약확인', '검증', 'VIEWER', 'ACTIVE');
--   → CK_USERS_LOCAL_PW 위반으로 실패해야 정상이다 (LOCAL 인데 비밀번호가 없다)
