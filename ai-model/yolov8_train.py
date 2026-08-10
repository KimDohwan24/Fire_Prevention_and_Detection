import os
from ultralytics import YOLO

def main():
    # ============================================================
    # 1. YOLOv8 모델 호출
    # ============================================================
    # 사전 학습된(Pre-trained) 베이스 모델을 불러옵니다.
    # 성능과 속도에 따라 n(nano), s(small), m(medium), l(large), x(xlarge) 선택 가능합니다.
    print("YOLOv8 모델을 로드하는 중...")
    model = YOLO('yolov8n.pt') 

    # ============================================================
    # 2. 모델 학습 시작 (YOLOv8 학습 프로세스 실행)
    # ============================================================
    # 이 명령어가 실행되면 YOLOv8은 내부적으로 지정된 yaml 설정을 읽어 학습을 시작합니다.
    # 학습 과정에서 혼돈 행렬(Confusion Matrix) 이미지와 bbox 시각화 결과가 
    # 'runs/detect/train/' 폴더 내에 자동으로 실시간 생성 및 저장됩니다.
    print("YOLOv8 모델 학습을 시작합니다...")
    results = model.train(
        data='/workspace/dataset/data.yaml',  # 전처리 경로 정보가 담긴 yaml 파일의 절대 경로
        epochs=100,                           # 전체 데이터셋을 반복 학습할 횟수 (기본 100)
        imgsz=640,                            # 입력 이미지 크기 (기본 640x640)
        device=0,                             # 사용할 GPU 번호 (RunPod의 단일 GPU 환경은 보통 0)
        workers=8,                            # 데이터 로딩에 사용할 CPU 스레드 개수 (RunPod 성능에 맞춤)
        project='runs/detect',                # 결과물이 저장될 상위 폴더 이름
        name='train',                         # 결과물이 저장될 하위 폴더 이름 (최종 경로: runs/detect/train/)
        exist_ok=True                         # 동일한 이름의 폴더가 이미 존재할 경우 덮어쓰기 허용
    )

    # ============================================================
    # 3. 요구사항 성능 지표 추출 및 출력 (IoU, AP, mAP, Confidence Score 대응)
    # ============================================================
    print("\n" + "="*50)
    print(" 학습 완료! 최종 검증(Validation) 및 요구사항 지표 추출 시작")
    print("="*50)

    # 학습이 끝난 후, 가장 성능이 좋았던 최고 가중치(best.pt) 모델로 최종 검증(val) 세트를 평가합니다.
    # 이 과정에서 내부적으로 IoU 임계값(기본 0.7) 및 Confidence 임계값(기본 0.25)을 기준으로 평가가 이루어집니다.
    metrics = model.val()

    # [지표 1, 2] mAP (mean Average Precision) 및 AP (Average Precision) 추출
    # box.map50: IoU 기준이 0.5일 때 모든 클래스의 평균 성능 (가장 널리 쓰이는 mAP 표준 지표)
    # box.map: IoU 기준을 0.5부터 0.95까지 0.05 단위로 올리며 평균을 낸 정밀한 mAP 점수
    mAP50 = metrics.box.map50
    mAP50_95 = metrics.box.map
    
    # 각 클래스별 AP 점수 목록을 가져옵니다. (yaml에 적힌 클래스 순서대로 배열 형태로 반환됩니다.)
    class_ap50_list = metrics.box.ap50

    # 결과를 터미널 창에 깔끔하게 리포트 형식으로 출력합니다.
    print(f"📌 [mAP] 전체 클래스 평균 성능 (mAP50)    : {mAP50:.4f} (0~1 사이, 1에 가까울수록 완벽)")
    print(f"📌 [mAP] 정밀 측정 성능 (mAP50-95)       : {mAP50_95:.4f}")
    print(f"📌 [AP]  각 클래스별 세부 성능 (AP50 목록) : {class_ap50_list}")
    
    print("\n💡 [IoU & Confidence Score 시각화 가이드]")
    print(" -> 'runs/detect/train/val_batch0_pred.jpg' 파일을 확인하세요.")
    print(" -> 해당 이미지 내 바운딩 박스 위에 '클래스명 Confidence_Score(예: dog 0.88)'가 자동 표기됩니다.")
    print(" -> 내부 설정된 IoU 기준값(기본 0.7)을 충족하여 최종 생존한 객체들만 시각화에 반영되었습니다.")
    
    print("\n💡 [혼돈 행렬(Confusion Matrix) 이미지 확인 가이드]")
    print(" -> 'runs/detect/train/confusion_matrix.png' 파일에 격자 표 형태의 이미지로 자동 저장되었습니다.")
    print("="*50)

if __name__ == '__main__':
    main()