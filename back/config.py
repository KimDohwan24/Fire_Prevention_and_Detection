"""환경변수 로드. 루트의 .env 를 읽는다."""
import os
from pathlib import Path

from dotenv import load_dotenv

# back/ 의 한 단계 위 = 프로젝트 루트
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "fireguard")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_EXPIRES_HOURS = int(os.getenv("JWT_EXPIRES_HOURS", "12"))

# AI 모델 → 백엔드 내부 API 인증 키 (X-Internal-Key 헤더로 비교)
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "dev-internal-key")

# 화재 확정 기준: 윈도우 안에서 이 프레임 수만큼 검출이 쌓이면 CONFIRMED
EVENT_THRESHOLD_FRAMES = int(os.getenv("EVENT_THRESHOLD_FRAMES", "30"))
# 마지막 검출로부터 이 시간(초)이 지나면 PENDING 이벤트를 기준미달(DISMISSED) 처리
EVENT_WINDOW_SEC = int(os.getenv("EVENT_WINDOW_SEC", "60"))

# 알림 응답 유예 시간(분): alert_deadline_at = alert_sent_at + 이 값
# 마감까지 무응답이면 에스컬레이션(1차→2차, 2차→119 신고)이 진행된다
ALERT_DEADLINE_MIN = int(os.getenv("ALERT_DEADLINE_MIN", "3"))

# 에스컬레이션 스윕 주기(초): 스케줄러가 이 간격으로 run_escalation_tick 을 돌린다
ESCALATION_INTERVAL_SEC = int(os.getenv("ESCALATION_INTERVAL_SEC", "10"))

# 119 신고: 한 기관에 최대 몇 번 전송을 시도하나 (안쪽 루프, report_attempt_count)
MAX_REPORT_ATTEMPTS = int(os.getenv("MAX_REPORT_ATTEMPTS", "4"))
# 119 신고: 기관 endpoint HTTP 전송 타임아웃(초)
REPORT_HTTP_TIMEOUT_SEC = float(os.getenv("REPORT_HTTP_TIMEOUT_SEC", "3"))

APP_PORT = int(os.getenv("APP_PORT", "5000"))

# 검출 프레임/클립 실제 파일이 놓이는 루트 디렉터리.
# 기본값은 프로젝트 루트의 media/ 이고, GET /media/<path> 로 서빙된다
# (event_media.media_url 의 "/media/events/12/frame_001.jpg" 가 곧 이 아래 경로).
# 실행 위치(cwd)에 따라 달라지지 않도록 임포트 시점에 절대경로로 확정한다.
MEDIA_ROOT = str(Path(os.getenv("MEDIA_ROOT") or (PROJECT_ROOT / "media")).resolve())
