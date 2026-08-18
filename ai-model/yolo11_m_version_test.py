from pathlib import Path
import csv

import torch
import albumentations as A
from ultralytics import YOLO
from ultralytics.models.yolo.detect.train import DetectionTrainer


# ============================================================
# 1. 기본 설정
# ============================================================

# ------------------------------------------------------------
# data.yaml 경로
#
# 현재 Python 파일 위치를 기준으로
#
# ../data/data.yaml
#
# 을 사용합니다.
#
# 예:
# project/
# ├── data/
# │   └── data.yaml
# │
# └── ai-model/
#     └── yolo11_test.py
#
# ------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

DATA_YAML = (
    BASE_DIR
    / ".."
    / "data"
    / "data.yaml"
).resolve()


# ------------------------------------------------------------
# 결과 저장 위치
# ------------------------------------------------------------

RUNS_DIR = (
    BASE_DIR
    / "runs"
    / "data"
).resolve()


# ------------------------------------------------------------
# 실행 이름
# ------------------------------------------------------------

TRAIN_RUN_NAME = "fire_yolo11m"

TEST_RUN_NAME = "fire_yolo11m_test"


# ============================================================
# 2. 클래스
# ============================================================

# 객체 클래스
#
# 0 = fire
# 1 = smoke
#
# 정상(background)은 클래스 번호를 부여하지 않습니다.
# 객체가 없는 빈 txt 라벨을 정상으로 사용합니다.

CLASS_NAMES = [
    "fire",
    "smoke",
]


# ============================================================
# 3. 학습 설정
# ============================================================

EPOCHS = 10

IMAGE_SIZE = 640

BATCH_SIZE = 16

WORKERS = 0

SEED = 42


# ============================================================
# 4. 최종 Test 예측 설정
# ============================================================

# Confidence threshold
CONF_THRESHOLD = 0.25

# NMS IoU threshold
IOU_THRESHOLD = 0.7

# 이미지 단위 평가에서 예측 박스와 실제 박스를 정탐으로 연결할 IoU
MATCH_IOU_THRESHOLD = 0.5


# ============================================================
# 5. 이미지 확장자
# ============================================================

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp",
    ".tif",
    ".tiff",
}


# ============================================================
# 6. 데이터 증강
# ============================================================
#
# 사용자 정의 Trainer가 아래 Albumentations 목록을
# Ultralytics 데이터 파이프라인에 연결합니다.
#
# ============================================================

CUSTOM_AUGMENTATIONS = [

    A.RandomBrightnessContrast(
        brightness_limit=0.15,
        contrast_limit=0.15,
        p=0.40
    ),

    A.HorizontalFlip(
        p=0.50
    ),

    A.GaussNoise(
        std_range=(0.01, 0.03),
        mean_range=(0.0, 0.0),
        p=0.20
    ),

    A.GaussianBlur(
        blur_limit=(3, 5),
        sigma_limit=(0.1, 1.0),
        p=0.20
    ),
]


class CustomAugmentationTrainer(DetectionTrainer):

    def build_dataset(
        self,
        img_path,
        mode="train",
        batch=None
    ):

        if mode == "train":

            # model.train()의 설정 검증이 끝난 뒤 데이터셋 생성 직전에
            # Ultralytics v8_transforms가 읽는 내부 설정을 추가합니다.
            self.args.augmentations = CUSTOM_AUGMENTATIONS

        return super().build_dataset(
            img_path,
            mode=mode,
            batch=batch
        )


# ============================================================
# 7. YAML 경로 확인
# ============================================================

def check_yaml():

    print()
    print("=" * 70)
    print("DATA.YAML 확인")
    print("=" * 70)

    print()
    print(f"Python 파일 위치 : {BASE_DIR}")
    print(f"data.yaml 위치   : {DATA_YAML}")

    if not DATA_YAML.exists():

        raise FileNotFoundError(
            "\n"
            "data.yaml 파일을 찾을 수 없습니다.\n"
            f"확인 경로: {DATA_YAML}\n"
        )

    print()
    print("[OK] data.yaml 확인 완료")


# ============================================================
# 8. data.yaml에서 Dataset Root 찾기
# ============================================================

def get_dataset_paths():

    try:

        import yaml

    except ImportError:

        raise ImportError(
            "\nPyYAML이 설치되어 있지 않습니다.\n"
            "다음 명령으로 설치하세요:\n"
            "pip install pyyaml"
        )


    with open(
        DATA_YAML,
        "r",
        encoding="utf-8"
    ) as file:

        yaml_data = yaml.safe_load(file)


    # ========================================================
    # path 처리
    # ========================================================

    yaml_root = yaml_data.get(
        "path",
        ""
    )


    if yaml_root:

        dataset_root = Path(
            yaml_root
        )


        # 상대 경로라면
        # data.yaml 기준으로 계산
        if not dataset_root.is_absolute():

            dataset_root = (
                DATA_YAML.parent
                / dataset_root
            ).resolve()

    else:

        dataset_root = (
            DATA_YAML.parent
        ).resolve()


    # ========================================================
    # train / val / test
    # ========================================================

    train_value = yaml_data.get(
        "train"
    )

    val_value = yaml_data.get(
        "val"
    )

    test_value = yaml_data.get(
        "test"
    )


    if train_value is None:

        raise ValueError(
            "data.yaml에 train 항목이 없습니다."
        )


    if val_value is None:

        raise ValueError(
            "data.yaml에 val 항목이 없습니다."
        )


    if test_value is None:

        raise ValueError(
            "data.yaml에 test 항목이 없습니다."
        )


    # --------------------------------------------------------
    # 이번 코드는 일반적인
    # images/train
    # images/val
    # images/test
    #
    # 형태를 기준으로 합니다.
    # --------------------------------------------------------

    train_images = (
        dataset_root
        / train_value
    ).resolve()


    val_images = (
        dataset_root
        / val_value
    ).resolve()


    test_images = (
        dataset_root
        / test_value
    ).resolve()


    # --------------------------------------------------------
    # labels 경로 자동 계산
    # --------------------------------------------------------

    train_labels = image_to_label_dir(
        train_images
    )

    val_labels = image_to_label_dir(
        val_images
    )

    test_labels = image_to_label_dir(
        test_images
    )


    return {
        "root": dataset_root,

        "train_images": train_images,
        "train_labels": train_labels,

        "val_images": val_images,
        "val_labels": val_labels,

        "test_images": test_images,
        "test_labels": test_labels,
    }


# ============================================================
# 9. images 경로 → labels 경로 변환
# ============================================================

def image_to_label_dir(
    image_dir
):

    parts = list(
        image_dir.parts
    )


    # 마지막 images 항목 찾기
    image_index = None


    for index in range(
        len(parts) - 1,
        -1,
        -1
    ):

        if parts[index].lower() == "images":

            image_index = index

            break


    if image_index is None:

        raise ValueError(
            "\n"
            "이미지 경로에서 'images' 폴더를 "
            "찾을 수 없습니다.\n"
            f"{image_dir}"
        )


    parts[image_index] = "labels"


    return Path(
        *parts
    )


# ============================================================
# 10. 데이터 폴더 확인
# ============================================================

def check_dataset():

    paths = get_dataset_paths()


    print()
    print("=" * 70)
    print("DATASET 경로")
    print("=" * 70)


    print()
    print("[TRAIN]")

    print(
        f"Image : "
        f"{paths['train_images']}"
    )

    print(
        f"Label : "
        f"{paths['train_labels']}"
    )


    print()
    print("[VAL]")

    print(
        f"Image : "
        f"{paths['val_images']}"
    )

    print(
        f"Label : "
        f"{paths['val_labels']}"
    )


    print()
    print("[TEST]")

    print(
        f"Image : "
        f"{paths['test_images']}"
    )

    print(
        f"Label : "
        f"{paths['test_labels']}"
    )


    # --------------------------------------------------------
    # 폴더 존재 확인
    # --------------------------------------------------------

    folders = [

        paths["train_images"],
        paths["train_labels"],

        paths["val_images"],
        paths["val_labels"],

        paths["test_images"],
        paths["test_labels"],
    ]


    for folder in folders:

        if not folder.exists():

            raise FileNotFoundError(
                "\n"
                "데이터 폴더를 찾을 수 없습니다.\n"
                f"{folder}"
            )


    return paths


# ============================================================
# 11. 이미지 검색
# ============================================================

def find_images(
    directory
):

    images = [

        file

        for file in directory.rglob("*")

        if (
            file.is_file()
            and
            file.suffix.lower()
            in IMAGE_EXTENSIONS
        )
    ]


    return sorted(
        images
    )


# ============================================================
# 12. 이미지에 대응하는 Label 찾기
# ============================================================

def find_label_path(
    image_path,
    image_root,
    label_root
):

    relative_path = (
        image_path.relative_to(
            image_root
        )
    )


    label_path = (

        label_root

        / relative_path.parent

        / (
            image_path.stem
            + ".txt"
        )
    )


    return label_path


# ============================================================
# 13. Label 클래스 읽기
# ============================================================

def read_label_classes(
    label_path
):

    # --------------------------------------------------------
    # 라벨 파일이 없으면 데이터셋 오류로 처리합니다.
    # background 이미지는 존재하는 빈 txt 파일로 구분합니다.
    # --------------------------------------------------------

    if not label_path.exists():

        raise FileNotFoundError(
            f"이미지에 대응하는 라벨 파일이 없습니다: {label_path}\n"
            "background 이미지는 같은 이름의 빈 txt 라벨 파일이 필요합니다."
        )


    content = label_path.read_text(
        encoding="utf-8"
    ).strip()


    # --------------------------------------------------------
    # 빈 txt
    # background
    # --------------------------------------------------------

    if not content:

        return []


    classes = []


    for line in content.splitlines():

        parts = (
            line
            .strip()
            .split()
        )


        if len(parts) != 5:

            raise ValueError(
                f"잘못된 YOLO 라벨 형식: {label_path}\n"
                f"각 행은 class x_center y_center width height 형식이어야 합니다: {line}"
            )


        try:

            values = [float(value) for value in parts]

            if not values[0].is_integer():

                raise ValueError(
                    f"클래스 ID는 정수여야 합니다: {label_path}\n{line}"
                )

            class_id = int(values[0])


            if not 0 <= class_id < len(CLASS_NAMES):

                raise ValueError(
                    f"지원하지 않는 클래스 ID {class_id}: {label_path}"
                )

            x_center, y_center, width, height = values[1:]

            if not (
                0.0 <= x_center <= 1.0
                and 0.0 <= y_center <= 1.0
                and 0.0 < width <= 1.0
                and 0.0 < height <= 1.0
            ):

                raise ValueError(
                    f"라벨 좌표는 0~1 범위이고 폭/높이는 0보다 커야 합니다: "
                    f"{label_path}\n{line}"
                )

            classes.append(class_id)


        except ValueError as error:

            if str(error).startswith((
                "클래스 ID",
                "지원하지 않는",
                "라벨 좌표",
            )):

                raise

            raise ValueError(
                f"숫자로 변환할 수 없는 YOLO 라벨입니다: {label_path}\n{line}"
            ) from error


    return sorted(
        set(classes)
    )


def read_label_boxes(
    label_path
):

    # 먼저 공통 검증을 수행합니다. 라벨 없음/빈 파일은 background입니다.
    read_label_classes(label_path)

    if not label_path.exists():

        return []

    content = label_path.read_text(
        encoding="utf-8"
    ).strip()

    if not content:

        return []

    return [
        tuple(float(value) for value in line.split())
        for line in content.splitlines()
    ]


def xywh_to_xyxy(
    box
):

    x_center, y_center, width, height = box

    return (
        x_center - width / 2,
        y_center - height / 2,
        x_center + width / 2,
        y_center + height / 2,
    )


def box_iou(
    first_box,
    second_box
):

    first = xywh_to_xyxy(first_box)
    second = xywh_to_xyxy(second_box)

    intersection_width = max(
        0.0,
        min(first[2], second[2]) - max(first[0], second[0])
    )

    intersection_height = max(
        0.0,
        min(first[3], second[3]) - max(first[1], second[1])
    )

    intersection = intersection_width * intersection_height
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection

    return intersection / union if union > 0.0 else 0.0


def match_predictions(
    actual_boxes,
    predicted_boxes,
    same_class_only=False
):

    candidates = []

    for actual_index, actual in enumerate(actual_boxes):

        for predicted_index, predicted in enumerate(predicted_boxes):

            if (
                same_class_only
                and int(actual[0]) != int(predicted[0])
            ):

                continue

            iou = box_iou(actual[1:], predicted[1:])

            if iou >= MATCH_IOU_THRESHOLD:

                candidates.append((iou, actual_index, predicted_index))

    matched_actual = set()
    matched_predicted = set()
    matches = []

    for iou, actual_index, predicted_index in sorted(candidates, reverse=True):

        if actual_index in matched_actual or predicted_index in matched_predicted:

            continue

        matched_actual.add(actual_index)
        matched_predicted.add(predicted_index)
        matches.append((actual_index, predicted_index, iou))

    return matches


# ============================================================
# 14. Dataset 통계
# ============================================================

def print_dataset_statistics(
    name,
    image_dir,
    label_dir
):

    images = find_images(
        image_dir
    )


    fire_images = 0

    smoke_images = 0

    background_images = 0

    fire_boxes = 0

    smoke_boxes = 0


    for image_path in images:

        label_path = find_label_path(

            image_path,

            image_dir,

            label_dir
        )


        label_boxes = read_label_boxes(label_path)

        if not label_boxes:

            background_images += 1

            continue

        label_classes = [int(box[0]) for box in label_boxes]

        found_fire = 0 in label_classes

        found_smoke = 1 in label_classes

        fire_boxes += label_classes.count(0)

        smoke_boxes += label_classes.count(1)


        if found_fire:

            fire_images += 1


        if found_smoke:

            smoke_images += 1


    print()
    print("-" * 70)
    print(f"{name} DATA")
    print("-" * 70)

    print(
        f"전체 이미지             : "
        f"{len(images)}"
    )

    print(
        f"Fire 포함 이미지        : "
        f"{fire_images}"
    )

    print(
        f"Smoke 포함 이미지       : "
        f"{smoke_images}"
    )

    print(
        f"Background 정상 이미지 : "
        f"{background_images}"
    )

    print(
        f"Fire Bounding Box       : "
        f"{fire_boxes}"
    )

    print(
        f"Smoke Bounding Box      : "
        f"{smoke_boxes}"
    )


# ============================================================
# 15. 전체 데이터 통계
# ============================================================

def print_all_dataset_statistics(
    paths
):

    print()
    print("=" * 70)
    print("DATASET 구성")
    print("=" * 70)


    print_dataset_statistics(

        "TRAIN",

        paths["train_images"],

        paths["train_labels"]
    )


    print_dataset_statistics(

        "VALIDATION",

        paths["val_images"],

        paths["val_labels"]
    )


    print_dataset_statistics(

        "TEST",

        paths["test_images"],

        paths["test_labels"]
    )


# ============================================================
# 16. GPU / CPU 확인
# ============================================================

def get_device():

    print()
    print("=" * 70)
    print("학습 장치")
    print("=" * 70)


    if torch.cuda.is_available():

        device = 0


        print(
            "CUDA : 사용 가능"
        )


        print(
            "GPU  : "
            f"{torch.cuda.get_device_name(0)}"
        )


        gpu_memory = (

            torch.cuda
            .get_device_properties(0)
            .total_memory

            / 1024 ** 3
        )


        print(
            f"VRAM : "
            f"{gpu_memory:.2f} GB"
        )


    else:

        device = "cpu"


        print(
            "CUDA : 사용 불가"
        )


        print(
            "CPU로 학습합니다."
        )


    return device


# ============================================================
# 17. 실험 설정 출력
# ============================================================

def print_experiment_settings():

    print()
    print("=" * 70)
    print("YOLO11m 실험 설정")
    print("=" * 70)


    print(
        f"data.yaml    : "
        f"{DATA_YAML}"
    )

    print(
        f"Epoch        : "
        f"{EPOCHS}"
    )

    print(
        f"Batch        : "
        f"{BATCH_SIZE}"
    )

    print(
        f"Image Size   : "
        f"{IMAGE_SIZE}"
    )

    print(
        "Optimizer    : auto"
    )

    print(
        f"Seed         : "
        f"{SEED}"
    )

    print(
        "Deterministic: True"
    )


    print()
    print("[데이터 사용]")

    print(
        "학습             : train"
    )

    print(
        "학습 중 검증     : val"
    )

    print(
        "최종 평가        : test"
    )


    print()
    print("[데이터 증강]")

    print(
        "음영/밝기/대비   : ±15%, p=0.40"
    )

    print(
        "좌우반전         : p=0.50"
    )

    print(
        "Gaussian Noise   : p=0.20"
    )

    print(
        "Gaussian Blur    : p=0.20"
    )

    print()
    print("[비활성화 증강]")

    print(
        "YOLO flipud      : OFF"
    )

    print(
        "Mosaic           : OFF"
    )

    print(
        "MixUp            : OFF"
    )

    print(
        "CutMix           : OFF"
    )

    print(
        "회전             : OFF"
    )

    print(
        "이동             : OFF"
    )

    print(
        "확대/축소        : OFF"
    )

# ============================================================
# 18. YOLO11m 학습
# ============================================================

def train_model(
    device
):

    print()
    print("=" * 70)
    print("YOLO11m 학습 시작")
    print("=" * 70)


    # --------------------------------------------------------
    # YOLO11m pretrained
    # --------------------------------------------------------

    model = YOLO(
        "yolo11m.pt"
    )


    # --------------------------------------------------------
    # 학습
    #
    # data.yaml의
    #
    # train → 학습
    # val   → 학습 중 검증
    #
    # --------------------------------------------------------

    results = model.train(

        trainer=CustomAugmentationTrainer,

        data=str(DATA_YAML),


        # ====================================================
        # 공통 실험 조건
        # ====================================================

        epochs=EPOCHS,

        imgsz=IMAGE_SIZE,

        batch=BATCH_SIZE,

        optimizer="auto",

        seed=SEED,

        deterministic=True,


        # ====================================================
        # 장치
        # ====================================================

        device=device,

        workers=WORKERS,


        # ====================================================
        # 증강
        # ====================================================

        # ----------------------------------------------------
        # 좌우반전은 CUSTOM_AUGMENTATIONS에서 처리
        # ----------------------------------------------------

        fliplr=0.0,

        flipud=0.0,


        # ----------------------------------------------------
        # 다른 YOLO 증강 OFF
        # ----------------------------------------------------

        degrees=0.0,

        translate=0.0,

        scale=0.0,

        shear=0.0,

        perspective=0.0,

        mosaic=0.0,

        mixup=0.0,

        cutmix=0.0,


        # 밝기/대비는 CUSTOM_AUGMENTATIONS에서 처리
        hsv_h=0.0,

        hsv_s=0.0,

        hsv_v=0.0,


        # ====================================================
        # 저장
        # ====================================================

        project=str(RUNS_DIR),

        name=TRAIN_RUN_NAME,

        exist_ok=False,

        val=True,

        plots=True,

        pretrained=True,

        save=True,

        verbose=True,
    )


    best_model_path = Path(model.trainer.best).resolve()

    if not best_model_path.exists():

        raise FileNotFoundError(
            f"학습 후 best.pt를 찾을 수 없습니다: {best_model_path}"
        )

    return best_model_path


# ============================================================
# 20. 최종 TEST 평가
# ============================================================

def evaluate_test(
    best_model_path,
    device
):


    print()
    print("=" * 70)
    print("BEST 모델 최종 TEST 평가")
    print("=" * 70)


    print()
    print(
        f"Model : "
        f"{best_model_path}"
    )


    print(
        "Split : test"
    )


    best_model = YOLO(
        str(best_model_path)
    )


    # --------------------------------------------------------
    # 중요
    #
    # 최종 평가는 반드시
    #
    # split="test"
    #
    # --------------------------------------------------------

    metrics = best_model.val(

        data=str(DATA_YAML),

        split="test",

        imgsz=IMAGE_SIZE,

        batch=BATCH_SIZE,

        device=device,

        workers=WORKERS,

        # PR/F1/mAP 곡선은 낮은 임계값의 예측까지 포함해 계산합니다.
        conf=0.001,

        iou=IOU_THRESHOLD,

        plots=True,

        project=str(RUNS_DIR),

        name=TEST_RUN_NAME,

        exist_ok=False,

        verbose=True,
    )


    return (
        metrics,
        Path(metrics.save_dir).resolve()
    )


# ============================================================
# 21. 객체 탐지 성능 출력
# ============================================================

def print_detection_metrics(
    metrics
):

    print()
    print("=" * 70)
    print("TEST 객체 탐지 성능")
    print("=" * 70)


    print()

    print(
        f"Precision       : "
        f"{metrics.box.mp:.6f}"
    )

    print(
        f"Recall          : "
        f"{metrics.box.mr:.6f}"
    )

    overall_f1 = (
        2 * metrics.box.mp * metrics.box.mr
        / (metrics.box.mp + metrics.box.mr)
        if metrics.box.mp + metrics.box.mr > 0
        else 0.0
    )

    print(
        f"F1 Score        : "
        f"{overall_f1:.6f}"
    )

    print(
        f"mAP@0.5         : "
        f"{metrics.box.map50:.6f}"
    )

    print(
        f"mAP@0.5:0.95    : "
        f"{metrics.box.map:.6f}"
    )


    print()
    print("-" * 70)
    print("클래스별 성능")
    print("-" * 70)


    for class_id, class_name in enumerate(
        CLASS_NAMES
    ):

        try:

            result = (
                metrics.box.class_result(
                    class_id
                )
            )


            print()
            print(
                f"[{class_id}] "
                f"{class_name}"
            )

            print(
                f"Precision       : "
                f"{float(result[0]):.6f}"
            )

            print(
                f"Recall          : "
                f"{float(result[1]):.6f}"
            )

            class_precision = float(result[0])
            class_recall = float(result[1])
            class_f1 = (
                2 * class_precision * class_recall
                / (class_precision + class_recall)
                if class_precision + class_recall > 0
                else 0.0
            )

            print(
                f"F1 Score        : "
                f"{class_f1:.6f}"
            )

            print(
                f"mAP@0.5         : "
                f"{float(result[2]):.6f}"
            )

            print(
                f"mAP@0.5:0.95    : "
                f"{float(result[3]):.6f}"
            )


        except Exception as error:

            print(
                f"[WARNING] "
                f"{class_name} 성능 출력 실패"
            )

            print(error)


# ============================================================
# 22. Detection Metric CSV
# ============================================================

def save_detection_metrics(
    metrics,
    output_dir
):


    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )


    output_file = (

        output_dir

        / "metrics_summary.csv"
    )


    with open(
        output_file,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.writer(
            file
        )


        writer.writerow([
            "class_id",
            "class_name",
            "precision",
            "recall",
            "f1_score",
            "mAP50",
            "mAP50-95"
        ])


        # 전체
        overall_f1 = (
            2 * metrics.box.mp * metrics.box.mr
            / (metrics.box.mp + metrics.box.mr)
            if metrics.box.mp + metrics.box.mr > 0
            else 0.0
        )

        writer.writerow([
            "all",
            "all",
            metrics.box.mp,
            metrics.box.mr,
            overall_f1,
            metrics.box.map50,
            metrics.box.map
        ])


        # 클래스별
        for class_id, class_name in enumerate(
            CLASS_NAMES
        ):

            try:

                result = (
                    metrics.box.class_result(
                        class_id
                    )
                )

                class_precision = float(result[0])
                class_recall = float(result[1])
                class_f1 = (
                    2 * class_precision * class_recall
                    / (class_precision + class_recall)
                    if class_precision + class_recall > 0
                    else 0.0
                )


                writer.writerow([
                    class_id,
                    class_name,
                    class_precision,
                    class_recall,
                    class_f1,
                    float(result[2]),
                    float(result[3])
                ])


            except Exception:

                pass


    print()
    print(
        "[완료] Detection Metric CSV"
    )

    print(
        output_file
    )


# ============================================================
# 23. YOLO Confusion Matrix CSV
# ============================================================

def save_yolo_confusion_matrix(
    metrics,
    output_dir
):


    output_file = (

        output_dir

        / "yolo_confusion_matrix.csv"
    )


    try:

        matrix = (
            metrics
            .confusion_matrix
            .matrix
        )


        names = (
            CLASS_NAMES
            + ["background"]
        )


        with open(
            output_file,
            "w",
            newline="",
            encoding="utf-8-sig"
        ) as file:

            writer = csv.writer(
                file
            )


            writer.writerow(
                ["Predicted / Actual"]
                + names
            )


            for index, row in enumerate(
                matrix
            ):

                if index < len(names):

                    row_name = names[index]

                else:

                    row_name = str(index)


                writer.writerow(

                    [row_name]

                    + [
                        float(value)

                        for value in row
                    ]
                )


        print()
        print(
            "[완료] YOLO Confusion Matrix CSV"
        )

        print(
            output_file
        )


    except Exception as error:

        print()
        print(
            "[WARNING] Confusion Matrix "
            "CSV 저장 실패"
        )

        print(error)


# ============================================================
# 24. TEST Background 포함 이미지 단위 평가
# ============================================================

def evaluate_background_test(
    best_model_path,
    device,
    paths,
    output_dir
):

    print()
    print("=" * 70)
    print("TEST BACKGROUND 포함 평가")
    print("=" * 70)


    test_image_dir = (
        paths["test_images"]
    )

    test_label_dir = (
        paths["test_labels"]
    )


    model = YOLO(
        str(best_model_path)
    )


    test_images = find_images(
        test_image_dir
    )


    # ========================================================
    # 카운터
    # ========================================================

    total_images = 0


    # 실제 데이터
    actual_background = 0

    actual_object = 0

    actual_fire = 0

    actual_smoke = 0


    # 정상 결과
    background_correct = 0

    background_false_positive = 0

    background_fire_fp = 0

    background_smoke_fp = 0


    # 객체 결과
    object_detected = 0

    object_missed = 0


    # 클래스 결과
    fire_correct = 0

    fire_missed = 0

    smoke_correct = 0

    smoke_missed = 0

    fire_false_positive_images = 0

    smoke_false_positive_images = 0


    # CSV
    detailed_rows = []


    print()
    print(
        f"TEST 이미지 : "
        f"{len(test_images)}"
    )

    print(
        f"Confidence  : "
        f"{CONF_THRESHOLD}"
    )


    # 테스트 이미지 전체를 한 번에 전달하고 배치 단위로 추론합니다.
    prediction_results = model.predict(

        source=[str(image_path) for image_path in test_images],

        conf=CONF_THRESHOLD,

        iou=IOU_THRESHOLD,

        imgsz=IMAGE_SIZE,

        batch=BATCH_SIZE,

        device=device,

        stream=True,

        verbose=False
    )


    # ========================================================
    # TEST 이미지별 평가
    # ========================================================

    for index, (image_path, prediction_result) in enumerate(
        zip(test_images, prediction_results),
        start=1
    ):

        total_images += 1


        # ----------------------------------------------------
        # 실제 라벨
        # ----------------------------------------------------

        label_path = find_label_path(

            image_path,

            test_image_dir,

            test_label_dir
        )


        actual_boxes = read_label_boxes(label_path)

        actual_classes = sorted(
            set(int(box[0]) for box in actual_boxes)
        )


        # ----------------------------------------------------
        # 예측
        # ----------------------------------------------------

        predicted_classes = []

        predicted_boxes = []


        boxes = (
            prediction_result.boxes
        )


        if (
            boxes is not None
            and
            len(boxes) > 0
        ):

            predicted_classes = [

                int(value)

                for value
                in boxes.cls.cpu().tolist()

            ]

            normalized_boxes = boxes.xywhn.cpu().tolist()

            predicted_boxes = [
                (int(class_id), *coordinates)
                for class_id, coordinates in zip(
                    boxes.cls.cpu().tolist(),
                    normalized_boxes
                )
            ]


        predicted_classes = sorted(
            set(predicted_classes)
        )

        spatial_matches = match_predictions(
            actual_boxes,
            predicted_boxes
        )

        class_matches = match_predictions(
            actual_boxes,
            predicted_boxes,
            same_class_only=True
        )

        matched_class_pairs = [
            (
                int(actual_boxes[actual_index][0]),
                int(predicted_boxes[predicted_index][0]),
            )
            for actual_index, predicted_index, _ in class_matches
        ]

        spatial_object_detected = len(spatial_matches) > 0

        correct_matches = [
            (actual_index, predicted_index, iou)
            for actual_index, predicted_index, iou in class_matches
        ]

        correct_actual_indices = {
            actual_index
            for actual_index, _, _ in correct_matches
        }

        correct_predicted_indices = {
            predicted_index
            for _, predicted_index, _ in correct_matches
        }

        image_has_false_positive = (
            len(correct_predicted_indices) < len(predicted_boxes)
        )

        image_has_miss = (
            len(correct_actual_indices) < len(actual_boxes)
        )

        if 0 not in actual_classes and 0 in predicted_classes:

            fire_false_positive_images += 1

        if 1 not in actual_classes and 1 in predicted_classes:

            smoke_false_positive_images += 1


        # ====================================================
        # Background
        # ====================================================

        actual_is_background = (
            len(actual_classes) == 0
        )


        predicted_is_background = (
            len(predicted_classes) == 0
        )


        # ====================================================
        # 실제 정상
        # ====================================================

        if actual_is_background:

            actual_background += 1


            if predicted_is_background:

                background_correct += 1

                result_text = (
                    "BACKGROUND -> BACKGROUND"
                )


            else:

                background_false_positive += 1


                if 0 in predicted_classes:

                    background_fire_fp += 1


                if 1 in predicted_classes:

                    background_smoke_fp += 1


                result_text = (
                    "BACKGROUND -> FALSE POSITIVE"
                )


        # ====================================================
        # 실제 Fire / Smoke
        # ====================================================

        else:

            actual_object += 1


            if 0 in actual_classes:

                actual_fire += 1


                if (0, 0) in matched_class_pairs:

                    fire_correct += 1

                else:

                    fire_missed += 1


            if 1 in actual_classes:

                actual_smoke += 1


                if (1, 1) in matched_class_pairs:

                    smoke_correct += 1

                else:

                    smoke_missed += 1


            if not spatial_object_detected:

                object_missed += 1

                result_text = (
                    "OBJECT -> NO MATCH (MISS)"
                )


            else:

                object_detected += 1

                result_text = (
                    "OBJECT -> OBJECT"
                )


        # ====================================================
        # 문자열
        # ====================================================

        if actual_is_background:

            actual_text = "background"

        else:

            actual_text = ",".join(

                CLASS_NAMES[x]

                for x in actual_classes
            )


        if predicted_is_background:

            predicted_text = "background"

        else:

            predicted_text = ",".join(

                CLASS_NAMES[x]

                for x in predicted_classes

                if (
                    0
                    <= x
                    < len(CLASS_NAMES)
                )
            )


        detailed_rows.append([

            image_path.name,

            actual_text,

            predicted_text,

            result_text,

            int(image_has_false_positive),

            int(image_has_miss),

            len(actual_boxes),

            len(predicted_boxes),

            len(correct_matches)

        ])


        if (
            index % 100 == 0
            or
            index == len(test_images)
        ):

            print(
                f"평가 진행 : "
                f"{index}"
                f"/"
                f"{len(test_images)}"
            )


    # ========================================================
    # 비율 계산
    # ========================================================

    background_accuracy = (

        background_correct
        / actual_background

        if actual_background > 0

        else 0.0
    )


    background_fp_rate = (

        background_false_positive
        / actual_background

        if actual_background > 0

        else 0.0
    )


    object_detection_rate = (

        object_detected
        / actual_object

        if actual_object > 0

        else 0.0
    )


    object_miss_rate = (

        object_missed
        / actual_object

        if actual_object > 0

        else 0.0
    )


    fire_recall = (

        fire_correct
        / actual_fire

        if actual_fire > 0

        else 0.0
    )


    smoke_recall = (

        smoke_correct
        / actual_smoke

        if actual_smoke > 0

        else 0.0
    )


    binary_accuracy = (

        (
            background_correct
            + object_detected
        )
        / total_images

        if total_images > 0

        else 0.0
    )

    binary_precision = (
        object_detected
        / (object_detected + background_false_positive)
        if object_detected + background_false_positive > 0
        else 0.0
    )

    binary_recall = object_detection_rate

    binary_f1 = (
        2 * binary_precision * binary_recall
        / (binary_precision + binary_recall)
        if binary_precision + binary_recall > 0
        else 0.0
    )

    fire_precision = (
        fire_correct
        / (fire_correct + fire_false_positive_images)
        if fire_correct + fire_false_positive_images > 0
        else 0.0
    )

    fire_f1 = (
        2 * fire_precision * fire_recall
        / (fire_precision + fire_recall)
        if fire_precision + fire_recall > 0
        else 0.0
    )

    smoke_precision = (
        smoke_correct
        / (smoke_correct + smoke_false_positive_images)
        if smoke_correct + smoke_false_positive_images > 0
        else 0.0
    )

    smoke_f1 = (
        2 * smoke_precision * smoke_recall
        / (smoke_precision + smoke_recall)
        if smoke_precision + smoke_recall > 0
        else 0.0
    )


    # ========================================================
    # 결과 출력
    # ========================================================

    print()
    print("=" * 70)
    print("TEST 최종 이미지 단위 결과")
    print("=" * 70)


    print()
    print("[실제 데이터]")

    print(
        f"전체 이미지                 : "
        f"{total_images}"
    )

    print(
        f"Background                  : "
        f"{actual_background}"
    )

    print(
        f"Fire 포함                   : "
        f"{actual_fire}"
    )

    print(
        f"Smoke 포함                  : "
        f"{actual_smoke}"
    )

    print(
        f"Fire/Smoke 객체 이미지      : "
        f"{actual_object}"
    )


    print()
    print("[Background]")

    print(
        f"정상 → 정상                 : "
        f"{background_correct}"
    )

    print(
        f"정상 → 객체 오탐            : "
        f"{background_false_positive}"
    )

    print(
        f"  Fire 오탐                 : "
        f"{background_fire_fp}"
    )

    print(
        f"  Smoke 오탐                : "
        f"{background_smoke_fp}"
    )

    print(
        f"정상 정확도                 : "
        f"{background_accuracy * 100:.2f}%"
    )

    print(
        f"정상 오탐률                 : "
        f"{background_fp_rate * 100:.2f}%"
    )


    print()
    print("[Fire / Smoke]")

    print(
        f"객체 → 객체 탐지            : "
        f"{object_detected}"
    )

    print(
        f"객체 → Background 미탐      : "
        f"{object_missed}"
    )

    print(
        f"객체 이미지 탐지율          : "
        f"{object_detection_rate * 100:.2f}%"
    )

    print(
        f"객체 이미지 미탐률          : "
        f"{object_miss_rate * 100:.2f}%"
    )


    print()
    print("[클래스별 이미지 탐지율]")

    print(
        f"Fire                        : "
        f"{fire_correct}/{actual_fire} "
        f"({fire_recall * 100:.2f}%)"
    )

    print(
        f"Smoke                       : "
        f"{smoke_correct}/{actual_smoke} "
        f"({smoke_recall * 100:.2f}%)"
    )


    print()
    print("[정상 VS 화재/연기]")

    print(
        f"전체 이미지 판정 정확도    : "
        f"{binary_accuracy * 100:.2f}%"
    )

    print(
        f"Precision                   : "
        f"{binary_precision * 100:.2f}%"
    )

    print(
        f"Recall                      : "
        f"{binary_recall * 100:.2f}%"
    )

    print(
        f"F1 Score                    : "
        f"{binary_f1 * 100:.2f}%"
    )


    # ========================================================
    # CSV 저장
    # ========================================================

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )


    # --------------------------------------------------------
    # 상세 결과
    # --------------------------------------------------------

    detailed_csv = (

        output_dir

        / "background_image_results.csv"
    )


    with open(
        detailed_csv,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.writer(
            file
        )


        writer.writerow([
            "image",
            "actual",
            "predicted",
            "result",
            "has_false_positive",
            "has_miss",
            "actual_box_count",
            "predicted_box_count",
            "correct_match_count"
        ])


        writer.writerows(
            detailed_rows
        )


    # --------------------------------------------------------
    # 요약
    # --------------------------------------------------------

    summary_csv = (

        output_dir

        / "background_summary.csv"
    )


    with open(
        summary_csv,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.writer(
            file
        )


        writer.writerow([
            "metric",
            "count",
            "rate"
        ])


        writer.writerow([
            "total_test_images",
            total_images,
            ""
        ])


        writer.writerow([
            "actual_background",
            actual_background,
            ""
        ])


        writer.writerow([
            "actual_fire",
            actual_fire,
            ""
        ])


        writer.writerow([
            "actual_smoke",
            actual_smoke,
            ""
        ])


        writer.writerow([
            "actual_object",
            actual_object,
            ""
        ])


        writer.writerow([
            "background_correct",
            background_correct,
            background_accuracy
        ])


        writer.writerow([
            "background_false_positive",
            background_false_positive,
            background_fp_rate
        ])


        writer.writerow([
            "background_fire_false_positive",
            background_fire_fp,
            ""
        ])


        writer.writerow([
            "background_smoke_false_positive",
            background_smoke_fp,
            ""
        ])


        writer.writerow([
            "object_detected",
            object_detected,
            object_detection_rate
        ])


        writer.writerow([
            "object_missed",
            object_missed,
            object_miss_rate
        ])


        writer.writerow([
            "fire_correct",
            fire_correct,
            fire_recall
        ])


        writer.writerow([
            "fire_missed",
            fire_missed,
            ""
        ])


        writer.writerow([
            "smoke_correct",
            smoke_correct,
            smoke_recall
        ])


        writer.writerow([
            "smoke_missed",
            smoke_missed,
            ""
        ])


        writer.writerow([
            "binary_image_accuracy",
            "",
            binary_accuracy
        ])

        writer.writerow(["binary_precision", "", binary_precision])
        writer.writerow(["binary_recall", "", binary_recall])
        writer.writerow(["binary_f1_score", "", binary_f1])


    # --------------------------------------------------------
    # 이미지 단위 Precision / Recall / F1 / 오탐률
    # --------------------------------------------------------

    image_metrics_csv = (
        output_dir
        / "image_level_metrics.csv"
    )

    fire_true_negative = (
        total_images - actual_fire - fire_false_positive_images
    )
    smoke_true_negative = (
        total_images - actual_smoke - smoke_false_positive_images
    )

    fire_accuracy = (
        (fire_correct + fire_true_negative) / total_images
        if total_images > 0 else 0.0
    )
    smoke_accuracy = (
        (smoke_correct + smoke_true_negative) / total_images
        if total_images > 0 else 0.0
    )
    fire_false_positive_rate = (
        fire_false_positive_images
        / (fire_false_positive_images + fire_true_negative)
        if fire_false_positive_images + fire_true_negative > 0 else 0.0
    )
    smoke_false_positive_rate = (
        smoke_false_positive_images
        / (smoke_false_positive_images + smoke_true_negative)
        if smoke_false_positive_images + smoke_true_negative > 0 else 0.0
    )

    with open(
        image_metrics_csv,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.writer(file)
        writer.writerow([
            "scope",
            "true_positive",
            "false_positive",
            "false_negative",
            "true_negative",
            "precision",
            "recall",
            "f1_score",
            "accuracy",
            "false_positive_rate"
        ])
        writer.writerow([
            "fire_or_smoke",
            object_detected,
            background_false_positive,
            object_missed,
            background_correct,
            binary_precision,
            binary_recall,
            binary_f1,
            binary_accuracy,
            background_fp_rate
        ])
        writer.writerow([
            "fire",
            fire_correct,
            fire_false_positive_images,
            fire_missed,
            fire_true_negative,
            fire_precision,
            fire_recall,
            fire_f1,
            fire_accuracy,
            fire_false_positive_rate
        ])
        writer.writerow([
            "smoke",
            smoke_correct,
            smoke_false_positive_images,
            smoke_missed,
            smoke_true_negative,
            smoke_precision,
            smoke_recall,
            smoke_f1,
            smoke_accuracy,
            smoke_false_positive_rate
        ])


    # --------------------------------------------------------
    # Background VS Object Confusion Matrix
    # --------------------------------------------------------

    confusion_csv = (

        output_dir

        / "background_confusion_matrix.csv"
    )


    with open(
        confusion_csv,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.writer(
            file
        )


        writer.writerow([
            "Actual / Predicted",
            "Background",
            "Fire_or_Smoke"
        ])


        writer.writerow([
            "Background",
            background_correct,
            background_false_positive
        ])


        writer.writerow([
            "Fire_or_Smoke",
            object_missed,
            object_detected
        ])


    print()
    print("=" * 70)
    print("TEST Background 결과 저장")
    print("=" * 70)

    print(
        detailed_csv
    )

    print(
        summary_csv
    )

    print(
        image_metrics_csv
    )

    print(
        confusion_csv
    )


# ============================================================
# 25. 결과 파일 출력
# ============================================================

def print_result_paths(
    best_model_path,
    test_dir
):

    train_dir = best_model_path.parent.parent


    print()
    print("=" * 70)
    print("YOLO11m 실험 완료")
    print("=" * 70)


    print()
    print("[BEST MODEL]")

    print(
        best_model_path
    )


    print()
    print("[TRAIN 결과]")

    print(
        train_dir
    )


    print()
    print("[TEST 결과]")

    print(
        test_dir
    )


    print()
    print("[주요 결과 파일]")


    files = [

        best_model_path,

        train_dir
        / "results.csv",

        train_dir
        / "results.png",

        test_dir
        / "confusion_matrix.png",

        test_dir
        / "confusion_matrix_normalized.png",

        test_dir
        / "PR_curve.png",

        test_dir
        / "F1_curve.png",

        test_dir
        / "P_curve.png",

        test_dir
        / "R_curve.png",

        test_dir
        / "metrics_summary.csv",

        test_dir
        / "yolo_confusion_matrix.csv",

        test_dir
        / "background_summary.csv",

        test_dir
        / "image_level_metrics.csv",

        test_dir
        / "background_image_results.csv",

        test_dir
        / "background_confusion_matrix.csv",
    ]


    for file in files:

        mark = (
            "O"
            if file.exists()
            else "X"
        )


        print(
            f"[{mark}] "
            f"{file}"
        )


# ============================================================
# 26. MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("YOLO11m 화재 / 연기 / Background 비교 실험")
    print("=" * 70)


    # --------------------------------------------------------
    # YAML 확인
    # --------------------------------------------------------

    check_yaml()


    # --------------------------------------------------------
    # Dataset 확인
    # --------------------------------------------------------

    paths = check_dataset()


    # --------------------------------------------------------
    # Dataset 통계
    # --------------------------------------------------------

    print_all_dataset_statistics(
        paths
    )


    # --------------------------------------------------------
    # 실험 설정
    # --------------------------------------------------------

    print_experiment_settings()


    # --------------------------------------------------------
    # GPU / CPU
    # --------------------------------------------------------

    device = get_device()


    # --------------------------------------------------------
    # YOLO11m 학습
    #
    # train → 학습
    # val   → 학습 중 검증
    # --------------------------------------------------------

    best_model_path = train_model(
        device
    )


    # --------------------------------------------------------
    # BEST 모델
    #
    # 최종 평가는 TEST만 사용
    # --------------------------------------------------------

    metrics, test_output_dir = (
        evaluate_test(
            best_model_path,
            device
        )
    )


    # --------------------------------------------------------
    # Detection 성능
    # --------------------------------------------------------

    print_detection_metrics(
        metrics
    )


    # --------------------------------------------------------
    # Detection Metric CSV
    # --------------------------------------------------------

    save_detection_metrics(
        metrics,
        test_output_dir
    )


    # --------------------------------------------------------
    # YOLO Confusion Matrix CSV
    # --------------------------------------------------------

    save_yolo_confusion_matrix(
        metrics,
        test_output_dir
    )


    # --------------------------------------------------------
    # Background 포함 TEST 평가
    # --------------------------------------------------------

    evaluate_background_test(

        best_model_path,

        device,

        paths,

        test_output_dir
    )


    # --------------------------------------------------------
    # 결과 위치
    # --------------------------------------------------------

    print_result_paths(
        best_model_path,
        test_output_dir
    )


# ============================================================
# 프로그램 시작
# ============================================================

if __name__ == "__main__":

    main()
