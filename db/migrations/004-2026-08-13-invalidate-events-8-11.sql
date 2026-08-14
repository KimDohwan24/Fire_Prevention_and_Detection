-- =====================================================
-- 004  2026-08-13  고정 창을 위반하고 확정된 이벤트 8·11 무효 처리
--
-- 구조 변경이 아니라 **데이터 교정**이다. db/schema.sql 은 바뀌지 않는다.
-- 새 DB 나 다른 개발 DB 에서는 조건에 걸리는 행이 없어 아무 일도 일어나지 않는다.
-- =====================================================
--
-- ■ 무엇이 잘못됐나
--     판정 규칙(발표 슬라이드 10)은 최초 감지 시각에 고정된 60초 창 안에서
--     임계 프레임 수를 채워야 CONFIRMED 다. 그런데 2026-08-13 주행에서
--
--       event 8  : 30프레임을 09:41:10 ~ 09:43:38, 즉 147.8초에 걸쳐 쌓고 확정
--       event 11 : 임계값이 10 으로 바뀐 뒤 확정 (같은 주행의 event 10 은 30)
--
--     둘 다 진행 중인 이벤트가 있는 상태에서 설정을 바꿔 백엔드를 재시작한 결과다.
--     당시 코드는 임계값만 이벤트 행에 박제하고 창 길이는 매 프레임 config 에서
--     읽었기 때문에, 재시작으로 판정 기준이 반쪽만 바뀌었다.
--     (같은 프레임 시각을 코드로 재생하면 16/11/3 세 이벤트로 쪼개지고 확정되지 않는다.
--      회귀 테스트: back/tests/test_internal_detections.py
--                   ::test_event8_replay_stays_within_window)
--
-- ■ 왜 지우지 않나
--     두 이벤트에는 알림 2건(PUSH/SMS)과 119 신고 2건이 딸려 있고 실제로
--     ACCEPTED 까지 갔다(R-000001, R-000002). 지우면 에스컬레이션 파이프라인이
--     끝까지 동작했다는 유일한 실증 기록도 함께 사라진다.
--     확정 판정만 잘못됐지 그 뒤 경로는 정상 동작했다.
--
-- ■ event_is_test 로 충분한가
--     그렇다. 이 플래그 하나로 목록 노출(routes/event_routes.py),
--     알림 생성(services/alert_service.py), 에스컬레이션(services/escalation.py),
--     119 신고(services/report_service.py)가 모두 차단된다.
--     이미 발송된 알림·신고 행은 기록으로 남는다.
--
-- ■ 되돌리려면
--     UPDATE fireguard.fire_event SET event_is_test = false
--      WHERE event_no IN (8, 11);
-- =====================================================

UPDATE fireguard.fire_event
   SET event_is_test = true
 WHERE event_no IN (8, 11)
   AND event_status = 'CONFIRMED'
   AND event_first_detected_at::date = DATE '2026-08-13';

-- 적용 확인 — 8·11 만 true 여야 한다
-- SELECT event_no, event_status, event_is_test FROM fireguard.fire_event ORDER BY event_no;
