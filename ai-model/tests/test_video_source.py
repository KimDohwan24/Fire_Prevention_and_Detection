"""영상 소스 단위 테스트 — cv2.VideoCapture 대신 가짜를 주입한다."""
import numpy as np
import pytest

from fireguard_detect.video_source import (
    DEFAULT_SOURCE_FPS,
    VideoSource,
    frame_interval,
)


class FakeCapture:
    """cv2.VideoCapture 중 우리가 쓰는 만큼만 흉내낸다.

    grab() 은 디코딩 없이 다음 프레임으로 넘어가고, retrieve() 가 실제로 디코딩한다.
    건너뛸 프레임까지 디코딩하면 1080p 영상에서 디코딩이 병목이 된다.
    """

    def __init__(self, n_frames, fps=30.0, opened=True):
        self._frames = [
            np.full((2, 2, 3), i % 256, dtype=np.uint8) for i in range(n_frames)
        ]
        self._fps = fps
        self._opened = opened
        self._pos = 0
        self.released = False
        self.decoded = []  # retrieve() 로 실제 디코딩한 프레임 번호

    def isOpened(self):
        return self._opened

    def get(self, prop):
        if prop == 7:  # CAP_PROP_FRAME_COUNT
            return len(self._frames)
        return self._fps

    def grab(self):
        if self._pos >= len(self._frames):
            return False
        self._pos += 1
        return True

    def retrieve(self):
        index = self._pos - 1
        if not (0 <= index < len(self._frames)):
            return False, None
        self.decoded.append(index)
        return True, self._frames[index]

    def release(self):
        self.released = True


# ---------------------------------------------------------------- 간격 계산


def test_interval_is_source_over_target():
    assert frame_interval(30.0, 3.0) == 10


def test_interval_rounds_to_nearest():
    assert frame_interval(25.0, 3.0) == 8


def test_interval_never_drops_below_one():
    """목표 fps 가 원본보다 높아도 프레임을 복제하지는 않는다."""
    assert frame_interval(10.0, 30.0) == 1


@pytest.mark.parametrize("bad", [0.0, -1.0, None, float("nan"), 100000.0])
def test_unreadable_source_fps_falls_back_to_default(bad):
    """webm 은 fps 를 0 으로 주는 경우가 있다. 그때도 돌아가야 한다."""
    assert frame_interval(bad, 3.0) == frame_interval(DEFAULT_SOURCE_FPS, 3.0)


# ---------------------------------------------------------------- 순회


def test_yields_every_nth_frame():
    cap = FakeCapture(n_frames=30, fps=30.0)
    source = VideoSource("dummy.mp4", target_fps=3.0, capture=cap)

    indices = [f.index for f in source]

    assert indices == [0, 10, 20]


def test_timestamp_comes_from_source_fps():
    cap = FakeCapture(n_frames=30, fps=30.0)
    source = VideoSource("dummy.mp4", target_fps=3.0, capture=cap)

    stamps = [f.timestamp_sec for f in source]

    assert stamps == pytest.approx([0.0, 1.0 / 3, 2.0 / 3])


def test_source_metadata_contains_duration():
    cap = FakeCapture(n_frames=90, fps=30.0)
    source = VideoSource("dummy.mp4", target_fps=3.0, capture=cap)

    list(source)

    assert source.source_frame_count == 90
    assert source.duration_sec == pytest.approx(3.0)


def test_frame_image_is_carried_through():
    cap = FakeCapture(n_frames=1, fps=30.0)
    source = VideoSource("dummy.mp4", target_fps=3.0, capture=cap)

    (frame,) = list(source)

    assert frame.image.shape == (2, 2, 3)


def test_short_video_still_yields_first_frame():
    """간격보다 짧은 영상이라도 최소 1장은 나와야 한다."""
    cap = FakeCapture(n_frames=3, fps=30.0)
    source = VideoSource("dummy.mp4", target_fps=1.0, capture=cap)

    assert [f.index for f in source] == [0]


def test_skipped_frames_are_never_decoded():
    """건너뛸 프레임은 grab() 으로만 넘긴다.

    1080p50 영상에서 17프레임 중 16장을 헛디코딩하면 디코딩이 추론보다 비싸진다.
    """
    cap = FakeCapture(n_frames=30, fps=30.0)
    source = VideoSource("dummy.mp4", target_fps=3.0, capture=cap)

    list(source)

    assert cap.decoded == [0, 10, 20]


def test_capture_is_released_after_iteration():
    cap = FakeCapture(n_frames=5, fps=30.0)
    source = VideoSource("dummy.mp4", target_fps=30.0, capture=cap)

    list(source)

    assert cap.released is True


def test_capture_is_released_even_if_consumer_stops_early():
    cap = FakeCapture(n_frames=100, fps=30.0)
    source = VideoSource("dummy.mp4", target_fps=30.0, capture=cap)

    for _ in source:
        break
    source.close()

    assert cap.released is True


def test_unopenable_video_fails_with_the_path():
    cap = FakeCapture(n_frames=0, opened=False)
    source = VideoSource("broken.mp4", capture=cap)

    with pytest.raises(OSError, match="broken.mp4"):
        list(source)


def test_missing_file_fails_before_opening(tmp_path):
    with pytest.raises(FileNotFoundError, match="absent.mp4"):
        VideoSource(tmp_path / "absent.mp4")


# ---------------------------------------------------------------- 재생 속도


def test_realtime_off_does_not_sleep():
    slept = []
    cap = FakeCapture(n_frames=30, fps=30.0)
    source = VideoSource("dummy.mp4", target_fps=3.0, capture=cap,
                         realtime=False, sleeper=slept.append)

    list(source)

    assert slept == []


def test_realtime_on_paces_to_the_source_timeline():
    """시연에서는 영상이 실제 속도로 흘러야 한다."""
    slept = []
    clock = iter([0.0] * 10)  # 처리 시간 0 이라고 가정
    cap = FakeCapture(n_frames=30, fps=30.0)
    source = VideoSource("dummy.mp4", target_fps=3.0, capture=cap,
                         realtime=True, sleeper=slept.append,
                         clock=lambda: next(clock))

    list(source)

    # 첫 프레임은 즉시, 이후 두 장은 1/3초 간격
    assert slept == pytest.approx([1.0 / 3, 2.0 / 3])


def test_realtime_never_sleeps_negative_when_processing_is_slow():
    """추론이 느려 이미 늦었으면 자지 않는다 (CPU 추론에서 실제로 일어난다)."""
    slept = []
    clock = iter([0.0, 99.0, 99.0, 99.0, 99.0])
    cap = FakeCapture(n_frames=30, fps=30.0)
    source = VideoSource("dummy.mp4", target_fps=3.0, capture=cap,
                         realtime=True, sleeper=slept.append,
                         clock=lambda: next(clock))

    list(source)

    assert slept == []
