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

TABLES = ["report_119", "alert", "event_media", "fire_event", "cctv", "agency", "users"]


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
        cur.execute(
            """
            INSERT INTO cctv (user_no, cctv_name, cctv_location, cctv_lat, cctv_lng,
                              cctv_stream_url, cctv_width, cctv_height, cctv_status) VALUES
            (1, '정문 카메라', '본관 정문 앞', 37.5665000, 126.9780000,
             'http://192.168.0.10:8080/live/cam1.m3u8', 1920, 1080, 'ACTIVE'),
            (1, '후문 카메라', '본관 후문',    37.5670000, 126.9790000,
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


def make_media(event_no, media_type="FRAME", is_primary=False, url=None,
               confidence=0.9123):
    row = db.execute_returning(
        """
        INSERT INTO event_media (event_no, media_type, media_url, media_detections,
                                 media_confidence, media_captured_at, media_is_primary)
        VALUES (%s, %s, %s,
                '[{"cls":"flame","conf":0.91,"box":[0.238,0.259,0.047,0.113]}]'::jsonb,
                %s, now(), %s)
        RETURNING media_no
        """,
        (event_no, media_type, url or f"/media/events/{event_no}/f.jpg",
         confidence, is_primary),
    )
    return row["media_no"]


def make_alert(event_no, user_no=1, level=1, channel="PUSH", status="SENT",
               deadline_offset_sec=180, responded=False):
    row = db.execute_returning(
        """
        INSERT INTO alert (event_no, user_no, alert_level, alert_channel, alert_status,
                           alert_sent_at, alert_deadline_at, alert_responded_at)
        VALUES (%s, %s, %s, %s, %s, now(),
                now() + (%s || ' seconds')::interval,
                CASE WHEN %s THEN now() ELSE NULL END)
        RETURNING alert_no
        """,
        (event_no, user_no, level, channel, status, deadline_offset_sec, responded),
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


def make_report(event_no, agency_no=1, sequence=1, status="DISPATCHED"):
    row = db.execute_returning(
        """
        INSERT INTO report_119 (event_no, agency_no, report_sequence, report_external_id,
                                report_trigger_reason, report_status, report_address,
                                report_distance_km, report_attempt_count,
                                reported_at, report_dispatched_at)
        VALUES (%s, %s, %s, 'R-TEST-001', 'NO_RESPONSE_TIMEOUT', %s,
                '서울시 종로구 세종대로 1', 1.234, 1, now(), now())
        RETURNING report_no
        """,
        (event_no, agency_no, sequence, status),
    )
    return row["report_no"]
