"""환경변수 로드. 루트의 .env 를 읽는다."""
import os
from pathlib import Path

from dotenv import load_dotenv

# back/ 의 한 단계 위 = 프로젝트 루트
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _env_bool(name: str, default: bool) -> bool:
    """"false"/"0"/"no"/"off"(대소문자 무관, 앞뒤 공백 무시)만 False 로 본다."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() not in ("false", "0", "no", "off")


DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "fireguard")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_EXPIRES_HOURS = int(os.getenv("JWT_EXPIRES_HOURS", "12"))

# AI 모델 → 백엔드 내부 API 인증 키 (X-Internal-Key 헤더로 비교)
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "dev-internal-key")

# 화재 확정 기준: 관측 창 안에서 이 프레임 수만큼 검출이 쌓이면 CONFIRMED
EVENT_THRESHOLD_FRAMES = int(os.getenv("EVENT_THRESHOLD_FRAMES", "30"))
# 관측 창 길이(초). 창은 최초 감지 시각(event_first_detected_at)에 고정되며
# 이후 검출로 연장되지 않는다 — 미달인 채로 창이 닫히면 기준미달(DISMISSED)
EVENT_WINDOW_SEC = int(os.getenv("EVENT_WINDOW_SEC", "60"))

# 알림 응답 유예 시간(초): alert_deadline_at = alert_sent_at + 이 값
# 마감까지 무응답이면 에스컬레이션이 곧바로 119 신고로 넘어간다.
# 기본 30초는 발표 슬라이드 11 타임라인(알림 02:14:08 → 신고 02:14:38) 기준.
# 화재는 초 단위로 번지므로 유예를 분 단위로 잡을 여유가 없다.
ALERT_DEADLINE_SEC = int(os.getenv("ALERT_DEADLINE_SEC", "30"))

# 에스컬레이션 스윕 주기(초): 스케줄러가 이 간격으로 run_escalation_tick 을 돌린다
ESCALATION_INTERVAL_SEC = int(os.getenv("ESCALATION_INTERVAL_SEC", "10"))

# 119 신고: 한 기관에 최대 몇 번 전송을 시도하나 (안쪽 루프, report_attempt_count)
MAX_REPORT_ATTEMPTS = int(os.getenv("MAX_REPORT_ATTEMPTS", "4"))
# 119 신고: 기관 endpoint HTTP 전송 타임아웃(초)
REPORT_HTTP_TIMEOUT_SEC = float(os.getenv("REPORT_HTTP_TIMEOUT_SEC", "3"))

# ----- 국가교통정보센터(ITS) CCTV 개방 데이터 -----
# ITS 가 주는 스트림 주소에는 시간 제한 토큰이 박혀 있어 저장해 두면 만료된다.
# 그래서 카메라 조회 시마다 최신 주소를 받아 이름이 같은 행을 갈아끼운다.
CCTV_API_KEY = os.getenv("CCTV_API_KEY", "")
ITS_API_URL = os.getenv("ITS_API_URL", "https://openapi.its.go.kr:9443/cctvInfo")
# 조회할 도로 유형: ex=고속도로, its=국도 (쉼표로 구분)
ITS_ROAD_TYPES = [t.strip() for t in os.getenv("ITS_ROAD_TYPES", "ex,its").split(",")
                  if t.strip()]
# 같은 영역 조회 결과를 재사용하는 시간(초)
CCTV_URL_TTL_SEC = int(os.getenv("CCTV_URL_TTL_SEC", "300"))
# 갱신 기능 스위치 — 끄면 DB 에 저장된 주소를 그대로 내려준다
ITS_REFRESH_ENABLED = _env_bool("ITS_REFRESH_ENABLED", True)

APP_PORT = int(os.getenv("APP_PORT", "5000"))

# 검출 프레임/클립 실제 파일이 놓이는 루트 디렉터리.
# 기본값은 프로젝트 루트의 media/ 이고, GET /media/<path> 로 서빙된다
# (event_media.media_url 의 "/media/events/12/frame_001.jpg" 가 곧 이 아래 경로).
# 실행 위치(cwd)에 따라 달라지지 않도록 임포트 시점에 절대경로로 확정한다.
MEDIA_ROOT = str(Path(os.getenv("MEDIA_ROOT") or (PROJECT_ROOT / "media")).resolve())
