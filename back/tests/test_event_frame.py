"""대표 프레임 로더 테스트 — services/event_frame.py.

이 로더는 119 신고(services/report_service.py)와 텔레그램 화재 알림
(services/alert_service.py)이 **같이** 쓴다. 둘 다 "가장 확실하게 잡힌 프레임에
검출 상자를 그린 그림"이 필요하고, 그 그림을 만드는 규칙이 두 벌로 갈라지면
119 로 간 사진과 사용자에게 간 사진이 서로 다른 화면이 된다.

지키는 성질은 하나다: **이미지 때문에 본 일이 막히면 안 된다.**
대표 행이 없든, 파일이 없든, 이미지로 못 열든 예외 대신 값으로 알린다.

conf 가 가장 높은 프레임을 고르는 일은 여기서 하지 않는다 — event_media.media_is_primary
가 이미 그 프레임을 가리킨다 (services/event_service.py 가 더 높은 conf 프레임이
들어올 때마다 대표를 갈아끼운다).
"""
import io

import pytest
from conftest import make_event, make_media
from PIL import Image

import config
import db
from services import event_frame

FLAME = {"cls": "flame", "conf": 0.91, "box": [0.238, 0.259, 0.047, 0.113]}


@pytest.fixture()
def media_root(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MEDIA_ROOT", str(tmp_path))
    return tmp_path


def write_black_jpeg(media_root, rel_path):
    """MEDIA_ROOT 아래에 검은 100x100 JPEG 를 만든다 (상자 선이 눈에 띄게)."""
    path = media_root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 100), (0, 0, 0)).save(path, "JPEG")
    return path


def red_pixels(content: bytes) -> list:
    im = Image.open(io.BytesIO(content)).convert("RGB")
    return [px for px in im.getdata() if px[0] > 150 and px[1] < 80 and px[2] < 80]


# ---------- 정상 경로 ----------

def test_returns_image_bytes_not_base64(media_root):
    """바이트를 돌려준다 — 텔레그램은 multipart 로 파일을 올려야 해서 base64 가 짐이다.

    119 신고만 base64 가 필요하고 그건 report_service 가 마지막에 감싼다.
    """
    event_no = make_event()
    write_black_jpeg(media_root, f"events/{event_no}/frame.jpg")
    make_media(event_no, is_primary=True, url=f"/media/events/{event_no}/frame.jpg")

    image, detections = event_frame.load_primary_frame(event_no)

    assert isinstance(image, bytes)
    assert detections == [FLAME]


def test_draws_the_detection_boxes_on_the_image(media_root):
    """받는 쪽이 좌표를 해석하지 않아도 발화 위치가 보이게 상자를 그려서 준다."""
    event_no = make_event()
    write_black_jpeg(media_root, f"events/{event_no}/frame.jpg")
    make_media(event_no, is_primary=True, url=f"/media/events/{event_no}/frame.jpg")

    image, _ = event_frame.load_primary_frame(event_no)

    assert red_pixels(image), "검출 상자 선이 그려지지 않았다"


def test_reads_the_primary_frame_and_not_some_other_one(media_root):
    """대표(media_is_primary) 행만 읽는다 — 그 행이 곧 최고 신뢰도 프레임이다."""
    event_no = make_event()
    write_black_jpeg(media_root, f"events/{event_no}/low.jpg")
    write_black_jpeg(media_root, f"events/{event_no}/best.jpg")
    make_media(event_no, is_primary=False, url=f"/media/events/{event_no}/low.jpg",
               confidence=0.51)
    make_media(event_no, is_primary=True, url=f"/media/events/{event_no}/best.jpg",
               confidence=0.97)

    # 대표가 아닌 파일을 지워도 결과가 나온다 = 대표 쪽을 읽었다는 뜻
    (media_root / "events" / str(event_no) / "low.jpg").unlink()

    image, _ = event_frame.load_primary_frame(event_no)

    assert image is not None


# ---------- 실패해도 값으로만 알린다 ----------

def test_returns_nothing_when_the_event_has_no_media(media_root):
    image, detections = event_frame.load_primary_frame(make_event())

    assert (image, detections) == (None, None)


def test_returns_nothing_when_the_file_is_gone(media_root):
    """디스크에 파일이 없어도 예외가 아니라 (None, None)."""
    event_no = make_event()
    make_media(event_no, is_primary=True, url=f"/media/events/{event_no}/ghost.jpg")

    assert event_frame.load_primary_frame(event_no) == (None, None)


def test_returns_nothing_when_the_url_shape_is_unexpected(media_root):
    """"/media/" 로 시작하지 않는 경로는 우리가 해석할 수 있는 값이 아니다.

    임의 경로를 그대로 열면 MEDIA_ROOT 밖의 파일을 읽게 된다.
    """
    event_no = make_event()
    make_media(event_no, is_primary=True, url="https://example.com/frame.jpg")

    assert event_frame.load_primary_frame(event_no) == (None, None)


def test_falls_back_to_the_raw_bytes_when_the_image_cannot_be_parsed(media_root):
    """이미지로 못 여는 파일이면 상자 그리기를 포기하고 원본을 그대로 준다."""
    event_no = make_event()
    path = media_root / "events" / str(event_no) / "frame.jpg"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xd8fake-jpeg-bytes")
    make_media(event_no, is_primary=True, url=f"/media/events/{event_no}/frame.jpg")

    image, _ = event_frame.load_primary_frame(event_no)

    assert image == b"\xff\xd8fake-jpeg-bytes"


def test_keeps_the_original_when_there_is_nothing_to_draw(media_root):
    """화재 클래스 검출이 없으면 다시 인코딩하지 않고 원본 바이트 그대로."""
    event_no = make_event()
    path = write_black_jpeg(media_root, f"events/{event_no}/frame.jpg")
    make_media(event_no, is_primary=True, url=f"/media/events/{event_no}/frame.jpg")
    db.execute(
        "UPDATE event_media SET media_detections = %s::jsonb WHERE event_no = %s",
        ('[{"cls":"person","conf":0.8,"box":[0.1,0.1,0.2,0.2]}]', event_no),
    )

    image, _ = event_frame.load_primary_frame(event_no)

    assert image == path.read_bytes()


# ---------- 검출 좌표 형식 호환 (draw_detections) ----------
# media_detections 에는 세대가 다른 세 형식이 섞여 있다:
#   * "box"                      — 초기 실시간 수집 형식, xywhn(중심·폭·높이 0~1 비율)
#   * "bbox" (형식 마커 없음)    — AI 검출기(detector.py) 원본, 픽셀 xyxy
#   * "bbox" + "bbox_format": "xywhn" — 영상 테스트(video_test.py) 증거
# 예전에는 "box" 만 읽어서 나머지 두 형식이 조용히 no-op 이 됐고, 119 사진과
# 텔레그램 사진이 전부 상자 없는 맨 이미지로 나갔다. 어느 형식이든 그려져야 한다.

def black_jpeg_bytes(size=(100, 100)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (0, 0, 0)).save(buffer, "JPEG")
    return buffer.getvalue()


def test_draws_pixel_xyxy_bbox_from_the_detector():
    """검출기 원본 형식: bbox = 픽셀 [x1, y1, x2, y2], 형식 마커 없음."""
    original = black_jpeg_bytes()

    out = event_frame.draw_detections(original, [
        {"cls": "flame", "conf": 0.85, "bbox": [10, 20, 60, 80]},
    ])

    assert out != original, "픽셀 xyxy 검출인데 아무것도 그려지지 않았다"
    assert red_pixels(out)


def test_clamps_pixel_bbox_that_leaves_the_image():
    """이미지 밖으로 나간 픽셀 좌표는 경계로 잘라서라도 그린다.

    실측: event 69 의 bbox 는 원본 해상도 기준이라 리사이즈된 프레임을 넘을 수 있다.
    """
    original = black_jpeg_bytes()

    out = event_frame.draw_detections(original, [
        {"cls": "flame", "conf": 0.85, "bbox": [50, 50, 400, 500]},
    ])

    assert out != original
    assert red_pixels(out)


def test_draws_xywhn_bbox_with_format_marker():
    """영상 테스트 증거 형식: bbox = [cx, cy, w, h] 비율 + bbox_format 마커."""
    original = black_jpeg_bytes()

    out = event_frame.draw_detections(original, [
        {"cls": "smoke", "conf": 0.5, "bbox": [0.5, 0.5, 0.2, 0.2],
         "bbox_format": "xywhn"},
    ])

    assert out != original
    assert red_pixels(out)


def test_still_draws_the_legacy_box_key():
    """기존 "box" 키(xywhn 비율)는 하위 호환으로 계속 그린다."""
    original = black_jpeg_bytes()

    out = event_frame.draw_detections(original, [FLAME])

    assert out != original
    assert red_pixels(out)


def test_skips_broken_or_non_fire_detections():
    """못 읽는 검출은 건너뛰고, 그릴 것이 없으면 원본 바이트 그대로(재인코딩 금지)."""
    original = black_jpeg_bytes()

    out = event_frame.draw_detections(original, [
        {"cls": "person", "conf": 0.9, "bbox": [10, 10, 50, 50]},   # 화재 클래스 아님
        {"cls": "flame", "conf": 0.9, "bbox": [10, 10, 50]},        # 좌표가 4개가 아님
        {"cls": "flame", "conf": 0.9, "bbox": [1, 2, 3, 4],
         "bbox_format": "xyxyn"},                                    # 모르는 형식 마커
        {"cls": "flame", "conf": 0.9},                               # 좌표 없음
    ])

    assert out == original


# ---------- 경로 이탈 방어 ----------
# media_url 은 AI 모델이 내부 검출 API 로 보내는 값이다(services/event_service.py 의
# process_detection). "/" 로 시작하면 그대로 저장되므로 "/media/../.." 같은 값이
# DB 에 들어올 수 있고, 실제로 개발 DB 에 그런 행이 남아 있었다.
#
# 접두어만 확인하고 떼어내면 MEDIA_ROOT 바깥 파일을 읽게 된다. 그 바이트는 이제
# 텔레그램(사진)과 119(base64)로 **바깥에 나간다** — 파일 유출 경로가 된다.
# 서빙 라우트(routes/media_routes.py)는 send_from_directory 의 safe_join 이 막아
# 주지만 이 로더는 파일을 직접 열므로 스스로 막아야 한다.

def test_a_traversal_url_reads_nothing(media_root, tmp_path):
    """/media/../<파일> 로 MEDIA_ROOT 바깥을 노리는 값은 거절한다."""
    secret = tmp_path.parent / "secret.txt"
    secret.write_bytes(b"top secret")
    event_no = make_event()
    make_media(event_no, is_primary=True, url=f"/media/../{secret.name}")

    image, detections = event_frame.load_primary_frame(event_no)

    assert image is None
    assert detections is None


def test_a_deep_traversal_url_reads_nothing(media_root, tmp_path):
    event_no = make_event()
    make_media(event_no, is_primary=True, url="/media/../../../../../../Windows/win.ini")

    assert event_frame.load_primary_frame(event_no) == (None, None)


def test_an_encoded_traversal_url_reads_nothing(media_root, tmp_path):
    """퍼센트 인코딩된 ../ 도 막는다 — 저장 시점에 디코딩돼 들어올 수 있다."""
    secret = tmp_path.parent / "secret2.txt"
    secret.write_bytes(b"top secret")
    event_no = make_event()
    make_media(event_no, is_primary=True, url=f"/media/%2e%2e/{secret.name}")

    assert event_frame.load_primary_frame(event_no) == (None, None)


def test_a_normal_nested_path_still_works(media_root):
    """방어가 정상 경로까지 막으면 안 된다 — 실제 프레임은 하위 폴더에 쌓인다."""
    write_black_jpeg(media_root, "events/2026-08-22/1_143005.jpg")
    event_no = make_event()
    make_media(event_no, is_primary=True, url="/media/events/2026-08-22/1_143005.jpg")

    image, _ = event_frame.load_primary_frame(event_no)

    assert image is not None
