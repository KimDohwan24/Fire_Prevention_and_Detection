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
#
# 이 값은 EVENT_WINDOW_SEC 와 독립이 아니다 — **검출 프레임 레이트에 묶여 있다.**
# 임계값 N 은 창 안에서 프레임 간격이 최대 EVENT_WINDOW_SEC/(N-1) 초일 때까지만
# 도달 가능하다. 2026-08-13 실주행(imgsz=640) 실측 검출 간격은 중앙값 3.62초로
# 창당 최대 16프레임이었고, 그래서 이전 기본값 30 은 산술적으로 도달 불가능했다
# (event 4~7 이 전부 기준미달 처리된 원인).
# N=10 이면 60/9 = 6.67초 간격까지 허용해 실측 대비 약 1.8배 여유가 있다.
#
# **imgsz 나 run_video.py 의 --fps 를 바꾸면 검출 레이트가 달라지므로 이 값을
# 다시 산출해야 한다.** 회귀 테스트는
# tests/test_internal_detections.py::test_threshold_reachable_at_measured_detection_rate.
EVENT_THRESHOLD_FRAMES = int(os.getenv("EVENT_THRESHOLD_FRAMES", "10"))
# 관측 창 길이(초). 창은 최초 감지 시각(event_first_detected_at)에 고정되며
# 이후 검출로 연장되지 않는다 — 미달인 채로 창이 닫히면 기준미달(DISMISSED)
EVENT_WINDOW_SEC = int(os.getenv("EVENT_WINDOW_SEC", "60"))

# 알림 응답 유예 시간(초): alert_deadline_at = alert_sent_at + 이 값
# 마감까지 무응답이면 에스컬레이션이 곧바로 119 신고로 넘어간다.
# 2026-08-13 에 30 → 60 으로 올렸다. 알림을 문자로 받고, 링크를 열고, 취소를
# 누르는 실제 동선이 30초로는 빠듯했기 때문이다.
# ⚠️ 발표 슬라이드 11 타임라인(알림 02:14:08 → 신고 02:14:38)은 30초 기준이라
#    이제 덱과 어긋난다 — 덱을 고칠지는 사람이 판단한다.
# 그래도 분 단위를 넘기지는 않는다. 화재는 초 단위로 번진다.
ALERT_DEADLINE_SEC = int(os.getenv("ALERT_DEADLINE_SEC", "60"))

# 에스컬레이션 스윕 주기(초): 스케줄러가 이 간격으로 run_escalation_tick 을 돌린다.
# 유예 마감 초과가 실제 신고로 이어지기까지 최대 이만큼 늦어지므로,
# 60초 유예에 대해 실제 유예는 60~65초가 된다. ALERT_DEADLINE_SEC 를 줄이면
# 이 값도 같이 줄여야 실제 유예가 의도한 값에서 크게 벗어나지 않는다.
ESCALATION_INTERVAL_SEC = int(os.getenv("ESCALATION_INTERVAL_SEC", "5"))

# 119 신고: 한 기관에 최대 몇 번 전송을 시도하나 (안쪽 루프, report_attempt_count)
MAX_REPORT_ATTEMPTS = int(os.getenv("MAX_REPORT_ATTEMPTS", "4"))
# 119 신고: 기관 endpoint HTTP 전송 타임아웃(초)
REPORT_HTTP_TIMEOUT_SEC = float(os.getenv("REPORT_HTTP_TIMEOUT_SEC", "3"))

# 역지오코딩(카카오 Local) HTTP 타임아웃(초).
# CCTV 등록 요청 안에서 부르므로 사람이 기다리는 시간이다 — 짧게 둔다.
# 실패해도 등록은 진행되고 주소만 NULL 로 남는다.
GEOCODE_HTTP_TIMEOUT_SEC = float(os.getenv("GEOCODE_HTTP_TIMEOUT_SEC", "3"))

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

# ----- 소셜 로그인(OAuth) -----
# 프로바이더별 앱 키. 각 개발자 콘솔에서 발급받아 .env 에 넣는다.
# **키가 없으면 그 프로바이더만 503 OAUTH_NOT_CONFIGURED 로 막힌다** — 서버는 그대로
# 뜨고 나머지 로그인 경로도 살아 있다. 하나도 안 넣은 상태로 배포해도 무방하다.
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
KAKAO_CLIENT_ID = os.getenv("KAKAO_CLIENT_ID", "")
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", "")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")

# ⚠️ 아래 두 주소는 **역할이 다르다.** 이름이 비슷해 자주 헷갈리는데, 바꿔 쓰면
#    증상이 프로바이더의 redirect_uri_mismatch 로만 나타나 원인을 찾기 어렵다.
#      OAUTH_CALLBACK_BASE — 프로바이더가 브라우저를 **되돌려보낼 백엔드 주소**
#                            (프로바이더 콘솔에 등록하는 값이 여기서 나온다)
#      OAUTH_REDIRECT_BASE — 로그인을 끝낸 뒤 **사용자를 보낼 프론트 주소**
#                            (콘솔과는 아무 상관이 없다)

# 프론트 주소. 콜백이 로그인을 마친 브라우저를 여기로 302 한다 —
#   {OAUTH_REDIRECT_BASE}/#access_token=...  또는  /#oauth_error=...
# 프로바이더 콘솔에 등록할 값이 **아니다** (그것은 아래 OAUTH_CALLBACK_BASE 쪽이다).
OAUTH_REDIRECT_BASE = os.getenv("OAUTH_REDIRECT_BASE", "http://localhost:5173")

# 백엔드 자신의 주소. 프로바이더에게 알려줄 콜백 주소를 서버가 여기에 붙여 만든다 —
#   {OAUTH_CALLBACK_BASE}/api/auth/{provider소문자}/callback
# 프로바이더는 브라우저를 프론트가 아니라 **백엔드로** 되돌려보낸다 (프론트는
# window.location.assign('/api/auth/kakao') 로 시작만 시킨다). 그래서 위
# OAUTH_REDIRECT_BASE 와 값이 다르다.
# **여기를 바꾸면 세 콘솔의 등록 URI 도 함께 고쳐야 한다** — 서버가 보내는 값과
# 글자 하나라도 다르면 프로바이더가 redirect_uri_mismatch 로 돌려보낸다.
OAUTH_CALLBACK_BASE = os.getenv("OAUTH_CALLBACK_BASE", "http://localhost:5000")

# 프로바이더 API 호출 타임아웃(초). 사람이 로그인 버튼을 누르고 기다리는 중이라
# 짧게 둔다. 119 신고(REPORT_HTTP_TIMEOUT_SEC)와 값을 나눠 쓰지 않는 이유는
# 저쪽이 사람이 기다리지 않는 백그라운드 전송이라 조정 기준이 다르기 때문이다.
OAUTH_HTTP_TIMEOUT_SEC = float(os.getenv("OAUTH_HTTP_TIMEOUT_SEC", "5"))

APP_PORT = int(os.getenv("APP_PORT", "5000"))

# 검출 프레임/클립 실제 파일이 놓이는 루트 디렉터리.
# 기본값은 프로젝트 루트의 media/ 이고, GET /media/<path> 로 서빙된다
# (event_media.media_url 의 "/media/events/12/frame_001.jpg" 가 곧 이 아래 경로).
# 실행 위치(cwd)에 따라 달라지지 않도록 임포트 시점에 절대경로로 확정한다.
MEDIA_ROOT = str(Path(os.getenv("MEDIA_ROOT") or (PROJECT_ROOT / "media")).resolve())
