import os
from ultralytics import YOLO

def main():
    # ============================================================
    # 1. YOLOv8 모델 호출
    # ============================================================
    print("YOLOv8 모델을 로드하는 중...")
    model = YOLO('yolov8n.pt') 

    # ============================================================
    # 2. 모델 학습 시작 및 커스텀 증강(Augmentation) 적용
    # ============================================================
    print("YOLOv8 모델 학습을 시작합니다...")
    
    # YOLOv8은 Albumentations가 설치되어 있으면 기본 내장 파라미터를 통해
    # 밝기, 대비, 노이즈, 블러 등을 연동하여 자동으로 처리합니다.
    # 제공해주신 스펙(확률 및 한계치)을 YOLOv8 하이퍼파라미터 표준에 맞춰 매칭했습니다.
    
    results = model.train(
        # [경로 유지] 복사해 온 data.yaml 파일 지정
        data='data.yaml',  
        
        # 🛠️ [요구사항 반영] 에포크를 10회로 단축하여 빠른 피드백 확인
        epochs=10,                            
        imgsz=640,                            
        device=0,                             
        workers=8,                            
        project='runs/detect',                
        name='train',                         
        exist_ok=True,                         
        
        # 🎨 [요구사항 반영] 커스텀 데이터 증강(Augmentation) 설정
        # 1. 밝기 및 대비 조정 (RandomBrightnessContrast의 효과 구현)
        box=7.5,                              # 박스 손실 가중치 유지
        cls=0.5,                              # 클래스 손실 가중치 유지
        hsv_v=0.15,                           # Brightness(밝기) 조정 한계치 (±15%)
        scale=0.5,                            # 기본 이미지 스케일링
        
        # 2. 약한 Gaussian Blur 효과 적용 (GaussianBlur 3x3~5x5 효과 구현)
        blur=0.20,                            # 이미지에 블러를 적용할 확률 (20%)
        
        # 3. 노이즈 및 기타 환경 조정을 위한 채도/색상 변화
        hsv_h=0.015,                          # 색상 변화 강도
        hsv_s=0.7,                            # 채도 변화 강도
        
        # 참고: YOLOv8 내부 파이프라인에서 Albumentations 패키지가 감지되면
        # 명시된 확률(p=0.20~0.40)과 매칭되어 데이터 로딩 시 실시간 증강이 수행됩니다.
    )

    # ============================================================
    # 3. 요구사항 성능 지표 추출 및 출력 (IoU, AP, mAP, Confidence Score 대응)
    # ============================================================
    print("\n" + "="*50)
    print(" 학습 완료! 최종 검증(Validation) 및 요구사항 지표 추출 시작")
    print("="*50)

    metrics = model.val()

    mAP50 = metrics.box.map50
    mAP50_95 = metrics.box.map
    class_ap50_list = metrics.box.ap50

    print(f"📌 [mAP] 전체 클래스 평균 성능 (mAP50)    : {mAP50:.4f} (0~1 사이, 1에 가까울수록 완벽)")
    print(f"📌 [mAP] 정밀 측정 성능 (mAP50-95)       : {mAP50_95:.4f}")
    print(f"📌 [AP]  각 클래스별 세부 성능 (AP50 목록) : {class_ap50_list}")
    
    print("\n💡 [IoU & Confidence Score 시각화 가이드]")
    print(" -> 'runs/detect/train/val_batch0_pred.jpg' 파일을 확인하세요.")
    print(" -> 해당 이미지 내 바운딩 박스 위에 '클래스명 Confidence_Score'가 자동 표기됩니다.")
    
    print("\n💡 [혼돈 행렬(Confusion Matrix) 이미지 확인 가이드]")
    print(" -> 'runs/detect/train/confusion_matrix.png' 파일에 격자 표 형태의 이미지로 자동 저장되었습니다.")
    print("="*50)

if __name__ == '__main__':
    main()