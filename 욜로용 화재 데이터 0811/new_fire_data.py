import os
from roboflow import Roboflow
from ultralytics import YOLO

def main():
    # 1. Roboflow 데이터셋 안전 다운로드
    print("[1/3] Roboflow 데이터셋 다운로드를 시작합니다...")
    
    # ⚠️ 여기에 본인의 API KEY를 꼭 입력하세요!
    rf = Roboflow(api_key="amnnDNFsdLEqAX6Y5jjU") 
    
    project = rf.workspace("andreis-workspace-ruw3q").project("fire-2-0")
    version = project.version(1)
    
    # 로컬 컴퓨터에 다운로드 실행
    dataset = version.download("yolov8")
    print("[성공] 데이터셋 다운로드가 완료되었습니다!")

    # 2. 데이터셋 설정 파일(.yaml) 절대 경로 파악
    yaml_path = os.path.abspath(os.path.join(dataset.location, "data.yaml"))
    print(f"[2/3] 데이터셋 학습 경로 설정 완료: {yaml_path}")

    # 3. YOLOv8 모델 초기화 및 학습 시작
    print("[3/3] YOLOv8 기본 모델을 로드하고 학습을 시작합니다...")
    model = YOLO('yolov8n.pt')

    # Windows 환경 최적화 파라미터 적용
     # model.train 내부 설정을 이렇게 수정하세요!
    model.train(
        data=yaml_path,
        epochs=10,
        imgsz=640,
        device='cpu',  # ← 0에서 'cpu'로 수정!
        workers=0,     
        name='cctv_fire_model'
    )
    print("--- [최종 완료] 모든 화재 감지 모델 학습이 끝났습니다! ---")

if __name__ == '__main__':
    main()