"""화재 이벤트 누적/확정 로직 — POST /api/internal/detections 의 본체.

판정 규칙은 발표 슬라이드 10 의 "고정 관측 창"이다:
최초로 화재·연기를 감지한 순간 판정이 시작되고, 그 시각에 **고정된**
EVENT_WINDOW_SEC 초 창 안에서 검출 프레임이 임계값만큼 쌓이면 화재 확정,
미달인 채로 창이 닫히면 판정 종료(DISMISSED) 후 감시 상태로 복귀한다.

창을 최초 감지 시각에 못 박는 것이 핵심이다. 마지막 검출 기준으로 창을 재면
검출이 들어올 때마다 창이 연장돼서, 창 간격보다 조금씩 빠르게 튀는 신호가
시간만 충분하면 결국 확정된다 — 이 로직이 걸러내려던 바로 그 신호다.

프레임 단위 검출 결과를 받아:
- flame/smoke 검출이 있으면 카메라별 열린(PENDING) 이벤트에 누적
- 최초 감지에서 EVENT_WINDOW_SEC 를 넘긴 PENDING 은 기준미달(DISMISSED) 처리
  (이후 검출은 쿨다운 없이 새 이벤트로 처음부터 다시 센다)
- 누적 프레임이 임계값(event_threshold_frames)에 도달하면 CONFIRMED 확정
  → 커밋 후 services.hooks.on_event_confirmed(event_no) 호출 (2단계 알림 훅)

판정 기준 두 가지(EVENT_WINDOW_SEC · EVENT_THRESHOLD_FRAMES)는 **둘 다 프레임마다
config 에서 읽는다.** event_threshold_frames 컬럼은 이벤트 시작 당시 값을 박제한 것이
아니라 "지금 적용 중인 기준"의 기록이고, 매 프레임 갱신된다.
한쪽만 박제하면 진행 중인 이벤트의 판정 기준이 반쪽만 바뀐다 — 2026-08-13 event 8 이
임계값 30 을 유지한 채 창만 늘어나 147.8초 만에 확정된 사고가 그것이다.
"""
import json
from datetime import datetime, timedelta

import config
import db
from services import hooks

# 화재로 취급하는 검출 클래스 → 이벤트 클래스 표기
FIRE_CLASSES = {"flame": "FLAME", "smoke": "SMOKE"}

# event_media.media_url 정본 접두어 — GET /media/<path> 서빙 경로와 같다
MEDIA_URL_PREFIX = "/media/"


def _normalize_media_url(media_url) -> str | None:
    """프레임 경로를 정본 형태 "/media/<상대경로>" 로 맞춘다.

    AI 모델은 MEDIA_ROOT 기준 **상대경로**("events/2026-08-13/1_143005.jpg")를
    보내는데, 이 값을 쓰는 쪽은 전부 "/media/..." 를 기대한다 — 프론트는
    <img src> 에 그대로 넣고, report_service._primary_frame 은 "/media/" 를
    떼어 파일을 읽는다. 그래서 수집 경계인 여기서 한 형태로 못박는다.
    (안 맞추면 프론트는 상대경로 해석으로 404, 119 신고는 이미지 없이 나간다)

    - 이미 "/" 로 시작하면 그대로 둔다 — 접두어가 두 번 붙지 않고,
      의도적으로 절대경로를 넣은 값을 여기서 지어내지 않는다.
    - 빈 문자열/공백은 NULL. "/media/" 만 남으면 디렉터리를 가리키게 된다.
    """
    if not isinstance(media_url, str):
        return None
    url = media_url.strip()
    if not url:
        return None
    if url.startswith("/"):
        return url
    return MEDIA_URL_PREFIX + url


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
    """카메라의 최신 PENDING 이벤트를 관측 창 시작 시각과 함께 가져온다.

    창의 기준점은 event_first_detected_at — 이후 프레임이 아무리 들어와도
    움직이지 않는다.
    """
    cur.execute(
        """
        SELECT e.event_no, e.event_status, e.event_class, e.event_confidence,
               e.event_detected_frames, e.event_threshold_frames,
               e.event_first_detected_at AS window_started_at
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
    media_url = _normalize_media_url(media_url)
    window = timedelta(seconds=config.EVENT_WINDOW_SEC)
    confirmed_no = None

    with db.get_cursor(commit=True) as cur:
        event = _find_open_event(cur, cctv_no)

        # 창 종료: 임계값에 미달한 채 창이 닫혔으므로 기준미달 처리하고 없는 것으로 본다.
        # (여기까지 PENDING 으로 살아 있다는 건 임계값을 못 채웠다는 뜻)
        # 이 프레임은 아래에서 새 이벤트의 최초 감지 프레임이 된다.
        if event and event["window_started_at"] is not None \
                and event["window_started_at"] < captured_at - window:
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
            # 누적: 프레임 수 +1, 클래스 병합, 신뢰도는 최고값 유지.
            # 임계값도 매번 현재 config 값으로 갱신한다 — 창(EVENT_WINDOW_SEC)이
            # 프레임마다 실시간 조회되므로 기준 두 개의 생애주기를 맞춰야 한다.
            cur.execute(
                """
                UPDATE fire_event
                SET event_detected_frames = event_detected_frames + 1,
                    event_class = %s,
                    event_confidence = GREATEST(coalesce(event_confidence, 0), %s),
                    event_threshold_frames = %s
                WHERE event_no = %s
                RETURNING event_no, event_status, event_detected_frames,
                          event_threshold_frames
                """,
                (_merge_class(event["event_class"], frame_classes),
                 frame_conf, config.EVENT_THRESHOLD_FRAMES, event["event_no"]),
            )
            event = dict(cur.fetchone())

        # 프레임 미디어 저장 (검출 목록은 원본 그대로 jsonb 로)
        cur.execute(
            """
            INSERT INTO event_media (event_no, media_url, media_detections,
                                     media_confidence, media_captured_at)
            VALUES (%s, %s, %s::jsonb, %s, %s)
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
    """최초 감지에서 EVENT_WINDOW_SEC 를 넘긴 모든 PENDING 을 DISMISSED 처리.

    다음 프레임이 도착해야 정리되는 걸 기다리지 않고, 창이 닫히는 시점에
    판정을 끝내는 경로다. 4단계 스케줄러가 주기적으로 호출한다.
    처리한 건수를 돌려준다.
    """
    cutoff = (now or datetime.now()) - timedelta(seconds=config.EVENT_WINDOW_SEC)
    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE fire_event e
            SET event_status = 'DISMISSED'
            WHERE e.event_status = 'PENDING'
              AND e.event_first_detected_at < %s
            """,
            (cutoff,),
        )
        return cur.rowcount
