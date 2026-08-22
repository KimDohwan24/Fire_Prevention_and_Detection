"""Evaluate image-level background false positives without retraining.

Run this file from any directory. Paths are resolved relative to this file.
"""

import importlib.util
import os
import csv
from argparse import ArgumentParser
from pathlib import Path

import cv2
import numpy as np


# Must be set before the original module imports torch.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")


BASE_DIR = Path(__file__).resolve().parent
ORIGINAL_SCRIPT = BASE_DIR / "yolo11_m_version_test.py"
DEFAULT_MODEL = (
    BASE_DIR
    / "runs"
    / "data"
    / "fire_yolo11m_tuned_e50"
    / "weights"
    / "best.pt"
)
DEFAULT_OUTPUT = BASE_DIR / "runs" / "data" / "background_fp_evaluation"


def load_original_module():
    if not ORIGINAL_SCRIPT.exists():
        raise FileNotFoundError(f"Original script not found: {ORIGINAL_SCRIPT}")

    spec = importlib.util.spec_from_file_location("fire_yolo_base", ORIGINAL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args():
    parser = ArgumentParser()
    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL,
        help="Path to best.pt (default: tuned experiment best.pt)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Directory in which evaluation CSV files are saved",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Operational confidence threshold",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=1,
        help="Inference batch size (default: 1 for low GPU memory use)",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Inference image size (use 512 or 416 if 640 still fails)",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Override device, for example 0 or cpu",
    )
    return parser.parse_args()


def load_letterboxed_image(image_path, size):
    """Decode on CPU and return an explicitly bounded square BGR image."""
    encoded = np.fromfile(str(image_path), dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not decode image: {image_path}")

    height, width = image.shape[:2]
    ratio = min(size / width, size / height)
    new_width = max(1, round(width * ratio))
    new_height = max(1, round(height * ratio))
    resized = cv2.resize(
        image,
        (new_width, new_height),
        interpolation=cv2.INTER_AREA if ratio < 1 else cv2.INTER_LINEAR,
    )

    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    left = (size - new_width) // 2
    top = (size - new_height) // 2
    canvas[top : top + new_height, left : left + new_width] = resized
    return np.ascontiguousarray(canvas)


def evaluate_background_only(base, model_path, paths, output_dir, device, conf, imgsz):
    """Evaluate empty-label test images one at a time without training."""
    model = base.YOLO(str(model_path))
    image_root = paths["test_images"]
    label_root = paths["test_labels"]

    background_images = []
    for image_path in base.find_images(image_root):
        label_path = base.find_label_path(image_path, image_root, label_root)
        if not label_path.exists():
            raise FileNotFoundError(
                f"Missing label: {label_path}\n"
                "Background images need an empty label txt file."
            )
        if not label_path.read_text(encoding="utf-8").strip():
            background_images.append(image_path)

    if not background_images:
        raise ValueError("No background images with empty label files were found")

    rows = []
    false_positive_count = 0
    fire_fp_count = 0
    smoke_fp_count = 0

    for index, image_path in enumerate(background_images, start=1):
        bounded_image = load_letterboxed_image(image_path, imgsz)
        result = model.predict(
            source=bounded_image,
            conf=conf,
            iou=base.IOU_THRESHOLD,
            imgsz=imgsz,
            device=device,
            batch=1,
            max_det=100,
            verbose=False,
        )[0]

        classes = [] if result.boxes is None else [
            int(value) for value in result.boxes.cls.cpu().tolist()
        ]
        has_fire = 0 in classes
        has_smoke = 1 in classes
        has_fp = bool(classes)

        false_positive_count += int(has_fp)
        fire_fp_count += int(has_fire)
        smoke_fp_count += int(has_smoke)
        rows.append([
            image_path.name,
            int(has_fp),
            int(has_fire),
            int(has_smoke),
            len(classes),
        ])

        del result, bounded_image
        if base.torch.cuda.is_available():
            base.torch.cuda.empty_cache()

        if index % 100 == 0 or index == len(background_images):
            print(f"Background evaluation: {index}/{len(background_images)}")

    total = len(background_images)
    fp_rate = false_positive_count / total
    output_dir.mkdir(parents=True, exist_ok=True)

    with (output_dir / "background_image_results.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.writer(file)
        writer.writerow([
            "image", "has_false_positive", "has_fire_fp",
            "has_smoke_fp", "prediction_count"
        ])
        writer.writerows(rows)

    with (output_dir / "background_summary.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.writer(file)
        writer.writerow(["metric", "count", "rate"])
        writer.writerow(["actual_background", total, ""])
        writer.writerow(["background_correct", total - false_positive_count, 1 - fp_rate])
        writer.writerow(["background_false_positive", false_positive_count, fp_rate])
        writer.writerow(["background_fire_false_positive", fire_fp_count, fire_fp_count / total])
        writer.writerow(["background_smoke_false_positive", smoke_fp_count, smoke_fp_count / total])

    return total, false_positive_count, fp_rate


def main():
    args = parse_args()
    base = load_original_module()

    model_path = args.model.expanduser().resolve()
    output_dir = args.output.expanduser().resolve()

    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    if not 0.0 <= args.conf <= 1.0:
        raise ValueError("--conf must be between 0 and 1")
    if args.batch < 1:
        raise ValueError("--batch must be at least 1")
    if args.imgsz < 32:
        raise ValueError("--imgsz must be at least 32")

    # The original evaluator reads this module-level threshold.
    base.CONF_THRESHOLD = args.conf
    base.BATCH_SIZE = args.batch
    base.IMAGE_SIZE = args.imgsz

    base.check_yaml()
    paths = base.check_dataset()
    device = args.device if args.device is not None else base.get_device()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Release memory left behind by earlier work in an interactive session.
    if base.torch.cuda.is_available():
        base.torch.cuda.empty_cache()

    total, fp_count, fp_rate = evaluate_background_only(
        base=base,
        model_path=model_path,
        paths=paths,
        output_dir=output_dir,
        device=device,
        conf=args.conf,
        imgsz=args.imgsz,
    )

    print("\nBackground FP evaluation complete")
    print(f"Confidence : {args.conf}")
    print(f"Batch      : {args.batch}")
    print(f"Image size : {args.imgsz}")
    print(f"Background : {total}")
    print(f"FP images  : {fp_count}")
    print(f"FP rate    : {fp_rate * 100:.2f}%")
    print(f"Summary    : {output_dir / 'background_summary.csv'}")
    print(f"Per image  : {output_dir / 'background_image_results.csv'}")


if __name__ == "__main__":
    main()
