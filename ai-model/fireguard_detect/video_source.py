"""영상 파일에서 추론할 프레임만 골라 내보낸다.

원본 30fps 를 전부 추론할 이유가 없다. 백엔드는 프레임 수만 세고(EVENT_THRESHOLD_FRAMES),
CPU 추론은 프레임당 수십 ms 가 든다. 초당 몇 장만 뽑아 쓴다.
"""
import time
from dataclasses import dataclass
from pathlib import Path

# webm 등에서 fps 를 못 읽는 경우가 있다. 그때 가정할 값.
DEFAULT_SOURCE_FPS = 30.0
# 이보다 큰 fps 는 컨테이너가 잘못 준 값으로 본다 (1000fps 짜리 CCTV 는 없다)
MAX_PLAUSIBLE_FPS = 1000.0


@dataclass
class Frame:
    index: int          # 원본 영상에서의 프레임 번호
    timestamp_sec: float  # 원본 시간축에서의 위치(초)
    image: object       # BGR ndarray


def _sane_fps(fps) -> float:
    """읽어 온 fps 가 쓸 만한 값인지 보고, 아니면 기본값으로 되돌린다."""
    try:
        value = float(fps)
    except (TypeError, ValueError):
        return DEFAULT_SOURCE_FPS
    if not (0 < value <= MAX_PLAUSIBLE_FPS) or value != value:  # NaN 은 자기 자신과 다르다
        return DEFAULT_SOURCE_FPS
    return value


def frame_interval(source_fps, target_fps: float) -> int:
    """몇 프레임마다 한 장을 뽑을지. 최소 1 (프레임을 복제하지는 않는다)."""
    return max(1, round(_sane_fps(source_fps) / target_fps))


def _sane_frame_count(value) -> int | None:
    """컨테이너가 알려 준 전체 프레임 수를 검증한다."""
    try:
        count = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return count if count > 0 else None


class VideoSource:
    """영상 파일을 열어 `Frame` 을 순서대로 내보낸다.

    `capture` 를 주면 그걸 쓰고(테스트용), 없으면 cv2.VideoCapture 로 연다.
    `realtime=True` 면 원본 시간축에 맞춰 대기한다 — 시연에서 영상이 2배속으로
    지나가면 곤란하기 때문이다.
    """

    def __init__(self, path, target_fps: float = 3.0, realtime: bool = False,
                 capture=None, sleeper=time.sleep, clock=time.monotonic):
        self.path = Path(path)
        self.target_fps = target_fps
        self.realtime = realtime
        self._sleep = sleeper
        self._clock = clock

        if capture is not None:
            self._capture = capture
        else:
            if not self.path.exists():
                raise FileNotFoundError(f"영상 파일을 찾을 수 없습니다: {self.path}")
            import cv2

            self._capture = cv2.VideoCapture(str(self.path))

        self.source_fps = None
        self.source_frame_count = None
        self.duration_sec = None
        self.interval = None

    def close(self):
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def __iter__(self):
        if not self._capture.isOpened():
            raise OSError(f"영상을 열 수 없습니다: {self.path}")

        import_cv2_prop_fps = 5  # cv2.CAP_PROP_FPS — cv2 없이도 테스트되게 상수로 둔다
        import_cv2_prop_frame_count = 7  # cv2.CAP_PROP_FRAME_COUNT
        self.source_fps = _sane_fps(self._capture.get(import_cv2_prop_fps))
        self.source_frame_count = _sane_frame_count(
            self._capture.get(import_cv2_prop_frame_count)
        )
        if self.source_frame_count is not None:
            self.duration_sec = self.source_frame_count / self.source_fps
        self.interval = frame_interval(self.source_fps, self.target_fps)

        started_at = None
        index = 0
        try:
            while True:
                # grab() 은 디코딩하지 않고 다음 프레임으로만 넘어간다. 쓸 프레임만
                # retrieve() 로 디코딩한다 — 1080p 영상에서는 이게 추론보다 비싸다.
                if not self._capture.grab():
                    return
                if index % self.interval == 0:
                    ok, image = self._capture.retrieve()
                    if not ok:
                        return
                    timestamp = index / self.source_fps
                    if self.realtime:
                        if started_at is None:
                            started_at = self._clock()
                        else:
                            behind = timestamp - (self._clock() - started_at)
                            if behind > 0:
                                self._sleep(behind)
                    yield Frame(index=index, timestamp_sec=timestamp, image=image)
                index += 1
        finally:
            self.close()
