from pathlib import Path
import random
import shutil
import csv

import torch
import albumentations as A

from ultralytics import YOLO


# ============================================================
# 1. 기본 경로
# ============================================================

DATASET_ROOT = Path(r"../data/")

# 원본 데이터
IMAGE_TEST_DIR = DATASET_ROOT / "images" / "test"
LABEL_TEST_DIR = DATASET_ROOT / "labels" / "test"

# train / val 자동 분할 폴더
SPLIT_ROOT = DATASET_ROOT / "yolo_split"

TRAIN_IMAGE_DIR = SPLIT_ROOT / "images" / "train"
VAL_IMAGE_DIR = SPLIT_ROOT / "images" / "val"

TRAIN_LABEL_DIR = SPLIT_ROOT / "labels" / "train"
VAL_LABEL_DIR = SPLIT_ROOT / "labels" / "val"

# data.yaml
YAML_PATH = SPLIT_ROOT / "data.yaml"

# 결과 저장 폴더
RUNS_DIR = Path(r"../data/fire_yolo11n_version1")

TRAIN_RUN_NAME = "fire_yolo11n"
VAL_RUN_NAME = "fire_yolo11n_validation"


# ============================================================
# 2. 클래스
# ============================================================

# 객체 클래스만 등록합니다.
#
# 0 = fire
# 1 = smoke
#
# background는 객체 클래스가 아닙니다.
# 빈 라벨 이미지를 이용해 정상 이미지로 처리합니다.

CLASS_NAMES = [
    "fire",
    "smoke",
]


# ============================================================
# 3. 학습 설정
# ============================================================

TRAIN_RATIO = 0.8

SEED = 42

EPOCHS = 5

IMAGE_SIZE = 640

BATCH_SIZE = 16

# Windows에서는 0이 안정적
WORKERS = 0


# ============================================================
# 4. 예측 설정
# ============================================================

# background 판정에도 사용되는 confidence
CONF_THRESHOLD = 0.25

# NMS IoU
IOU_THRESHOLD = 0.7


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
# 요청한 증강:
#
# 1. 음영 조정
# 2. 좌우 반전
# 3. 약한 Noise
# 4. 약한 Blur
#
# 좌우 반전은 YOLO의 fliplr 사용
#
# 나머지는 Albumentations 사용
# ============================================================

CUSTOM_AUGMENTATIONS = [

    # --------------------------------------------------------
    # 음영 / 밝기 / 대비 조정
    # --------------------------------------------------------
    # ±15% 정도
    # 40% 확률

    A.RandomBrightnessContrast(
        brightness_limit=0.15,
        contrast_limit=0.15,
        p=0.40
    ),


    # --------------------------------------------------------
    # 약한 Gaussian Noise
    # --------------------------------------------------------
    # 20% 확률

    A.GaussNoise(
        std_range=(0.01, 0.03),
        mean_range=(0.0, 0.0),
        p=0.20
    ),


    # --------------------------------------------------------
    # 약한 Gaussian Blur
    # --------------------------------------------------------
    # 3x3 ~ 5x5 정도
    # 20% 확률

    A.GaussianBlur(
        blur_limit=(3, 5),
        sigma_limit=(0.1, 1.0),
        p=0.20
    ),
]


# ============================================================
# 7. 필요한 폴더 생성
# ============================================================

def make_directories():

    directories = [
        TRAIN_IMAGE_DIR,
        VAL_IMAGE_DIR,
        TRAIN_LABEL_DIR,
        VAL_LABEL_DIR,
        RUNS_DIR,
    ]

    for directory in directories:

        directory.mkdir(
            parents=True,
            exist_ok=True
        )


# ============================================================
# 8. 기존 split 폴더 초기화
# ============================================================

def clear_split_directory():

    if SPLIT_ROOT.exists():

        print()
        print("[INFO] 기존 yolo_split 폴더 삭제")

        shutil.rmtree(SPLIT_ROOT)

    make_directories()


# ============================================================
# 9. 이미지 찾기
# ============================================================

def find_images():

    if not IMAGE_TEST_DIR.exists():

        raise FileNotFoundError(
            f"\n이미지 폴더가 없습니다.\n"
            f"{IMAGE_TEST_DIR}"
        )

    if not LABEL_TEST_DIR.exists():

        raise FileNotFoundError(
            f"\n라벨 폴더가 없습니다.\n"
            f"{LABEL_TEST_DIR}"
        )

    images = [

        file

        for file in IMAGE_TEST_DIR.rglob("*")

        if file.is_file()

        and file.suffix.lower() in IMAGE_EXTENSIONS
    ]

    if len(images) == 0:

        raise RuntimeError(
            f"\n이미지가 없습니다.\n"
            f"{IMAGE_TEST_DIR}"
        )

    return images


# ============================================================
# 10. 원본 데이터 통계
# ============================================================

def count_original_dataset():

    images = find_images()

    fire_images = 0
    smoke_images = 0
    background_images = 0

    total_boxes_fire = 0
    total_boxes_smoke = 0


    for image_path in images:

        relative_path = image_path.relative_to(
            IMAGE_TEST_DIR
        )

        label_path = (

            LABEL_TEST_DIR
            / relative_path.parent
            / f"{image_path.stem}.txt"
        )


        # ----------------------------------------------------
        # 라벨 자체가 없는 경우
        # 정상(background)
        # ----------------------------------------------------

        if not label_path.exists():

            background_images += 1

            continue


        text = label_path.read_text(
            encoding="utf-8"
        ).strip()


        # ----------------------------------------------------
        # 빈 txt인 경우
        # 정상(background)
        # ----------------------------------------------------

        if not text:

            background_images += 1

            continue


        found_fire = False
        found_smoke = False


        for line in text.splitlines():

            parts = line.strip().split()

            if len(parts) < 1:
                continue

            try:

                class_id = int(
                    float(parts[0])
                )

            except ValueError:

                continue


            if class_id == 0:

                found_fire = True

                total_boxes_fire += 1


            elif class_id == 1:

                found_smoke = True

                total_boxes_smoke += 1


        if found_fire:
            fire_images += 1

        if found_smoke:
            smoke_images += 1


        # 유효 클래스가 하나도 없다면 background
        if not found_fire and not found_smoke:

            background_images += 1


    print()
    print("=" * 70)
    print("원본 데이터 통계")
    print("=" * 70)

    print(
        f"전체 이미지                : "
        f"{len(images)}"
    )

    print(
        f"Fire 포함 이미지           : "
        f"{fire_images}"
    )

    print(
        f"Smoke 포함 이미지          : "
        f"{smoke_images}"
    )

    print(
        f"정상(background) 이미지    : "
        f"{background_images}"
    )

    print()

    print(
        f"Fire Bounding Box          : "
        f"{total_boxes_fire}"
    )

    print(
        f"Smoke Bounding Box         : "
        f"{total_boxes_smoke}"
    )


# ============================================================
# 11. 데이터 train / val 분할
# ============================================================

def split_dataset():

    images = find_images()

    random.seed(SEED)

    random.shuffle(images)


    split_index = int(
        len(images) * TRAIN_RATIO
    )


    if len(images) >= 2:

        split_index = max(
            1,
            split_index
        )

        split_index = min(
            split_index,
            len(images) - 1
        )


    train_images = images[:split_index]

    val_images = images[split_index:]


    print()
    print("=" * 70)
    print("데이터 분할")
    print("=" * 70)

    print(
        f"전체        : "
        f"{len(images)}"
    )

    print(
        f"Train 80%   : "
        f"{len(train_images)}"
    )

    print(
        f"Validation  : "
        f"{len(val_images)}"
    )


    copy_dataset(
        train_images,
        "train"
    )

    copy_dataset(
        val_images,
        "val"
    )


# ============================================================
# 12. 이미지와 라벨 복사
# ============================================================

def copy_dataset(
    image_list,
    split_name
):

    if split_name == "train":

        image_destination = TRAIN_IMAGE_DIR

        label_destination = TRAIN_LABEL_DIR

    else:

        image_destination = VAL_IMAGE_DIR

        label_destination = VAL_LABEL_DIR


    missing_labels = 0

    empty_labels = 0


    for index, image_path in enumerate(
        image_list
    ):

        # 같은 이름 충돌 방지
        new_stem = (

            f"{index:06d}_"
            f"{image_path.stem}"
        )


        new_image_path = (

            image_destination
            / (
                new_stem
                + image_path.suffix.lower()
            )
        )


        new_label_path = (

            label_destination
            / (
                new_stem
                + ".txt"
            )
        )


        # 이미지 복사
        shutil.copy2(
            image_path,
            new_image_path
        )


        # 원본 이미지 상대 경로
        relative_path = (

            image_path.relative_to(
                IMAGE_TEST_DIR
            )
        )


        original_label = (

            LABEL_TEST_DIR
            / relative_path.parent
            / (
                image_path.stem
                + ".txt"
            )
        )


        # ----------------------------------------------------
        # 라벨이 존재하는 경우
        # ----------------------------------------------------

        if original_label.exists():

            shutil.copy2(
                original_label,
                new_label_path
            )


            # 빈 라벨인지 확인
            if not original_label.read_text(
                encoding="utf-8"
            ).strip():

                empty_labels += 1


        # ----------------------------------------------------
        # 라벨 자체가 없으면
        # 빈 txt 파일 생성
        # ----------------------------------------------------

        else:

            new_label_path.touch()

            missing_labels += 1


    print()

    print(
        f"[{split_name}] "
        f"전체 이미지 : "
        f"{len(image_list)}"
    )

    print(
        f"[{split_name}] "
        f"기존 빈 라벨(background) : "
        f"{empty_labels}"
    )

    print(
        f"[{split_name}] "
        f"라벨 없음 → background 처리 : "
        f"{missing_labels}"
    )


# ============================================================
# 13. validation 데이터 통계
# ============================================================

def count_validation_dataset():

    background_count = 0

    fire_count = 0

    smoke_count = 0


    for label_path in VAL_LABEL_DIR.glob(
        "*.txt"
    ):

        content = label_path.read_text(
            encoding="utf-8"
        ).strip()


        if not content:

            background_count += 1

            continue


        classes = set()


        for line in content.splitlines():

            parts = line.split()

            if len(parts) < 1:

                continue

            try:

                classes.add(
                    int(float(parts[0]))
                )

            except ValueError:

                pass


        if 0 in classes:
            fire_count += 1

        if 1 in classes:
            smoke_count += 1


        if len(classes) == 0:
            background_count += 1


    print()
    print("=" * 70)
    print("Validation 이미지 구성")
    print("=" * 70)

    print(
        f"Fire 포함 이미지        : "
        f"{fire_count}"
    )

    print(
        f"Smoke 포함 이미지       : "
        f"{smoke_count}"
    )

    print(
        f"Background 정상 이미지 : "
        f"{background_count}"
    )


# ============================================================
# 14. data.yaml 생성
# ============================================================

def create_yaml():

    names_text = "\n".join(

        f"  {index}: {name}"

        for index, name
        in enumerate(CLASS_NAMES)
    )


    yaml_content = f"""path: {SPLIT_ROOT.as_posix()}

train: images/train
val: images/val

names:
{names_text}
"""


    YAML_PATH.write_text(
        yaml_content,
        encoding="utf-8"
    )


    print()
    print("=" * 70)
    print("data.yaml")
    print("=" * 70)

    print(yaml_content)


# ============================================================
# 15. GPU 확인
# ============================================================

def get_device():

    print()
    print("=" * 70)
    print("학습 장치")
    print("=" * 70)


    if torch.cuda.is_available():

        device = 0

        print("CUDA : 사용 가능")

        print(
            "GPU  :",
            torch.cuda.get_device_name(0)
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

        print("CUDA : 사용 불가")

        print(
            "CPU로 학습합니다."
        )


    return device


# ============================================================
# 16. 증강 설정 출력
# ============================================================

def print_augmentation_settings():

    print()
    print("=" * 70)
    print("데이터 증강")
    print("=" * 70)

    print(
        "음영/밝기/대비 : "
        "±15%, 확률 40%"
    )

    print(
        "좌우 반전      : "
        "확률 50%"
    )

    print(
        "약한 Noise     : "
        "확률 20%"
    )

    print(
        "약한 Blur      : "
        "확률 20%"
    )

    print()

    print(
        "회전       : OFF"
    )

    print(
        "상하 반전  : OFF"
    )

    print(
        "Mosaic     : OFF"
    )

    print(
        "MixUp      : OFF"
    )

    print(
        "확대/축소  : OFF"
    )


# ============================================================
# 17. YOLO11n 학습
# ============================================================

def train_model(device):

    print()
    print("=" * 70)
    print("YOLO11n 학습 시작")
    print("=" * 70)

    print(
        f"Epoch      : {EPOCHS}"
    )

    print(
        f"Batch      : {BATCH_SIZE}"
    )

    print(
        f"Image Size : {IMAGE_SIZE}"
    )


    model = YOLO(
        "yolo11n.pt"
    )


    results = model.train(

        data=str(YAML_PATH),

        epochs=EPOCHS,

        imgsz=IMAGE_SIZE,

        batch=BATCH_SIZE,

        device=device,

        workers=WORKERS,


        # ====================================================
        # 데이터 증강
        # ====================================================

        # 좌우반전
        fliplr=0.5,

        # 상하반전 OFF
        flipud=0.0,

        # 사용자 정의 Albumentations
        augmentations=CUSTOM_AUGMENTATIONS,


        # ----------------------------------------------------
        # 사용하지 않는 증강 OFF
        # ----------------------------------------------------

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


        # ====================================================
        # 결과 저장
        # ====================================================

        project=str(RUNS_DIR),

        name=TRAIN_RUN_NAME,

        exist_ok=True,

        val=True,

        plots=True,

        pretrained=True,

        seed=SEED,

        save=True,

        verbose=True,
    )


    return results


# ============================================================
# 18. BEST 모델 validation
# ============================================================

def validate_best_model(device):

    best_model_path = (

        RUNS_DIR
        / TRAIN_RUN_NAME
        / "weights"
        / "best.pt"
    )


    if not best_model_path.exists():

        raise FileNotFoundError(
            f"\nbest.pt가 없습니다.\n"
            f"{best_model_path}"
        )


    print()
    print("=" * 70)
    print("BEST 모델 검증")
    print("=" * 70)

    print(
        best_model_path
    )


    best_model = YOLO(
        str(best_model_path)
    )


    metrics = best_model.val(

        data=str(YAML_PATH),

        split="val",

        imgsz=IMAGE_SIZE,

        batch=BATCH_SIZE,

        device=device,

        workers=WORKERS,

        plots=True,

        project=str(RUNS_DIR),

        name=VAL_RUN_NAME,

        exist_ok=True,

        verbose=True,
    )


    return metrics, best_model_path


# ============================================================
# 19. YOLO 객체 성능 출력
# ============================================================

def print_metrics(metrics):

    print()
    print("=" * 70)
    print("YOLO 객체 탐지 성능")
    print("=" * 70)


    try:

        print(
            f"Precision       : "
            f"{metrics.box.mp:.6f}"
        )

        print(
            f"Recall          : "
            f"{metrics.box.mr:.6f}"
        )

        print(
            f"mAP@0.5         : "
            f"{metrics.box.map50:.6f}"
        )

        print(
            f"mAP@0.5:0.95    : "
            f"{metrics.box.map:.6f}"
        )


    except Exception as error:

        print(
            "[WARNING] 전체 성능 출력 실패"
        )

        print(error)


    print()
    print("-" * 70)
    print("클래스별 성능")
    print("-" * 70)


    try:

        for class_id, class_name in enumerate(
            CLASS_NAMES
        ):

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
            "[WARNING] 클래스별 성능 출력 실패"
        )

        print(error)


# ============================================================
# 20. 일반 Metric CSV 저장
# ============================================================

def save_metrics_csv(metrics):

    output_dir = (
        RUNS_DIR
        / VAL_RUN_NAME
    )

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

        writer = csv.writer(file)


        writer.writerow([
            "class_id",
            "class_name",
            "precision",
            "recall",
            "mAP50",
            "mAP50-95",
        ])


        # 전체
        writer.writerow([
            "all",
            "all",
            metrics.box.mp,
            metrics.box.mr,
            metrics.box.map50,
            metrics.box.map,
        ])


        # 클래스별
        for class_id, class_name in enumerate(
            CLASS_NAMES
        ):

            result = (
                metrics.box.class_result(
                    class_id
                )
            )


            writer.writerow([
                class_id,
                class_name,
                float(result[0]),
                float(result[1]),
                float(result[2]),
                float(result[3]),
            ])


    print()
    print(
        "[완료] 객체 성능 CSV:"
    )

    print(
        output_file
    )


# ============================================================
# 21. 실제 라벨 읽기 함수
# ============================================================

def get_actual_classes(
    image_path
):

    label_path = (

        VAL_LABEL_DIR

        / (
            image_path.stem
            + ".txt"
        )
    )


    # 라벨 파일이 없으면 정상
    if not label_path.exists():

        return []


    content = label_path.read_text(
        encoding="utf-8"
    ).strip()


    # 빈 라벨이면 정상
    if not content:

        return []


    classes = []


    for line in content.splitlines():

        parts = line.split()


        if len(parts) < 1:

            continue


        try:

            class_id = int(
                float(parts[0])
            )


            if class_id in [
                0,
                1
            ]:

                classes.append(
                    class_id
                )


        except ValueError:

            pass


    return sorted(
        set(classes)
    )


# ============================================================
# 22. Background 포함 이미지 단위 평가
# ============================================================

def evaluate_background_images(
    best_model_path,
    device
):

    print()
    print("=" * 70)
    print("BACKGROUND 포함 이미지 단위 평가")
    print("=" * 70)


    model = YOLO(
        str(best_model_path)
    )


    # ========================================================
    # 각종 카운터
    # ========================================================

    total_images = 0


    # 실제 정상
    actual_background = 0

    # 실제 fire 포함 이미지
    actual_fire = 0

    # 실제 smoke 포함 이미지
    actual_smoke = 0


    # 정상 판정
    background_correct = 0

    # 정상인데 객체 탐지
    background_false_positive = 0

    # 정상에서 fire 오탐
    background_fire_false_positive = 0

    # 정상에서 smoke 오탐
    background_smoke_false_positive = 0


    # 실제 객체 이미지
    actual_object_images = 0

    # 객체가 있는 이미지에서 객체 하나 이상 탐지
    object_detected_images = 0

    # 실제 객체가 있는데 아무것도 탐지 안 함
    object_missed_images = 0


    # fire 이미지 탐지
    fire_correct_images = 0

    # fire 이미지에서 fire 못 찾음
    fire_missed_images = 0


    # smoke 이미지 탐지
    smoke_correct_images = 0

    # smoke 이미지에서 smoke 못 찾음
    smoke_missed_images = 0


    # 전체 예측
    predicted_background = 0

    predicted_fire = 0

    predicted_smoke = 0


    # 결과 저장
    rows = []


    val_images = sorted([

        file

        for file in VAL_IMAGE_DIR.iterdir()

        if file.is_file()

        and file.suffix.lower()
        in IMAGE_EXTENSIONS

    ])


    print(
        f"평가 이미지 수 : "
        f"{len(val_images)}"
    )

    print(
        f"Confidence     : "
        f"{CONF_THRESHOLD}"
    )

    print()


    # ========================================================
    # 이미지별 예측
    # ========================================================

    for image_index, image_path in enumerate(
        val_images,
        start=1
    ):

        total_images += 1


        # ----------------------------------------------------
        # 실제 클래스
        # ----------------------------------------------------

        actual_classes = (
            get_actual_classes(
                image_path
            )
        )


        # ----------------------------------------------------
        # 모델 예측
        # ----------------------------------------------------

        results = model.predict(

            source=str(image_path),

            conf=CONF_THRESHOLD,

            iou=IOU_THRESHOLD,

            imgsz=IMAGE_SIZE,

            device=device,

            verbose=False
        )


        predicted_classes = []


        if len(results) > 0:

            boxes = results[0].boxes


            if (
                boxes is not None
                and len(boxes) > 0
            ):

                predicted_classes = [

                    int(class_id)

                    for class_id
                    in boxes.cls.cpu().tolist()

                ]


        predicted_classes = sorted(
            set(predicted_classes)
        )


        # ----------------------------------------------------
        # Background 여부
        # ----------------------------------------------------

        actual_is_background = (
            len(actual_classes) == 0
        )


        predicted_is_background = (
            len(predicted_classes) == 0
        )


        # ====================================================
        # 실제 정상 이미지
        # ====================================================

        if actual_is_background:

            actual_background += 1


            if predicted_is_background:

                background_correct += 1

                predicted_background += 1

                result_text = (
                    "BACKGROUND -> BACKGROUND"
                )


            else:

                background_false_positive += 1


                if 0 in predicted_classes:

                    background_fire_false_positive += 1

                    predicted_fire += 1


                if 1 in predicted_classes:

                    background_smoke_false_positive += 1

                    predicted_smoke += 1


                result_text = (
                    "BACKGROUND -> FALSE POSITIVE"
                )


        # ====================================================
        # 실제 fire / smoke 존재 이미지
        # ====================================================

        else:

            actual_object_images += 1


            if 0 in actual_classes:

                actual_fire += 1


            if 1 in actual_classes:

                actual_smoke += 1


            if predicted_is_background:

                object_missed_images += 1

                predicted_background += 1

                result_text = (
                    "OBJECT -> BACKGROUND (MISS)"
                )


            else:

                object_detected_images += 1

                result_text = (
                    "OBJECT -> OBJECT"
                )


                if 0 in predicted_classes:

                    predicted_fire += 1


                if 1 in predicted_classes:

                    predicted_smoke += 1


            # ------------------------------------------------
            # Fire 클래스별 이미지 탐지
            # ------------------------------------------------

            if 0 in actual_classes:

                if 0 in predicted_classes:

                    fire_correct_images += 1

                else:

                    fire_missed_images += 1


            # ------------------------------------------------
            # Smoke 클래스별 이미지 탐지
            # ------------------------------------------------

            if 1 in actual_classes:

                if 1 in predicted_classes:

                    smoke_correct_images += 1

                else:

                    smoke_missed_images += 1


        # ====================================================
        # CSV 기록
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

                if x < len(CLASS_NAMES)
            )


        rows.append([

            image_path.name,

            actual_text,

            predicted_text,

            result_text

        ])


        # 진행 상황
        if (
            image_index % 100 == 0
            or image_index
            == len(val_images)
        ):

            print(
                f"평가 진행 : "
                f"{image_index}"
                f"/"
                f"{len(val_images)}"
            )


    # ========================================================
    # 통계 계산
    # ========================================================

    if actual_background > 0:

        background_accuracy = (

            background_correct
            / actual_background
        )


        background_false_positive_rate = (

            background_false_positive
            / actual_background
        )

    else:

        background_accuracy = 0.0

        background_false_positive_rate = 0.0


    if actual_object_images > 0:

        object_detection_rate = (

            object_detected_images
            / actual_object_images
        )


        object_miss_rate = (

            object_missed_images
            / actual_object_images
        )

    else:

        object_detection_rate = 0.0

        object_miss_rate = 0.0


    if actual_fire > 0:

        fire_image_recall = (

            fire_correct_images
            / actual_fire
        )

    else:

        fire_image_recall = 0.0


    if actual_smoke > 0:

        smoke_image_recall = (

            smoke_correct_images
            / actual_smoke
        )

    else:

        smoke_image_recall = 0.0


    # --------------------------------------------------------
    # 정상/이상 이진 판정 Accuracy
    # --------------------------------------------------------

    if total_images > 0:

        binary_accuracy = (

            background_correct
            + object_detected_images

        ) / total_images

    else:

        binary_accuracy = 0.0


    # ========================================================
    # 화면 출력
    # ========================================================

    print()
    print("=" * 70)
    print("BACKGROUND 결과")
    print("=" * 70)

    print()

    print(
        f"전체 Validation 이미지           : "
        f"{total_images}"
    )

    print()

    print("-" * 70)
    print("실제 데이터 구성")
    print("-" * 70)

    print(
        f"실제 Background 정상 이미지      : "
        f"{actual_background}"
    )

    print(
        f"실제 Fire 포함 이미지            : "
        f"{actual_fire}"
    )

    print(
        f"실제 Smoke 포함 이미지           : "
        f"{actual_smoke}"
    )

    print(
        f"실제 Fire/Smoke 객체 이미지      : "
        f"{actual_object_images}"
    )


    print()
    print("-" * 70)
    print("정상(background) 판정 결과")
    print("-" * 70)

    print(
        f"정상 → 정상                      : "
        f"{background_correct}"
    )

    print(
        f"정상 → 객체 오탐                 : "
        f"{background_false_positive}"
    )

    print(
        f"  └ Fire 오탐                    : "
        f"{background_fire_false_positive}"
    )

    print(
        f"  └ Smoke 오탐                   : "
        f"{background_smoke_false_positive}"
    )

    print()

    print(
        f"정상 이미지 정확도               : "
        f"{background_accuracy * 100:.2f}%"
    )

    print(
        f"정상 이미지 오탐률               : "
        f"{background_false_positive_rate * 100:.2f}%"
    )


    print()
    print("-" * 70)
    print("화재 / 연기 이미지 판정 결과")
    print("-" * 70)

    print(
        f"객체 이미지 → 객체 탐지          : "
        f"{object_detected_images}"
    )

    print(
        f"객체 이미지 → 정상으로 미탐      : "
        f"{object_missed_images}"
    )

    print()

    print(
        f"객체 이미지 탐지율               : "
        f"{object_detection_rate * 100:.2f}%"
    )

    print(
        f"객체 이미지 미탐률               : "
        f"{object_miss_rate * 100:.2f}%"
    )


    print()
    print("-" * 70)
    print("클래스별 이미지 탐지")
    print("-" * 70)

    print(
        f"Fire 이미지 탐지 성공            : "
        f"{fire_correct_images}"
        f" / {actual_fire}"
    )

    print(
        f"Fire 이미지 탐지율               : "
        f"{fire_image_recall * 100:.2f}%"
    )

    print()

    print(
        f"Smoke 이미지 탐지 성공           : "
        f"{smoke_correct_images}"
        f" / {actual_smoke}"
    )

    print(
        f"Smoke 이미지 탐지율              : "
        f"{smoke_image_recall * 100:.2f}%"
    )


    print()
    print("-" * 70)
    print("정상 VS 화재/연기 이진 판정")
    print("-" * 70)

    print(
        f"전체 이미지 판정 정확도          : "
        f"{binary_accuracy * 100:.2f}%"
    )


    # ========================================================
    # 결과 저장 폴더
    # ========================================================

    output_dir = (

        RUNS_DIR
        / VAL_RUN_NAME
    )


    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )


    # ========================================================
    # 이미지별 결과 CSV
    # ========================================================

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

        writer = csv.writer(file)


        writer.writerow([

            "image",

            "actual",

            "predicted",

            "result"

        ])


        writer.writerows(
            rows
        )


    # ========================================================
    # Background 요약 CSV
    # ========================================================

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

        writer = csv.writer(file)


        writer.writerow([
            "metric",
            "count",
            "rate"
        ])


        writer.writerow([
            "total_validation_images",
            total_images,
            ""
        ])


        writer.writerow([
            "actual_background",
            actual_background,
            ""
        ])


        writer.writerow([
            "actual_fire_images",
            actual_fire,
            ""
        ])


        writer.writerow([
            "actual_smoke_images",
            actual_smoke,
            ""
        ])


        writer.writerow([
            "actual_object_images",
            actual_object_images,
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
            background_false_positive_rate
        ])


        writer.writerow([
            "background_fire_false_positive",
            background_fire_false_positive,
            ""
        ])


        writer.writerow([
            "background_smoke_false_positive",
            background_smoke_false_positive,
            ""
        ])


        writer.writerow([
            "object_detected_images",
            object_detected_images,
            object_detection_rate
        ])


        writer.writerow([
            "object_missed_images",
            object_missed_images,
            object_miss_rate
        ])


        writer.writerow([
            "fire_correct_images",
            fire_correct_images,
            fire_image_recall
        ])


        writer.writerow([
            "fire_missed_images",
            fire_missed_images,
            ""
        ])


        writer.writerow([
            "smoke_correct_images",
            smoke_correct_images,
            smoke_image_recall
        ])


        writer.writerow([
            "smoke_missed_images",
            smoke_missed_images,
            ""
        ])


        writer.writerow([
            "binary_image_accuracy",
            "",
            binary_accuracy
        ])


    # ========================================================
    # 정상 VS 객체 2x2 혼동행렬 CSV
    # ========================================================

    binary_cm_csv = (

        output_dir
        / "background_confusion_matrix.csv"
    )


    with open(
        binary_cm_csv,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.writer(file)


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

            object_missed_images,

            object_detected_images

        ])


    print()
    print("=" * 70)
    print("Background 결과 저장 완료")
    print("=" * 70)

    print(
        detailed_csv
    )

    print(
        summary_csv
    )

    print(
        binary_cm_csv
    )


# ============================================================
# 23. YOLO confusion matrix CSV 저장
# ============================================================

def save_yolo_confusion_matrix(
    metrics
):

    output_dir = (

        RUNS_DIR
        / VAL_RUN_NAME
    )


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


        # YOLO Detection confusion matrix는
        # 마지막 행/열이 background로 표현될 수 있음

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

            writer = csv.writer(file)


            writer.writerow(
                ["Actual / Predicted"]
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
            "[완료] YOLO Confusion Matrix CSV:"
        )

        print(
            output_file
        )


    except Exception as error:

        print()
        print(
            "[WARNING] YOLO Confusion Matrix "
            "CSV 저장 실패"
        )

        print(error)


# ============================================================
# 24. 최종 결과 파일 위치
# ============================================================

def print_result_paths(
    best_model_path
):

    train_dir = (

        RUNS_DIR
        / TRAIN_RUN_NAME
    )


    val_dir = (

        RUNS_DIR
        / VAL_RUN_NAME
    )


    print()
    print("=" * 70)
    print("모든 작업 완료")
    print("=" * 70)


    print()
    print("[최종 BEST 모델]")

    print(
        best_model_path
    )


    print()
    print("[학습 결과]")

    print(
        train_dir
    )


    print()
    print("[Validation / Background 결과]")

    print(
        val_dir
    )


    print()
    print("중요 파일:")


    important_files = [

        train_dir
        / "weights"
        / "best.pt",

        train_dir
        / "results.png",

        train_dir
        / "results.csv",

        val_dir
        / "confusion_matrix.png",

        val_dir
        / "confusion_matrix_normalized.png",

        val_dir
        / "PR_curve.png",

        val_dir
        / "F1_curve.png",

        val_dir
        / "metrics_summary.csv",

        val_dir
        / "background_summary.csv",

        val_dir
        / "background_image_results.csv",

        val_dir
        / "background_confusion_matrix.csv",

        val_dir
        / "yolo_confusion_matrix.csv",
    ]


    for file in important_files:

        if file.exists():

            mark = "O"

        else:

            mark = "X"


        print(
            f"[{mark}] "
            f"{file}"
        )


# ============================================================
# 25. MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("YOLO11n 화재 / 연기 / 정상(background) 모델 학습")
    print("=" * 70)


    print()
    print(
        f"이미지 경로 : "
        f"{IMAGE_TEST_DIR}"
    )

    print(
        f"라벨 경로   : "
        f"{LABEL_TEST_DIR}"
    )


    # --------------------------------------------------------
    # 원본 통계
    # --------------------------------------------------------

    count_original_dataset()


    # --------------------------------------------------------
    # 증강 확인
    # --------------------------------------------------------

    print_augmentation_settings()


    # --------------------------------------------------------
    # 기존 split 초기화
    # --------------------------------------------------------

    clear_split_directory()


    # --------------------------------------------------------
    # 80:20 분할
    # --------------------------------------------------------

    split_dataset()


    # --------------------------------------------------------
    # validation 데이터 구성 확인
    # --------------------------------------------------------

    count_validation_dataset()


    # --------------------------------------------------------
    # YAML
    # --------------------------------------------------------

    create_yaml()


    # --------------------------------------------------------
    # GPU
    # --------------------------------------------------------

    device = get_device()


    # --------------------------------------------------------
    # 학습
    # --------------------------------------------------------

    train_model(
        device
    )


    # --------------------------------------------------------
    # BEST 모델 Validation
    # --------------------------------------------------------

    metrics, best_model_path = (
        validate_best_model(
            device
        )
    )


    # --------------------------------------------------------
    # YOLO 객체 성능
    # --------------------------------------------------------

    print_metrics(
        metrics
    )


    # --------------------------------------------------------
    # Metric CSV
    # --------------------------------------------------------

    save_metrics_csv(
        metrics
    )


    # --------------------------------------------------------
    # YOLO Confusion Matrix CSV
    # --------------------------------------------------------

    save_yolo_confusion_matrix(
        metrics
    )


    # --------------------------------------------------------
    # Background까지 포함한 평가
    # --------------------------------------------------------

    evaluate_background_images(
        best_model_path,
        device
    )


    # --------------------------------------------------------
    # 결과 경로
    # --------------------------------------------------------

    print_result_paths(
        best_model_path
    )


# ============================================================
# 프로그램 실행
# ============================================================

if __name__ == "__main__":

    main()