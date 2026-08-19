"""YOLO11m fire/smoke tuning experiment.

The dataset validation and reporting functions are reused from the original
project script, while the training recipe is kept here so the baseline file
does not need to be modified.
"""

from pathlib import Path
import importlib.util

from ultralytics import YOLO


BASE_DIR = Path(__file__).resolve().parent
ORIGINAL_SCRIPT = BASE_DIR / "yolo11_m_version_test.py"

# Experiment settings
EPOCHS = 50
PATIENCE = 12
IMAGE_SIZE = 640
BATCH_SIZE = 16
WORKERS = 4
SEED = 42

# Use a new directory/name so the baseline result is never overwritten.
RUN_NAME = "fire_yolo11m_tuned_e50"


def load_original_module():
    if not ORIGINAL_SCRIPT.exists():
        raise FileNotFoundError(f"Original script not found: {ORIGINAL_SCRIPT}")

    spec = importlib.util.spec_from_file_location("fire_yolo_base", ORIGINAL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def train(base, device):
    model = YOLO("yolo11m.pt")

    model.train(
        trainer=base.CustomAugmentationTrainer,
        data=str(base.DATA_YAML),

        # Convergence / reproducibility
        epochs=EPOCHS,
        patience=PATIENCE,
        imgsz=IMAGE_SIZE,
        batch=BATCH_SIZE,
        seed=SEED,
        deterministic=True,

        # Optimizer
        optimizer="AdamW",
        lr0=0.001,
        lrf=0.01,
        weight_decay=0.0005,
        cos_lr=True,
        warmup_epochs=3.0,

        # Device / throughput
        device=device,
        workers=WORKERS,
        amp=True,
        cache="disk",

        # Mild geometric augmentations. Brightness, contrast, noise, blur and
        # horizontal flip are supplied by CustomAugmentationTrainer.
        fliplr=0.0,
        flipud=0.0,
        hsv_h=0.0,
        hsv_s=0.0,
        hsv_v=0.0,
        degrees=5.0,
        translate=0.08,
        scale=0.30,
        shear=2.0,
        perspective=0.0002,
        mosaic=0.50,
        mixup=0.05,
        cutmix=0.0,
        close_mosaic=10,

        # Output
        project=str(base.RUNS_DIR),
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
    base = load_original_module()

    base.check_yaml()
    paths = base.check_dataset()
    base.print_all_dataset_statistics(paths)
    device = base.get_device()

    best_path = train(base, device)

    # The test split is intentionally evaluated only after training finishes.
    metrics, test_dir = base.evaluate_test(best_path, device)
    base.print_detection_metrics(metrics)
    base.save_detection_metrics(metrics, test_dir)
    base.save_yolo_confusion_matrix(metrics, test_dir)
    base.evaluate_background_test(best_path, device, paths, test_dir)
    base.print_result_paths(best_path, test_dir)


if __name__ == "__main__":
    main()
