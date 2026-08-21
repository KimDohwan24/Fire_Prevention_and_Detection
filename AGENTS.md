# 파이어가드 — 에이전트 지침

CCTV 영상에서 화재를 감지(YOLO)하고, 관리자 알림 → 무응답 시 119 자동 신고·승계까지 하는 프로젝트.
스택: Flask + PostgreSQL(raw SQL) / React(front) / YOLO(ai-model). 브랜치 흐름: dev-Wang → dev.

> 이 파일은 CI 의 에이전트가 읽는다. `.gitignore` 의 `*.md` 규칙에 대한 **의도적 예외**다
> (개인 메모가 아니라 도구가 읽는 설정이라서). 사람이 읽는 문서는 여전히 md 로 만들지 말 것.

## 규칙 1 — 코드가 문서를 이긴다

설계·아키텍처 판단 전에 실제 호출 흐름을 먼저 읽어라. 2026-08-11 에 낡은 문서 문구만 보고
폴링이 필요하다고 오판한 사고가 있었다. 자주 오해되는 지점:

- **119 신고는 동기다.** `back/routes/alert_routes.py` 의 respond 핸들러가
  `report_service.start_report` 를 요청 스레드에서 직접 호출한다. 백그라운드 큐가 아니다.
  최악 지연이 곧 HTTP 응답 지연이다.
- **비동기인 것은 에스컬레이션뿐이다.** APScheduler 가 `ESCALATION_INTERVAL_SEC`(기본 5초)마다
  `run_escalation_tick` 을 돌린다 (`back/app.py`).
- **알림 실발송 채널은 SMS 하나다.** PUSH 는 DB 행일 뿐 실제로 밀어내는 것이 없다.

## 규칙 2 — API 문서의 원본은 하나다

`back/openapi.yaml` 이 유일한 원본이다. Swagger UI(`/api/docs/`) 가 이걸 렌더링하고
`back/tests/test_openapi.py` 가 실제 라우트와 대조한다. 별도 html 명세서를 만들지 마라
(중복 때문에 2026-08-11 삭제했다). 라우트를 바꾸면 이 파일과 `info.version` 을 같이 고쳐라.

## 자주 깨지는 곳

- `report_119` 에 부분 유니크 인덱스가 있어 진행 중(SENDING/ACCEPTED/DISPATCHED) 신고는
  이벤트당 1건만 들어간다. 신고 생성 시 위반(23505) 처리 필수. 이 집합은
  `back/services/report_service.py` 의 `ACTIVE_STATUSES` 와 항상 같아야 한다.
- DB 접근은 raw SQL 이다. 파라미터 바인딩(`%s`) 없이 문자열을 이어붙이면 안 된다.
- 커넥션 풀은 첫 쿼리 때 lazy 로 만들어진다 (`back/db.py`). DB 가 안 떠 있어도 앱은 뜬다.
- `mock-119` 기본 포트는 **8119** 다. 6000 은 크롬이 차단한다.
- DB 접속 정보는 루트 `.env` (깃 제외). 템플릿은 `.env.example`.

## 검증 명령

```bash
# 백엔드 테스트 (fireguard_test DB 자동 생성, 개발 DB 는 안 건드림)
cd back && .venv/Scripts/python -m pytest tests -v

# 프론트
cd front && npm run lint && npm run build
```

## 커밋

- 메시지는 한국어. `feat:` / `fix:` / `refactor:` 접두어를 쓴다.
- **AI 공동작성자 트레일러(`Co-Authored-By: Claude ...`)를 붙이지 마라.**
