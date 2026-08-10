"""119 신고 서비스 (D4 확정 설계).

트리거 (start_report 호출 지점):
- USER_CONFIRMED      사용자가 알림에서 화재를 확인(READ)한 즉시 (alert_routes)
- NO_RESPONSE_TIMEOUT 최종(2차) 알림까지 무응답 → 4단계 에스컬레이션이 호출

동작:
- 활성 기관(agency_is_active)을 CCTV 좌표 기준 하버사인 거리 오름차순으로 시도한다.
- 바깥 루프 = 기관 승계(report_sequence 1, 2, ...),
  안쪽 루프 = 한 기관에 최대 MAX_REPORT_ATTEMPTS 회 전송(report_attempt_count).
- 행을 먼저 SENDING 으로 INSERT 해서 부분 유니크 인덱스(UX_report_119_active)의
  슬롯을 선점한다 — 동시에 두 신고가 진행되는 것을 DB 가 막는다.
- 기관 소진 시 그 행은 NO_RESPONSE(무응답으로 승계) 로 닫고 다음 기관으로.
  더 시도할 기관이 없으면 마지막 행만 FAILED(전송실패).
- 점검 모드(event_is_test) 이벤트는 신고하지 않는다.
"""
import logging
from datetime import datetime

import psycopg2.errors
import requests

import config
import db
from utils.geo import haversine_km

logger = logging.getLogger("fireguard.report")

# 진행 중으로 간주하는 상태 (부분 유니크 인덱스와 동일한 집합)
ACTIVE_STATUSES = ("SENDING", "DISPATCHED")


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


def _find_active_report(event_no: int) -> dict | None:
    """이벤트의 진행 중(SENDING/DISPATCHED) 신고를 찾는다."""
    return db.query_one(
        """
        SELECT r.report_no, r.event_no, r.agency_no, ag.agency_name,
               r.report_sequence, r.report_status, r.report_external_id,
               r.report_trigger_reason, r.reported_at, r.report_dispatched_at
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
               r.report_attempt_count, r.reported_at, r.report_dispatched_at
        FROM report_119 r
        JOIN agency ag ON ag.agency_no = r.agency_no
        WHERE r.report_no = %s
        """,
        (report_no,),
    )


def _attempt_agency(event: dict, agency: dict, sequence: int,
                    trigger_reason: str, is_last: bool) -> dict | None:
    """한 기관에 대해 신고 행 생성 + 최대 MAX_REPORT_ATTEMPTS 회 전송을 시도한다.

    반환: 최종 신고 정보 dict. 상태가 DISPATCHED(또는 동시성 가드로 찾은 기존
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
             event["cctv_location"], round(agency["distance_km"], 3)),
        )
    except psycopg2.errors.UniqueViolation:
        # 다른 경로(에스컬레이션 vs 사용자 확인)가 먼저 신고를 진행 중 — 그걸 돌려준다
        logger.info("이미 진행 중인 신고 존재 — 새 신고 생략 (event_no=%s)",
                    event["event_no"])
        return db.query_one(
            """
            SELECT r.report_no, r.event_no, r.agency_no, ag.agency_name,
                   r.report_sequence, r.report_status, r.report_external_id,
                   r.report_trigger_reason, r.reported_at, r.report_dispatched_at
            FROM report_119 r
            JOIN agency ag ON ag.agency_no = r.agency_no
            WHERE r.event_no = %s AND r.report_status IN %s
            """,
            (event["event_no"], ACTIVE_STATUSES),
        )
    report_no = created["report_no"]

    # 2) 안쪽 루프: 같은 기관에 최대 MAX_REPORT_ATTEMPTS 회 전송
    payload = {
        "event_no": event["event_no"],
        "address": event["cctv_location"],
        "lat": float(event["cctv_lat"]),
        "lng": float(event["cctv_lng"]),
        "event_class": event["event_class"],
        "confidence": float(event["event_confidence"]),
        "reported_at": datetime.now().isoformat(timespec="seconds"),
    }
    max_attempts = config.MAX_REPORT_ATTEMPTS
    for attempt in range(1, max_attempts + 1):
        try:
            resp = _post_report(agency["agency_endpoint"], payload)
            ok = 200 <= resp.status_code < 300
        except requests.exceptions.RequestException as exc:
            # 타임아웃/연결 실패 등 전송 계층 실패 — 거절과 동일하게 재시도
            logger.warning("신고 전송 실패 (report_no=%s, attempt=%s/%s): %s",
                           report_no, attempt, max_attempts, exc)
            ok = False
        else:
            if not ok:
                logger.warning("신고 거절 응답 %s (report_no=%s, attempt=%s/%s)",
                               resp.status_code, report_no, attempt, max_attempts)

        if ok:
            # 2xx 성공 — 본문의 external_id 는 있으면 저장 (없는 2xx 도 성공)
            try:
                external_id = resp.json().get("external_id")
            except (ValueError, AttributeError):
                external_id = None
            db.execute(
                """
                UPDATE report_119
                SET report_status = 'DISPATCHED', report_external_id = %s,
                    report_dispatched_at = now(), report_attempt_count = %s
                WHERE report_no = %s
                """,
                (external_id, attempt, report_no),
            )
            logger.info("119 출동 접수 (report_no=%s, agency=%s, attempt=%s)",
                        report_no, agency["agency_name"], attempt)
            return _report_info(report_no)

        # 실패 — 시도 횟수만 기록하고 재시도
        db.execute(
            "UPDATE report_119 SET report_attempt_count = %s WHERE report_no = %s",
            (attempt, report_no),
        )

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
    - 멱등: 이미 진행 중(SENDING/DISPATCHED) 신고가 있으면 그 정보를 그대로 돌려준다.
    """
    event = db.query_one(
        """
        SELECT e.event_no, e.event_class, e.event_confidence, e.event_is_test,
               c.cctv_location, c.cctv_lat, c.cctv_lng
        FROM fire_event e
        JOIN cctv c ON c.cctv_no = e.cctv_no
        WHERE e.event_no = %s
        """,
        (event_no,),
    )
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

    # 후보 기관: 활성 기관을 CCTV 좌표 기준 거리 오름차순으로
    agencies = db.query(
        """
        SELECT agency_no, agency_name, agency_lat, agency_lng, agency_endpoint
        FROM agency
        WHERE agency_is_active
        """
    )
    for a in agencies:
        a["distance_km"] = haversine_km(
            float(event["cctv_lat"]), float(event["cctv_lng"]),
            float(a["agency_lat"]), float(a["agency_lng"]),
        )
    agencies.sort(key=lambda a: a["distance_km"])
    if not agencies:
        logger.warning("신고 불가 — 활성 기관 없음 (event_no=%s)", event_no)
        return None

    # 바깥 루프: 기관 승계 (sequence 1, 2, ...)
    result = None
    for sequence, agency in enumerate(agencies, start=1):
        is_last = sequence == len(agencies)
        result = _attempt_agency(event, agency, sequence, trigger_reason, is_last)
        if result is None:
            continue
        if result["report_status"] in ACTIVE_STATUSES:
            # DISPATCHED 성공, 또는 동시성 가드가 찾은 기존 활성 신고 — 승계 종료
            return result
    # 전 기관 소진 — 마지막 행(FAILED) 정보를 돌려준다
    return result
