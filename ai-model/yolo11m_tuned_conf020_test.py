"""
YOLO11m / YOLO11n Confidence & IoU Threshold 실험 코드

이미 학습된 best.pt 모델을 불러와
Confidence Threshold와 NMS IoU Threshold를 변경하면서
TEST 데이터의 탐지 성능을 비교하기 위한 코드입니다.

모델 학습은 수행하지 않으며,
기존 프로젝트의 데이터 검증 및 평가 함수를 재사용합니다.

실험 대상
1. Confidence Threshold
2. NMS IoU Threshold

MATCH_IOU_THRESHOLD는 평가 기준이므로 0.5로 고정합니다.
"""


from pathlib import Path
import importlib.util

from ultralytics import YOLO


# ============================================================
# 1. 기본 경로 설정
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

# 기존 프로젝트의 평가 함수가 들어있는 파일
ORIGINAL_SCRIPT = BASE_DIR / "yolo11_m_version_test.py"


# ============================================================
# 2. 실험할 모델 설정
# ============================================================

# 이미 학습이 완료된 best.pt 경로
# YOLO11n 또는 YOLO11m 중 최종 선택된 모델로 변경하면 됨
BEST_MODEL = (
    BASE_DIR
    / "runs"
    / "fire_yolo11m_tuned_e50"
    / "weights"
    / "best.pt"
)


# ============================================================
# 3. Threshold 실험 설정
# ============================================================

# Confidence Threshold
# 낮을수록 낮은 신뢰도의 예측도 포함
CONF_THRESHOLD = 0.20

# NMS IoU Threshold
# 높을수록 겹치는 예측 박스를 더 많이 허용
IOU_THRESHOLD = 0.70

# 실제 박스와 예측 박스를 정탐으로 연결할 평가 기준
# 실험 중에는 변경하지 않음
MATCH_IOU_THRESHOLD = 0.50


# ============================================================
# 4. 결과 저장 이름
# ============================================================

RUN_NAME = (
    f"threshold_test_conf{CONF_THRESHOLD:.2f}"
    f"_iou{IOU_THRESHOLD:.2f}"
)


# ============================================================
# 5. 기존 프로젝트 코드 불러오기
# ============================================================

def load_original_module():

    if not ORIGINAL_SCRIPT.exists():
        raise FileNotFoundError(
            f"Original script not found: {ORIGINAL_SCRIPT}"
        )

    spec = importlib.util.spec_from_file_location(
        "fire_yolo_base",
        ORIGINAL_SCRIPT
    )

    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    return module


# ============================================================
# 6. TEST 평가
# ============================================================

def evaluate(model_path, base, device):

    print("=" * 70)
    print("YOLO Threshold 실험")
    print("=" * 70)

    print(f"Model              : {model_path}")
    print(f"Confidence         : {CONF_THRESHOLD}")
    print(f"NMS IoU            : {IOU_THRESHOLD}")
    print(f"Match IoU          : {MATCH_IOU_THRESHOLD}")
    print("=" * 70)


    # --------------------------------------------------------
    # 기존 평가 함수에서 사용할 Threshold를 변경
    # --------------------------------------------------------

    base.CONF_THRESHOLD = CONF_THRESHOLD
    base.IOU_THRESHOLD = IOU_THRESHOLD
    base.MATCH_IOU_THRESHOLD = MATCH_IOU_THRESHOLD


    # --------------------------------------------------------
    # TEST 평가
    # --------------------------------------------------------

    metrics, test_dir = base.evaluate_test(
        model_path,
        device
    )


    # --------------------------------------------------------
    # 결과 출력
    # --------------------------------------------------------

    base.print_detection_metrics(metrics)


    # --------------------------------------------------------
    # 결과 저장
    # --------------------------------------------------------

    base.save_detection_metrics(
        metrics,
        test_dir
    )

    base.save_yolo_confusion_matrix(
        metrics,
        test_dir
    )


    # --------------------------------------------------------
    # 결과 경로 출력
    # --------------------------------------------------------

    base.print_result_paths(
        model_path,
        test_dir
    )


# ============================================================
# 7. Main
# ============================================================

def main():

    base = load_original_module()


    # --------------------------------------------------------
    # 모델 존재 여부 확인
    # --------------------------------------------------------

    if not BEST_MODEL.exists():

        raise FileNotFoundError(
            f"best.pt not found: {BEST_MODEL}"
        )


    # --------------------------------------------------------
    # 기존 데이터 검증
    # --------------------------------------------------------

    base.check_yaml()

    paths = base.check_dataset()

    base.print_all_dataset_statistics(paths)


    # --------------------------------------------------------
    # GPU / CPU 확인
    # --------------------------------------------------------

    device = base.get_device()


    print()
    print("Device:", device)
    print()


    # --------------------------------------------------------
    # Threshold 실험 실행
    # --------------------------------------------------------

    evaluate(
        BEST_MODEL,
        base,
        device
    )


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    main()