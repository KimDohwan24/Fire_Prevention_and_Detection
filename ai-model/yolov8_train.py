import os
import csv
import torch
import albumentations as A
from pathlib import Path
from ultralytics import YOLO

def main():
    # ============================================================
    # [피드백 5, 6번 반영] 증강 정의 및 인자 주입 방식 변경 (몽키패치 제거)
    # ============================================================
    CUSTOM_AUGMENTATIONS = [
        A.RandomBrightnessContrast(brightness_limit=0.15, contrast_limit=0.15, p=0.40),
        A.GaussNoise(std_range=(0.01, 0.03), mean_range=(0.0, 0.0), p=0.20),
        A.GaussianBlur(blur_limit=(3, 5), sigma_limit=(0.1, 1.0), p=0.20),
    ]

    # [피드백 1, 2번 반영] 데이터 경로 설정 (평가는 test 스플릿 조준)
    DATA_YAML_PATH = "../data/data.yaml"
    
    # 최종 평가(Background 전수조사) 대상 폴더를 'test' 스플릿으로 변경
    TEST_IMAGE_DIR = "../data/yolo_split/images/test"
    TEST_LABEL_DIR = "../data/yolo_split/labels/test"
    CLASS_NAMES = ["fire", "smoke"]
    
    # ★ [교수 첨삭] 파일 충돌 및 오염 방지를 위해 v8 전용 날짜 폴더 정의
    OUTPUT_PROJECT_DIR = "run_v8_0814"
    RUN_NAME = "train_v8_compare"
    
    model_name = "yolov8n.pt"  
    print(f"🔬 [RESEARCH] {model_name} 기반 피드백 반영 통일 실험을 시작합니다.")
    print(f"📁 [PATH] 모든 실험 결과는 독립 폴더 '{OUTPUT_PROJECT_DIR}/{RUN_NAME}'에 안전하게 저장됩니다.")
    model = YOLO(model_name) 

    # ============================================================
    # [피드백 3, 4, 5, 7번 반영] 하이퍼파라미터 공정 통일 구역
    # ============================================================
    results = model.train(
        data=DATA_YAML_PATH,   
        imgsz=640,                 
        epochs=10,                 # [피드백 3] epochs=10 통일
        batch=8,                   
        patience=10,               
        
        # [피드백 4] optimizer="auto" 설정 및 lr0, momentum 제거
        optimizer='auto',           
        val=True,                  
        conf=0.001,                
        
        # 런팟 OOM 방지 및 하드웨어 가속
        device=0,                  
        workers=2,                 
        cache=False,               
        
        # [피드백 7] Seed 및 Deterministic 환경 고정
        seed=42,
        deterministic=True,
        
        # [피드백 6] 증강 주입 방식을 'augmentations=' 인자로 직접 전달
        augmentations=CUSTOM_AUGMENTATIONS,
        
        # [피드백 5] 내장 증강 플래그 전부 명시 및 제어
        fliplr=0.5,         
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
        
        # 결과 저장 및 시각화 자료 뽑기 강제 활성화
        project=OUTPUT_PROJECT_DIR, # ★ 'run_v8_0814'로 경로 변경     
        name=RUN_NAME,   
        exist_ok=True,             
        plots=True,                
        box=7.5,
        cls=0.5,
    )

    # ============================================================
    # [피드백 2번 반영] 최종 평가는 단 1개의 test 스플릿과 함수로 수행
    # ============================================================
    print("\n" + "="*60)
    print("🎓 [EVALUATION] 학습 완료. 피드백 기준에 맞춰 'test' 스플릿 최종 평가를 시작합니다.")
    print("="*60)

    output_dir = Path(results.save_dir)
    best_model_path = output_dir / "weights" / "best.pt"
    
    if not best_model_path.exists():
        best_model_path = output_dir / "weights" / "last.pt"

    # [피드백 2] 검증(val)이 아닌 최종 평가용 test 스플릿 적용
    best_model = YOLO(str(best_model_path))
    test_metrics = best_model.val(
        data=DATA_YAML_PATH,
        split="test",          # ★ 핵심: 최종 평가는 오직 test 스플릿으로 통일
        imgsz=640,
        batch=8,
        device=0,
        workers=2,
        plots=True,            # 대조군 비교를 위한 Confusion Matrix, PR-Curve 시각화 출력
        project=OUTPUT_PROJECT_DIR, # ★ 검증 플롯 파일도 'run_v8_0814' 내부로 경로 통일
        name=f"{RUN_NAME}_test_evaluation",
        exist_ok=True
    )

    # 메트릭 안전 추출
    mp = test_metrics.box.mp        
    mr = test_metrics.box.mr        
    map50 = test_metrics.box.map50  
    map95 = test_metrics.box.map    

    print(f"📊 [{model_name} 최종 TEST 성능 보고서]")
    print(f"✔️ Precision (정밀도) : {mp:.6f}")
    print(f"✔️ Recall    (재현율) : {mr:.6f}")
    print(f"✔️ mAP50              : {map50:.4f}")
    print(f"✔️ mAP50-95           : {map95:.4f}")

    # 성능 지표 CSV 저장 파이프라인
    csv_path = output_dir / "metrics_summary.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["class_id", "class_name", "precision", "recall", "mAP50", "mAP50-95"])
        writer.writerow(["all", "all", mp, mr, map50, map95])
        
        try:
            for class_id, class_name in enumerate(CLASS_NAMES):
                result = test_metrics.box.class_result(class_id)
                writer.writerow([class_id, class_name, float(result), float(result), float(result), float(result)])
            print(f"💾 클래스별 연구용 CSV 백업 완료: {csv_path}")
        except Exception as e:
            print(f"[WARNING] 클래스별 세부 지표 기록 생략 (전체 지표는 요약 저장됨): {e}")

    # ============================================================
    # [피드백 2번 연동] Background 포함 이미지 단위 평가 루틴 (test 셋 대상)
    # ============================================================
    evaluate_background_images_on_test(
        model_path=best_model_path,
        test_image_dir=TEST_IMAGE_DIR,
        test_label_dir=TEST_LABEL_DIR,
        conf_threshold=0.25,
        iou_threshold=0.7,
        imgsz=640,
        device=0
    )


def evaluate_background_images_on_test(model_path, test_image_dir, test_label_dir, conf_threshold, iou_threshold, imgsz, device):
    """ test 스플릿의 정상(Background) 이미지 단위 전수조사 함수 """
    print("\n" + "=" * 70)
    print("🎓 [EVALUATION] TEST 스플릿 기준 BACKGROUND 단위 상세 평가")
    print("=" * 70)
    
    model = YOLO(str(model_path))
    test_images = sorted([f for f in Path(test_image_dir).iterdir() if f.is_file() and f.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp", ".webp"]])
    
    if not test_images:
        print("[WARNING] test 스플릿 이미지 폴더가 비어있거나 경로가 올바르지 않습니다.")
        return

    total_images = 0
    actual_background = 0
    actual_object_images = 0
    background_correct = 0
    background_false_positive = 0
    object_detected_images = 0
    object_missed_images = 0
    
    for image_path in test_images:
        total_images += 1
        label_path = Path(test_label_dir) / f"{image_path.stem}.txt"
        
        if not label_path.exists() or not label_path.read_text(encoding="utf-8").strip():
            actual_classes = []
        else:
            actual_classes = [int(float(line.split())) for line in label_path.read_text(encoding="utf-8").strip().splitlines() if line.split()]
            
        actual_is_background = (len(actual_classes) == 0)
        
        results = model.predict(source=str(image_path), conf=conf_threshold, iou=iou_threshold, imgsz=imgsz, device=device, verbose=False)
        predicted_classes = []
        if len(results) > 0 and results.boxes is not None:
            predicted_classes = [int(cls) for cls in results.boxes.cls.cpu().tolist()]
            
        predicted_is_background = (len(predicted_classes) == 0)
        
        if actual_is_background:
            actual_background += 1
            if predicted_is_background:
                background_correct += 1
            else:
                background_false_positive += 1
        else:
            actual_object_images += 1
            if predicted_is_background:
                object_missed_images += 1
            else:
                object_detected_images += 1

    bg_acc = (background_correct / actual_background) if actual_background > 0 else 0.0
    bg_fpr = (background_false_positive / actual_background) if actual_background > 0 else 0.0
    obj_det_rate = (object_detected_images / actual_object_images) if actual_object_images > 0 else 0.0
    obj_miss_rate = (object_missed_images / actual_object_images) if actual_object_images > 0 else 0.0
    
    print(f"평가 이미지 수 : {len(test_images)}")
    print(f"✔️ [TEST] 정상 이미지 맞춘 정확도 : {bg_acc:.4f}")
    print(f"✔️ [TEST] 정상 이미지 오탐 확률(FPR): {bg_fpr:.4f}")
    print(f"✔️ [TEST] 화재 이미지 탐지 성공률    : {obj_det_rate:.4f}")
    print(f"✔️ [TEST] 화재 이미지 미탐 확률(Miss) : {obj_miss_rate:.4f}")
    print("=" * 70)

if __name__ == "__main__":
    main()
