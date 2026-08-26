"""Train YOLO11m with the combined EXP4 + EXP6 augmentation recipe.

Place this file in the same directory as ``yolo11_m_version_test.py`` and run:
    python yolo11m_augmentation_retouch.py

By default the experiment starts from the official COCO-pretrained yolo11m.pt.
To continue training from an existing checkpoint instead, use:
    python yolo11m_augmentation_retouch.py --weights yolo11m_best.pt
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import albumentations as A
from ultralytics import YOLO
from ultralytics.models.yolo.detect.train import DetectionTrainer


BASE_DIR = Path(__file__).resolve().parent
ORIGINAL_SCRIPT = BASE_DIR / "yolo11_m_version_test.py"

# Keep exactly the same cloud-relative paths as yolo11_m_version_test.py.
DATA_YAML = (BASE_DIR / ".." / "data" / "data.yaml").resolve()
RUNS_DIR = (BASE_DIR / "runs" / "data").resolve()

EPOCHS = 50
PATIENCE = 10
IMAGE_SIZE = 640
BATCH_SIZE = 16
WORKERS = 4
SEED = 42
RUN_NAME = "yolo11m_augmentation_retouch"


# EXP4: compression/noise/blur/brightness-contrast degradation.
# EXP6: partial occlusion (CoarseDropout).
CUSTOM_AUGMENTATIONS = [
    A.ImageCompression(quality_range=(60, 90), p=0.40),
    A.GaussNoise(std_range=(0.005, 0.025), p=0.20),
    A.GaussianBlur(blur_limit=(3, 3), p=0.15),
    A.RandomBrightnessContrast(
        brightness_limit=0.15,
        contrast_limit=0.10,
        p=0.25,
    ),
    A.CoarseDropout(
        num_holes_range=(1, 4),
        hole_height_range=(0.03, 0.10),
        hole_width_range=(0.03, 0.10),
        fill=0,
        p=0.25,
    ),
]


class Exp4Exp6Trainer(DetectionTrainer):
    """Inject the EXP4 + EXP6 Albumentations into train data only."""

    def build_dataset(self, img_path, mode="train", batch=None):
        if mode == "train":
            self.args.augmentations = CUSTOM_AUGMENTATIONS
        return super().build_dataset(img_path, mode=mode, batch=batch)


def load_original_module():
    """Load the same cloud-relative base module as yolo11m_tuned_test.py."""
    if not ORIGINAL_SCRIPT.exists():
        raise FileNotFoundError(f"Original script not found: {ORIGINAL_SCRIPT}")

    spec = importlib.util.spec_from_file_location("fire_yolo_base", ORIGINAL_SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load original script: {ORIGINAL_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def print_experiment_settings(args):
    print("\n" + "=" * 70)
    print("YOLO11m EXP4 + EXP6 학습 설정")
    print("=" * 70)
    print(f"초기 가중치 : {args.weights}")
    print(f"Epochs       : {args.epochs}")
    print(f"Image size   : {IMAGE_SIZE}")
    print(f"Batch        : {args.batch}")
    print(f"Workers      : {args.workers}")
    print("EXP4         : JPEG 압축, 노이즈, 약한 블러, 밝기/대비")
    print("EXP6         : CoarseDropout, scale=0.20, translate=0.05")
    print("기타 증강    : 모두 비활성화")


def print_result_paths(best_model_path, test_dir):
    """Print the same result checklist as yolo11_test.py with an m-model title."""
    train_dir = best_model_path.parent.parent
    files = [
        best_model_path,
        train_dir / "results.csv",
        train_dir / "results.png",
        test_dir / "confusion_matrix.png",
        test_dir / "confusion_matrix_normalized.png",
        test_dir / "PR_curve.png",
        test_dir / "F1_curve.png",
        test_dir / "P_curve.png",
        test_dir / "R_curve.png",
        test_dir / "metrics_summary.csv",
        test_dir / "yolo_confusion_matrix.csv",
        test_dir / "background_summary.csv",
        test_dir / "image_level_metrics.csv",
        test_dir / "background_image_results.csv",
        test_dir / "background_confusion_matrix.csv",
    ]

    print("\n" + "=" * 70)
    print("YOLO11m EXP4 + EXP6 실험 완료")
    print("=" * 70)
    print(f"\n[BEST MODEL]\n{best_model_path}")
    print(f"\n[TRAIN 결과]\n{train_dir}")
    print(f"\n[TEST 결과]\n{test_dir}")
    print("\n[주요 결과 파일]")
    for file in files:
        print(f"[{'O' if file.exists() else 'X'}] {file}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Train YOLO11m using the combined EXP4 + EXP6 recipe."
    )
    parser.add_argument(
        "--weights",
        default="yolo11m.pt",
        help=(
            "Initial weights. Use yolo11m.pt for a comparable fresh experiment "
            "or yolo11m_best.pt to continue from the existing model."
        ),
    )
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--batch", type=int, default=BATCH_SIZE)
    parser.add_argument("--workers", type=int, default=WORKERS)
    parser.add_argument("--device", default=None, help="For example: 0 or cpu")
    return parser.parse_args()


def resolve_weights(value: str) -> str:
    """Use a local path when supplied, while preserving Ultralytics model names."""
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        if not candidate.exists():
            raise FileNotFoundError(f"Weights not found: {candidate}")
        return str(candidate.resolve())

    local_candidate = BASE_DIR / candidate
    if local_candidate.exists():
        return str(local_candidate.resolve())
    return value


def train(base, device, args):
    model = YOLO(resolve_weights(args.weights))

    model.train(
        trainer=Exp4Exp6Trainer,
        data=str(DATA_YAML),
        epochs=args.epochs,
        patience=PATIENCE,
        imgsz=IMAGE_SIZE,
        batch=args.batch,
        seed=SEED,
        deterministic=True,
        optimizer="AdamW",
        lr0=0.001,
        lrf=0.01,
        weight_decay=0.0005,
        cos_lr=True,
        warmup_epochs=3.0,
        device=device,
        workers=args.workers,
        amp=True,
        cache="disk",

        # Disable other Ultralytics augmentations, then retain only EXP6's
        # light geometric transformation.
        hsv_h=0.0,
        hsv_s=0.0,
        hsv_v=0.0,
        degrees=0.0,
        translate=0.05,
        scale=0.20,
        shear=0.0,
        perspective=0.0,
        fliplr=0.0,
        flipud=0.0,
        mosaic=0.0,
        mixup=0.0,
        cutmix=0.0,
        close_mosaic=0,

        project=str(RUNS_DIR),
        name=RUN_NAME,
        exist_ok=False,
        pretrained=True,
        val=True,
        plots=True,
        save=True,
        verbose=True,
    )

    best_path = Path(model.trainer.best).resolve()
    if not best_path.exists():
        raise FileNotFoundError(f"best.pt was not created: {best_path}")
    return best_path


def main():
    args = parse_args()
    if args.epochs < 1 or args.batch < 1 or args.workers < 0:
        raise ValueError("epochs/batch must be positive and workers cannot be negative")

    # The base module supplies validation/reporting functions only. Force those
    # helpers to use this script's matching cloud-relative paths as well.
    base = load_original_module()
    base.DATA_YAML = DATA_YAML
    base.RUNS_DIR = RUNS_DIR
    base.check_yaml()
    paths = base.check_dataset()
    base.print_all_dataset_statistics(paths)
    print_experiment_settings(args)
    device = args.device if args.device is not None else base.get_device()

    # Avoid overwriting the baseline test output.
    base.TEST_RUN_NAME = f"{RUN_NAME}_test"
    best_path = train(base, device, args)

    metrics, test_dir = base.evaluate_test(best_path, device)
    base.print_detection_metrics(metrics)
    base.save_detection_metrics(metrics, test_dir)
    base.save_yolo_confusion_matrix(metrics, test_dir)
    base.evaluate_background_test(best_path, device, paths, test_dir)
    print_result_paths(best_path, test_dir)


if __name__ == "__main__":
    main()
