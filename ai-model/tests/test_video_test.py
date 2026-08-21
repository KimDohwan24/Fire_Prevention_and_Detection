"""영상 단위 FIRE/NO_FIRE 판정과 증거 프레임 선택 테스트."""
from datetime import datetime

import numpy as np
import pytest

from fireguard_detect.video_source import Frame
from fireguard_detect.video_test import (
    VideoDecisionEngine,
    build_manifest,
    normalize_fire_detections,
)


def frame(index, second):
    return Frame(index=index, timestamp_sec=second,
                 image=np.zeros((100, 200, 3), dtype=np.uint8))


def flame(confidence=0.8, bbox=None):
    return {
        "cls": "flame",
        "conf": confidence,
        "bbox": bbox or [20, 10, 120, 60],
    }


def finish(engine, duration=120):
    return engine.finish(duration_sec=duration, source_fps=30)


def test_no_positive_frames_is_no_fire_without_evidence():
    engine = VideoDecisionEngine(window_sec=60, threshold_frames=3)
    for index in range(5):
        engine.add(frame(index, index), [])

    decision = finish(engine)

    assert decision.result == "NO_FIRE"
    assert decision.processed_frames == 5
    assert decision.positive_frames == 0
    assert decision.evidence == []
    assert decision.first_detected_offset_sec is None


def test_threshold_inside_fixed_window_confirms_fire():
    engine = VideoDecisionEngine(window_sec=60, threshold_frames=3)
    for index, second in enumerate((5, 30, 60)):
        engine.add(frame(index, second), [flame(0.7 + index * 0.1)])

    decision = finish(engine)

    assert decision.result == "FIRE"
    assert decision.confirmed_offset_sec == 60
    assert decision.positive_frames == 3


def test_failed_window_resets_and_later_window_can_confirm():
    engine = VideoDecisionEngine(window_sec=60, threshold_frames=3)
    # 0초 창은 두 프레임으로 실패. 61초부터 새 창이 열려 세 프레임으로 확정된다.
    for index, second in enumerate((0, 30, 61, 70, 80)):
        engine.add(frame(index, second), [flame()])

    decision = finish(engine)

    assert decision.result == "FIRE"
    assert decision.confirmed_offset_sec == 80
    assert decision.first_detected_offset_sec == 0


def test_exact_window_boundary_is_included():
    engine = VideoDecisionEngine(window_sec=60, threshold_frames=2)
    engine.add(frame(0, 10), [flame()])
    engine.add(frame(1, 70), [flame()])

    assert finish(engine).result == "FIRE"


def test_analysis_keeps_counting_frames_after_fire_confirmation():
    engine = VideoDecisionEngine(window_sec=60, threshold_frames=1)
    engine.add(frame(0, 0), [flame()])
    for index in range(1, 6):
        engine.add(frame(index, index), [])

    decision = finish(engine)

    assert decision.result == "FIRE"
    assert decision.processed_frames == 6


def test_evidence_is_first_confirmation_and_peak_with_max_three_images():
    engine = VideoDecisionEngine(window_sec=60, threshold_frames=2)
    engine.add(frame(10, 1), [flame(0.5)])
    engine.add(frame(20, 2), [flame(0.7)])  # confirmation
    engine.add(frame(30, 3), [flame(0.95)])  # peak

    decision = finish(engine)

    assert len(decision.evidence) == 3
    assert [item.roles for item in decision.evidence] == [
        {"FIRST"}, {"CONFIRMATION"}, {"PEAK"}
    ]


def test_same_frame_roles_are_deduplicated():
    engine = VideoDecisionEngine(window_sec=60, threshold_frames=1)
    engine.add(frame(10, 1), [flame(0.9)])

    decision = finish(engine)

    assert len(decision.evidence) == 1
    assert decision.evidence[0].roles == {"FIRST", "CONFIRMATION", "PEAK"}


def test_pixel_xyxy_is_converted_to_normalized_xywh():
    normalized = normalize_fire_detections(
        [flame(0.8, bbox=[20, 10, 120, 60])],
        (100, 200, 3),
    )

    assert normalized[0]["bbox"] == pytest.approx([0.35, 0.35, 0.5, 0.5])
    assert normalized[0]["bbox_format"] == "xywhn"


def test_non_fire_classes_do_not_count():
    engine = VideoDecisionEngine(window_sec=60, threshold_frames=1)
    engine.add(frame(0, 0), [{"cls": "person", "conf": 0.99,
                              "bbox": [0, 0, 100, 100]}])

    assert finish(engine).result == "NO_FIRE"


def test_manifest_contains_replaceable_model_identity(tmp_path):
    weights = tmp_path / "next_model.pt"
    weights.write_bytes(b"weights")
    engine = VideoDecisionEngine(window_sec=60, threshold_frames=1)
    engine.add(frame(0, 0), [flame(0.9)])
    decision = finish(engine, duration=1)

    class FakeDetector:
        conf = 0.25
        iou = 0.7
        imgsz = 640
        device = "cpu"
        max_det = 10

    manifest = build_manifest(
        decision=decision,
        cctv_no=3,
        video_path=tmp_path / "input.mp4",
        weights_path=weights,
        detector=FakeDetector(),
        inference_fps=3,
        started_at=datetime(2026, 8, 19, 10, 0),
        finished_at=datetime(2026, 8, 19, 10, 1),
    )

    assert manifest["model"]["filename"] == "next_model.pt"
    assert len(manifest["model"]["sha256"]) == 64
    assert manifest["evidence"][0]["roles"] == ["FIRST", "CONFIRMATION", "PEAK"]
