"""영상 테스트 CLI 인자와 CCTV 선택 테스트."""
import pytest

import validate_video
from fireguard_detect.video_test_sender import VideoTestSenderError


class FakeSender:
    def __init__(self, items):
        self.items = items

    def list_active_cctvs(self):
        return self.items


def test_defaults_match_current_decision_policy():
    args = validate_video.parse_args(["--video", "input.mp4", "--cctv-no", "1"])

    assert args.fps == 3.0
    assert args.window_sec == 60.0
    assert args.threshold_frames == 10
    assert args.weights.endswith("yolo11n_best.pt")


def test_explicit_cctv_does_not_fetch_list():
    class NeverCalled:
        def list_active_cctvs(self):
            raise AssertionError("목록을 조회하면 안 됨")

    assert validate_video.choose_cctv(NeverCalled(), 7) == 7


def test_missing_cctv_is_selected_from_active_list():
    sender = FakeSender([
        {"cctv_no": 1, "cctv_name": "정문", "cctv_location": "본관"},
        {"cctv_no": 3, "cctv_name": "창고", "cctv_location": "B동"},
    ])

    assert validate_video.choose_cctv(sender, None, input_fn=lambda _: "3") == 3


def test_selection_rejects_cctv_outside_active_list():
    sender = FakeSender([{"cctv_no": 1, "cctv_name": "정문"}])

    with pytest.raises(VideoTestSenderError, match="ACTIVE 목록"):
        validate_video.choose_cctv(sender, None, input_fn=lambda _: "9")


def test_empty_active_list_is_an_error():
    with pytest.raises(VideoTestSenderError, match="ACTIVE CCTV"):
        validate_video.choose_cctv(FakeSender([]), None)


@pytest.mark.parametrize("args", [
    ["--video", "x.mp4", "--fps", "0"],
    ["--video", "x.mp4", "--window-sec", "0"],
    ["--video", "x.mp4", "--threshold-frames", "0"],
    ["--video", "x.mp4", "--conf", "1.1"],
])
def test_invalid_numeric_options_fail_fast(args):
    with pytest.raises(SystemExit):
        validate_video.parse_args(args)
