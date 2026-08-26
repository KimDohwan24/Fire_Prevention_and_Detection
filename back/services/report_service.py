"""119 신고 서비스 (D4 확정 설계).

트리거 (start_report 호출 지점):
- USER_CONFIRMED      사용자가 알림에서 화재를 확인(READ)한 즉시 (alert_routes)
- NO_RESPONSE_TIMEOUT 최종(2차) 알림까지 무응답 → 4단계 에스컬레이션이 호출

동작:
- 활성 기관(agency_is_active)을 CCTV 좌표 기준 하버사인 거리 오름차순으로 시도한다.
- 바깥 루프 = 기관 승계(report_sequence 1, 2, ...),
  안쪽 루프 = 한 기관에 최대 MAX_REPORT_ATTEMPTS 회 전송(report_attempt_count).
- 안쪽 루프는 실패 종류를 가린다. 재시도해도 결과가 같은 실패(연결 실패·4xx 거절)는
  남은 시도를 버리고 곧장 승계하고, 일시적일 수 있는 실패(응답 타임아웃·5xx)만
  재시도를 다 쓴다. 같은 서버의 연속 실패는 원인이 지속되는 탓에 서로 독립이 아니라
  회차를 거듭해도 성공 확률이 거의 오르지 않는 반면, 다른 기관은 실패 원인이 독립이다.
- 행을 먼저 SENDING 으로 INSERT 해서 부분 유니크 인덱스(UX_report_119_active)의
  슬롯을 선점한다 — 동시에 두 신고가 진행되는 것을 DB 가 막는다.
- 기관 소진 시 그 행은 NO_RESPONSE(무응답으로 승계) 로 닫고 다음 기관으로.
  더 시도할 기관이 없으면 마지막 행만 FAILED(전송실패).
- 점검 모드(event_is_test) 이벤트는 신고하지 않는다.
"""
import base64
import json
import logging
import time
from datetime import datetime

import psycopg2.errors
import requests

import config
import db
from services import event_frame

logger = logging.getLogger("fireguard.report")

# 최근접 소방서 탐색 — 거리 계산과 정렬을 DB(PostGIS)에 맡긴다.
#
# `<->` 는 GiST 인덱스를 타는 KNN 연산자다. 기관 수가 늘어도 전 건을 재지 않고
# 인덱스로 후보를 좁힌다. geography 타입이라 거리는 **미터**이고 구면이 아니라
# 타원체(WGS84) 기준이라 하버사인보다 정확하다.
#
# 좌표가 없는 행은 제외한다 — 거리를 모르는 것과 먼 것은 다르다. NULL 을 그냥 두면
# 정렬 맨 뒤에 붙어 '가장 먼 기관'처럼 승계 후보에 남는다.
_NEAREST_AGENCIES_SQL = """
    SELECT a.agency_no, a.agency_name, a.agency_endpoint,
           public.ST_Distance(a.agency_geog, c.cctv_geog) / 1000.0 AS distance_km
    FROM fireguard.agency a
    JOIN fireguard.cctv c ON c.cctv_no = %s
    WHERE a.agency_is_active
      AND a.agency_geog IS NOT NULL
      AND c.cctv_geog IS NOT NULL
    ORDER BY a.agency_geog <-> c.cctv_geog, a.agency_no
"""


def nearest_agencies(cctv_no: int) -> list[dict]:
    """활성 기관을 CCTV 에서 가까운 순으로 돌려준다 (거리 km 포함).

    승계 순서가 곧 이 순서다. 좌표가 없는 기관, 좌표 없는 카메라는 결과가 비거나
    빠진다 — 그 경우 신고할 곳이 없다는 뜻이고 호출자가 판단한다.
    """
    return db.query(_NEAREST_AGENCIES_SQL, (cctv_no,))

# 진행 중으로 간주하는 상태 (부분 유니크 인덱스 UX_report_119_active 와 동일한 집합)
# ⚠️ 이 튜플과 인덱스 조건이 어긋나면, 출동 중인 화재에 신고가 한 번 더 나가거나
#    INSERT 가 유니크 위반(23505)으로 터진다. 바꿀 때는 db/schema.sql 도 같이 바꾼다.
ACTIVE_STATUSES = ("SENDING", "ACCEPTED", "DISPATCHED")

_REPORT_EVENT_SQL = """
    SELECT e.event_no, e.event_class, e.event_confidence, e.event_is_test,
           e.event_first_detected_at, e.event_detected_frames,
           e.event_threshold_frames,
           c.cctv_no, c.cctv_name, c.cctv_location, c.cctv_address,
           c.cctv_lat, c.cctv_lng, c.cctv_stream_url,
           c.cctv_width, c.cctv_height, c.cctv_status
    FROM fire_event e
    JOIN cctv c ON c.cctv_no = e.cctv_no
    WHERE e.event_no = %s
"""


def _load_report_event(event_no: int) -> dict | None:
    """119 payload 조립에 필요한 이벤트·CCTV 정보를 읽는다."""
    return db.query_one(_REPORT_EVENT_SQL, (event_no,))


def report_uid(event_no: int) -> str:
    """119 에 보내는 신고 ID — 화재(이벤트) 하나에 하나.

    재전송에도 승계에도 같은 값이라, 받는 쪽이 "아까 그 신고"임을 알 수 있다.
    재전송은 상대가 못 받았다는 뜻이 아니라 응답이 안 왔다는 뜻일 뿐이다.
    ID 가 없으면 3초 타임아웃 뒤 재전송한 4건이 같은 화재에 대한 출동 4건이 된다.

    event_no 에서 바로 만든다 — 컬럼을 새로 두지 않아도 언제든 같은 값이 나오고,
    로그에서 신고 ID 만 보고 이벤트를 찾을 수 있다.
    """
    return f"FG-{event_no}"


def _report_address(event: dict) -> str:
    """119 에 보낼 주소를 정한다.

    우선순위:
      1. cctv_address — CCTV 등록 시 좌표를 역지오코딩해 둔 값 (도로명 또는 지번)
      2. 좌표 문자열 — "위도 37.5665, 경도 126.978 (본관 정문 앞)"
      3. cctv_location — 좌표조차 없을 때의 마지막 수단

    2번이 가짜 주소보다 안전하고 빈 칸보다 쓸모 있다. 사람이 읽고 지도에 찍을 수
    있어서 신고가 무용지물이 되지 않는다. 괄호 안은 설치 위치 설명이고, 없으면
    괄호째 뺀다.
    """
    if event.get("cctv_address"):
        return event["cctv_address"]

    lat, lng = event.get("cctv_lat"), event.get("cctv_lng")
    if lat is None or lng is None:
        return event.get("cctv_location") or ""

    # numeric(10,7) 이라 그대로 쓰면 "37.5665000" 처럼 0 이 붙는다 — 사람이 읽을 형태로
    text = f"위도 {float(lat):g}, 경도 {float(lng):g}"
    if event.get("cctv_location"):
        text += f" ({event['cctv_location']})"
    return text


def _real_post_report(endpoint: str, payload: dict) -> requests.Response:
    """실제 HTTP 전송 구현 — 실제 HTTP 는 여기서만 나간다.

    통합 테스트(test_mock119_integration)가 전역 스텁을 걷어내고
    이 함수를 다시 _post_report 자리에 꽂아 실제 전송을 검증한다.
    """
    return requests.post(endpoint, json=payload,
                         timeout=config.REPORT_HTTP_TIMEOUT_SEC)


def _post_report(endpoint: str, payload: dict) -> requests.Response:
    """기관 endpoint 로 신고 JSON 을 전송한다.

    테스트에서 monkeypatch 하는 지점 — 기본은 실제 구현에 위임한다.
    """
    return _real_post_report(endpoint, payload)


def _log_attempt(report_no: int, attempt: int, endpoint: str, request_body: dict,
                 sent_at: datetime, elapsed_ms: int, result: str,
                 http_status: int | None, response_body, error: str | None) -> None:
    """전송 1회를 report_log 에 그대로 남긴다 (요구사항 N-04).

    report_119 는 결과 요약만 갖고 있어서, 사후에 "몇 시에 뭘 보냈고 뭐라고
    답이 왔는지"를 따질 수 없었다. 승계 판단의 근거도 여기 남는다.

    이미지(base64)만은 예외로 생략한다 — 원본이 디스크(MEDIA_ROOT)에 있는데
    로그 행마다 그대로 남기면 재전송 4회에 같은 이미지가 4번 DB 에 쌓인다.
    검출 좌표(image_detections)는 작고 승계 판단에 유용해 그대로 남긴다.
    """
    if request_body.get("image_base64"):
        request_body = dict(
            request_body,
            image_base64=f"<base64 {len(request_body['image_base64'])}자 생략"
                         " — 원본은 event_media 대표 프레임 파일>",
        )
    db.execute(
        """
        INSERT INTO report_log (report_no, log_attempt, log_endpoint, log_request,
                                log_result, log_http_status, log_response,
                                log_error, log_elapsed_ms, log_sent_at)
        VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, %s, %s, %s)
        """,
        (report_no, attempt, endpoint, json.dumps(request_body), result, http_status,
         None if response_body is None else json.dumps(response_body),
         None if error is None else error[:500], elapsed_ms, sent_at),
    )


def _primary_frame(event_no: int) -> tuple[str | None, list | None]:
    """대표 프레임(media_is_primary)의 이미지(base64)와 검출 상자 좌표를 가져온다.

    실제 119라면 외부에서 우리 서버 URL 에 접근할 수 없으므로 이미지 자체를
    페이로드에 싣는다. 파일을 읽고 검출 상자를 그리는 일은 services/event_frame.py
    가 한다 — 같은 그림을 텔레그램 화재 알림도 쓰기 때문이다. 여기 남는 것은
    **JSON 에 실을 수 있게 base64 로 감싸는 것뿐**이다 (텔레그램은 multipart 라
    바이트를 그대로 쓴다).

    파일이 없거나 못 읽으면 (None, None) — 이미지는 곁들이고 신고가 본체라,
    이미지 때문에 신고가 막히면 안 된다.
    """
    content, detections = event_frame.load_primary_frame(event_no)
    if content is None:
        return None, None
    return base64.b64encode(content).decode("ascii"), detections


def _test_report_payload(event: dict) -> dict:
    """영상 테스트용 mock-119 접수 payload를 만든다.

    테스트 신고는 실제 기관 선택·report_119 장부와 분리하지만, mock-119 접수
    화면에서 실제 신고와 같은 형태로 보이도록 기존 119 payload 구조를 따른다.
    """
    image_base64, image_detections = _primary_frame(event["event_no"])
    confidence = event.get("event_confidence")
    lat = event.get("cctv_lat")
    lng = event.get("cctv_lng")
    return {
        "report_uid": f"FG-TEST-{event['event_no']}",
        "event_no": event["event_no"],
        "address": _report_address(event),
        "place": event.get("cctv_location"),
        "lat": None if lat is None else float(lat),
        "lng": None if lng is None else float(lng),
        "event_class": event.get("event_class"),
        "confidence": None if confidence is None else float(confidence),
        "first_detected_at": (
            event["event_first_detected_at"].isoformat(timespec="seconds")
            if event.get("event_first_detected_at") else None
        ),
        "reported_at": datetime.now().isoformat(timespec="seconds"),
        "image_base64": image_base64,
        "image_detections": image_detections,
        "callback_url": f"{config.PUBLIC_BASE_URL}/api/reports/dispatch",
        "cctv": {
            "cctv_no": event["cctv_no"],
            "name": event.get("cctv_name"),
            "location": event.get("cctv_location"),
            "address": event.get("cctv_address"),
            "lat": None if lat is None else float(lat),
            "lng": None if lng is None else float(lng),
            "stream_url": event.get("cctv_stream_url"),
            "width": event.get("cctv_width"),
            "height": event.get("cctv_height"),
            "status": event.get("cctv_status"),
        },
        "detection": {
            "frames": event.get("event_detected_frames"),
            "threshold_frames": event.get("event_threshold_frames"),
        },
        "agency": {
            "name": "mock-119 (영상 테스트)",
            "distance_km": None,
        },
    }


def send_test_report(event_no: int) -> dict | None:
    """영상 테스트 확정 결과를 mock-119에만 전송한다.

    실제 운영 신고인 :func:`start_report`와 달리 ``report_119`` 행을 만들거나
    관할기관을 고르지 않는다. 테스트 이벤트가 아닌 이벤트에는 안전을 위해
    전송하지 않는다.
    """
    event = _load_report_event(event_no)
    if event is None:
        logger.warning("테스트 신고 불가 — 이벤트 없음 (event_no=%s)", event_no)
        return None
    if not event["event_is_test"]:
        logger.warning("테스트 신고 생략 — 테스트 이벤트가 아님 (event_no=%s)", event_no)
        return None

    endpoint = config.MOCK119_TEST_ENDPOINT
    payload = _test_report_payload(event)
    try:
        response = _post_report(endpoint, payload)
    except requests.exceptions.RequestException as exc:
        logger.warning("테스트 mock-119 연결 실패 (event_no=%s): %s", event_no, exc)
        return {
            "report_status": "FAILED",
            "report_endpoint": endpoint,
            "report_http_status": None,
            "report_error": str(exc)[:500],
        }

    http_status = response.status_code
    try:
        response_body = response.json()
    except (ValueError, AttributeError):
        response_body = None

    if 200 <= http_status < 300:
        external_id = (
            response_body.get("external_id")
            if isinstance(response_body, dict) else None
        )
        logger.info("테스트 mock-119 접수 확인 (event_no=%s, external_id=%s)",
                    event_no, external_id)
        return {
            "report_status": "ACCEPTED",
            "report_endpoint": endpoint,
            "report_http_status": http_status,
            "report_external_id": external_id,
            "report_response": response_body,
        }

    logger.warning("테스트 mock-119 접수 거절 (event_no=%s, status=%s)",
                   event_no, http_status)
    return {
        "report_status": "FAILED",
        "report_endpoint": endpoint,
        "report_http_status": http_status,
        "report_response": response_body,
    }


def _find_active_report(event_no: int) -> dict | None:
    """이벤트의 진행 중(SENDING/ACCEPTED) 신고를 찾는다."""
    return db.query_one(
        """
        SELECT r.report_no, r.event_no, r.agency_no, ag.agency_name,
               r.report_sequence, r.report_status, r.report_external_id,
               r.report_trigger_reason, r.reported_at, r.report_accepted_at
        FROM report_119 r
        JOIN agency ag ON ag.agency_no = r.agency_no
        WHERE r.event_no = %s AND r.report_status IN %s
        """,
        (event_no, ACTIVE_STATUSES),
    )


def _report_info(report_no: int) -> dict:
    """신고 행 + 기관명을 결과 dict 로 돌려준다."""
    return db.query_one(
        """
        SELECT r.report_no, r.event_no, r.agency_no, ag.agency_name,
               r.report_sequence, r.report_status, r.report_external_id,
               r.report_trigger_reason, r.report_distance_km,
               r.report_attempt_count, r.reported_at, r.report_accepted_at
        FROM report_119 r
        JOIN agency ag ON ag.agency_no = r.agency_no
        WHERE r.report_no = %s
        """,
        (report_no,),
    )


def _attempt_agency(event: dict, agency: dict, sequence: int,
                    trigger_reason: str, is_last: bool) -> dict | None:
    """한 기관에 대해 신고 행 생성 + 최대 MAX_REPORT_ATTEMPTS 회 전송을 시도한다.

    '최대'인 이유: 재시도해도 결과가 같은 실패(연결 실패·4xx)면 남은 시도를 버리고
    바로 빠져나온다. 이때도 상태는 NO_RESPONSE/FAILED 로 닫히지만, 실제 사유는
    report_log.log_result(ERROR / REJECTED / TIMEOUT)에 시도별로 그대로 남는다.

    반환: 최종 신고 정보 dict. 상태가 ACCEPTED(또는 동시성 가드로 찾은 기존
    활성 신고)면 호출자는 승계를 멈춘다. NO_RESPONSE 면 다음 기관으로 넘어간다.
    """
    # 1) 행을 먼저 SENDING 으로 INSERT — 유니크 인덱스 슬롯 선점 (동시성 가드)
    try:
        created = db.execute_returning(
            """
            INSERT INTO report_119 (event_no, agency_no, report_sequence,
                                    report_trigger_reason, report_status,
                                    report_address, report_distance_km,
                                    report_attempt_count, reported_at)
            VALUES (%s, %s, %s, %s, 'SENDING', %s, %s, 0, now())
            RETURNING report_no
            """,
            (event["event_no"], agency["agency_no"], sequence, trigger_reason,
             _report_address(event), round(agency["distance_km"], 3)),
        )
    except psycopg2.errors.UniqueViolation:
        # 다른 경로(에스컬레이션 vs 사용자 확인)가 먼저 신고를 진행 중 — 그걸 돌려준다
        logger.info("이미 진행 중인 신고 존재 — 새 신고 생략 (event_no=%s)",
                    event["event_no"])
        return db.query_one(
            """
            SELECT r.report_no, r.event_no, r.agency_no, ag.agency_name,
                   r.report_sequence, r.report_status, r.report_external_id,
                   r.report_trigger_reason, r.reported_at, r.report_accepted_at
            FROM report_119 r
            JOIN agency ag ON ag.agency_no = r.agency_no
            WHERE r.event_no = %s AND r.report_status IN %s
            """,
            (event["event_no"], ACTIVE_STATUSES),
        )
    report_no = created["report_no"]

    # 2) 안쪽 루프: 같은 기관에 최대 MAX_REPORT_ATTEMPTS 회 전송
    payload = {
        # 신고 ID — 재전송·승계 내내 같은 값. 받는 쪽의 중복 접수 방지 키다.
        "report_uid": report_uid(event["event_no"]),
        "event_no": event["event_no"],
        # 소방서가 출동할 주소. cctv_location(설치 위치 설명)이 아니다 — 그건 place 로 간다.
        "address": _report_address(event),
        "place": event["cctv_location"],
        "lat": float(event["cctv_lat"]),
        "lng": float(event["cctv_lng"]),
        "event_class": event["event_class"],
        "confidence": float(event["event_confidence"]),
        # 최초 검출 시각 — 유예 30초 + 승계가 겹치면 신고가 검출보다 1분 이상
        # 늦을 수 있다. 소방 입장에선 신고 시각이 아니라 발화 시점이 중요하다.
        "first_detected_at": event["event_first_detected_at"].isoformat(timespec="seconds")
        if event.get("event_first_detected_at") else None,
        "reported_at": datetime.now().isoformat(timespec="seconds"),
        # 대표 프레임(bbox 검출 좌표 포함) — 접수 서버가 화면에 띄울 수 있게 싣는다
        "image_base64": event["image_base64"],
        "image_detections": event["image_detections"],
        # 출동 통지를 되쏠 주소. 받는 쪽이 우리 주소를 미리 알지 않아도 되게 한다.
        "callback_url": f"{config.PUBLIC_BASE_URL}/api/reports/dispatch",
        # 카메라 정보 — 접수자가 어느 카메라 건인지 특정하고 화면을 띄울 수 있게
        "cctv": {
            "cctv_no": event["cctv_no"],
            "name": event["cctv_name"],
            "location": event["cctv_location"],
            "address": event["cctv_address"],
            "lat": float(event["cctv_lat"]),
            "lng": float(event["cctv_lng"]),
            "stream_url": event["cctv_stream_url"],
            "width": event["cctv_width"],
            "height": event["cctv_height"],
            "status": event["cctv_status"],
        },
        # 판정 근거 — 몇 프레임이 쌓여 확정됐나
        "detection": {
            "frames": event["event_detected_frames"],
            "threshold_frames": event["event_threshold_frames"],
        },
        # 이 시도의 수신 기관. 승계하면 달라지므로 payload 조립이 기관 루프 안에 있다.
        "agency": {
            "name": agency["agency_name"],
            "distance_km": round(agency["distance_km"], 3),
        },
    }
    max_attempts = config.MAX_REPORT_ATTEMPTS
    endpoint = agency["agency_endpoint"]
    for attempt in range(1, max_attempts + 1):
        sent_at = datetime.now()
        started = time.monotonic()
        http_status = body = error = None
        # 이 기관을 다시 두드릴 값어치가 있는가. 없으면 남은 시도를 버리고 곧장 승계한다.
        retry_worthwhile = True
        try:
            resp = _post_report(endpoint, payload)
        except (requests.exceptions.ConnectTimeout,
                requests.exceptions.ConnectionError) as exc:
            # 연결이 성립하지 않았다 = 신고가 전달되지 않은 것이 확실하다.
            # 같은 기관을 다시 두드려도 원인(다운·방화벽·경로)이 그대로라 결과가 같고,
            # 전달되지 않았으니 승계해도 중복 접수 위험이 없다 — 승계가 공짜인 유일한 경우.
            # ConnectTimeout 은 Timeout 이기도 해서 반드시 아래 절보다 먼저 잡아야 한다
            # (아래에 잡히면 '상대가 접수했을 수도 있다'로 잘못 기록된다).
            result, ok, error = "ERROR", False, str(exc)
            retry_worthwhile = False
            logger.warning("신고 연결 실패 — 재시도 없이 승계 (report_no=%s): %s",
                           report_no, exc)
        except requests.exceptions.Timeout as exc:
            # 요청은 닿았고 응답만 없다 — 상대는 접수했을 수도 있다.
            # 승계하면 중복 출동 위험을 지므로, 같은 기관에 재확인을 먼저 다 쓴다.
            result, ok, error = "TIMEOUT", False, str(exc)
            logger.warning("신고 응답 없음 (report_no=%s, attempt=%s/%s): %s",
                           report_no, attempt, max_attempts, exc)
        except requests.exceptions.RequestException as exc:
            # 잘못된 URL·SSL 오류 등 — 설정 문제라 재시도로 풀리지 않는다
            result, ok, error = "ERROR", False, str(exc)
            retry_worthwhile = False
            logger.warning("신고 전송 실패 — 재시도 없이 승계 (report_no=%s): %s",
                           report_no, exc)
        else:
            http_status = resp.status_code
            ok = 200 <= http_status < 300
            result = "ACCEPTED" if ok else "REJECTED"
            try:
                body = resp.json()
            except (ValueError, AttributeError):
                body = None       # 본문 없는 2xx 도 성공으로 본다
            if not ok:
                # 4xx 는 우리 요청이 상대 규격에 안 맞는다는 뜻이라 같은 걸 다시 보내도
                # 같은 답이 온다. 5xx(일시 장애)만 재시도할 값어치가 있다.
                # 다만 다른 기관도 거절하리라는 보장은 없으므로 승계는 계속한다.
                retry_worthwhile = 500 <= http_status < 600
                logger.warning("신고 거절 응답 %s (report_no=%s, attempt=%s/%s)",
                               http_status, report_no, attempt, max_attempts)

        elapsed_ms = int((time.monotonic() - started) * 1000)
        try:
            _log_attempt(report_no, attempt, endpoint, payload, sent_at,
                         elapsed_ms, result, http_status, body, error)
        except Exception:
            # 증거를 남기려다 신고를 막으면 본말전도다
            logger.exception("송수신 로그 기록 실패 — 신고는 계속한다 "
                             "(report_no=%s, attempt=%s)", report_no, attempt)

        if ok:
            external_id = body.get("external_id") if isinstance(body, dict) else None
            db.execute(
                """
                UPDATE report_119
                SET report_status = 'ACCEPTED', report_external_id = %s,
                    report_accepted_at = now(), report_attempt_count = %s
                WHERE report_no = %s
                """,
                (external_id, attempt, report_no),
            )
            logger.info("119 접수 확인 (report_no=%s, agency=%s, attempt=%s)",
                        report_no, agency["agency_name"], attempt)
            return _report_info(report_no)

        # 실패 — 시도 횟수만 기록하고 재시도
        db.execute(
            "UPDATE report_119 SET report_attempt_count = %s WHERE report_no = %s",
            (attempt, report_no),
        )

        if not retry_worthwhile:
            # 남은 시도를 써봐야 같은 결과다. 그 시간에 다음 기관으로 가는 편이 낫다.
            break

    # 3) 소진: 마지막 기관이면 FAILED(전송실패), 아니면 NO_RESPONSE(무응답으로 승계)
    #    NO_RESPONSE/FAILED 는 활성 상태가 아니므로 유니크 슬롯이 풀린다.
    final_status = "FAILED" if is_last else "NO_RESPONSE"
    db.execute(
        "UPDATE report_119 SET report_status = %s WHERE report_no = %s",
        (final_status, report_no),
    )
    logger.warning("기관 무응답 — 상태 %s (report_no=%s, agency=%s)",
                   final_status, report_no, agency["agency_name"])
    return _report_info(report_no)


def start_report(event_no: int, trigger_reason: str) -> dict | None:
    """이벤트에 대한 119 신고를 시작한다 (진입점).

    - trigger_reason: 'USER_CONFIRMED'(사용자 화재 확인) 또는
      'NO_RESPONSE_TIMEOUT'(무응답 에스컬레이션).
    - 반환: 최종 신고 정보 dict. 점검 모드 이벤트/이벤트 없음/활성 기관 없음이면 None.
    - 멱등: 이미 진행 중(SENDING/ACCEPTED) 신고가 있으면 그 정보를 그대로 돌려준다.
    """
    event = _load_report_event(event_no)
    if event is None:
        logger.warning("신고 불가 — 이벤트 없음 (event_no=%s)", event_no)
        return None
    if event["event_is_test"]:
        logger.info("점검 모드 이벤트 — 신고 생략 (event_no=%s)", event_no)
        return None

    # 멱등 가드: 이미 진행 중인 신고가 있으면 새로 만들지 않는다
    existing = _find_active_report(event_no)
    if existing:
        logger.info("이미 진행 중인 신고 반환 (event_no=%s, report_no=%s)",
                    event_no, existing["report_no"])
        return existing

    # 대표 프레임은 이벤트 단위 — 재전송·승계 내내 같으니 한 번만 읽는다
    event["image_base64"], event["image_detections"] = _primary_frame(event_no)

    # 후보 기관: PostGIS 공간 질의로 가까운 순 (좌표 없는 행은 애초에 빠진다)
    agencies = nearest_agencies(event["cctv_no"])
    if not agencies:
        logger.warning("신고 불가 — 좌표로 찾을 수 있는 활성 기관 없음 (event_no=%s)",
                       event_no)
        return None

    # 시도 대상 자르기. 기본(REPORT_MAX_AGENCIES=1)은 가장 가까운 한 곳뿐이라
    # 아래 루프가 한 바퀴만 돌고 끝난다 — 기관 승계가 일어나지 않는다.
    # 0 이면 자르지 않고 후보 전체를 순서대로 시도한다(원래 승계 동작).
    if config.REPORT_MAX_AGENCIES:
        agencies = agencies[:config.REPORT_MAX_AGENCIES]

    # 바깥 루프: 기관 승계 (sequence 1, 2, ...)
    # 후보가 한 곳뿐이면 is_last 가 곧바로 True 라, 그 기관이 재시도를 소진하면
    # NO_RESPONSE(승계 예정)가 아니라 FAILED(전송 실패)로 닫힌다. 의도된 동작이다.
    result = None
    for sequence, agency in enumerate(agencies, start=1):
        is_last = sequence == len(agencies)
        result = _attempt_agency(event, agency, sequence, trigger_reason, is_last)
        if result is None:
            continue
        if result["report_status"] in ACTIVE_STATUSES:
            # ACCEPTED 성공, 또는 동시성 가드가 찾은 기존 활성 신고 — 승계 종료
            return result
    # 전 기관 소진 — 마지막 행(FAILED) 정보를 돌려준다
    return result
