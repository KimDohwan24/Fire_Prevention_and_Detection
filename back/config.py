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

# 소방서(119) → 백엔드 출동 통지 인증 키 (X-Agency-Key 헤더로 비교)
# INTERNAL_API_KEY 와 나눠 쓴다 — 하나가 새면 AI 검출 수집 경로까지 함께 열린다.
AGENCY_CALLBACK_KEY = os.getenv("AGENCY_CALLBACK_KEY", "dev-agency-key")

# ----- 시크릿 가드: 위 세 값이 기본값이면 서버를 띄우지 않는다 -----
#
# 위 세 줄의 `os.getenv(이름, "dev-...")` 는 **조용하다.** `.env` 에 값이 없으면
# 경고 한 줄 없이 저 문자열로 돌아간다. 그런데 JWT_SECRET 하나가
#   로그인 토큰 서명(auth.py)          OAuth state HMAC(services/oauth_provider.py)
#   계정찾기 인증코드(services/account_recovery.py)  텔레그램 연동코드(services/telegram_link.py)
# 를 전부 떠받친다. 소스코드에 적힌 공개 문자열이 서명 키가 되는 순간, 공격자는
# 서버를 거치지 않고 자기 자리에서 `user_role: ADMIN` 짜리 토큰을 만들어 넣을 수
# 있다 — 서명이 실제로 맞으므로 jwt.decode 가 통과시킨다. 비밀번호도 로그인도
# 필요 없다. 토큰 폐기 검사(auth._assert_not_revoked)도 못 막는다: 그건 '훔친 진짜
# 토큰'용이고, 위조 토큰은 iat 를 지금 시각으로 넣으면 그만이다.
#
# **잘못 뜬 서버보다 안 뜨는 서버가 낫다.** 안 뜨면 사람이 알아채지만, 잘못 뜬 것은
# 아무도 모른다. 그래서 조용한 기본값을 시끄러운 실패로 바꾼다.
#
# 기본값을 지우고 여기서 바로 raise 하지 않는 이유: config 는 임포트만 해도
# 평가되는 모듈이라, 서버와 무관한 도구(스키마 점검 스크립트 등)까지 임포트
# 순간에 죽는다. 판정은 값으로 두고 **차단은 앱 팩토리(app.create_app)에서** 한다.
INSECURE_DEFAULTS = {
    "JWT_SECRET": "dev-secret-change-me",
    "INTERNAL_API_KEY": "dev-internal-key",
    "AGENCY_CALLBACK_KEY": "dev-agency-key",
}


def insecure_secret_names(values: dict | None = None) -> list[str]:
    """설정되지 않았거나 개발용 기본값 그대로인 시크릿 이름들. 정상이면 빈 리스트.

    `values` 를 주면 그것을, 안 주면 이 모듈의 실제 설정값을 본다 (테스트용 구멍이
    아니라, 가드 자체를 서버 기동 없이 검증하기 위한 입력 분리다).

    빈 문자열도 '미설정'으로 본다 — `.env.example` 을 복사해 만든 `.env` 는
    `JWT_SECRET=` 처럼 **빈 값**이고, 그러면 os.getenv 는 그것을 '값 있음'으로
    보고 위의 기본값조차 쓰지 않는다. 서명 키가 "" 가 되는 쪽이 더 나쁘다.
    내부 키가 "" 면 `X-Internal-Key:` 를 빈 값으로 보낸 요청까지 통과한다
    (auth.internal_key_required 는 헤더 값과 이 값을 그대로 비교한다).
    """
    source = globals() if values is None else values
    return [name for name, default in INSECURE_DEFAULTS.items()
            if (source.get(name) or "").strip() in ("", default)]


def assert_secrets_configured(values: dict | None = None) -> None:
    """시크릿이 하나라도 기본값/미설정이면 RuntimeError. app.create_app 이 부른다.

    문제를 **한 번에 전부** 나열한다 — 하나 고쳐 재기동, 또 하나 고쳐 재기동을
    반복하게 만들지 않으려는 것이다.
    """
    bad = insecure_secret_names(values)
    if not bad:
        return
    raise RuntimeError(
        "보안 설정이 비어 있어 서버를 띄우지 않습니다: " + ", ".join(bad) + "\n"
        "  이 값들은 로그인 토큰 서명과 내부 API 인증에 쓰이는 시크릿입니다.\n"
        "  기본값 그대로 두면 누구나 관리자 토큰을 위조할 수 있습니다.\n"
        "  루트 .env 에 각각 임의의 값을 넣어 주세요. 값 만들기:\n"
        "    python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )

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
#   1 = 요청 한 번·응답 한 번으로 끝낸다 — 재전송 없음. **기본값**
#   2 이상 = 재시도할 값어치가 있는 실패(응답 타임아웃·5xx)에 한해 그 횟수까지 재전송
# 2026-08-24 시연 단순화로 기본을 1 로 두었다. REPORT_MAX_AGENCIES=1(기관 승계
# 해제)과 짝이다 — 119 와 주고받는 것을 한 왕복으로 보여주는 것이 시연 목표라,
# 재전송이 남아 있으면 접수 콘솔에 같은 신고가 여러 줄로 찍혀 그림이 흐려진다.
# 재전송 코드는 그대로 남아 있어 .env 에 MAX_REPORT_ATTEMPTS=4 만 넣으면 되돌아간다.
MAX_REPORT_ATTEMPTS = int(os.getenv("MAX_REPORT_ATTEMPTS", "1"))
# 119 신고: 기관 endpoint HTTP 전송 타임아웃(초)
REPORT_HTTP_TIMEOUT_SEC = float(os.getenv("REPORT_HTTP_TIMEOUT_SEC", "3"))

# 119 신고에서 시도할 최대 기관 수 (가까운 순).
#   1 = 가장 가까운 한 곳에만 신고하고 끝낸다 — 기관 승계 없음. **기본값**
#   0 = 후보 전체를 가까운 순서대로 시도한다 — 원래의 승계 동작
# 2026-08-21 시연 단순화로 기본을 1 로 두었다. 승계 코드는 그대로 남아 있어
# .env 에 REPORT_MAX_AGENCIES=0 만 넣으면 예전 동작으로 되돌아간다.
REPORT_MAX_AGENCIES = int(os.getenv("REPORT_MAX_AGENCIES", "1"))

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

# ----- 생활안전지도(safemap.go.kr) 소방시설 개방 데이터 -----
# 전국 소방서·119안전센터 목록(이름·주소·전화·좌표)을 받아 agency 테이블을 채운다.
# 앱이 돌면서 부르는 값이 아니다 — services/agencies_safemap.py 만 이 키를 쓴다.
# 갱신주기가 1년이라 요청마다 부를 이유가 없고, 119 신고는 동기 경로라 신고 순간에
# 외부 API 를 부르면 그 지연이 그대로 HTTP 응답 지연이 된다 (services/geocode.py 와 같은 판단).
# 발급: https://www.safemap.go.kr 개발자센터 → 오픈API 인증키 발급
# .env 에서의 항목 이름은 `AGENCY` 다 (.env.example 과 같은 이름).
SAFEMAP_SERVICE_KEY = os.getenv("AGENCY", "")
SAFEMAP_API_URL = os.getenv("SAFEMAP_API_URL", "https://www.safemap.go.kr/openapi2/IF_0038")

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

# 이 백엔드의 외부 공개 주소. 119 신고 페이로드의 callback_url 을 여기에 붙여 만든다 —
#   {PUBLIC_BASE_URL}/api/reports/dispatch
# 소방서가 출동 통지를 되쏘는 곳이라, 상대가 닿을 수 있는 주소여야 한다.
# 시연은 같은 PC 라 localhost 로 충분하고, 다른 PC 에서 접속시키려면 LAN IP 를 넣는다.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:5000")

APP_PORT = int(os.getenv("APP_PORT", "5000"))

# 검출 프레임/클립 실제 파일이 놓이는 루트 디렉터리.
# 기본값은 프로젝트 루트의 media/ 이고, GET /media/<path> 로 서빙된다
# (event_media.media_url 의 "/media/events/12/frame_001.jpg" 가 곧 이 아래 경로).
# 실행 위치(cwd)에 따라 달라지지 않도록 임포트 시점에 절대경로로 확정한다.
MEDIA_ROOT = str(Path(os.getenv("MEDIA_ROOT") or (PROJECT_ROOT / "media")).resolve())

# ── 로깅 ────────────────────────────────────────────────────────────────────
# 서비스 코드는 logging.getLogger("fireguard.*") 로 로그를 남기기만 하고,
# 어디에 어떤 모양으로 쓸지는 app.setup_logging() 이 한 곳에서 정한다.
# 남기는 쪽 44곳은 이 값들과 무관하게 그대로다.
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# 로그 파일이 쌓이는 곳. 기본은 back/logs/ 이고 .gitignore 의 logs/ 에 걸린다.
# MEDIA_ROOT 와 달리 프로젝트 루트가 아니라 back/ 아래인 이유는 이게 백엔드
# 서버의 산출물이라서다 (ai-model 은 자기 로그를 따로 남긴다).
LOG_DIR = str(Path(os.getenv("LOG_DIR") or (Path(__file__).resolve().parent / "logs")))

# 하루치씩 끊어 며칠분을 남길지. 자정마다 fireguard.log.2026-08-22 로 넘어간다.
LOG_BACKUP_DAYS = int(os.getenv("LOG_BACKUP_DAYS", "14"))

# ----- 텔레그램 알림 (화재 알림 발송 + 버튼 응답 수신) -----
# 화재 알림을 사용자 휴대폰으로 보내고, 알림에 붙은 버튼으로 '확인/취소'를 되받는 채널.
#
# **왜 SMS 가 아니라 텔레그램인가** (2026-08-22 결정):
#   문자·알림톡은 건당 과금 이전에 발신번호 사전등록(통신사 본인·사업자 확인)이
#   법적 전제고, 알림톡은 사업자등록증이 있어야 시작조차 못 한다. 더 결정적인 건
#   **회신을 받을 수 없다**는 점이다 — 수신 번호는 월정액 임대 영역이라 무료가 없다.
#   우리 알림은 유예 안에 '확인/취소'를 되받아야 의미가 있으므로(services/escalation.py)
#   단방향 채널로는 기능 자체가 성립하지 않는다.
#   텔레그램은 무료·무제한이고 인라인 버튼으로 회신을 받으며, 롱폴링 방식이라
#   공인 IP·HTTPS 웹훅이 필요 없다 — 로컬 시연 구성 그대로 돈다.
#   상용 전환 시에는 services/sms.py 를 실제 발송으로 갈아끼우면 된다. 알림 발송은
#   services/notify.py 한 곳을 지나므로 두 채널이 공존해도 호출부는 바뀌지 않는다.
#
# 발급: 텔레그램에서 @BotFather 에게 /newbot → 토큰과 봇 이름을 받아 .env 에 넣는다.
# **비어 있으면 텔레그램 발송·폴링이 통째로 꺼지고 기존 모의 SMS 로만 나간다** —
# 토큰 없이도 서버는 그대로 뜨고 나머지 경로는 전부 살아 있다.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# 봇 사용자명(@ 없이). 마이페이지가 t.me/<이름>?start=<코드> 딥링크를 만들 때 쓴다.
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")
# Bot API HTTP 타임아웃(초). 알림 발송은 확정 경로 안에서 부르므로 짧게 둔다.
# 롱폴링(getUpdates)에서는 이 값이 **여유분**으로 쓰인다 — services/telegram.py 의
# _http_timeout 참고. 서버가 25초 붙잡는 요청에 5초 타임아웃을 걸면 매번 터진다.
TELEGRAM_HTTP_TIMEOUT_SEC = float(os.getenv("TELEGRAM_HTTP_TIMEOUT_SEC", "5"))

# 버튼 응답을 받아오는 방식은 **롱폴링**이다. 이 값은 텔레그램 서버가 응답을 붙잡고
# 기다려 주는 시간(초)이지 폴링 '주기'가 아니다 — 주기라는 개념 자체가 없어졌다.
#
# 2026-08-22 이전에는 timeout=0 짧은 폴링을 APScheduler 잡으로 2초마다 돌렸고,
# 로그가 `skipped: maximum number of running instances reached (1)` 로 계속 더러웠다.
# 원인을 실측으로 잡았다 (api.telegram.org, 왕복은 235ms 로 고정):
#   - getMe 는 몇 번을 불러도 235ms. 망도, requests.Session 재사용도 멀쩡했다.
#   - getUpdates 는 **직전 getUpdates 로부터 3.0초 안에 도착하면 서버가 정확히
#     3.000초 붙잡았다가** 빈 배열을 돌려준다. 호출 간격을 바꿔 가며 확인:
#       간격 2.74초 → 두 번에 한 번 3초 홀드,  3.04초 → 0/5 회 (한 번도 안 걸림).
#   - 그래서 2초 주기는 원리상 지킬 수 없다. 틱이 0.24초 / 3.24초로 번갈아 걸리고
#     6초마다 한 번씩 잡이 통째로 건너뛰어진다. '틱 1회가 6초'의 정체가 이것이다.
# 롱폴링은 이 바닥에 아예 닿지 않는다 — timeout=25 로 쉬지 않고 4회 연속 호출해도
# 매번 25.00초 정확히였고 얹히는 지연은 0이었다.
#
# 25초로 둔 이유: 3초 바닥에서 충분히 멀고, 중간 프록시·NAT 의 유휴 커넥션 정리
# 시간(대개 60초 이상)보다는 짧아 끊길 일이 없다. **이 값을 줄여도 버튼 반응이
# 빨라지지 않는다** — 업데이트가 생기면 서버가 기다림을 끊고 곧바로 돌려주는 것이
# 롱폴링의 계약이라, 반응 속도는 이 값과 무관하고 빈 요청 수만 늘어난다.
TELEGRAM_LONG_POLL_SEC = int(os.getenv("TELEGRAM_LONG_POLL_SEC", "25"))
