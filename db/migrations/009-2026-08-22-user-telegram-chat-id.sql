-- =====================================================
-- 2026-08-22  사용자에 텔레그램 대화방 컬럼
--
-- 적용 대상: 이 날짜 이전에 db/schema.sql 로 만든 기존 개발 DB.
-- 새로 만드는 DB 는 db/schema.sql 하나면 되고 이 파일은 필요 없다.
--
-- 실행:
--   psql -U postgres -d fireguard -f db/migrations/009-2026-08-22-user-telegram-chat-id.sql
--   (또는 pgAdmin Query Tool 에 통째로 붙여넣기)
--
-- 전체가 한 트랜잭션이다. 중간에 실패하면 아무것도 반영되지 않는다.
-- 재실행해도 안전하다 (IF NOT EXISTS).
--
-- 무엇이 바뀌나:
--   1) users 에 컬럼 1개 — 화재 알림을 받을 텔레그램 대화방(chat_id)
--   2) 그 컬럼에 부분 유니크 인덱스
--
-- 왜 필요한가:
--   화재 알림은 유예(ALERT_DEADLINE_SEC) 안에 사용자의 '확인/취소'를 되받아야
--   의미가 있다 — 무응답이면 119 로 넘어가기 때문이다(services/escalation.py).
--   그런데 문자·알림톡은 **회신을 받을 수 없다.** 수신 번호는 월정액 임대 영역이라
--   무료 경로가 없고, 발송조차 발신번호 사전등록(통신사 본인·사업자 확인)이 전제다.
--   알림톡은 사업자등록증이 있어야 시작조차 못 한다.
--
--   텔레그램 봇은 무료·무제한이고 알림에 인라인 버튼을 붙여 회신을 받는다.
--   롱폴링이라 공인 IP·HTTPS 웹훅도 필요 없어 로컬 시연 구성 그대로 돈다.
--   그래서 "누구의 텔레그램으로 보낼지"를 사용자 행에 들고 있어야 한다.
--
--   저장하는 값은 chat_id 하나뿐이다. 연동 코드는 저장하지 않는다 —
--   services/telegram_link.py 가 HMAC 으로 매번 계산해 대조한다
--   (services/account_recovery.py 와 같은 방식). 그래서 컬럼이 하나로 끝난다.
--
-- 왜 유니크인가:
--   봇이 받는 것은 chat_id 뿐이다. 같은 대화방이 두 사용자에 걸쳐 있으면 버튼을
--   누른 사람이 누구인지 결정할 수 없다. NULL(미연동)은 여럿이어도 되므로 부분
--   인덱스로 둔다.
--
-- 되돌리기:
--   DROP INDEX IF EXISTS fireguard.UX_users_telegram_chat_id;
--   ALTER TABLE fireguard.users DROP COLUMN IF EXISTS user_telegram_chat_id;
--   (컬럼이 없으면 텔레그램 연동만 꺼지고 나머지 경로는 그대로 돈다)
-- =====================================================

BEGIN;

-- 1) 컬럼 — 텔레그램 chat_id 는 int32 를 넘을 수 있어 bigint 다
ALTER TABLE fireguard.users
    ADD COLUMN IF NOT EXISTS user_telegram_chat_id bigint NULL;

-- 2) 대화방 하나는 사용자 한 명에게만
CREATE UNIQUE INDEX IF NOT EXISTS UX_users_telegram_chat_id
    ON fireguard.users (user_telegram_chat_id)
    WHERE user_telegram_chat_id IS NOT NULL;

COMMIT;
