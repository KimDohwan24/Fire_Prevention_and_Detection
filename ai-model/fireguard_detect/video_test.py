"""영상 전체를 분석해 FIRE/NO_FIRE와 최대 3장의 증거 프레임을 만든다."""
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from fireguard_detect.video_source import Frame

FIRE_CLASS_NAMES = {"flame": "FLAME", "smoke": "SMOKE"}
ROLE_ORDER = ("FIRST", "CONFIRMATION", "PEAK")


@dataclass
class EvidenceFrame:
    frame_index: int
    offset_sec: float
    image: object
    detections: list[dict]
    confidence: float
    roles: set[str] = field(default_factory=set)

    def metadata(self, file_field: str) -> dict:
        return {
            "file_field": file_field,
            "frame_index": self.frame_index,
            "offset_sec": self.offset_sec,
            "confidence": self.confidence,
            "roles": [role for role in ROLE_ORDER if role in self.roles],
            "detections": self.detections,
        }


@dataclass
class VideoTestDecision:
    result: str
    processed_frames: int
    positive_frames: int
    threshold_frames: int
    window_sec: float
    first_detected_offset_sec: float | None
    confirmed_offset_sec: float | None
    max_confidence: float | None
    detected_classes: list[str]
    duration_sec: float
    source_fps: float
    evidence: list[EvidenceFrame]


def normalize_fire_detections(detections: list[dict], image_shape) -> list[dict]:
    """픽셀 xyxy 검출을 저장 계약인 YOLO xywhn 좌표로 바꾼다."""
    height, width = image_shape[:2]
    if width <= 0 or height <= 0:
        raise ValueError("프레임 크기가 올바르지 않습니다.")

    normalized = []
    for detection in detections:
        if not isinstance(detection, dict) or detection.get("cls") not in FIRE_CLASS_NAMES:
            continue
        bbox = detection.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        try:
            x1, y1, x2, y2 = (float(value) for value in bbox)
            confidence = float(detection["conf"])
        except (KeyError, TypeError, ValueError):
            continue

        x1, x2 = sorted((max(0.0, min(float(width), x1)),
                         max(0.0, min(float(width), x2))))
        y1, y2 = sorted((max(0.0, min(float(height), y1)),
                         max(0.0, min(float(height), y2))))
        box_width = x2 - x1
        box_height = y2 - y1
        if box_width <= 0 or box_height <= 0:
            continue
        normalized.append({
            "cls": detection["cls"],
            "conf": confidence,
            "bbox": [
                round((x1 + x2) / 2 / width, 6),
                round((y1 + y2) / 2 / height, 6),
                round(box_width / width, 6),
                round(box_height / height, 6),
            ],
            "bbox_format": "xywhn",
        })
    normalized.sort(key=lambda item: item["conf"], reverse=True)
    return normalized


def _copy_image(image):
    copy = getattr(image, "copy", None)
    return copy() if callable(copy) else image


def _snapshot(frame: Frame, detections: list[dict]) -> EvidenceFrame:
    return EvidenceFrame(
        frame_index=frame.index,
        offset_sec=float(frame.timestamp_sec),
        image=_copy_image(frame.image),
        detections=detections,
        confidence=max(item["conf"] for item in detections),
    )


class VideoDecisionEngine:
    """최초 양성 프레임에 고정된 관측 창을 영상 끝까지 반복 적용한다."""

    def __init__(self, *, window_sec: float = 60, threshold_frames: int = 10):
        if window_sec <= 0:
            raise ValueError("window_sec 는 0보다 커야 합니다.")
        if threshold_frames <= 0:
            raise ValueError("threshold_frames 는 1 이상이어야 합니다.")
        self.window_sec = float(window_sec)
        self.threshold_frames = int(threshold_frames)
        self.processed_frames = 0
        self.positive_frames = 0
        self.detected_classes: set[str] = set()
        self._window_started_at = None
        self._window_positive_frames = 0
        self._first = None
        self._confirmation = None
        self._peak = None
        self._last_offset = 0.0

    def add(self, frame: Frame, detections: list[dict]):
        self.processed_frames += 1
        self._last_offset = max(self._last_offset, float(frame.timestamp_sec))
        fire_detections = normalize_fire_detections(detections, frame.image.shape)
        if not fire_detections:
            return

        self.positive_frames += 1
        self.detected_classes.update(
            FIRE_CLASS_NAMES[item["cls"]] for item in fire_detections
        )
        current = _snapshot(frame, fire_detections)
        if self._first is None:
            self._first = current
        if self._peak is None or current.confidence > self._peak.confidence:
            self._peak = current

        offset = float(frame.timestamp_sec)
        if self._window_started_at is None \
                or offset - self._window_started_at > self.window_sec:
            self._window_started_at = offset
            self._window_positive_frames = 1
        else:
            self._window_positive_frames += 1

        if self._confirmation is None \
                and self._window_positive_frames >= self.threshold_frames:
            self._confirmation = current

    @property
    def first_detected_offset_sec(self) -> float | None:
        return self._first.offset_sec if self._first else None

    @property
    def confirmed_offset_sec(self) -> float | None:
        return self._confirmation.offset_sec if self._confirmation else None

    @property
    def is_confirmed(self) -> bool:
        return self._confirmation is not None

    @property
    def max_confidence(self) -> float | None:
        return self._peak.confidence if self._peak else None

    def finish(self, *, duration_sec: float | None, source_fps: float) -> VideoTestDecision:
        if self.processed_frames == 0:
            raise ValueError("영상에서 처리할 프레임을 읽지 못했습니다.")
        fallback_duration = self._last_offset + (1 / source_fps)
        duration = max(float(duration_sec or 0), fallback_duration)

        selected: dict[int, EvidenceFrame] = {}
        for role, candidate in (
            ("FIRST", self._first),
            ("CONFIRMATION", self._confirmation),
            ("PEAK", self._peak),
        ):
            if candidate is None:
                continue
            existing = selected.get(candidate.frame_index)
            if existing is None:
                existing = candidate
                selected[candidate.frame_index] = existing
            existing.roles.add(role)

        evidence = sorted(selected.values(), key=lambda item: item.offset_sec)
        return VideoTestDecision(
            result="FIRE" if self._confirmation is not None else "NO_FIRE",
            processed_frames=self.processed_frames,
            positive_frames=self.positive_frames,
            threshold_frames=self.threshold_frames,
            window_sec=self.window_sec,
            first_detected_offset_sec=(self._first.offset_sec if self._first else None),
            confirmed_offset_sec=(self._confirmation.offset_sec
                                  if self._confirmation else None),
            max_confidence=(self._peak.confidence if self._peak else None),
            detected_classes=[name for name in ("FLAME", "SMOKE")
                              if name in self.detected_classes],
            duration_sec=duration,
            source_fps=float(source_fps),
            evidence=evidence,
        )


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(*, decision: VideoTestDecision, cctv_no: int,
                   video_path, weights_path, detector, inference_fps: float,
                   started_at: datetime, finished_at: datetime,
                   job_id: str | None = None) -> dict:
    """백엔드 POST /api/internal/video-tests 계약을 만든다."""
    manifest = {
        "cctv_no": cctv_no,
        "result": decision.result,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "video": {
            "name": Path(video_path).name,
            "duration_sec": decision.duration_sec,
            "source_fps": decision.source_fps,
        },
        "model": {
            "filename": Path(weights_path).name,
            "sha256": sha256_file(weights_path),
            "confidence": float(detector.conf),
            "iou": float(detector.iou),
            "imgsz": int(detector.imgsz),
            "device": detector.device,
            "inference_fps": float(inference_fps),
            "max_det": int(detector.max_det),
        },
        "statistics": {
            "processed_frames": decision.processed_frames,
            "positive_frames": decision.positive_frames,
            "threshold_frames": decision.threshold_frames,
            "window_sec": decision.window_sec,
            "first_detected_offset_sec": decision.first_detected_offset_sec,
            "confirmed_offset_sec": decision.confirmed_offset_sec,
            "max_confidence": decision.max_confidence,
            "detected_classes": decision.detected_classes,
        },
        "evidence": [
            item.metadata(f"evidence_{index}")
            for index, item in enumerate(decision.evidence)
        ],
    }
    if job_id:
        manifest["job_id"] = job_id
    return manifest
