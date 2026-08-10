"""
YOLOv10 화재/연기 객체탐지 학습 + 평가 + 시각화 통합 코드

기능
1. YOLOv10n 학습
2. best.pt 기준 Validation 평가
3. Precision / Recall / F1 / mAP50 / mAP50-95 출력
4. 클래스별 AP(mAP50-95 기준) 출력
5. Test 예측 기반 평균 IoU 계산
6. Confidence Score 평균/최소/최대 계산
7. Confusion Matrix, PR/P/R/F1 Curve, results.png 저장
8. 발표용 추가 그래프 저장
9. final_metrics.csv / final_summary.txt 저장
10. 마지막에 핵심 결과를 print()로 출력

전처리 데이터 구조

dataset/
├─ data.yaml
├─ images/train, val, test
└─ labels/train, val, test

클래스
0 = fire
1 = smoke

정상 이미지는 빈 TXT 라벨로 처리되어 있다고 가정합니다.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
import albumentations as A
from ultralytics import YOLO


class YOLOv10FireTrainer:

    def __init__(
        self,
        model_name="yolov10n.pt",
        yaml_path="./dataset/data.yaml",
        image_size=640,
        epochs=10,
        batch=8,
        patience=10,
        conf_threshold=0.25,
    ):
        # 모델 및 데이터 경로
        self.model_name = model_name
        self.yaml_path = Path(yaml_path)

        # 학습 조건
        self.image_size = image_size
        self.epochs = epochs
        self.batch = batch
        self.patience = patience

        # Test 예측 분석 때 사용할 최소 Confidence
        self.conf_threshold = conf_threshold

        # NVIDIA GPU가 있으면 GPU(0), 없으면 CPU 사용
        self.device = 0 if torch.cuda.is_available() else "cpu"

        # 결과 저장 위치
        self.project_dir = Path("./runs/fire_detection")
        self.run_name = "yolov10n_fire"

        self.train_result = None
        self.best_model = None
        self.save_dir = None

    # ============================================================
    # 1. 환경 확인
    # ============================================================
    def check_environment(self):
        """학습 시작 전 파일 경로와 장치를 확인합니다."""

        print("\n" + "=" * 70)
        print("1. 학습 환경 확인")
        print("=" * 70)

        if not self.yaml_path.exists():
            raise FileNotFoundError(
                f"data.yaml을 찾을 수 없습니다: {self.yaml_path.resolve()}"
            )

        print(f"모델             : {self.model_name}")
        print(f"data.yaml        : {self.yaml_path.resolve()}")
        print(f"입력 이미지 크기 : {self.image_size} x {self.image_size}")
        print(f"Epochs           : {self.epochs}")
        print(f"Batch            : {self.batch}")
        print(f"Patience         : {self.patience}")
        print(f"Confidence 기준  : {self.conf_threshold}")

        if self.device == "cpu":
            print("학습 장치         : CPU")
        else:
            print(f"학습 장치         : GPU ({torch.cuda.get_device_name(0)})")

    # ============================================================
    # 2. YOLOv10 학습
    # ============================================================
    def train(self):
        """
        YOLOv10n 사전학습 모델을 Fire/Smoke 데이터로 Fine-Tuning 합니다.

        plots=True로 설정하면 Ultralytics가 다음 자료를 자동 저장합니다.
        - results.png
        - confusion_matrix.png
        - confusion_matrix_normalized.png
        - PR_curve.png
        - P_curve.png
        - R_curve.png
        - F1_curve.png
        """

        print("\n" + "=" * 70)
        print("2. YOLOv10 모델 학습 시작")
        print("=" * 70)

        model = YOLO(self.model_name)

        # ============================================================
        # 커스텀 Albumentations 증강
        # ============================================================
        # CCTV 환경에서 발생할 수 있는 밝기 변화, 센서 노이즈,
        # 약한 흐림을 가정한 증강입니다.
        #
        # Train 데이터에만 학습 중 적용되며 Val/Test에는 적용되지 않습니다.
        # 아래 3개는 이미지의 픽셀 값만 바꾸므로 bbox 위치는 그대로 유지됩니다.
        custom_augmentations = [
            # 밝기 ±15%, 대비 ±15% / 40% 확률
            A.RandomBrightnessContrast(
                brightness_limit=0.15,
                contrast_limit=0.15,
                p=0.40,
            ),

            # 약한 Gaussian Noise / 20% 확률
            A.GaussNoise(
                std_range=(0.01, 0.03),
                mean_range=(0.0, 0.0),
                p=0.20,
            ),

            # 약한 Gaussian Blur(3x3~5x5) / 20% 확률
            A.GaussianBlur(
                blur_limit=(3, 5),
                sigma_limit=(0.1, 1.0),
                p=0.20,
            ),
        ]

        print("\n[학습 증강 설정]")
        print("- RandomBrightnessContrast : p=0.40")
        print("- GaussNoise               : p=0.20")
        print("- GaussianBlur             : p=0.20")

        start_time = time.time()

        self.train_result = model.train(
            data=str(self.yaml_path),
            epochs=self.epochs,
            imgsz=self.image_size,
            batch=self.batch,
            device=self.device,
            patience=self.patience,

            # 사용자 정의 Albumentations 증강 적용
            augmentations=custom_augmentations,

            plots=True,
            save=True,
            seed=42,
            deterministic=True,
            optimizer="auto",
            val=True,
            project=str(self.project_dir),
            name=self.run_name,
            exist_ok=False,
            verbose=True,
        )

        elapsed = time.time() - start_time

        self.save_dir = Path(self.train_result.save_dir)
        best_path = self.save_dir / "weights" / "best.pt"

        if not best_path.exists():
            raise FileNotFoundError(f"best.pt를 찾을 수 없습니다: {best_path}")

        self.best_model = YOLO(str(best_path))

        print("\n학습 완료")
        print(f"학습 시간      : {elapsed / 60:.2f}분")
        print(f"결과 저장 위치 : {self.save_dir}")
        print(f"Best 모델      : {best_path}")

        return elapsed

    # ============================================================
    # 3. Validation 평가
    # ============================================================
    def validate(self):
        """
        best.pt를 Validation 데이터로 평가합니다.

        Precision : 탐지했다고 판단한 객체 중 실제 정답 비율
        Recall    : 실제 객체 중 모델이 찾아낸 비율
        mAP50     : IoU 0.50 기준 AP의 클래스 평균
        mAP50-95  : IoU 0.50~0.95 기준 AP 평균
        """

        print("\n" + "=" * 70)
        print("3. Validation 성능 평가")
        print("=" * 70)

        metrics = self.best_model.val(
            data=str(self.yaml_path),
            split="val",
            imgsz=self.image_size,
            device=self.device,
            conf=0.001,
            plots=True,
            project=str(self.save_dir),
            name="validation",
        )

        precision = float(metrics.box.mp)
        recall = float(metrics.box.mr)
        map50 = float(metrics.box.map50)
        map50_95 = float(metrics.box.map)

        # F1 Score 직접 계산
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall > 0
            else 0.0
        )

        # 클래스별 AP(mAP50-95 기준)
        class_maps = np.asarray(metrics.box.maps, dtype=float)
        class_names = self.best_model.names

        print("\n[Validation 전체 성능]")
        print(f"Precision       : {precision:.4f} ({precision * 100:.2f}%)")
        print(f"Recall          : {recall:.4f} ({recall * 100:.2f}%)")
        print(f"F1-Score        : {f1:.4f} ({f1 * 100:.2f}%)")
        print(f"mAP@0.50        : {map50:.4f} ({map50 * 100:.2f}%)")
        print(f"mAP@0.50:0.95   : {map50_95:.4f} ({map50_95 * 100:.2f}%)")

        print("\n[클래스별 AP - mAP50:95 기준]")
        for class_id, ap_value in enumerate(class_maps):
            class_name = class_names.get(class_id, str(class_id))
            print(
                f"{class_name:<10} AP : "
                f"{ap_value:.4f} ({ap_value * 100:.2f}%)"
            )

        return {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "map50": map50,
            "map50_95": map50_95,
            "class_maps": class_maps,
            "class_names": class_names,
        }

    # ============================================================
    # 4. YOLO TXT 라벨을 실제 픽셀 좌표로 복원
    # ============================================================
    @staticmethod
    def load_ground_truth(label_path, image_width, image_height):
        """
        YOLO 라벨
            class x_center y_center width height
        를
            class x1 y1 x2 y2
        픽셀 좌표로 바꿉니다.
        """

        boxes = []

        if not label_path.exists():
            return boxes

        text = label_path.read_text(encoding="utf-8").strip()

        # 정상 이미지는 빈 TXT이므로 여기서 빈 리스트 반환
        if not text:
            return boxes

        for line in text.splitlines():
            values = line.split()

            if len(values) != 5:
                continue

            class_id = int(float(values[0]))
            xc = float(values[1]) * image_width
            yc = float(values[2]) * image_height
            w = float(values[3]) * image_width
            h = float(values[4]) * image_height

            x1 = xc - w / 2
            y1 = yc - h / 2
            x2 = xc + w / 2
            y2 = yc + h / 2

            boxes.append(
                {
                    "class_id": class_id,
                    "box": np.array([x1, y1, x2, y2], dtype=float),
                }
            )

        return boxes

    # ============================================================
    # 5. IoU 계산
    # ============================================================
    @staticmethod
    def calculate_iou(box_a, box_b):
        """
        IoU = 실제 박스와 예측 박스의 겹친 영역 / 합친 전체 영역

        0~1 사이 값이며 1에 가까울수록 위치가 잘 맞습니다.
        """

        x1 = max(box_a[0], box_b[0])
        y1 = max(box_a[1], box_b[1])
        x2 = min(box_a[2], box_b[2])
        y2 = min(box_a[3], box_b[3])

        inter_w = max(0.0, x2 - x1)
        inter_h = max(0.0, y2 - y1)
        intersection = inter_w * inter_h

        area_a = max(0.0, box_a[2] - box_a[0]) * max(
            0.0, box_a[3] - box_a[1]
        )
        area_b = max(0.0, box_b[2] - box_b[0]) * max(
            0.0, box_b[3] - box_b[1]
        )

        union = area_a + area_b - intersection

        if union <= 0:
            return 0.0

        return intersection / union

    # ============================================================
    # 6. Test 데이터 IoU / Confidence 분석
    # ============================================================
    def evaluate_iou_and_confidence(self):
        """
        Test 이미지에서 실제 박스와 예측 박스를 직접 비교합니다.

        같은 클래스끼리만 비교하고,
        Confidence가 높은 예측부터 가장 IoU가 높은 GT 박스와 매칭합니다.

        계산값
        - Average IoU
        - Median IoU
        - Average Confidence
        - Min / Max Confidence
        """

        print("\n" + "=" * 70)
        print("4. Test IoU / Confidence Score 분석")
        print("=" * 70)

        test_image_dir = Path("./dataset/images/test")
        test_label_dir = Path("./dataset/labels/test")

        default_result = {
            "ious": [],
            "confidences": [],
            "mean_iou": 0.0,
            "median_iou": 0.0,
            "mean_conf": 0.0,
            "min_conf": 0.0,
            "max_conf": 0.0,
        }

        if not test_image_dir.exists():
            print("Test 이미지 폴더가 없어 추가 분석을 생략합니다.")
            return default_result

        image_files = []
        for extension in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
            image_files.extend(test_image_dir.glob(extension))

        image_files = sorted(image_files)

        if not image_files:
            print("Test 이미지가 없어 추가 분석을 생략합니다.")
            return default_result

        # Test 폴더 전체 추론
        prediction_results = self.best_model.predict(
            source=str(test_image_dir),
            imgsz=self.image_size,
            conf=self.conf_threshold,
            device=self.device,
            save=True,
            project=str(self.save_dir),
            name="test_predictions",
            verbose=False,
        )

        all_ious = []
        all_confidences = []

        for result in prediction_results:
            image_path = Path(result.path)
            label_path = test_label_dir / f"{image_path.stem}.txt"

            original_height, original_width = result.orig_shape

            gt_boxes = self.load_ground_truth(
                label_path,
                original_width,
                original_height,
            )

            used_gt = set()
            predictions = []

            if result.boxes is None:
                continue

            # 모델 예측값 수집
            for box in result.boxes:
                pred_class = int(box.cls.item())
                confidence = float(box.conf.item())
                xyxy = box.xyxy[0].cpu().numpy().astype(float)

                predictions.append(
                    {
                        "class_id": pred_class,
                        "confidence": confidence,
                        "box": xyxy,
                    }
                )

                all_confidences.append(confidence)

            # Confidence 높은 예측부터 GT와 매칭
            predictions.sort(
                key=lambda item: item["confidence"],
                reverse=True,
            )

            for pred in predictions:
                best_iou = 0.0
                best_gt_index = None

                for gt_index, gt in enumerate(gt_boxes):
                    if gt_index in used_gt:
                        continue

                    # Fire는 Fire, Smoke는 Smoke끼리 비교
                    if gt["class_id"] != pred["class_id"]:
                        continue

                    current_iou = self.calculate_iou(
                        pred["box"],
                        gt["box"],
                    )

                    if current_iou > best_iou:
                        best_iou = current_iou
                        best_gt_index = gt_index

                if best_gt_index is not None:
                    used_gt.add(best_gt_index)
                    all_ious.append(best_iou)

        mean_iou = float(np.mean(all_ious)) if all_ious else 0.0
        median_iou = float(np.median(all_ious)) if all_ious else 0.0
        mean_conf = float(np.mean(all_confidences)) if all_confidences else 0.0
        min_conf = float(np.min(all_confidences)) if all_confidences else 0.0
        max_conf = float(np.max(all_confidences)) if all_confidences else 0.0

        print(f"Test 이미지 수       : {len(image_files)}")
        print(f"예측 박스 수         : {len(all_confidences)}")
        print(f"GT 매칭 박스 수      : {len(all_ious)}")
        print(f"Average IoU          : {mean_iou:.4f} ({mean_iou * 100:.2f}%)")
        print(f"Median IoU           : {median_iou:.4f} ({median_iou * 100:.2f}%)")
        print(f"Average Confidence   : {mean_conf:.4f} ({mean_conf * 100:.2f}%)")
        print(f"Minimum Confidence   : {min_conf:.4f} ({min_conf * 100:.2f}%)")
        print(f"Maximum Confidence   : {max_conf:.4f} ({max_conf * 100:.2f}%)")

        return {
            "ious": all_ious,
            "confidences": all_confidences,
            "mean_iou": mean_iou,
            "median_iou": median_iou,
            "mean_conf": mean_conf,
            "min_conf": min_conf,
            "max_conf": max_conf,
        }

    # ============================================================
    # 7. 발표용 추가 시각화
    # ============================================================
    def create_custom_visualizations(self, metrics, extra_metrics):
        """
        Ultralytics 기본 그래프 외에 아래 발표용 그래프를 추가 저장합니다.

        - performance_summary.png
        - class_ap.png
        - iou_distribution.png
        - confidence_distribution.png
        """

        print("\n" + "=" * 70)
        print("5. 추가 데이터 시각화 생성")
        print("=" * 70)

        visual_dir = self.save_dir / "custom_visualization"
        visual_dir.mkdir(parents=True, exist_ok=True)

        # A. 주요 성능지표 막대그래프
        metric_names = [
            "Precision",
            "Recall",
            "F1",
            "mAP50",
            "mAP50-95",
            "Avg IoU",
            "Avg Conf",
        ]

        metric_values = [
            metrics["precision"],
            metrics["recall"],
            metrics["f1"],
            metrics["map50"],
            metrics["map50_95"],
            extra_metrics["mean_iou"],
            extra_metrics["mean_conf"],
        ]

        plt.figure(figsize=(11, 6))
        bars = plt.bar(metric_names, metric_values)
        plt.ylim(0, 1.0)
        plt.ylabel("Score")
        plt.title("YOLOv10 Fire Detection Performance Summary")
        plt.xticks(rotation=20)

        for bar, value in zip(bars, metric_values):
            plt.text(
                bar.get_x() + bar.get_width() / 2,
                min(value + 0.02, 0.98),
                f"{value:.3f}",
                ha="center",
                fontsize=9,
            )

        plt.tight_layout()
        plt.savefig(visual_dir / "performance_summary.png", dpi=200)
        plt.close()

        # B. 클래스별 AP 그래프
        names = []
        values = []

        for class_id, ap_value in enumerate(metrics["class_maps"]):
            names.append(metrics["class_names"].get(class_id, str(class_id)))
            values.append(float(ap_value))

        plt.figure(figsize=(7, 5))
        bars = plt.bar(names, values)
        plt.ylim(0, 1.0)
        plt.ylabel("AP (mAP50-95)")
        plt.title("AP by Class")

        for bar, value in zip(bars, values):
            plt.text(
                bar.get_x() + bar.get_width() / 2,
                min(value + 0.02, 0.98),
                f"{value:.3f}",
                ha="center",
            )

        plt.tight_layout()
        plt.savefig(visual_dir / "class_ap.png", dpi=200)
        plt.close()

        # C. IoU 분포 그래프
        if extra_metrics["ious"]:
            plt.figure(figsize=(8, 5))
            plt.hist(
                extra_metrics["ious"],
                bins=10,
                range=(0, 1),
                edgecolor="black",
            )
            plt.xlim(0, 1)
            plt.xlabel("IoU")
            plt.ylabel("Matched Box Count")
            plt.title("IoU Distribution")
            plt.tight_layout()
            plt.savefig(visual_dir / "iou_distribution.png", dpi=200)
            plt.close()

        # D. Confidence Score 분포 그래프
        if extra_metrics["confidences"]:
            plt.figure(figsize=(8, 5))
            plt.hist(
                extra_metrics["confidences"],
                bins=10,
                range=(0, 1),
                edgecolor="black",
            )
            plt.xlim(0, 1)
            plt.xlabel("Confidence Score")
            plt.ylabel("Prediction Count")
            plt.title("Confidence Score Distribution")
            plt.tight_layout()
            plt.savefig(visual_dir / "confidence_distribution.png", dpi=200)
            plt.close()

        print(f"추가 시각화 저장 위치 : {visual_dir}")

    # ============================================================
    # 8. 최종 결과 CSV / TXT 저장
    # ============================================================
    def save_summary(self, metrics, extra_metrics, elapsed):
        """주요 결과를 CSV와 TXT로 저장합니다."""

        summary_csv = self.save_dir / "final_metrics.csv"
        summary_txt = self.save_dir / "final_summary.txt"

        rows = [
            ["Model", self.model_name],
            ["Epochs", self.epochs],
            ["Image Size", self.image_size],
            ["Precision", metrics["precision"]],
            ["Recall", metrics["recall"]],
            ["F1 Score", metrics["f1"]],
            ["mAP50", metrics["map50"]],
            ["mAP50-95", metrics["map50_95"]],
            ["Average IoU", extra_metrics["mean_iou"]],
            ["Median IoU", extra_metrics["median_iou"]],
            ["Average Confidence", extra_metrics["mean_conf"]],
            ["Minimum Confidence", extra_metrics["min_conf"]],
            ["Maximum Confidence", extra_metrics["max_conf"]],
            ["Training Time Minutes", elapsed / 60],
        ]

        with summary_csv.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["Metric", "Value"])
            writer.writerows(rows)

        lines = [
            "=" * 70,
            "YOLOv10 Fire / Smoke Detection Final Result",
            "=" * 70,
            f"Model              : {self.model_name}",
            f"Epochs             : {self.epochs}",
            f"Image Size         : {self.image_size}",
            f"Precision          : {metrics['precision']:.4f} ({metrics['precision']*100:.2f}%)",
            f"Recall             : {metrics['recall']:.4f} ({metrics['recall']*100:.2f}%)",
            f"F1 Score           : {metrics['f1']:.4f} ({metrics['f1']*100:.2f}%)",
            f"mAP@0.50           : {metrics['map50']:.4f} ({metrics['map50']*100:.2f}%)",
            f"mAP@0.50:0.95      : {metrics['map50_95']:.4f} ({metrics['map50_95']*100:.2f}%)",
            f"Average IoU        : {extra_metrics['mean_iou']:.4f} ({extra_metrics['mean_iou']*100:.2f}%)",
            f"Median IoU         : {extra_metrics['median_iou']:.4f} ({extra_metrics['median_iou']*100:.2f}%)",
            f"Average Confidence : {extra_metrics['mean_conf']:.4f} ({extra_metrics['mean_conf']*100:.2f}%)",
            f"Min Confidence     : {extra_metrics['min_conf']:.4f}",
            f"Max Confidence     : {extra_metrics['max_conf']:.4f}",
            f"Training Time      : {elapsed / 60:.2f} min",
            "",
            "[Class AP - mAP50:95]",
        ]

        for class_id, ap_value in enumerate(metrics["class_maps"]):
            class_name = metrics["class_names"].get(class_id, str(class_id))
            lines.append(
                f"{class_name:<10} : {float(ap_value):.4f} "
                f"({float(ap_value)*100:.2f}%)"
            )

        lines.extend(
            [
                "",
                f"Result Directory   : {self.save_dir}",
                "=" * 70,
            ]
        )

        summary_txt.write_text("\n".join(lines), encoding="utf-8")

        print(f"최종 CSV 저장 : {summary_csv}")
        print(f"최종 TXT 저장 : {summary_txt}")

    # ============================================================
    # 9. 마지막 Print 결과 출력
    # ============================================================
    def print_final_result(self, metrics, extra_metrics, elapsed):
        """터미널에서 최종 성능을 한 번에 확인할 수 있게 출력합니다."""

        print("\n\n" + "=" * 75)
        print("               YOLOv10 최종 모델 성능 결과")
        print("=" * 75)
        print(f"Model               : {self.model_name}")
        print(f"Epoch                : {self.epochs}")
        print(f"Image Size           : {self.image_size} x {self.image_size}")
        print("Augmentation         : Brightness/Contrast 40%, Noise 20%, Blur 20%")
        print("-" * 75)

        print(
            f"Precision            : {metrics['precision']:.4f} "
            f"({metrics['precision'] * 100:.2f}%)"
        )
        print(
            f"Recall               : {metrics['recall']:.4f} "
            f"({metrics['recall'] * 100:.2f}%)"
        )
        print(
            f"F1-Score             : {metrics['f1']:.4f} "
            f"({metrics['f1'] * 100:.2f}%)"
        )
        print(
            f"mAP@0.50             : {metrics['map50']:.4f} "
            f"({metrics['map50'] * 100:.2f}%)"
        )
        print(
            f"mAP@0.50:0.95        : {metrics['map50_95']:.4f} "
            f"({metrics['map50_95'] * 100:.2f}%)"
        )
        print(
            f"Average IoU          : {extra_metrics['mean_iou']:.4f} "
            f"({extra_metrics['mean_iou'] * 100:.2f}%)"
        )
        print(
            f"Average Confidence   : {extra_metrics['mean_conf']:.4f} "
            f"({extra_metrics['mean_conf'] * 100:.2f}%)"
        )

        print("-" * 75)
        print("클래스별 AP (mAP50:95)")

        for class_id, ap_value in enumerate(metrics["class_maps"]):
            class_name = metrics["class_names"].get(class_id, str(class_id))
            print(
                f"{class_name:<20}: {float(ap_value):.4f} "
                f"({float(ap_value) * 100:.2f}%)"
            )

        print("-" * 75)
        print(f"학습 시간            : {elapsed / 60:.2f}분")
        print(f"결과 저장 위치       : {self.save_dir}")
        print(f"Best 모델 위치       : {self.save_dir / 'weights' / 'best.pt'}")
        print("=" * 75)

        print("\n[자동/추가 생성 시각화]")
        print("- results.png")
        print("- confusion_matrix.png")
        print("- confusion_matrix_normalized.png")
        print("- PR_curve.png")
        print("- P_curve.png")
        print("- R_curve.png")
        print("- F1_curve.png")
        print("- custom_visualization/performance_summary.png")
        print("- custom_visualization/class_ap.png")
        print("- custom_visualization/iou_distribution.png")
        print("- custom_visualization/confidence_distribution.png")

    # ============================================================
    # 전체 실행
    # ============================================================
    def run(self):
        self.check_environment()
        elapsed = self.train()
        metrics = self.validate()
        extra_metrics = self.evaluate_iou_and_confidence()
        self.create_custom_visualizations(metrics, extra_metrics)
        self.save_summary(metrics, extra_metrics, elapsed)
        self.print_final_result(metrics, extra_metrics, elapsed)


# ================================================================
# 프로그램 실행
# ================================================================
if __name__ == "__main__":

    trainer = YOLOv10FireTrainer(
        # 샘플 확인용 YOLOv10 Nano 모델
        model_name="yolov10n.pt",

        # 팀원 전처리 코드가 만든 data.yaml
        yaml_path="./dataset/data.yaml",

        # 전처리 Letterbox 크기와 동일
        image_size=640,

        # 확인용 기본값. 전체 학습 때 늘려도 됩니다.
        epochs=10,

        # GPU 메모리 부족 또는 CPU 학습이면 4/2로 낮추세요.
        batch=8,

        # 일정 Epoch 동안 성능 개선이 없으면 Early Stopping
        patience=10,

        # Test Confidence 분석 기준
        conf_threshold=0.25,
    )

    trainer.run()
