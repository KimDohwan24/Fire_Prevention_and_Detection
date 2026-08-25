"""YOLO 프레임 검출.

백엔드(`back/services/event_service.py`)는 화재 클래스를 `flame` / `smoke` 로 부르는데
학습된 모델은 `fire` / `smoke` 로 부른다. 이름이 어긋나면 불꽃 검출이 통째로
"비화재 프레임"으로 무시되므로, 나가는 길목인 여기서 한 번만 이름을 맞춘다.
"""
from pathlib import Path

# 모델 클래스 이름 → 백엔드가 알아듣는 이름.
# smoke 는 양쪽이 같아서 표에 없다. 표에 없는 이름은 그대로 통과시킨다.
CLASS_MAP = {"fire": "flame"}

DEFAULT_WEIGHTS = Path(__file__).resolve().parent.parent / "yolo11n_best.pt"
DEFAULT_CONF = 0.25
DEFAULT_IOU = 0.7
DEFAULT_IMGSZ = 640
# 프레임당 남길 검출 개수 상한. 신뢰도가 보정되지 않은 가중치는 임계값을 낮추면
# 프레임당 수십 개를 뱉는데, 그대로 넘기면 백엔드 media_detections 가 불어난다.
DEFAULT_MAX_DET = 10


def cuda_available() -> bool:
    """GPU 판별을 함수로 뽑아 둔다 — 테스트에서 갈아끼우고, 클라우드에선 참이 된다."""
    try:
        import torch
    except ImportError:
        return False
    return torch.cuda.is_available()


def resolve_device(device: str) -> str:
    """'auto' 를 실제 장치 이름으로 바꾼다. 나머지는 그대로 쓴다."""
    if device != "auto":
        return device
    return "cuda:0" if cuda_available() else "cpu"


class Detector:
    """프레임 한 장을 받아 검출 목록을 돌려준다.

    `model` 을 주면 그걸 쓰고(테스트용), 없으면 `weights` 에서 YOLO 를 읽는다.
    """

    def __init__(self, weights=None, conf=DEFAULT_CONF, iou=DEFAULT_IOU,
                 imgsz=DEFAULT_IMGSZ, device="auto", max_det=DEFAULT_MAX_DET,
                 model=None):
        self.conf = conf
        self.iou = iou
        self.imgsz = imgsz
        self.max_det = max_det
        self.device = resolve_device(device)

        if model is not None:
            self._model = model
            self.weights_path = None
            return

        path = Path(weights) if weights is not None else DEFAULT_WEIGHTS
        if not path.exists():
            raise FileNotFoundError(f"모델 가중치를 찾을 수 없습니다: {path}")
        self.weights_path = path

        from ultralytics import YOLO  # 무거워서 필요할 때만 읽는다

        self._model = YOLO(str(path))

    def detect(self, frame) -> list[dict]:
        """프레임 1장 → `[{"cls": "flame", "conf": 0.9, "bbox": [x1,y1,x2,y2]}, ...]`"""
        result = self._model.predict(
            frame,
            conf=self.conf,
            iou=self.iou,
            imgsz=self.imgsz,
            device=self.device,
            max_det=self.max_det,
            verbose=False,
        )[0]

        names = result.names
        detections = []
        for box in result.boxes:
            score = float(box.conf[0])
            if score < self.conf:
                continue
            raw_name = names[int(box.cls[0])]
            detections.append({
                "cls": CLASS_MAP.get(raw_name, raw_name),
                "conf": score,
                "bbox": [float(v) for v in box.xyxy[0]],
            })

        detections.sort(key=lambda d: d["conf"], reverse=True)
        return detections[:self.max_det]
