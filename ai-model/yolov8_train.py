import os
import csv
from pathlib import Path
import torch
import albumentations as A
from ultralytics import YOLO
from ultralytics.models.yolo.detect.train import DetectionTrainer
from yolo11_test import (
    evaluate_background_test as evaluate_background_test_common,
)

# ============================================================
# 1. 기본 설정 (런팟 및 모델 충돌 방지 독립 경로 지정)
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_YAML = (BASE_DIR / ".." / "data" / "data.yaml").resolve()

# ★ [교수 첨삭] 조원들과 파일 오염을 방지하기 위한 v8 독립 폴더 지정
OUTPUT_PROJECT_DIR = "run_v8_0814"
TRAIN_RUN_NAME = "train_v8_compare"
TEST_RUN_NAME = "train_v8_compare_test_evaluation"
# ============================================================
# 2. 클래스 및 환경 상수 (AI 통일 피드백 규격 주입)
# ============================================================
CLASS_NAMES = ["fire", "smoke"]
EPOCHS = 10
IMAGE_SIZE = 640
BATCH_SIZE = 16  # 메모리 OOM 발생 시 8로 낮추어 실행하세요.
WORKERS = 2      # 런팟 환경 병목 및 RAM 오버플로우 방지 최적화 값
SEED = 42

CONF_THRESHOLD = 0.25
IOU_THRESHOLD = 0.7
MATCH_IOU_THRESHOLD = 0.5

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

# ============================================================
# 6. 데이터 증강 (AI 피드백 준수: 몽키패치 배제형 클린 래퍼)
# ============================================================
CUSTOM_AUGMENTATIONS = [
    A.RandomBrightnessContrast(brightness_limit=0.15, contrast_limit=0.15, p=0.40),
    A.HorizontalFlip(p=0.50),
    A.GaussNoise(std_range=(0.01, 0.03), mean_range=(0.0, 0.0), p=0.20),
    A.GaussianBlur(blur_limit=(3, 5), sigma_limit=(0.1, 1.0), p=0.20),
]

class CustomAugmentationTrainer(DetectionTrainer):
    def build_dataset(self, img_path, mode="train", batch=None):
        if mode == "train":
            self.args.augmentations = CUSTOM_AUGMENTATIONS
        return super().build_dataset(img_path, mode=mode, batch=batch)
# ============================================================
# 7 ~ 13. 데이터 파이프라인 및 IO 유틸리티 함수 (원본 로직 100% 유지)
# ============================================================
def check_yaml():
    if not DATA_YAML.exists():
        raise FileNotFoundError(f"data.yaml 파일을 찾을 수 없습니다.\n확인 경로: {DATA_YAML}")

def get_dataset_paths():
    import yaml
    with open(DATA_YAML, "r", encoding="utf-8") as file:
        yaml_data = yaml.safe_load(file)
    
    yaml_root = yaml_data.get("path", "")
    if yaml_root:
        dataset_root = Path(yaml_root)
        if not dataset_root.is_absolute():
            dataset_root = (DATA_YAML.parent / dataset_root).resolve()
    else:
        dataset_root = DATA_YAML.parent.resolve()
        
    return {
        "root": dataset_root,
        "train_images": (dataset_root / yaml_data.get("train")).resolve(),
        "val_images": (dataset_root / yaml_data.get("val")).resolve(),
        "test_images": (dataset_root / yaml_data.get("test")).resolve(),
        "train_labels": image_to_label_dir((dataset_root / yaml_data.get("train")).resolve()),
        "val_labels": image_to_label_dir((dataset_root / yaml_data.get("val")).resolve()),
        "test_labels": image_to_label_dir((dataset_root / yaml_data.get("test")).resolve()),
    }

def image_to_label_dir(image_dir):
    parts = list(image_dir.parts)
    image_index = None
    for index in range(len(parts) - 1, -1, -1):
        if parts[index].lower() == "images":
            image_index = index
            break
    if image_index is None:
        raise ValueError(f"이미지 경로에서 'images' 폴더를 찾을 수 없습니다.\n{image_dir}")
    parts[image_index] = "labels"
    return Path(*parts)

def find_images(directory):
    images = [file for file in directory.rglob("*") if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS]
    return sorted(images)

def find_label_path(image_path, image_root, label_root):
    relative_path = image_path.relative_to(image_root)
    return label_root / relative_path.parent / f"{image_path.stem}.txt"

def read_label_classes(label_path):
    if not label_path.exists():
        return []
    content = label_path.read_text(encoding="utf-8").strip()
    if not content:
        return []
    classes = []
    for line in content.splitlines():
        parts = line.strip().split()
        if len(parts) != 5: continue
        classes.append(int(float(parts[0])))
    return sorted(set(classes))

def read_label_boxes(label_path):
    if not label_path.exists():
        return []
    content = label_path.read_text(encoding="utf-8").strip()
    if not content:
        return []
    return [tuple(float(value) for value in line.split()) for line in content.splitlines()]

def get_device():
    return 0 if torch.cuda.is_available() else "cpu"
# ============================================================
# 18. YOLOv8 대조군 실험 진행 (AI 통일 규격 주입)
# ============================================================
def train_model(device):
    print("\n" + "=" * 70)
    print("🚀 [RESEARCH] YOLOv8n 피드백 반영 대조군 학습 시작")
    print("=" * 70)
    
    # ★ [교수 첨삭] 수강생의 개별 배정 모델인 v8 가중치 선언
    model = YOLO("yolov8n.pt")
    
    results = model.train(
        trainer=CustomAugmentationTrainer,
        data=str(DATA_YAML),
        epochs=EPOCHS,
        imgsz=IMAGE_SIZE,
        batch=BATCH_SIZE,
        
        # [AI 피드백 지침 준수] 오토 옵티마이저 가동 및 초기 하이퍼파라미터 인자 제거
        optimizer="auto",
        seed=SEED,
        deterministic=True,
        
        device=device,
        workers=WORKERS,
        cache=False,  # VRAM/RAM 부족으로 인한 런팟 에러를 원천 차단합니다.
        
        # [AI 피드백 지침 준수] YOLO 자체 내장 가변 증강 변동성 강제 OFF 
        fliplr=0.0,
        flipud=0.0,
        degrees=0.0,
        translate=0.0,
        scale=0.0,
        shear=0.0,
        perspective=0.0,
        mosaic=0.0,
        mixup=0.0,
        cutmix=0.0,
        hsv_h=0.0,
        hsv_s=0.0,
        hsv_v=0.0,
        
        # [결과 저장 경로 독립 격리 변경] 
        project=OUTPUT_PROJECT_DIR,
        name=TRAIN_RUN_NAME,
        exist_ok=True,
        val=True,
        plots=True,
        pretrained=True,
        save=True,
        verbose=True,
    )
    return Path(model.trainer.best).resolve()

# ============================================================
# 20. 최종 TEST 평가 (AI 피드백 지침 준수: split="test")
# ============================================================
def evaluate_test(best_model_path, device):
    print("\n" + "=" * 70)
    print("🎓 [EVALUATION] BEST 모델 최종 TEST 스플릿 평가")
    print("=" * 70)
    
    best_model = YOLO(str(best_model_path))
    metrics = best_model.val(
        data=str(DATA_YAML),
        split="test",  # ★ 핵심 지침: 평가는 무조건 test 스플릿 통일입니다.
        imgsz=IMAGE_SIZE,
        batch=BATCH_SIZE,
        device=device,
        workers=WORKERS,
        # PR/F1/mAP 곡선은 낮은 임계값의 예측까지 포함해 계산합니다.
        conf=0.001,
        iou=IOU_THRESHOLD,
        plots=True,
        project=OUTPUT_PROJECT_DIR,
        name=TEST_RUN_NAME,
        exist_ok=True,
        verbose=True,
    )
    return metrics, Path(metrics.save_dir).resolve()
import matplotlib.pyplot as plt

# ============================================================
# 21 ~ 23. 성능 리포트 및 지표 CSV/컨퓨전 매트릭스 백업 + 커스텀 시각화
# ============================================================
def print_detection_metrics(metrics):
    mp, mr = metrics.box.mp, metrics.box.mr
    overall_f1 = (2 * mp * mr / (mp + mr)) if (mp + mr) > 0 else 0.0
    print(f"\n📊 [TEST 객체 탐지 종합 성능]")
    print(f"Precision : {mp:.6f}")
    print(f"Recall    : {mr:.6f}")
    print(f"F1 Score  : {overall_f1:.6f}")
    print(f"mAP@0.5   : {metrics.box.map50:.6f}")
    print(f"mAP50-95  : {metrics.box.map:.6f}\n")

def save_detection_metrics(metrics, output_dir):
    output_file = output_dir / "metrics_summary.csv"
    mp, mr = metrics.box.mp, metrics.box.mr
    overall_f1 = (2 * mp * mr / (mp + mr)) if (mp + mr) > 0 else 0.0
    
    # 챠트용 데이터 리스트
    labels = ["All"]
    map50_values = [metrics.box.map50]
    
    with open(output_file, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["class_id", "class_name", "precision", "recall", "f1_score", "mAP50", "mAP50-95"])
        writer.writerow(["all", "all", mp, mr, overall_f1, metrics.box.map50, metrics.box.map])
        
        for class_id, class_name in enumerate(CLASS_NAMES):
            try:
                res = metrics.box.class_result(class_id)
                cf1 = (2 * float(res[0]) * float(res[1]) / (float(res[0]) + float(res[1]))) if (float(res[0]) + float(res[1])) > 0 else 0.0
                writer.writerow([class_id, class_name, float(res[0]), float(res[1]), cf1, float(res[2]), float(res[3])])
                
                # 가시화 챠트용 데이터 추가
                labels.append(class_name)
                map50_values.append(float(res[2]))
            except: 
                pass
    print(f"💾 지표 CSV 저장 완료: {output_file}")
    
    # 📊 [발표용 커스텀 시각화 1] 클래스별 mAP@0.5 비교 막대그래프 자동 생성
    try:
        plt.figure(figsize=(8, 5))
        colors = ['#4C72B0', '#DD8452', '#55A868']
        bars = plt.bar(labels, map50_values, color=colors[:len(labels)], edgecolor='black', width=0.5)
        plt.title("YOLOv8 Class-wise mAP@0.5 Performance", fontsize=14, fontweight='bold', pad=15)
        plt.xlabel("Evaluation Target", fontsize=12)
        plt.ylabel("mAP @ 0.5 Score", fontsize=12)
        plt.ylim(0, 1.1)
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        
        # 막대 위에 수치 텍스트 표시
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2.0, height + 0.02, f'{height:.4f}', ha='center', va='bottom', fontsize=11, fontweight='bold')
            
        chart_path = output_dir / "presentation_mAP_chart.png"
        plt.savefig(chart_path, bbox_inches='tight', dpi=300)
        plt.close()
        print(f"📊 발표용 mAP 시각화 그래프 저장 완료: {chart_path}")
    except Exception as e:
        print(f"[WARNING] 커스텀 mAP 차트 생성 실패: {e}")

def save_yolo_confusion_matrix(metrics, output_dir):
    output_file = output_dir / "yolo_confusion_matrix.csv"
    try:
        matrix = metrics.confusion_matrix.matrix
        names = CLASS_NAMES + ["background"]
        
        with open(output_file, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["Predicted / Actual"] + names)
            for index, row in enumerate(matrix):
                row_name = names[index] if index < len(names) else str(index)
                writer.writerow([row_name] + [float(val) for val in row])
        print(f"💾 컨퓨전 매트릭스 CSV 저장 완료: {output_file}")
    except Exception as e:
        print(f"[WARNING] 매트릭스 CSV 저장 실패: {e}")

# ============================================================
# 24. TEST Background 포함 이미지 단위 전수조사 + 오탐 분석 파이차트
# ============================================================
def evaluate_background_test(best_model_path, device, paths, output_dir):
    # 세 모델이 동일한 IoU 매칭, TP/FP/FN/TN 정의와 CSV 형식을
    # 사용하도록 YOLO11과 같은 평가 구현을 공유합니다.
    return evaluate_background_test_common(
        best_model_path,
        device,
        paths,
        output_dir,
    )

# ============================================================
# Main 실행 컨트롤러 (전체 실험 파이프라인 제어)
# ============================================================
def main():
    check_yaml()
    dataset_paths = get_dataset_paths()
    device = get_device()
    
    # 1. YOLOv8 학습 진행 및 최적 pt 추출
    best_pt = train_model(device)
    
    # 2. 최종 오피셜 TEST 세트 평가 및 시각화 플롯 추출
    metrics, eval_save_dir = evaluate_test(best_pt, device)
    
    # 3. 종합 성능 터미널 레포팅 및 CSV/Matrix 디스크 백업 (내부에서 막대차트 생성)
    print_detection_metrics(metrics)
    save_detection_metrics(metrics, eval_save_dir)
    save_yolo_confusion_matrix(metrics, eval_save_dir)
    
    # 4. 백그라운드 정상 샘플 대상 오탐률/미탐률 전수조사 수행 (내부에서 파이차트 생성)
    evaluate_background_test(best_pt, device, dataset_paths, eval_save_dir)

if __name__ == "__main__":
    main()
