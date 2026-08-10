"""검출기 단위 테스트 — 실제 YOLO 대신 가짜 모델을 주입해서 돌린다.

여기서 지키려는 계약은 하나다: 백엔드(`event_service.FIRE_CLASSES`)가 알아듣는
클래스 이름(`flame`/`smoke`)으로 나가야 한다. 모델은 `fire` 라고 부른다.
"""
import numpy as np
import pytest

from fireguard_detect.detector import CLASS_MAP, Detector


class FakeBox:
    def __init__(self, cls_id, conf, xyxy):
        self.cls = [cls_id]
        self.conf = [conf]
        self.xyxy = [xyxy]


class FakeResult:
    def __init__(self, names, boxes):
        self.names = names
        self.boxes = boxes


class FakeModel:
    """ultralytics YOLO 의 predict() 만 흉내낸다."""

    def __init__(self, names, boxes):
        self._result = FakeResult(names, boxes)
        self.calls = []

    def predict(self, frame, **kwargs):
        self.calls.append(kwargs)
        return [self._result]


FIRE_SMOKE_NAMES = {0: "fire", 1: "smoke"}


def make_detector(boxes, names=None, **kwargs):
    model = FakeModel(names or FIRE_SMOKE_NAMES, boxes)
    return Detector(model=model, **kwargs), model


def test_fire_is_renamed_to_flame():
    """모델의 'fire' 는 백엔드가 기다리는 'flame' 으로 나가야 한다."""
    det, _ = make_detector([FakeBox(0, 0.9, [10, 20, 110, 220])])

    result = det.detect(np.zeros((4, 4, 3), dtype=np.uint8))

    assert [d["cls"] for d in result] == ["flame"]


def test_smoke_keeps_its_name():
    det, _ = make_detector([FakeBox(1, 0.8, [0, 0, 5, 5])])

    result = det.detect(np.zeros((4, 4, 3), dtype=np.uint8))

    assert [d["cls"] for d in result] == ["smoke"]


def test_class_map_only_renames_fire():
    """매핑표가 조용히 늘어나면 백엔드와 어긋난다 — 여기서 고정한다."""
    assert CLASS_MAP == {"fire": "flame"}


def test_detection_shape():
    det, _ = make_detector([FakeBox(0, 0.875, [10.4, 20.6, 110.2, 220.9])])

    (one,) = det.detect(np.zeros((4, 4, 3), dtype=np.uint8))

    assert set(one) == {"cls", "conf", "bbox"}
    assert one["conf"] == pytest.approx(0.875)
    assert one["bbox"] == [pytest.approx(10.4), pytest.approx(20.6),
                           pytest.approx(110.2), pytest.approx(220.9)]


def test_below_threshold_is_dropped():
    """ultralytics 가 이미 걸러주지만, 임계값은 우리 쪽에서도 확정적이어야 한다."""
    det, _ = make_detector(
        [FakeBox(0, 0.9, [0, 0, 1, 1]), FakeBox(1, 0.10, [0, 0, 1, 1])],
        conf=0.25,
    )

    result = det.detect(np.zeros((4, 4, 3), dtype=np.uint8))

    assert [d["cls"] for d in result] == ["flame"]


def test_unknown_class_passes_through_unchanged():
    """person 같은 클래스가 섞여도 죽지 않는다. 화재 판정은 백엔드가 걸러낸다."""
    det, _ = make_detector([FakeBox(2, 0.9, [0, 0, 1, 1])],
                           names={0: "fire", 1: "smoke", 2: "person"})

    (one,) = det.detect(np.zeros((4, 4, 3), dtype=np.uint8))

    assert one["cls"] == "person"


def test_keeps_only_the_highest_confidence_detections():
    """신뢰도가 보정되지 않은 가중치는 프레임당 수십 개를 뱉는다.

    전부 백엔드로 넘기면 media_detections jsonb 가 쓰레기로 불어난다.
    상위 몇 개만 남긴다.
    """
    det, _ = make_detector(
        [FakeBox(0, 0.30, [0, 0, 1, 1]),
         FakeBox(1, 0.90, [0, 0, 2, 2]),
         FakeBox(0, 0.60, [0, 0, 3, 3])],
        max_det=2,
    )

    result = det.detect(np.zeros((4, 4, 3), dtype=np.uint8))

    assert [d["conf"] for d in result] == [pytest.approx(0.9), pytest.approx(0.6)]


def test_max_det_is_passed_to_predict():
    """NMS 단계에서 잘라내야 후처리가 싸다."""
    det, model = make_detector([], max_det=5)

    det.detect(np.zeros((4, 4, 3), dtype=np.uint8))

    assert model.calls[0]["max_det"] == 5


def test_no_boxes_gives_empty_list():
    det, _ = make_detector([])

    assert det.detect(np.zeros((4, 4, 3), dtype=np.uint8)) == []


def test_predict_receives_configured_params():
    det, model = make_detector([], conf=0.4, iou=0.5, imgsz=320, device="cpu")

    det.detect(np.zeros((4, 4, 3), dtype=np.uint8))

    (kwargs,) = model.calls
    assert kwargs["conf"] == 0.4
    assert kwargs["iou"] == 0.5
    assert kwargs["imgsz"] == 320
    assert kwargs["device"] == "cpu"
    assert kwargs["verbose"] is False


def test_auto_device_resolves_to_cpu_without_cuda(monkeypatch):
    """지금은 CPU, 나중에 클라우드 GPU. 'auto' 가 양쪽을 알아서 고른다."""
    monkeypatch.setattr("fireguard_detect.detector.cuda_available", lambda: False)
    det, model = make_detector([], device="auto")

    det.detect(np.zeros((4, 4, 3), dtype=np.uint8))

    assert model.calls[0]["device"] == "cpu"


def test_auto_device_resolves_to_cuda_when_available(monkeypatch):
    monkeypatch.setattr("fireguard_detect.detector.cuda_available", lambda: True)
    det, model = make_detector([], device="auto")

    det.detect(np.zeros((4, 4, 3), dtype=np.uint8))

    assert model.calls[0]["device"] == "cuda:0"


def test_missing_weights_file_fails_with_the_path():
    with pytest.raises(FileNotFoundError, match="nope.pt"):
        Detector(weights="nope.pt")
