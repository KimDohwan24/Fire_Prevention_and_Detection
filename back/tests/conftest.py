"""테스트 인프라.

- 테스트 전용 DB `fireguard_test` 를 세션 시작 때 새로 만들고 db/schema.sql 을 실행한다.
- 각 테스트 전에 모든 테이블을 비우고 기준 데이터를 다시 심는다.
- 개발 DB(firegaurd)는 절대 건드리지 않는다.
"""
import os
from pathlib import Path

# back 모듈 import 전에 DB 이름을 오버라이드한다
# (config.load_dotenv 는 기존 환경변수를 덮어쓰지 않는다)
os.environ["DB_NAME"] = "fireguard_test"

import bcrypt
import psycopg2
import pytest

import config
import db
from app import create_app
from auth import issue_token

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "db" / "schema.sql"

# 테스트 계정 공통 비밀번호 (bcrypt 는 느려서 해시를 한 번만 만든다)
# 비밀번호 작성규칙(3종 조합 8자 이상 등)을 만족하는 값이어야 한다
PW = "Guard#2026"
PW_HASH = bcrypt.hashpw(PW.encode(), bcrypt.gensalt(rounds=4)).decode()

TABLES = ["user_activity", "report_log", "report_119", "alert", "event_media",
          "fire_event", "cctv", "agency", "users"]


def _admin_conn(dbname: str):
    conn = psycopg2.connect(
        host=config.DB_HOST, port=config.DB_PORT, dbname=dbname,
        user=config.DB_USER, password=config.DB_PASSWORD,
    )
    conn.autocommit = True
    return conn


@pytest.fixture(scope="session", autouse=True)
def _test_db():
    """fireguard_test DB 를 새로 만들고 스키마를 깐다."""
    assert config.DB_NAME == "fireguard_test", "테스트가 개발 DB 를 바라보고 있음!"

    conn = _admin_conn("postgres")
    with conn.cursor() as cur:
        cur.execute("DROP DATABASE IF EXISTS fireguard_test WITH (FORCE)")
        cur.execute("CREATE DATABASE fireguard_test")
    conn.close()

    conn = _admin_conn("fireguard_test")
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.close()
    yield


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def seed(_test_db):
    """매 테스트 전: 전부 비우고 기준 데이터를 심는다."""
    with db.get_cursor(commit=True) as cur:
        cur.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")
        cur.execute(
            """
            INSERT INTO users (user_id, user_pw, user_name, user_email, user_phone,
                               user_role, user_status) VALUES
            ('admin01',  %(pw)s, '관리자',   'admin@fg.kr',  '01011111111', 'ADMIN',  'ACTIVE'),
            ('viewer01', %(pw)s, '조회자',   'viewer@fg.kr', '01022222222', 'VIEWER', 'ACTIVE'),
            ('susp01',   %(pw)s, '정지자',   NULL, NULL, 'ADMIN', 'SUSPENDED'),
            ('gone01',   %(pw)s, '탈퇴자',   NULL, NULL, 'ADMIN', 'WITHDRAWN')
            """,
            {"pw": PW_HASH},
        )
        # 1번은 주소 있음 · 2번은 NULL 로 갈라 둔다 — 119 신고가 주소를 못 구했을 때의
        # 폴백 경로를 검증하려면 주소가 비어 있는 카메라가 기준 데이터에 있어야 한다
        # (컬럼 추가 이전에 등록된 카메라가 실제로 그 상태다).
        cur.execute(
            """
            INSERT INTO cctv (user_no, cctv_name, cctv_location, cctv_address,
                              cctv_lat, cctv_lng,
                              cctv_stream_url, cctv_width, cctv_height, cctv_status) VALUES
            (1, '정문 카메라', '본관 정문 앞', '서울특별시 중구 세종대로 110',
             37.5665000, 126.9780000,
             'http://192.168.0.10:8080/live/cam1.m3u8', 1920, 1080, 'ACTIVE'),
            (1, '후문 카메라', '본관 후문',    NULL,
             37.5670000, 126.9790000,
             'http://192.168.0.11:8080/live/cam2.m3u8', 1280, 720, 'INACTIVE')
            """
        )
        cur.execute(
            """
            INSERT INTO agency (agency_name, agency_lat, agency_lng, agency_endpoint) VALUES
            ('종로소방서', 37.5720000, 126.9794000, 'http://localhost:6000/report'),
            ('중부소방서', 37.5610000, 126.9950000, 'http://localhost:6000/report')
            """
        )
    yield


class _FakeReportResponse:
    """requests.Response 대역 — 2xx + external_id 본문 흉내."""
    status_code = 200

    def json(self):
        return {"external_id": "MOCK-OK"}


@pytest.fixture(autouse=True)
def _agency_takeover_on(monkeypatch):
    """테스트는 기관 승계가 켜진 상태를 기본으로 한다.

    운영 기본값은 REPORT_MAX_AGENCIES=1 이다 — 가장 가까운 한 곳에만 신고하고
    끝낸다(2026-08-21 시연 단순화). 하지만 승계 구현은 그대로 살아 있고 .env 한
    줄(REPORT_MAX_AGENCIES=0)로 되살아나므로, 그 경로가 썩지 않게 하려면 테스트는
    승계가 도는 상태를 봐야 한다.

    운영 기본값 자체(승계 없음)는 test_report_service.py 의 전용 테스트 두 개가
    REPORT_MAX_AGENCIES 를 1 로 되돌려 따로 검증한다.
    """
    monkeypatch.setattr(config, "REPORT_MAX_AGENCIES", 0)


@pytest.fixture(autouse=True)
def _no_real_report_http(monkeypatch):
    """전역 가드: 어떤 테스트도 실제 119 신고 HTTP 를 보내지 않는다.

    알림 READ 응답이 report_service.start_report 를 부르므로, 스텁이 없으면
    무관한 테스트가 seed 기관 endpoint(localhost:6000)로 실제 접속을 시도하며
    재시도×타임아웃만큼 느려진다. 기본은 '항상 성공' 스텁 — 특정 실패 시나리오가
    필요한 테스트는 자기 monkeypatch 로 _post_report 를 다시 덮어쓰면 된다
    (테스트 본문의 setattr 가 나중에 적용되므로 이 스텁을 이긴다).
    """
    monkeypatch.setattr(
        "services.report_service._post_report",
        lambda endpoint, payload: _FakeReportResponse(),
    )
    yield


# ITS(국가교통정보센터) 정상 응답 대역 — 실제 응답과 같은 키 구성.
# 이름을 일부러 시드 카메라('정문 카메라'/'후문 카메라')와 다르게 둬서,
# 기본 상태에서는 어떤 테스트의 저장된 스트림 주소도 바뀌지 않게 한다.
ITS_SAMPLE_PAYLOAD = {
    "response": {
        "coordtype": 1,
        "data": [
            {
                "roadsectionid": "", "coordx": 127.1058, "coordy": 37.3855,
                "cctvresolution": "", "filecreatetime": "",
                "cctvtype": 1, "cctvformat": "HLS",
                "cctvname": "[경부선] 판교분기점",
                "cctvurl": "http://cctvsec.example/1?wmsAuthSign=CANNED-A",
            },
            {
                "roadsectionid": "", "coordx": 126.9012, "coordy": 37.4821,
                "cctvresolution": "", "filecreatetime": "",
                "cctvtype": 1, "cctvformat": "HLS",
                "cctvname": "[서해안선] 금천IC",
                "cctvurl": "http://cctvsec.example/2?wmsAuthSign=CANNED-B",
            },
        ],
    }
}


@pytest.fixture(autouse=True)
def _no_real_its_http(monkeypatch):
    """전역 가드: 어떤 테스트도 실제 ITS 오픈 API 를 호출하지 않는다.

    카메라 조회(GET /api/cctvs 등)가 스트림 주소 갱신을 부르므로, 스텁이 없으면
    무관한 테스트가 openapi.its.go.kr 로 실제 접속을 시도하며 느려지고
    (키 유무·망 상태에 따라) 결과도 흔들린다. 기본은 '시드와 이름이 겹치지 않는
    정상 응답' 스텁 — 매칭/실패 시나리오가 필요한 테스트는 자기 monkeypatch 로
    _get 을 다시 덮어쓰면 된다 (테스트 본문의 setattr 가 나중에 적용되므로 이김).
    모듈 TTL 캐시도 테스트 간에 새로 비운다.
    """
    from services import its_cctv

    its_cctv.clear_cache()
    monkeypatch.setattr("services.its_cctv._get", lambda params: ITS_SAMPLE_PAYLOAD)
    yield
    its_cctv.clear_cache()


@pytest.fixture(autouse=True)
def _no_real_geocode_http(request, monkeypatch):
    """전역 가드: 어떤 테스트도 실제 카카오 Local API 를 부르지 않는다.

    CCTV 등록 경로가 역지오코딩을 호출하므로, 스텁이 없으면 무관한 테스트가
    매번 외부로 나가며 느려지고 네트워크 상태에 따라 깜빡인다. 기본은 '주소를
    못 찾음(None)' — 주소가 필요한 테스트는 자기 monkeypatch 로 덮어쓴다
    (테스트 본문의 setattr 가 나중에 적용되므로 이 스텁을 이긴다).

    앞의 두 가드와 달리 HTTP 함수가 아니라 reverse_geocode 를 통째로 바꾼다.
    geocode 모듈은 requests 를 모듈째 참조하므로 services.geocode.requests.get 을
    덮으면 requests.get 이 프로세스 전역에서 바뀌어, 진짜 HTTP 를 쓰는 다른
    테스트(mock-119 연동)까지 이 대역을 받게 된다.

    대신 함수를 바꾸면 그 함수 자체를 검증하는 tests/test_geocode.py 가 자기
    대역 대신 이 스텁을 보게 되므로 그 파일만 뺀다 — 그 파일은 이미 requests
    단에서 스스로 막고 있어 실제 호출이 나갈 일이 없다.
    """
    if request.module.__name__.rsplit(".", 1)[-1] == "test_geocode":
        yield
        return

    monkeypatch.setattr("services.geocode.reverse_geocode", lambda lat, lng: None)
    yield


# ---------- 인증 헬퍼 ----------

def _headers(user_no, user_id, role):
    token = issue_token({"user_no": user_no, "user_id": user_id, "user_role": role})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers():
    return _headers(1, "admin01", "ADMIN")


@pytest.fixture()
def viewer_headers():
    return _headers(2, "viewer01", "VIEWER")


# ---------- 데이터 헬퍼 ----------

def make_social_user(user_id="google_1001", provider="GOOGLE", provider_id="1001",
                     name="소셜사용자", role="VIEWER", status="ACTIVE"):
    """비밀번호가 NULL 인 소셜 계정 1명을 만든다.

    기준 데이터에 넣지 않고 헬퍼로 둔 이유: 사용자 수를 세는 기존 테스트
    (test_users.py 의 total_count == 4)가 전부 깨지기 때문이다. 소셜 계정이
    필요한 테스트만 부르면 된다.
    """
    row = db.execute_returning(
        """
        INSERT INTO users (user_id, user_pw, user_name, user_role, user_status,
                           user_provider, user_provider_id)
        VALUES (%s, NULL, %s, %s, %s, %s, %s)
        RETURNING user_no
        """,
        (user_id, name, role, status, provider, provider_id),
    )
    return row["user_no"]


# ---------- 데이터 헬퍼 (이벤트 계열 테스트에서 사용) ----------

def make_event(cctv_no=1, status="CONFIRMED", event_class="FLAME",
               confidence=0.9123, is_test=False, detected_at="2026-08-08 14:30:00"):
    row = db.execute_returning(
        """
        INSERT INTO fire_event (cctv_no, event_status, event_class,
                                event_first_detected_at, event_detected_at,
                                event_detected_frames, event_threshold_frames,
                                event_confidence, event_is_test)
        VALUES (%s, %s, %s, %s::timestamp - interval '10 seconds', %s,
                32, 30, %s, %s)
        RETURNING event_no
        """,
        (cctv_no, status, event_class, detected_at, detected_at, confidence, is_test),
    )
    return row["event_no"]


def make_media(event_no, is_primary=False, url=None, confidence=0.9123):
    row = db.execute_returning(
        """
        INSERT INTO event_media (event_no, media_url, media_detections,
                                 media_confidence, media_captured_at, media_is_primary)
        VALUES (%s, %s,
                '[{"cls":"flame","conf":0.91,"box":[0.238,0.259,0.047,0.113]}]'::jsonb,
                %s, now(), %s)
        RETURNING media_no
        """,
        (event_no, url or f"/media/events/{event_no}/f.jpg",
         confidence, is_primary),
    )
    return row["media_no"]


def make_alert(event_no, user_no=1, channel="PUSH", status="SENT",
               deadline_offset_sec=180, responded=False):
    row = db.execute_returning(
        """
        INSERT INTO alert (event_no, user_no, alert_channel, alert_status,
                           alert_sent_at, alert_deadline_at, alert_responded_at)
        VALUES (%s, %s, %s, %s, now(),
                now() + (%s || ' seconds')::interval,
                CASE WHEN %s THEN now() ELSE NULL END)
        RETURNING alert_no
        """,
        (event_no, user_no, channel, status, deadline_offset_sec, responded),
    )
    return row["alert_no"]


def make_alert_pair(event_no, user_no=1, status="SENT", sms_status=None,
                    deadline_offset_sec=180, responded=False):
    """확정 시 실제로 만들어지는 PUSH+SMS 한 쌍을 흉내낸다.

    반환: (push_alert_no, sms_alert_no). sms_status 를 주면 SMS 행만 다른 상태로.
    """
    push_no = make_alert(event_no, user_no=user_no, channel="PUSH", status=status,
                         deadline_offset_sec=deadline_offset_sec, responded=responded)
    sms_no = make_alert(event_no, user_no=user_no, channel="SMS",
                        status=sms_status or status,
                        deadline_offset_sec=deadline_offset_sec, responded=responded)
    return push_no, sms_no


def make_report(event_no, agency_no=1, sequence=1, status="ACCEPTED"):
    row = db.execute_returning(
        """
        INSERT INTO report_119 (event_no, agency_no, report_sequence, report_external_id,
                                report_trigger_reason, report_status, report_address,
                                report_distance_km, report_attempt_count,
                                reported_at, report_accepted_at)
        VALUES (%s, %s, %s, 'R-TEST-001', 'NO_RESPONSE_TIMEOUT', %s,
                '서울시 종로구 세종대로 1', 1.234, 1, now(), now())
        RETURNING report_no
        """,
        (event_no, agency_no, sequence, status),
    )
    return row["report_no"]


@pytest.fixture(autouse=True)
def _no_real_telegram_http(monkeypatch):
    """전역 가드: 어떤 테스트도 실제 텔레그램 Bot API 를 부르지 않는다.

    .env 에 봇 토큰이 들어 있는 환경에서 돌리면(시연 준비된 PC 가 그렇다) 알림 발송
    경로를 지나는 무관한 테스트가 진짜 메시지를 쏴 버린다. 기본은 '성공했다고 답하는'
    대역 — 발송 여부나 본문을 검증하는 테스트는 자기 monkeypatch 로 덮어쓴다
    (테스트 본문의 setattr 가 나중에 적용되므로 이 대역을 이긴다).

    폴링 오프셋은 모듈 전역이라 테스트 간에 새로 비운다.

    폴링 **스레드**도 마찬가지로 프로세스 전역이라 여기서 거둔다. 스레드를 띄운 채로
    테스트가 끝나면 위 대역이 풀린 뒤 진짜 api.telegram.org 로 나가서, 무관한
    테스트와 getUpdates 소비권을 다투고 Conflict 를 만든다. 스레드를 띄우는 테스트가
    스스로 정리하는 것이 원칙이고 이건 마지막 그물이다.
    """
    from services import telegram, telegram_bot

    monkeypatch.setattr(
        telegram, "_api",
        lambda method, payload: {"ok": True, "result": {"message_id": 1}},
    )
    telegram_bot.reset_offset()
    yield
    telegram_bot.stop_polling()
    telegram_bot.reset_offset()
