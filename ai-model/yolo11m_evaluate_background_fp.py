"""Evaluate image-level background false positives without retraining.

Run this file from any directory. Paths are resolved relative to this file.
"""

import importlib.util
import os
from argparse import ArgumentParser
from pathlib import Path


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

    base.evaluate_background_test(
        model_path,
        device,
        paths,
        output_dir,
    )

    print("\nBackground FP evaluation complete")
    print(f"Confidence : {args.conf}")
    print(f"Batch      : {args.batch}")
    print(f"Image size : {args.imgsz}")
    print(f"Summary    : {output_dir / 'background_summary.csv'}")
    print(f"Per image  : {output_dir / 'background_image_results.csv'}")
    print(f"Metrics    : {output_dir / 'image_level_metrics.csv'}")


if __name__ == "__main__":
    main()
