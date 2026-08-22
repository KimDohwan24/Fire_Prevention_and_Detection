from __future__ import annotations

import csv
import gc
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import torch
import yaml
import albumentations as A
from ultralytics import YOLO


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
BASE_DIR = Path.cwd().resolve()
DATA_SIBLING_DIR = (BASE_DIR.parent / "data").resolve()

TRAIN_IMAGE_DIRS = [
    BASE_DIR / "fire_yolov11_dataset" / "train" / "images",
    BASE_DIR / "fire-2" / "train" / "images",
    BASE_DIR / "fire-smoke-1" / "train" / "images",
    DATA_SIBLING_DIR / "images" / "train",
]

VAL_IMAGE_DIRS = [
    DATA_SIBLING_DIR / "images" / "val",
]

TEST_IMAGE_DIRS = [
        DATA_SIBLING_DIR / "images" / "test",
]

CLASS_NAMES = ["fire", "smoke"]  # 반드시 모든 원본 데이터셋에서 0=fire, 1=smoke여야 함
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

EPOCHS = 20
IMAGE_SIZE = 640
BATCH_SIZE = 16
SEED = 42
WORKERS = 4
PREDICT_CONF = 0.25

OUTPUT_PROJECT_DIR = BASE_DIR / "ai-model"
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
TRAIN_RUN_NAME = f"ccs_yolo11n_{RUN_ID}"
TEST_RUN_NAME = f"ccs_yolo11n_{RUN_ID}_eval"

# 허용하는 증강은 좌우반전, 약한 명암 대비, 약한 Gaussian noise, 약한 Gaussian blur뿐이다.
# 사용자 정의 Albumentations에는 bbox 위치를 바꾸는 변환이 없으므로 라벨 좌표는 그대로 유지된다.
FLIPLR_PROBABILITY = 0.5
BRIGHTNESS_CONTRAST_PROBABILITY = 0.25
NOISE_PROBABILITY = 0.15
BLUR_PROBABILITY = 0.10

# 안전한 기본값: 라벨 파일 누락을 정상 이미지로 간주하지 않음.
# 정상 이미지에 라벨 파일을 만들지 않는 데이터셋 규칙이 확실할 때만 True로 변경.
MISSING_LABEL_MEANS_BACKGROUND = False


def image_files(image_dirs: list[Path]) -> list[Path]:
    files: list[Path] = []
    for image_dir in image_dirs:
        files.extend(
            path.resolve()
            for path in image_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
    return sorted(files)


def label_path_for(image_path: Path) -> Path:
    """
    [구조 가이드 반영 완료] 
    .../images/train/x.jpg 구조를 인식하여 
    .../labels/train/x.txt 정답 경로를 정확하게 산출합니다.
    """
    # 1. Path 객체의 부모 폴더들을 역추적하기 위해 문자열로 변환
    img_path_str = str(image_path.resolve())
    
    # 2. 경로 상에 'images'라는 폴더 명이 핵심 분기점으로 존재하는지 검증
    if "images" not in img_path_str:
        raise ValueError(f"전체 경로에 'images' 구조가 누락되었습니다: {image_path}")
        
    # 3. YOLO 글로벌 규격에 맞춰 'images' 세그먼트를 'labels'로 정밀 치환
    # 예: .../data/images/train/abc.jpg -> .../data/labels/train/abc.jpg
    label_path_str = img_path_str.replace("images", "labels")
    
    # 4. 파일 확장자를 이미지 포맷에서 YOLO 라벨 텍스트(.txt) 규격으로 변경
    # 예: .../data/labels/train/abc.jpg -> .../data/labels/train/abc.txt
    return Path(label_path_str).with_suffix(".txt")



def read_gt_classes(image_path: Path) -> set[int]:
    label_path = label_path_for(image_path)
    if not label_path.exists():
        if MISSING_LABEL_MEANS_BACKGROUND:
            return set()
        raise FileNotFoundError(
            f"라벨 파일이 없습니다: {label_path}\n"
            "정상 이미지라면 빈 .txt 라벨 파일을 만들거나, 데이터셋 규칙을 확인한 뒤 "
            "MISSING_LABEL_MEANS_BACKGROUND=True로 설정하세요."
        )

    classes: set[int] = set()
    for line_number, raw_line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:  # 빈 라벨 파일은 정상(background) 이미지
            continue
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"YOLO 라벨 열 개수가 5가 아닙니다: {label_path}:{line_number}")
        try:
            class_id = int(parts[0])
            coordinates = [float(value) for value in parts[1:]]
        except ValueError as exc:
            raise ValueError(f"라벨 형식 오류: {label_path}:{line_number}") from exc
        if not 0 <= class_id < len(CLASS_NAMES):
            raise ValueError(f"허용되지 않은 class_id={class_id}: {label_path}:{line_number}")
        if not all(0.0 <= value <= 1.0 for value in coordinates):
            raise ValueError(f"정규화 좌표가 [0, 1] 범위를 벗어났습니다: {label_path}:{line_number}")
        classes.add(class_id)
    return classes


def validate_dataset() -> dict[str, list[Path]]:
    split_dirs = {
        "train": TRAIN_IMAGE_DIRS,
        "val": VAL_IMAGE_DIRS,
        "test": TEST_IMAGE_DIRS,
    }
    split_images: dict[str, list[Path]] = {}

    for split, directories in split_dirs.items():
        missing_dirs = [str(path) for path in directories if not path.is_dir()]
        if missing_dirs:
            raise FileNotFoundError(f"{split} 이미지 폴더가 없습니다:\n" + "\n".join(missing_dirs))

        images = image_files(directories)
        if not images:
            raise RuntimeError(f"{split} 이미지가 한 장도 없습니다.")
            
        # ----------------------------------------------------------------------
        # [최소 교정] 라벨 유실 이미지를 에러 없이 건너뛰고 정상 파일만 수집합니다.
        # ----------------------------------------------------------------------
        valid_images: list[Path] = []
        for image_path in images:
            try:
                read_gt_classes(image_path)
                valid_images.append(image_path)
            except FileNotFoundError:
                continue  # 라벨 파일이 없으면 조용히 건너뜁니다.
        
        if not valid_images:
            raise RuntimeError(f"라벨이 정상적으로 존재하는 {split} 이미지가 한 장도 없습니다.")
        split_images[split] = valid_images
        # ----------------------------------------------------------------------

    # 같은 파일 경로가 split 사이에 직접 중복되는 실수를 차단한다.
    for left, right in (("train", "val"), ("train", "test"), ("val", "test")):
        overlap = set(split_images[left]) & set(split_images[right])
        if overlap:
            raise RuntimeError(f"{left}/{right} 경로 중복 발견: {next(iter(overlap))}")

    print(
        "데이터셋 검증 완료: "
        + ", ".join(f"{split}={len(paths)}" for split, paths in split_images.items())
    )
    print("주의: 증강본/유사 이미지 누수는 원본 그룹 ID 또는 perceptual hash로 별도 검사해야 합니다.")
    return split_images



def write_data_yaml() -> Path:
    yaml_path = BASE_DIR / "quad_fire_data.yaml"
    content = {
        "train": [str(path.resolve()) for path in TRAIN_IMAGE_DIRS],
        "val": [str(path.resolve()) for path in VAL_IMAGE_DIRS],
        "test": [str(path.resolve()) for path in TEST_IMAGE_DIRS],
        "nc": len(CLASS_NAMES),
        "names": CLASS_NAMES,
    }
    yaml_path.write_text(
        yaml.safe_dump(content, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return yaml_path.resolve()


def get_device() -> int | str:
    return 0 if torch.cuda.is_available() else "cpu"


def train_model(data_yaml: Path, device: int | str) -> Path:
    model = YOLO("yolo11n.pt")

    custom_augmentations = [
        A.RandomBrightnessContrast(
            brightness_limit=0.10,
            contrast_limit=0.10,
            p=BRIGHTNESS_CONTRAST_PROBABILITY,
        ),
        A.GaussNoise(
            std_range=(0.005, 0.015),
            mean_range=(0.0, 0.0),
            p=NOISE_PROBABILITY,
        ),
        A.GaussianBlur(
            blur_limit=(3, 3),
            sigma_limit=(0.1, 0.8),
            p=BLUR_PROBABILITY,
        ),
    ]

    print("\n" + "=" * 76)
    print("[TRAIN] YOLO11n 학습 시작")
    print("=" * 76)
    print(f"장치                 : {device}")
    print(f"Epoch / Batch / Size : {EPOCHS} / {BATCH_SIZE} / {IMAGE_SIZE}")
    print(f"좌우반전 확률         : {FLIPLR_PROBABILITY:.2f}")
    print(f"약한 명암 대비 확률   : {BRIGHTNESS_CONTRAST_PROBABILITY:.2f} (±10%)")
    print(f"약한 Gaussian noise  : {NOISE_PROBABILITY:.2f} (std 0.5~1.5%)")
    print(f"약한 Gaussian blur   : {BLUR_PROBABILITY:.2f} (kernel 3x3)")
    print("나머지 증강           : 모두 비활성화")

    model.train(
        data=str(data_yaml),
        epochs=EPOCHS,
        imgsz=IMAGE_SIZE,
        batch=BATCH_SIZE,
        optimizer="auto",
        seed=SEED,
        deterministic=True,
        patience=10,
        device=device,
        workers=WORKERS,
        cache=False,
        # 좌우반전만 사용하는 YOLO 공간 증강
        fliplr=FLIPLR_PROBABILITY,
        flipud=0.0,
        degrees=0.0,
        translate=0.0,
        scale=0.0,
        shear=0.0,
        perspective=0.0,
        mosaic=0.0,
        mixup=0.0,
        cutmix=0.0,
        copy_paste=0.0,
        # 색상 변화도 사용자 정의 명암 대비 외에는 모두 끈다.
        hsv_h=0.0,
        hsv_s=0.0,
        hsv_v=0.0,
        augmentations=custom_augmentations,
        project=str(OUTPUT_PROJECT_DIR),
        name=TRAIN_RUN_NAME,
        exist_ok=False,
        val=True,
        plots=True,
        pretrained=True,
        save=True,
        verbose=True,
    )

    best_path = Path(model.trainer.best).resolve()
    if not best_path.is_file():
        raise FileNotFoundError(f"학습 후 best.pt가 생성되지 않았습니다: {best_path}")

    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return best_path


def evaluate_detection(best_path: Path, data_yaml: Path, device: int | str):
    """클래스와 IoU를 반영하는 공식 YOLO 객체 탐지 평가."""
    model = YOLO(str(best_path))
    metrics = model.val(
        data=str(data_yaml),
        split="test",
        imgsz=IMAGE_SIZE,
        batch=BATCH_SIZE,
        device=device,
        workers=WORKERS,
        conf=0.25,
        plots=True,
        project=str(OUTPUT_PROJECT_DIR),
        name=TEST_RUN_NAME,
        exist_ok=False,
        verbose=True,
    )
    output_dir = Path(metrics.save_dir).resolve()

    precision = float(metrics.box.mp)
    recall = float(metrics.box.mr)
    f1 = safe_div(2 * precision * recall, precision + recall)
    with (output_dir / "detection_metrics.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["scope", "precision", "recall", "f1_from_mean_pr", "mAP50", "mAP50-95"])
        writer.writerow(["all", precision, recall, f1, float(metrics.box.map50), float(metrics.box.map)])

    matrix = metrics.confusion_matrix.matrix
    names = CLASS_NAMES + ["background"]
    with (output_dir / "yolo_confusion_matrix.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["Predicted / Actual", *names])
        for index, row in enumerate(matrix):
            writer.writerow([names[index] if index < len(names) else str(index), *map(float, row)])

    print("\n" + "=" * 76)
    print("[TEST] IoU 기반 객체 탐지 성능")
    print("=" * 76)
    print(f"Precision             : {precision:.6f}")
    print(f"Recall                : {recall:.6f}")
    print(f"F1 (mean P/R 기반)    : {f1:.6f}")
    print(f"mAP@0.5               : {float(metrics.box.map50):.6f}")
    print(f"mAP@0.5:0.95          : {float(metrics.box.map):.6f}")
    print(f"평가 결과 폴더         : {output_dir}")

    summary = {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "map50": float(metrics.box.map50),
        "map50_95": float(metrics.box.map),
    }

    del metrics
    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return summary, output_dir


def safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def predict_images_one_by_one(
    model: YOLO,
    test_images: list[Path],
    device: int | str,
):
    """이미지 경로 전체가 거대한 단일 배치가 되지 않도록 한 장씩 예측한다."""
    total = len(test_images)

    for index, image_path in enumerate(test_images, start=1):
        results = model.predict(
            source=str(image_path),
            imgsz=IMAGE_SIZE,
            batch=1,
            device=device,
            conf=PREDICT_CONF,
            save=False,
            verbose=False,
            stream=False,
        )

        if len(results) != 1:
            raise RuntimeError(
                f"이미지 한 장의 예측 결과가 1개가 아닙니다: "
                f"path={image_path}, results={len(results)}"
            )

        yield results[0]
        del results

        if index % 100 == 0 or index == total:
            print(f"[IMAGE LEVEL] 예측 진행: {index}/{total}")


def evaluate_image_level(
    best_path: Path,
    test_images: list[Path],
    device: int | str,
    output_dir: Path,
) -> dict[str, float]:
    """
    자동 신고 관점의 이미지 단위 평가.

    양성 GT: 이미지에 fire 또는 smoke 라벨이 하나 이상 있음.
    양성 예측: confidence 기준을 넘는 fire 또는 smoke 박스가 하나 이상 있음.
    박스 위치 정확도는 여기서 평가하지 않고 evaluate_detection()의 mAP로 평가한다.
    """
    model = YOLO(str(best_path))
    predictions = predict_images_one_by_one(
        model=model,
        test_images=test_images,
        device=device,
    )

    tp = tn = fp = fn = 0
    class_tp = [0] * len(CLASS_NAMES)
    class_fp = [0] * len(CLASS_NAMES)
    class_fn = [0] * len(CLASS_NAMES)
    rows: list[list[object]] = []
    actual_fire = actual_smoke = actual_background = actual_alarm = 0
    background_fire_fp = background_smoke_fp = 0

    seen_paths: set[Path] = set()
    for result in predictions:
        image_path = Path(result.path).resolve()
        seen_paths.add(image_path)
        gt_classes = read_gt_classes(image_path)
        pred_classes = set(result.boxes.cls.int().cpu().tolist()) if len(result.boxes) else set()

        gt_alarm = bool(gt_classes)
        pred_alarm = bool(pred_classes)
        actual_fire += int(0 in gt_classes)
        actual_smoke += int(1 in gt_classes)
        actual_alarm += int(gt_alarm)
        actual_background += int(not gt_alarm)
        if gt_alarm and pred_alarm:
            tp += 1
        elif not gt_alarm and not pred_alarm:
            tn += 1
        elif not gt_alarm and pred_alarm:
            fp += 1
            background_fire_fp += int(0 in pred_classes)
            background_smoke_fp += int(1 in pred_classes)
        else:
            fn += 1

        for class_id in range(len(CLASS_NAMES)):
            gt_has = class_id in gt_classes
            pred_has = class_id in pred_classes
            class_tp[class_id] += int(gt_has and pred_has)
            class_fp[class_id] += int(not gt_has and pred_has)
            class_fn[class_id] += int(gt_has and not pred_has)

        rows.append([
            str(image_path),
            "|".join(CLASS_NAMES[i] for i in sorted(gt_classes)) or "background",
            "|".join(CLASS_NAMES[i] for i in sorted(pred_classes)) or "background",
            int(gt_alarm),
            int(pred_alarm),
        ])

    expected_paths = set(test_images)
    if seen_paths != expected_paths:
        missing = expected_paths - seen_paths
        extra = seen_paths - expected_paths
        raise RuntimeError(f"예측 결과 이미지 불일치: missing={len(missing)}, extra={len(extra)}")

    total = tp + tn + fp + fn
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    metrics = {
        "accuracy": safe_div(tp + tn, total),
        "precision": precision,
        "recall": recall,
        "f1": safe_div(2 * precision * recall, precision + recall),
        "false_alarm_rate": safe_div(fp, fp + tn),
        "miss_rate": safe_div(fn, fn + tp),
    }

    class_metrics: list[dict[str, float | int | str]] = []
    for class_id, name in enumerate(CLASS_NAMES):
        ctp, cfp, cfn = class_tp[class_id], class_fp[class_id], class_fn[class_id]
        cp = safe_div(ctp, ctp + cfp)
        cr = safe_div(ctp, ctp + cfn)
        class_metrics.append({
            "name": name,
            "tp": ctp,
            "fp": cfp,
            "fn": cfn,
            "precision": cp,
            "recall": cr,
            "f1": safe_div(2 * cp * cr, cp + cr),
        })

    with (output_dir / "image_level_predictions.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["image_path", "gt_classes", "pred_classes", "gt_alarm", "pred_alarm"])
        writer.writerows(rows)

    with (output_dir / "image_level_metrics.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["scope", "tp", "tn", "fp", "fn", "accuracy", "precision", "recall", "f1"])
        writer.writerow(["alarm", tp, tn, fp, fn, metrics["accuracy"], precision, recall, metrics["f1"]])
        for item in class_metrics:
            writer.writerow([
                item["name"], item["tp"], "", item["fp"], item["fn"], "",
                item["precision"], item["recall"], item["f1"],
            ])

    with (output_dir / "image_level_confusion_matrix.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["Actual / Predicted", "alarm", "background"])
        writer.writerow(["alarm", tp, fn])
        writer.writerow(["background", fp, tn])

    make_image_level_plot(output_dir, metrics, class_metrics)

    print("\n" + "=" * 76)
    print(f"[IMAGE LEVEL] 자동 신고 평가 (confidence >= {PREDICT_CONF})")
    print("=" * 76)
    print("\n[실제 테스트 데이터]")
    print(f"전체 이미지            : {total}")
    print(f"정상(background)       : {actual_background}")
    print(f"화재/연기 이미지        : {actual_alarm}")
    print(f"Fire 포함 이미지        : {actual_fire}")
    print(f"Smoke 포함 이미지       : {actual_smoke}")

    print("\n[자동 신고 혼동행렬]")
    print(f"TP 위험→위험            : {tp}")
    print(f"TN 정상→정상            : {tn}")
    print(f"FP 정상→위험(오탐)      : {fp}")
    print(f"FN 위험→정상(미탐)      : {fn}")

    print("\n[정상 이미지 제어]")
    print(f"정상 판정 성공          : {tn}/{actual_background}")
    print(f"정상 이미지 오탐        : {fp}/{actual_background}")
    print(f"  Fire 오탐 포함        : {background_fire_fp}")
    print(f"  Smoke 오탐 포함       : {background_smoke_fp}")
    print(f"정상 정확도             : {safe_div(tn, actual_background) * 100:.2f}%")
    print(f"False alarm rate       : {metrics['false_alarm_rate'] * 100:.2f}%")

    print("\n[화재/연기 자동 신고 성능]")
    print(f"탐지 이미지             : {tp}/{actual_alarm}")
    print(f"미탐 이미지             : {fn}/{actual_alarm}")
    print(f"Accuracy               : {metrics['accuracy'] * 100:.2f}%")
    print(f"Precision              : {metrics['precision'] * 100:.2f}%")
    print(f"Recall                 : {metrics['recall'] * 100:.2f}%")
    print(f"F1 Score               : {metrics['f1'] * 100:.2f}%")
    print(f"Miss rate              : {metrics['miss_rate'] * 100:.2f}%")

    print("\n[클래스 존재 여부 성능 — 박스 위치 무관]")
    for item in class_metrics:
        print(
            f"{str(item['name']).capitalize():5s}  "
            f"TP={item['tp']}, FP={item['fp']}, FN={item['fn']}, "
            f"P={float(item['precision']) * 100:.2f}%, "
            f"R={float(item['recall']) * 100:.2f}%, "
            f"F1={float(item['f1']) * 100:.2f}%"
        )
    print("※ 박스 위치 정확도는 위의 IoU 기반 mAP 지표를 확인하세요.")
    print(f"\n상세 예측 CSV           : {output_dir / 'image_level_predictions.csv'}")
    del predictions
    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return metrics


def make_image_level_plot(
    output_dir: Path,
    metrics: dict[str, float],
    class_metrics: list[dict[str, float | int | str]],
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"Comprehensive Image-level Evaluation (conf={PREDICT_CONF})", weight="bold")

    panels = [
        (axes[0, 0], ["Accuracy", "Precision", "Recall", "F1"],
         [metrics["accuracy"], metrics["precision"], metrics["recall"], metrics["f1"]],
         "Binary Alarm Performance"),
        (axes[0, 1], ["Detection", "Miss"],
         [metrics["recall"], metrics["miss_rate"]], "Alarm Detection vs Miss"),
        (axes[1, 0], [str(item["name"]).capitalize() for item in class_metrics],
         [float(item["recall"]) for item in class_metrics], "Class-presence Recall"),
        (axes[1, 1], ["BG Accuracy", "False Alarm"],
         [1.0 - metrics["false_alarm_rate"], metrics["false_alarm_rate"]],
         "Background Control Reliability"),
    ]
    colors = ["#4C72B0", "#55A868", "#DD8452", "#C44E52"]
    for axis, labels, values, title in panels:
        bars = axis.bar(labels, values, color=colors[:len(values)], edgecolor="black", width=0.55)
        axis.set_ylim(0, 1.1)
        axis.set_title(title, weight="bold")
        axis.grid(axis="y", linestyle="--", alpha=0.4)
        for bar, value in zip(bars, values):
            axis.text(bar.get_x() + bar.get_width() / 2, value + 0.02, f"{value * 100:.1f}%", ha="center")
    fig.tight_layout()
    fig.savefig(output_dir / "presentation_image_level_chart.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    split_images = validate_dataset()
    data_yaml = write_data_yaml()
    device = get_device()

    best_path = train_model(data_yaml, device)
    detection_metrics, output_dir = evaluate_detection(best_path, data_yaml, device)
    image_metrics = evaluate_image_level(best_path, split_images["test"], device, output_dir)

    print("\n평가 완료")
    print(f"Best model : {best_path}")
    print(f"Output dir : {output_dir}")
    print(f"mAP50      : {detection_metrics['map50']:.6f}")
    print(f"mAP50-95   : {detection_metrics['map50_95']:.6f}")
    print(f"Alarm F1   : {image_metrics['f1']:.6f}")


if __name__ == "__main__":
    main()
