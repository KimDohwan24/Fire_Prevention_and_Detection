"""CPU-only background false-positive evaluation (no training)."""

from argparse import ArgumentParser
from pathlib import Path

import yolo11m_evaluate_background_fp as evaluator


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL = (
    BASE_DIR
    / "runs"
    / "data"
    / "fire_yolo11m_tuned_e50"
    / "weights"
    / "best.pt"
)
DEFAULT_OUTPUT = BASE_DIR / "runs" / "data" / "background_fp_cpu_evaluation"


def parse_args():
    parser = ArgumentParser(
        description="Evaluate background false positives using CPU only."
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL,
        help="Path to the trained best.pt file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Directory for evaluation CSV files",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Confidence threshold (default: 0.25)",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Inference image size (default: 640)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    model_path = args.model.expanduser().resolve()
    output_dir = args.output.expanduser().resolve()

    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    if not 0.0 <= args.conf <= 1.0:
        raise ValueError("--conf must be between 0 and 1")
    if args.imgsz < 32:
        raise ValueError("--imgsz must be at least 32")

    base = evaluator.load_original_module()
    base.check_yaml()
    paths = base.check_dataset()

    print("\nCPU-only evaluation: no training and no CUDA usage")
    print(f"Model      : {model_path}")
    print(f"Confidence : {args.conf}")
    print(f"Image size : {args.imgsz}")

    total, fp_count, fp_rate = evaluator.evaluate_background_only(
        base=base,
        model_path=model_path,
        paths=paths,
        output_dir=output_dir,
        device="cpu",
        conf=args.conf,
        imgsz=args.imgsz,
    )

    print("\nCPU background FP evaluation complete")
    print(f"Background : {total}")
    print(f"FP images  : {fp_count}")
    print(f"FP rate    : {fp_rate * 100:.2f}%")
    print(f"Summary    : {output_dir / 'background_summary.csv'}")
    print(f"Per image  : {output_dir / 'background_image_results.csv'}")


if __name__ == "__main__":
    main()
