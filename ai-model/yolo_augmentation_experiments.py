"""YOLO11 fire/smoke augmentation experiments (EXP0~EXP9).

Copy this file next to ``yolo11_test.py`` and run, for example:
    python yolo_augmentation_experiments.py --stage search --exp exp2
    python yolo_augmentation_experiments.py --stage combo --combine exp2 exp3 exp5
    python yolo_augmentation_experiments.py --stage final --combine exp2 exp3 exp5

EXP9 is a dataset-composition experiment. Add hard-negative images with empty
YOLO label files to the training split before running it.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import albumentations as A
from ultralytics import YOLO
from ultralytics.models.yolo.detect.train import DetectionTrainer


BASE_DIR = Path(__file__).resolve().parent
ORIGINAL_SCRIPT = BASE_DIR / "yolo11_test.py"

SEARCH_EPOCHS = 30
FINAL_EPOCHS = 50
SEARCH_PATIENCE = 8
FINAL_PATIENCE = 12
IMAGE_SIZE = 640
BATCH_SIZE = 16
WORKERS = 4
SEED = 42


def load_original_module():
    if not ORIGINAL_SCRIPT.exists():
        raise FileNotFoundError(f"Original script not found: {ORIGINAL_SCRIPT}")
    spec = importlib.util.spec_from_file_location("fire_yolo_base", ORIGINAL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def common_yolo_augmentations():
    return {
        "hsv_h": 0.0, "hsv_s": 0.0, "hsv_v": 0.0,
        "degrees": 0.0, "translate": 0.0, "scale": 0.0,
        "shear": 0.0, "perspective": 0.0,
        "fliplr": 0.0, "flipud": 0.0,
        "mosaic": 0.0, "mixup": 0.0, "cutmix": 0.0,
    }


def make_experiment(exp: str):
    """Return (Albumentations transforms, Ultralytics augmentation args)."""
    yolo = common_yolo_augmentations()

    if exp == "exp0":
        custom = []

    elif exp == "exp1":
        custom = [
            A.RandomBrightnessContrast(0.15, 0.15, p=0.40),
            A.HorizontalFlip(p=0.50),
            A.GaussNoise(std_range=(0.01, 0.03), p=0.20),
            A.GaussianBlur(blur_limit=(3, 5), sigma_limit=(0.1, 1.0), p=0.20),
        ]

    elif exp == "exp2":
        custom = [
            A.RandomBrightnessContrast(0.20, 0.20, p=0.45),
            A.RandomGamma(gamma_limit=(80, 120), p=0.30),
        ]
        yolo.update(hsv_h=0.015, hsv_s=0.40, hsv_v=0.30, fliplr=0.50)

    elif exp == "exp3":
        custom = [
            A.OneOf([
                A.GaussianBlur(blur_limit=(3, 5), p=1.0),
                A.MotionBlur(blur_limit=(3, 7), p=1.0),
            ], p=0.35),
            A.GaussNoise(std_range=(0.01, 0.04), p=0.25),
            A.RandomBrightnessContrast(0.10, 0.10, p=0.20),
        ]

    elif exp == "exp4":
        custom = [
            A.ImageCompression(quality_range=(60, 90), p=0.40),
            A.GaussNoise(std_range=(0.005, 0.025), p=0.20),
            A.GaussianBlur(blur_limit=(3, 3), p=0.15),
            A.RandomBrightnessContrast(0.15, 0.10, p=0.25),
        ]

    elif exp == "exp5":
        custom = []
        yolo.update(
            degrees=3.0, translate=0.10, scale=0.25,
            perspective=0.0005, fliplr=0.50,
        )

    elif exp == "exp6":
        custom = [
            A.CoarseDropout(
                num_holes_range=(1, 4), hole_height_range=(0.03, 0.10),
                hole_width_range=(0.03, 0.10), fill=0, p=0.25,
            ),
        ]
        yolo.update(scale=0.20, translate=0.05)

    elif exp == "exp7":
        custom = [
            A.RandomFog(fog_coef_range=(0.05, 0.20), alpha_coef=0.08, p=0.25),
            A.RandomBrightnessContrast(0.10, 0.15, p=0.25),
        ]

    elif exp == "exp8":
        custom = []
        yolo.update(
            mosaic=1.0, scale=0.30, translate=0.10,
            hsv_h=0.015, hsv_s=0.40, hsv_v=0.30, fliplr=0.50,
        )

    elif exp == "exp9":
        # No special pixel transform: hard negatives must exist in train data.
        custom = []

    else:
        raise ValueError(f"Unknown experiment: {exp}")

    return custom, yolo


def make_combination(experiments):
    """Combine selected recipes without applying the same custom transform twice."""
    custom_by_type = {}
    combined_yolo = common_yolo_augmentations()

    for exp in experiments:
        custom, yolo = make_experiment(exp)
        for transform in custom:
            custom_by_type.setdefault(type(transform).__name__, transform)
        for key, value in yolo.items():
            combined_yolo[key] = max(combined_yolo[key], value)

    return list(custom_by_type.values()), combined_yolo


def make_trainer(custom_augmentations):
    class ExperimentTrainer(DetectionTrainer):
        def build_dataset(self, img_path, mode="train", batch=None):
            if mode == "train":
                self.args.augmentations = custom_augmentations
            return super().build_dataset(img_path, mode=mode, batch=batch)

    return ExperimentTrainer


def train(base, device, stage: str, experiments):
    if stage == "search":
        custom, yolo_aug = make_experiment(experiments[0])
    else:
        custom, yolo_aug = make_combination(experiments)

    is_search = stage == "search"
    is_final = stage == "final"
    model_name = "yolo11m.pt" if is_final else "yolo11n.pt"
    epochs = FINAL_EPOCHS if is_final else SEARCH_EPOCHS
    patience = FINAL_PATIENCE if is_final else SEARCH_PATIENCE
    model = YOLO(model_name)
    model_size = "yolo11m" if is_final else "yolo11n"
    recipe_name = experiments[0] if is_search else "combo_" + "_".join(experiments)
    run_name = f"fire_{model_size}_{recipe_name}_e{epochs}"

    # evaluate_test() reads this value from the imported base script. Give
    # every experiment a separate output directory to prevent collisions.
    base.TEST_RUN_NAME = f"{run_name}_test"

    model.train(
        trainer=make_trainer(custom),
        data=str(base.DATA_YAML),
        epochs=epochs,
        patience=patience,
        imgsz=IMAGE_SIZE,
        batch=BATCH_SIZE,
        seed=SEED,
        deterministic=True,
        optimizer="AdamW",
        lr0=0.001,
        lrf=0.01,
        weight_decay=0.0005,
        cos_lr=True,
        warmup_epochs=3.0,
        device=device,
        workers=WORKERS,
        amp=True,
        cache="disk",
        close_mosaic=10 if yolo_aug["mosaic"] > 0 else 0,
        project=str(base.RUNS_DIR),
        name=run_name,
        exist_ok=False,
        pretrained=True,
        val=True,
        plots=True,
        save=True,
        verbose=True,
        **yolo_aug,
    )

    best_path = Path(model.trainer.best).resolve()
    if not best_path.exists():
        raise FileNotFoundError(f"best.pt was not created: {best_path}")
    return best_path


def evaluate_validation(base, best_path, device, paths):
    """Evaluate the selected checkpoint on val, including background FP."""
    model = YOLO(str(best_path))
    train_dir = best_path.parent.parent
    val_name = f"{train_dir.name}_val"
    metrics = model.val(
        data=str(base.DATA_YAML),
        split="val",
        imgsz=IMAGE_SIZE,
        batch=BATCH_SIZE,
        device=device,
        workers=WORKERS,
        conf=0.001,
        iou=base.IOU_THRESHOLD,
        plots=True,
        project=str(base.RUNS_DIR),
        name=val_name,
        exist_ok=False,
        verbose=True,
    )
    val_dir = Path(metrics.save_dir).resolve()
    base.print_detection_metrics(metrics)
    base.save_detection_metrics(metrics, val_dir)
    base.save_yolo_confusion_matrix(metrics, val_dir)

    # Reuse the image-level FP evaluator, but point its test keys to val data.
    val_paths = dict(paths)
    val_paths["test_images"] = paths["val_images"]
    val_paths["test_labels"] = paths["val_labels"]
    base.evaluate_background_test(best_path, device, val_paths, val_dir)
    return val_dir


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["search", "combo", "final"], required=True)
    parser.add_argument("--exp", choices=[f"exp{i}" for i in range(10)])
    parser.add_argument("--combine", nargs="+", choices=[f"exp{i}" for i in range(10)])
    return parser.parse_args()


def main():
    args = parse_args()
    if args.stage == "search":
        if not args.exp or args.combine:
            raise SystemExit("search 단계는 --exp 하나를 지정해야 합니다.")
        experiments = [args.exp]
    else:
        if args.exp or not args.combine:
            raise SystemExit("combo/final 단계는 --combine exp2 exp3 형식으로 지정해야 합니다.")
        experiments = list(dict.fromkeys(args.combine))

    base = load_original_module()
    base.check_yaml()
    paths = base.check_dataset()
    base.print_all_dataset_statistics(paths)
    device = base.get_device()

    best_path = train(base, device, args.stage, experiments)

    if args.stage in {"search", "combo"}:
        val_dir = evaluate_validation(base, best_path, device, paths)
        print(f"\n[{args.stage.upper()} 완료]")
        print(f"증강 구성: {', '.join(experiments)}")
        print(f"best.pt: {best_path}")
        print(f"validation 평가: {val_dir}")
        print("test 데이터 평가는 최종 YOLO11m 단계에서만 수행합니다.")
        return

    # Only the final YOLO11m model is evaluated on the test split.
    metrics, test_dir = base.evaluate_test(best_path, device)
    base.print_detection_metrics(metrics)
    base.save_detection_metrics(metrics, test_dir)
    base.save_yolo_confusion_matrix(metrics, test_dir)
    base.evaluate_background_test(best_path, device, paths, test_dir)
    base.print_result_paths(best_path, test_dir)


if __name__ == "__main__":
    main()
