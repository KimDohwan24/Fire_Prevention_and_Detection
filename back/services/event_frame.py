"""이벤트 대표 프레임 로더 — 검출 상자를 그린 그림 한 장을 만드는 유일한 곳.

**왜 따로 뺐나**: 119 신고(services/report_service.py)와 사용자 화재 알림
(services/alert_service.py)이 같은 그림을 쓴다. 원래 이 로직은 report_service 안에
있었는데, 알림 쪽이 같은 그림을 필요로 하게 되면서 복사하면 규칙이 두 벌로 갈라진다 —
소방서로 간 사진과 사용자가 받은 사진에 상자가 다르게 그려지는 상황이 생긴다.

**conf 가 가장 높은 프레임을 여기서 고르지 않는다.** event_media.media_is_primary 가
이미 그 프레임을 가리킨다 — 프레임이 들어올 때마다 services/event_service.py 가
더 높은 conf 면 대표를 갈아끼운다. 여기서 다시 고르면 두 곳이 서로 다른 기준으로
'대표'를 정하게 되고, 한쪽만 고치는 순간 어긋난다.

**돌려주는 것은 base64 가 아니라 바이트다.** 텔레그램 sendPhoto 는 multipart 로
파일을 올리므로 base64 를 다시 풀어야 하고, 119 신고만 JSON 페이로드라 base64 가
필요하다. 공통 부분은 바이트까지고, 감싸는 일은 필요한 쪽이 한다.

이 모듈이 지키는 성질: **이미지 때문에 본 일(신고·알림)이 막히면 안 된다.**
대표 행이 없든, 파일을 못 읽든, 이미지로 못 열든 예외 대신 값으로 알린다.
"""
import io
import logging
from pathlib import Path

import config
import db

logger = logging.getLogger("fireguard.media")

# media_url 정본 접두어 — services/event_service.py 의 MEDIA_URL_PREFIX 와 같은 값이다.
# (수집 경계에서 이 형태로 못박고, 여기서 떼어 디스크 경로로 되돌린다)
MEDIA_URL_PREFIX = "/media/"


def _pixel_rect(det: dict, width: int, height: int) -> tuple | None:
    """검출 dict 하나에서 픽셀 사각형 (x1, y1, x2, y2) 를 뽑는다.

    media_detections 에는 세대가 다른 세 형식이 섞여 있다:
      * "box"                      — 초기 실시간 수집 형식, xywhn(중심·폭·높이 0~1 비율)
      * "bbox" (형식 마커 없음)    — AI 검출기(ai-model detector.py) 원본, 픽셀 xyxy
      * "bbox" + "bbox_format": "xywhn" — 영상 테스트(video_test.py) 증거
    "box" 만 읽던 시절에는 나머지 두 형식이 조용히 no-op 이 됐고, 119 사진과
    텔레그램 사진이 전부 상자 없는 맨 이미지로 나갔다.

    모르는 형식·깨진 좌표는 None — 그 검출만 건너뛴다. 픽셀 좌표는 원본 해상도
    기준이라 이미지 밖으로 나갈 수 있으므로 경계로 잘라서 그린다.
    """
    if "box" in det:
        values, fmt = det.get("box"), "xywhn"
    else:
        values = det.get("bbox")
        fmt = det.get("bbox_format")
        if fmt is None:
            fmt = "xyxy"  # 검출기 원본은 마커 없이 픽셀 좌표를 보낸다
        elif fmt != "xywhn":
            return None
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        return None
    try:
        a, b, c, d = (float(v) for v in values)
    except (TypeError, ValueError):
        return None
    if fmt == "xywhn":
        x1, y1 = (a - c / 2) * width, (b - d / 2) * height
        x2, y2 = (a + c / 2) * width, (b + d / 2) * height
    else:
        x1, y1, x2, y2 = a, b, c, d
    x1, x2 = sorted((min(max(x1, 0), width - 1), min(max(x2, 0), width - 1)))
    y1, y2 = sorted((min(max(y1, 0), height - 1), min(max(y2, 0), height - 1)))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def draw_detections(content: bytes, detections: list | None) -> bytes:
    """검출 상자(bbox)를 이미지에 그려 넣는다 — 보는 쪽이 좌표를 몰라도 되게.

    좌표 형식은 세 가지를 모두 받는다 (_pixel_rect 참고). 화재 클래스
    (flame/smoke)만 그린다. 어떤 이유로든 실패하면 원본을 그대로 돌려준다 —
    이미지 때문에 신고나 알림이 막히면 안 된다.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        # Pillow 는 requirements.txt 에 선언된 필수 의존성이다. 여기서 아래 일반
        # except 로 함께 삼키면 "설치가 빠졌다"가 경고 한 줄로 묻혀서, 상자 없는
        # 사진이 119 로 나가도 아무도 모른다. 전달 자체는 계속하되(이미지 때문에
        # 신고가 막히면 안 된다) 원인만은 error 로 분명히 남긴다.
        logger.error("Pillow 가 설치돼 있지 않다 — 검출 상자 없이 원본으로 전송한다. "
                     "requirements.txt 를 다시 설치할 것")
        return content

    try:
        im = Image.open(io.BytesIO(content)).convert("RGB")
        draw = ImageDraw.Draw(im)
        width, height = im.size
        drew = False
        for det in detections or []:
            if not isinstance(det, dict) or det.get("cls") not in ("flame", "smoke"):
                continue
            rect = _pixel_rect(det, width, height)
            if rect is None:
                continue
            draw.rectangle(list(rect), outline=(220, 30, 30),
                           width=max(2, width // 300))
            drew = True
        if not drew:
            # 그릴 것이 없으면 원본 그대로. 다시 인코딩하면 화질만 한 번 더 깎인다.
            return content
        out = io.BytesIO()
        im.save(out, "JPEG", quality=90)
        return out.getvalue()
    except Exception as exc:                       # noqa: BLE001
        logger.warning("bbox 그리기 실패 — 원본 이미지로 전송: %s", exc)
        return content


def resolve_media_path(media_url: str) -> Path | None:
    """media_url("/media/<상대경로>")을 디스크 경로로 해석한다.

    두 단계를 확인한다:
      1. 접두어 — 정본 형태가 아니면 우리가 해석할 수 있는 값이 아니다. 접두어를
         떼지 않고 그대로 열면 MEDIA_ROOT 바깥 파일을 읽거나 쓰게 된다.
      2. MEDIA_ROOT 탈출 — 접두어 확인만으로는 부족하다. "/media/../.." 는
         접두어를 통과한 뒤 MEDIA_ROOT 바깥을 가리킨다. media_url 은 AI 모델이
         내부 검출 API 로 보내는 값이고(services/event_service.py 의
         _normalize_media_url 은 "/" 로 시작하면 그대로 통과시킨다), 실제로
         개발 DB 에 그런 행이 남아 있었다.

    호출자가 이 경로로 읽은 바이트는 **바깥으로 나간다**(텔레그램 사진, 119 신고
    페이로드) — 이 구멍은 '엉뚱한 그림이 간다'가 아니라 '서버 파일이 유출된다'에
    가깝다. 쓰기 쪽(annotate_media_file)에서는 반대로 MEDIA_ROOT 밖 파일을
    **덮어쓰는** 구멍이 된다. 서빙 라우트(routes/media_routes.py)는
    send_from_directory 의 safe_join 이 막아 주지만 여기는 파일을 직접 여니
    스스로 막아야 한다.

    형식이 안 맞거나 MEDIA_ROOT 밖이면 None — 호출자가 그 사정에 맞는 로그를 남기고
    조용히 포기한다.
    """
    if not isinstance(media_url, str) or not media_url.startswith(MEDIA_URL_PREFIX):
        return None
    root = Path(config.MEDIA_ROOT).resolve()
    target = (root / media_url[len(MEDIA_URL_PREFIX):]).resolve()
    if not target.is_relative_to(root):
        return None
    return target


def load_primary_frame(event_no: int) -> tuple[bytes | None, list | None]:
    """대표 프레임의 이미지 바이트(검출 상자를 그린)와 검출 좌표를 가져온다.

    반환: (이미지 바이트, 검출 좌표). 대표 프레임이 없거나 파일을 못 읽으면
    (None, None) — 호출자는 이미지 없이 하던 일을 계속하면 된다.
    """
    row = db.query_one(
        """
        SELECT media_url, media_detections FROM event_media
        WHERE event_no = %s AND media_is_primary
        """,
        (event_no,),
    )
    if row is None or not row["media_url"]:
        return None, None

    url = row["media_url"]
    target = resolve_media_path(url)
    if target is None:
        logger.warning("대표 프레임 경로 형식이 예상과 다르거나 MEDIA_ROOT 를 벗어남 — "
                       "이미지 없이 진행 (event_no=%s, url=%s)", event_no, url)
        return None, None
    try:
        content = target.read_bytes()
    except OSError as exc:
        logger.warning("대표 프레임 파일 읽기 실패 — 이미지 없이 진행 (event_no=%s): %s",
                       event_no, exc)
        return None, None

    return draw_detections(content, row["media_detections"]), row["media_detections"]


def annotate_media_file(media_url: str, detections: list | None) -> None:
    """수집 시점에 디스크 프레임 파일 자체를 검출 상자 그린 그림으로 덮어쓴다.

    실제(CCTV_LIVE) 경로는 event_media 적재 때 이 함수를 한 번 호출해 두면
    이후 /media/ 서빙과 119/알림 전송이 모두 같은(상자 있는) 그림을 보게 된다.
    전송 시점의 draw_detections 재호출은 그대로 둔다 — 좌표가 같아 결과가
    같고, 상자 없이 이미 저장된 기존 행과의 하위 호환이 필요하다.

    이 모듈 전체가 지키는 성질 그대로: **이미지 때문에 검출 수집이 막히면
    안 된다.** 경로 불량·파일 없음·읽기/쓰기 실패는 warning 로그 후 조용히
    반환한다 — 절대 raise 하지 않는다.
    """
    target = resolve_media_path(media_url)
    if target is None:
        logger.warning("프레임 경로 형식이 예상과 다르거나 MEDIA_ROOT 를 벗어남 — "
                       "상자 그리기 생략 (url=%s)", media_url)
        return
    try:
        content = target.read_bytes()
    except OSError as exc:
        logger.warning("프레임 파일 읽기 실패 — 상자 그리기 생략 (url=%s): %s",
                       media_url, exc)
        return

    drawn = draw_detections(content, detections)
    if drawn == content:
        # 그릴 것이 없었다 — 재인코딩·쓰기 자체를 생략한다(다시 인코딩하면
        # 화질만 한 번 더 깎이고, 파일은 이미 원본과 같은 내용이다).
        return
    try:
        target.write_bytes(drawn)
    except OSError as exc:
        logger.warning("프레임 파일 쓰기 실패 — 원본 파일 유지 (url=%s): %s",
                       media_url, exc)
