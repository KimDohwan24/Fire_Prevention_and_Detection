"""화재 이벤트 누적/확정 로직 — POST /api/internal/detections 의 본체.

프레임 단위 검출 결과를 받아:
- flame/smoke 검출이 있으면 카메라별 열린(PENDING) 이벤트에 누적
- 마지막 활동에서 EVENT_WINDOW_SEC 를 넘긴 PENDING 은 기준미달(DISMISSED) 처리
- 누적 프레임이 임계값(event_threshold_frames)에 도달하면 CONFIRMED 확정
  → 커밋 후 services.hooks.on_event_confirmed(event_no) 호출 (2단계 알림 훅)
"""
import json
from datetime import datetime, timedelta

import config
import db
from services import hooks

# 화재로 취급하는 검출 클래스 → 이벤트 클래스 표기
FIRE_CLASSES = {"flame": "FLAME", "smoke": "SMOKE"}


def _fire_summary(detections: list) -> tuple[set, float | None]:
    """검출 목록에서 화재 클래스 집합과 최고 화재 신뢰도를 뽑는다.

    flame/smoke 이외의 클래스(person 등)는 화재 판정에서 제외한다.
    (저장은 원본 그대로 media_detections 에 한다)
    """
    classes: set = set()
    max_conf: float | None = None
    for det in detections:
        if not isinstance(det, dict):
            continue
        cls = FIRE_CLASSES.get(det.get("cls"))
        if cls is None:
            continue
        classes.add(cls)
        try:
            conf = float(det.get("conf") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        max_conf = conf if max_conf is None else max(max_conf, conf)
    return classes, max_conf


def _merge_class(existing: str | None, frame_classes: set) -> str:
    """이벤트 클래스 병합: FLAME + SMOKE → FLAME_SMOKE."""
    merged = set(frame_classes)
    if existing == "FLAME_SMOKE":
        merged.update({"FLAME", "SMOKE"})
    elif existing:
        merged.add(existing)
    return "FLAME_SMOKE" if merged == {"FLAME", "SMOKE"} else merged.pop()


def _event_state(row: dict) -> dict:
    """응답 공통 형식으로 축약한다."""
    return {
        "event_no": row["event_no"],
        "event_status": row["event_status"],
        "event_detected_frames": row["event_detected_frames"],
        "event_threshold_frames": row["event_threshold_frames"],
    }


def _find_open_event(cur, cctv_no: int) -> dict | None:
    """카메라의 최신 PENDING 이벤트와 마지막 활동 시각을 가져온다.

    마지막 활동 = 미디어 중 가장 늦은 media_captured_at,
    미디어가 없으면 event_first_detected_at.
    """
    cur.execute(
        """
        SELECT e.event_no, e.event_status, e.event_class, e.event_confidence,
               e.event_detected_frames, e.event_threshold_frames,
               coalesce((SELECT max(m.media_captured_at)
                         FROM event_media m WHERE m.event_no = e.event_no),
                        e.event_first_detected_at) AS last_activity_at
        FROM fire_event e
        WHERE e.cctv_no = %s AND e.event_status = 'PENDING'
        ORDER BY e.event_no DESC
        LIMIT 1
        """,
        (cctv_no,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def process_detection(cctv_no: int, captured_at: datetime,
                      media_url: str | None, detections: list) -> dict:
    """프레임 1장의 검출 결과를 반영하고 이벤트 현재 상태를 돌려준다."""
    frame_classes, frame_conf = _fire_summary(detections)
    window = timedelta(seconds=config.EVENT_WINDOW_SEC)
    confirmed_no = None

    with db.get_cursor(commit=True) as cur:
        event = _find_open_event(cur, cctv_no)

        # 윈도우 초과: 끊긴 PENDING 은 기준미달 처리하고 없는 것으로 본다
        if event and event["last_activity_at"] is not None \
                and event["last_activity_at"] < captured_at - window:
            cur.execute(
                "UPDATE fire_event SET event_status = 'DISMISSED' WHERE event_no = %s",
                (event["event_no"],),
            )
            event = None

        # 비화재 프레임: 누적/저장 없이 현재 상태만 알려준다
        if not frame_classes:
            if event is None:
                return {"event_no": None, "ignored": True}
            return _event_state(event)

        if event is None:
            # 새 이벤트 시작
            cur.execute(
                """
                INSERT INTO fire_event (cctv_no, event_status, event_class,
                                        event_first_detected_at, event_detected_frames,
                                        event_threshold_frames, event_confidence)
                VALUES (%s, 'PENDING', %s, %s, 1, %s, %s)
                RETURNING event_no, event_status, event_detected_frames,
                          event_threshold_frames
                """,
                (cctv_no, _merge_class(None, frame_classes), captured_at,
                 config.EVENT_THRESHOLD_FRAMES, frame_conf),
            )
            event = dict(cur.fetchone())
        else:
            # 누적: 프레임 수 +1, 클래스 병합, 신뢰도는 최고값 유지
            cur.execute(
                """
                UPDATE fire_event
                SET event_detected_frames = event_detected_frames + 1,
                    event_class = %s,
                    event_confidence = GREATEST(coalesce(event_confidence, 0), %s)
                WHERE event_no = %s
                RETURNING event_no, event_status, event_detected_frames,
                          event_threshold_frames
                """,
                (_merge_class(event["event_class"], frame_classes),
                 frame_conf, event["event_no"]),
            )
            event = dict(cur.fetchone())

        # 프레임 미디어 저장 (검출 목록은 원본 그대로 jsonb 로)
        cur.execute(
            """
            INSERT INTO event_media (event_no, media_type, media_url, media_detections,
                                     media_confidence, media_captured_at)
            VALUES (%s, 'FRAME', %s, %s::jsonb, %s, %s)
            RETURNING media_no
            """,
            (event["event_no"], media_url, json.dumps(detections),
             frame_conf, captured_at),
        )
        media_no = cur.fetchone()["media_no"]

        # 대표 이미지: 지금까지 최고 신뢰도 프레임이 대표가 되도록 같은 트랜잭션에서 교체
        cur.execute(
            """
            SELECT media_confidence FROM event_media
            WHERE event_no = %s AND media_is_primary
            """,
            (event["event_no"],),
        )
        primary = cur.fetchone()
        if primary is None or float(primary["media_confidence"] or 0) < frame_conf:
            cur.execute(
                "UPDATE event_media SET media_is_primary = false "
                "WHERE event_no = %s AND media_is_primary",
                (event["event_no"],),
            )
            cur.execute(
                "UPDATE event_media SET media_is_primary = true WHERE media_no = %s",
                (media_no,),
            )

        # 임계값 도달 → 확정
        if event["event_status"] == "PENDING" \
                and event["event_detected_frames"] >= event["event_threshold_frames"]:
            cur.execute(
                """
                UPDATE fire_event
                SET event_status = 'CONFIRMED', event_detected_at = now()
                WHERE event_no = %s
                """,
                (event["event_no"],),
            )
            event["event_status"] = "CONFIRMED"
            confirmed_no = event["event_no"]

    # 커밋이 끝난 뒤 확정 훅 호출 (2단계에서 알림 발송으로 교체)
    if confirmed_no is not None:
        hooks.on_event_confirmed(confirmed_no)

    return _event_state(event)


def sweep_stale_pending(now: datetime | None = None) -> int:
    """마지막 활동에서 EVENT_WINDOW_SEC 를 넘긴 모든 PENDING 을 DISMISSED 처리.

    4단계 스케줄러가 주기적으로 호출한다. 처리한 건수를 돌려준다.
    """
    cutoff = (now or datetime.now()) - timedelta(seconds=config.EVENT_WINDOW_SEC)
    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE fire_event e
            SET event_status = 'DISMISSED'
            WHERE e.event_status = 'PENDING'
              AND coalesce((SELECT max(m.media_captured_at)
                            FROM event_media m WHERE m.event_no = e.event_no),
                           e.event_first_detected_at) < %s
            """,
            (cutoff,),
        )
        return cur.rowcount
