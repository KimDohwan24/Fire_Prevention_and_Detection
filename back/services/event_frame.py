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


def _draw_bboxes(content: bytes, detections: list | None) -> bytes:
    """검출 상자(bbox)를 이미지에 그려 넣는다 — 보는 쪽이 좌표를 몰라도 되게.

    media_detections 에는 두 형식이 실제로 들어온다 (키는 둘 다 "bbox"):
    - 영상 테스트 경로: [cx, cy, w, h] 0~1 비율, "bbox_format": "xywhn"
    - 라이브 검출 경로: [x1, y1, x2, y2] 픽셀 (bbox_format 없음)
    bbox_format 이 없으면 값의 크기로 가른다 — 전부 1 이하면 xywhn 비율,
    아니면 픽셀 xyxy. 화재 클래스(flame/smoke)만 그린다. 어떤 이유로든
    실패하면 원본을 그대로 돌려준다 — 이미지 때문에 신고나 알림이 막히면 안 된다.
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
            box = det.get("bbox") or det.get("box") or []
            if len(box) != 4:
                continue
            values = [float(v) for v in box]
            if det.get("bbox_format") == "xywhn" or max(values) <= 1.0:
                cx, cy, w, h = values
                x1, y1 = (cx - w / 2) * width, (cy - h / 2) * height
                x2, y2 = (cx + w / 2) * width, (cy + h / 2) * height
            else:
                x1, y1, x2, y2 = values
            draw.rectangle([x1, y1, x2, y2], outline=(220, 30, 30),
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
    if not url.startswith(MEDIA_URL_PREFIX):
        # 정본 형태가 아니면 우리가 해석할 수 있는 값이 아니다. 접두어를 떼지 않고
        # 그대로 열면 MEDIA_ROOT 바깥 파일을 읽게 된다.
        logger.warning("대표 프레임 경로 형식이 예상과 다름 — 이미지 없이 진행 "
                       "(event_no=%s, url=%s)", event_no, url)
        return None, None
    # 접두어 확인만으로는 부족하다 — "/media/../.." 는 접두어를 통과한 뒤 MEDIA_ROOT
    # 바깥을 가리킨다. media_url 은 AI 모델이 내부 검출 API 로 보내는 값이고
    # (services/event_service.py 의 _normalize_media_url 은 "/" 로 시작하면 그대로
    # 통과시킨다), 실제로 개발 DB 에 그런 행이 남아 있었다.
    #
    # 여기서 읽은 바이트는 **바깥으로 나간다** — 텔레그램 사진과 119 신고 페이로드다.
    # 즉 이 구멍은 '엉뚱한 그림이 간다'가 아니라 '서버 파일이 유출된다'에 가깝다.
    # 서빙 라우트(routes/media_routes.py)는 send_from_directory 의 safe_join 이
    # 막아 주지만 여기는 파일을 직접 여니 스스로 막아야 한다.
    root = Path(config.MEDIA_ROOT).resolve()
    target = (root / url[len(MEDIA_URL_PREFIX):]).resolve()
    if not target.is_relative_to(root):
        logger.warning("대표 프레임 경로가 MEDIA_ROOT 를 벗어남 — 이미지 없이 진행 "
                       "(event_no=%s, url=%s)", event_no, url)
        return None, None
    try:
        content = target.read_bytes()
    except OSError as exc:
        logger.warning("대표 프레임 파일 읽기 실패 — 이미지 없이 진행 (event_no=%s): %s",
                       event_no, exc)
        return None, None

    return _draw_bboxes(content, row["media_detections"]), row["media_detections"]
