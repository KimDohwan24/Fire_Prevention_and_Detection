"""실제 가중치 인수 테스트 — 이 모델을 시연에 써도 되는가.

2026-08-13 현재 **둘 다 통과한다.**

이 파일은 원래 전부 실패하라고 만든 것이었다. 2026-08-10 의 `best.pt` 는 명백한
화재 이미지와 무작위 노이즈에 거의 같은 점수를 냈고(0.0083 vs 0.0067, 임계값
0.25 의 1/30) 학습 자체가 되지 않은 상태였다. 그 문제는 해결됐다.

2026-08-13 09:25 재학습분 (yolo11n, 10 epoch, imgsz 640) 기준:
- 체크포인트 지표  mAP50 0.785 · mAP50-95 0.447 · precision 0.834 · recall 0.698
- house_fire 5프레임 중 4장 검출 (검출률 0.80, MIN_HIT_RATE 0.30)
- 화재 최고점 0.9002 vs 무작위 노이즈 0.0000

**통과가 "어떤 영상에서도 충분하다"는 뜻은 아니다.** 검출률은 영상과 추론
해상도에 크게 좌우된다. 같은 가중치로 `taipo_apartment_fire.webm` 을 재면
imgsz 640 에서 18%, 960 에서 35% 다 — 이 파일이 초록이어도 640 에서는
MIN_HIT_RATE 에 못 미치는 영상이 있다. 백엔드 확정 임계값이 검출률에 묶여
있으므로(back/config.py:EVENT_THRESHOLD_FRAMES) 대상 영상이 바뀌면 다시 잰다.

    pytest tests --slow -k acceptance
"""
from pathlib import Path

import cv2
import numpy as np
import pytest

from fireguard_detect.detector import Detector

pytestmark = pytest.mark.slow

AI_MODEL_DIR = Path(__file__).resolve().parent.parent
WEIGHTS = AI_MODEL_DIR / "best.pt"
# 연기가 화면을 가득 채우고 창문에 불꽃이 보이는 프레임. 못 잡으면 쓸 수 없다.
SAMPLE_VIDEO = AI_MODEL_DIR / "samples" / "house_fire.webm"

# 실화재 영상에서 이 정도는 잡아야 시연이 성립한다.
# 백엔드가 관측 창 안에서 EVENT_THRESHOLD_FRAMES 개를 누적해야 확정하므로,
# 검출률이 이보다 낮으면 창 안에 프레임이 모이지 않는다.
# (2026-08-13 에 백엔드 기본 임계값을 30 → 10 으로 낮췄다 — 실측 검출 간격
#  3.62초로는 60초 창에 최대 16프레임뿐이라 30 은 도달 불가능했다)
MIN_HIT_RATE = 0.30


@pytest.fixture(scope="module")
def detector():
    if not WEIGHTS.exists():
        pytest.skip(f"가중치 없음: {WEIGHTS}")
    return Detector(weights=WEIGHTS, device="cpu")


@pytest.fixture(scope="module")
def fire_frames():
    if not SAMPLE_VIDEO.exists():
        pytest.skip(f"샘플 영상 없음: {SAMPLE_VIDEO}")
    cap = cv2.VideoCapture(str(SAMPLE_VIDEO))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames = []
    for ratio in (0.2, 0.35, 0.5, 0.65, 0.8):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * ratio))
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
    cap.release()
    if not frames:
        pytest.skip("샘플 영상에서 프레임을 읽지 못했습니다")
    return frames


def test_detects_something_in_a_real_fire_video(detector, fire_frames):
    hits = sum(1 for f in fire_frames if detector.detect(f))

    assert hits / len(fire_frames) >= MIN_HIT_RATE, (
        f"{len(fire_frames)}장 중 {hits}장에서만 검출됨 — 재학습이 필요하다"
    )


def test_reacts_more_to_fire_than_to_random_noise(detector, fire_frames):
    """모델이 화재를 '보고 있는지' 가리는 대조 실험.

    노이즈보다 확실히 높은 점수가 나와야 한다. 비슷하면 학습이 안 된 것이다.
    """
    rng = np.random.default_rng(42)
    noise = rng.integers(0, 256, size=fire_frames[0].shape, dtype=np.uint8)

    fire_top = max(_top_score(detector, f) for f in fire_frames)
    noise_top = _top_score(detector, noise)

    assert fire_top > noise_top * 3, (
        f"화재 최고점 {fire_top:.4f} vs 노이즈 {noise_top:.4f} — "
        f"모델이 화재와 노이즈를 구분하지 못한다"
    )


def _top_score(detector, image) -> float:
    """임계값을 무시한 최고 점수. conf 0 으로 낮춰 원시 반응을 본다."""
    original = detector.conf
    detector.conf = 0.001
    try:
        found = detector.detect(image)
    finally:
        detector.conf = original
    return max((d["conf"] for d in found), default=0.0)
