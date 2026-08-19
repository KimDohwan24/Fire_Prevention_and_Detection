"""Evaluate image-level background false positives without retraining.

Run this file from any directory. Paths are resolved relative to this file.
"""

from argparse import ArgumentParser
from pathlib import Path
import importlib.util


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

    # The original evaluator reads this module-level threshold.
    base.CONF_THRESHOLD = args.conf

    base.check_yaml()
    paths = base.check_dataset()
    device = base.get_device()
    output_dir.mkdir(parents=True, exist_ok=True)

    base.evaluate_background_test(
        model_path,
        device,
        paths,
        output_dir,
    )

    print("\nBackground FP evaluation complete")
    print(f"Confidence : {args.conf}")
    print(f"Summary    : {output_dir / 'background_summary.csv'}")
    print(f"Per image  : {output_dir / 'background_image_results.csv'}")
    print(f"Metrics    : {output_dir / 'image_level_metrics.csv'}")


if __name__ == "__main__":
    main()
