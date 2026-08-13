# prepare_data.py

import os
import json
import random
import shutil
from pathlib import Path

import cv2
import numpy as np


class YoloDataPreparer:

    def __init__(
        self,
        train_ratio=0.8,
        val_ratio=0.1,
        test_ratio=0.1,
        image_size=640,
        clean_output=True,
    ):

        # ============================================================
        # 1. 원천 이미지 ROOT
        # ============================================================

        self.src_img_fl = Path(
            r"D:\089.화재 발생 예측 영상_고도화_영상 기반 화재 감시 및 발생 위치 탐지 데이터\3.개방데이터\1.데이터\Training\01.원천데이터\화재현상\이미지\불꽃"
        )

        self.src_img_sm = Path(
            r"D:\089.화재 발생 예측 영상_고도화_영상 기반 화재 감시 및 발생 위치 탐지 데이터\3.개방데이터\1.데이터\Training\01.원천데이터\화재현상\이미지\연기"
        )

        self.src_img_no = Path(
            r"D:\089.화재 발생 예측 영상_고도화_영상 기반 화재 감시 및 발생 위치 탐지 데이터\3.개방데이터\1.데이터\Training\01.원천데이터\화재현상\이미지\정상"
        )

        # ============================================================
        # 2. JSON 라벨 ROOT
        # ============================================================

        self.src_lbl_fl = Path(
            r"D:\TL\화재 현상\이미지\불꽃"
        )

        self.src_lbl_sm = Path(
            r"D:\TL\화재 현상\이미지\연기"
        )

        self.src_lbl_no = Path(
            r"D:\TL\화재 현상\이미지\정상"
        )

        # ============================================================
        # 3. 결과 저장 위치
        # ============================================================

        self.dest_root = Path("./dataset")
        self.yaml_path = self.dest_root / "data.yaml"

        # ============================================================
        # 4. 설정
        # ============================================================

        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio

        self.image_size = image_size
        self.clean_output = clean_output

        ratio_sum = (
            self.train_ratio
            + self.val_ratio
            + self.test_ratio
        )

        if abs(ratio_sum - 1.0) > 1e-6:
            raise ValueError(
                "train_ratio + val_ratio + test_ratio의 합은 1이어야 합니다."
            )

        # 동일한 실행 시 동일한 분할 결과
        random.seed(42)
        np.random.seed(42)

    # ================================================================
    # 기존 dataset 삭제
    # ================================================================

    def _clean_dataset(self):

        if (
            self.clean_output
            and self.dest_root.exists()
        ):

            print()
            print("=" * 70)
            print("기존 dataset 폴더 삭제")
            print(self.dest_root.resolve())
            print("=" * 70)

            shutil.rmtree(
                self.dest_root
            )

    # ================================================================
    # 결과 폴더 생성
    # ================================================================

    def _make_directories(self):

        for phase in [
            "train",
            "val",
            "test",
        ]:

            (
                self.dest_root
                / "images"
                / phase
            ).mkdir(
                parents=True,
                exist_ok=True,
            )

            (
                self.dest_root
                / "labels"
                / phase
            ).mkdir(
                parents=True,
                exist_ok=True,
            )

    # ================================================================
    # data.yaml 생성
    #
    # normal은 객체 클래스가 아닙니다.
    # 정상 이미지는 빈 TXT로 학습합니다.
    # ================================================================

    def _create_yaml(self):

        yaml_content = (
            f"path: {os.path.abspath(str(self.dest_root))}\n"
            "train: images/train\n"
            "val: images/val\n"
            "test: images/test\n"
            "\n"
            "names:\n"
            "  0: fire\n"
            "  1: smoke\n"
        )

        with open(
            self.yaml_path,
            "w",
            encoding="utf-8",
        ) as file:

            file.write(
                yaml_content
            )

        print()
        print("data.yaml 생성 완료")

    # ================================================================
    # 이미지 검색
    #
    # 모든 하위폴더를 탐색
    #
    # 파일명의 마지막 문자가 1인 이미지들만 사용
    #
    # 예:
    #
    # abc000001.jpg O
    # abc000011.jpg O
    # abc000021.jpg O
    #
    # abc000002.jpg X
    # abc000010.jpg X
    # ================================================================

    def _find_images(
        self,
        root,
    ):

        extensions = {
            ".jpg",
            ".jpeg",
            ".png",
            ".bmp",
        }

        images = []

        folder_count = 0
        total_image_count = 0
        selected_count = 0

        print()
        print("=" * 70)
        print("이미지 검색")
        print(root)
        print("=" * 70)

        for current_folder, _, files in os.walk(
            root
        ):

            folder_count += 1

            current_folder = Path(
                current_folder
            )

            for filename in files:

                file_path = (
                    current_folder
                    / filename
                )

                if (
                    file_path.suffix.lower()
                    not in extensions
                ):
                    continue

                total_image_count += 1

                # 확장자 제외 파일명
                stem = file_path.stem

                # 마지막 문자 1
                if not stem.endswith("1"):
                    continue

                images.append(
                    file_path
                )

                selected_count += 1

        images = sorted(
            images
        )

        print()
        print(
            f"탐색 폴더 수       : "
            f"{folder_count:,}개"
        )

        print(
            f"전체 이미지        : "
            f"{total_image_count:,}장"
        )

        print(
            f"끝자리 1 선택      : "
            f"{selected_count:,}장"
        )

        if total_image_count > 0:

            print(
                f"선택 비율          : "
                f"{selected_count / total_image_count * 100:.2f}%"
            )

        if images:

            print()
            print("[이미지 예시]")

            for image_path in images[:5]:
                print(image_path)

        return images

    # ================================================================
    # 영상 그룹 찾기
    #
    # 핵심 수정 부분
    #
    # JPG 폴더 바로 위의 "경로"를 영상 그룹으로 사용합니다.
    #
    # 예:
    #
    # 불꽃
    # └─ A
    #    └─ 0087
    #       └─ JPG
    #          └─ frame.jpg
    #
    # 그룹 = A/0087
    #
    # 단순히 parts[0]만 사용하지 않기 때문에
    # 수많은 영상이 4개 그룹으로 합쳐지는 문제가 없습니다.
    # ================================================================

    def _get_group_name(
        self,
        img_path,
        img_root,
    ):

        current = (
            img_path.parent
        )

        while current != img_root:

            if current.name.lower() in [
                "jpg",
                "jpeg",
                "image",
                "images",
            ]:

                video_folder = (
                    current.parent
                )

                try:

                    relative_group = (
                        video_folder.relative_to(
                            img_root
                        )
                    )

                    return (
                        relative_group.as_posix()
                    )

                except ValueError:

                    return (
                        video_folder.name
                    )

            current = (
                current.parent
            )

        # JPG 폴더가 없는 특수 구조
        try:

            relative_parent = (
                img_path.parent.relative_to(
                    img_root
                )
            )

            return (
                relative_parent.as_posix()
            )

        except ValueError:

            return (
                img_path.parent.name
            )

    # ================================================================
    # 그룹 단위 Train / Val / Test
    #
    # 같은 영상의 프레임은
    # 절대로 서로 다른 세트에 들어가지 않음
    # ================================================================

    def _split_groups(
        self,
        img_list,
        img_root,
    ):

        groups = {}

        for img_path in img_list:

            group_name = (
                self._get_group_name(
                    img_path,
                    img_root,
                )
            )

            groups.setdefault(
                group_name,
                [],
            ).append(
                img_path
            )

        group_names = list(
            groups.keys()
        )

        print()
        print("[발견된 영상 그룹 예시]")

        for group_name in sorted(
            group_names
        )[:20]:

            print(
                f"  {group_name}"
            )

        random.shuffle(
            group_names
        )

        total_groups = len(
            group_names
        )

        # ------------------------------------------------------------
        # 그룹 기준 8 : 1 : 1
        # ------------------------------------------------------------

        train_count = int(
            total_groups
            * self.train_ratio
        )

        val_count = int(
            total_groups
            * self.val_ratio
        )

        train_end = (
            train_count
        )

        val_end = (
            train_count
            + val_count
        )

        train_groups = (
            group_names[
                :train_end
            ]
        )

        val_groups = (
            group_names[
                train_end:val_end
            ]
        )

        test_groups = (
            group_names[
                val_end:
            ]
        )

        # 그룹이 매우 적은 경우
        if total_groups >= 3:

            if (
                len(val_groups) == 0
                and len(train_groups) > 1
            ):

                val_groups.append(
                    train_groups.pop()
                )

            if (
                len(test_groups) == 0
                and len(train_groups) > 1
            ):

                test_groups.append(
                    train_groups.pop()
                )

        phase_map = {}

        for group in train_groups:
            phase_map[group] = "train"

        for group in val_groups:
            phase_map[group] = "val"

        for group in test_groups:
            phase_map[group] = "test"

        print()
        print("=" * 70)
        print("영상 그룹 분할")
        print("=" * 70)

        print(
            f"전체 그룹 : "
            f"{total_groups:,}"
        )

        print(
            f"Train     : "
            f"{len(train_groups):,}"
        )

        print(
            f"Val       : "
            f"{len(val_groups):,}"
        )

        print(
            f"Test      : "
            f"{len(test_groups):,}"
        )

        return phase_map

    # ================================================================
    # JSON 인덱스 생성
    #
    # 이미지 한 장마다 rglob() 하는 방식 제거
    #
    # JSON 전체를 처음 한 번만 읽습니다.
    # ================================================================

    def _build_json_index(
        self,
        lbl_root,
    ):

        print()
        print("=" * 70)
        print("JSON 인덱스 생성")
        print(lbl_root)
        print("=" * 70)

        json_index = {}

        total_json = 0

        for current_folder, _, files in os.walk(
            lbl_root
        ):

            current_folder = Path(
                current_folder
            )

            for filename in files:

                if not filename.lower().endswith(
                    ".json"
                ):
                    continue

                json_path = (
                    current_folder
                    / filename
                )

                stem = (
                    json_path.stem
                )

                if stem not in json_index:
                    json_index[stem] = []

                json_index[
                    stem
                ].append(
                    json_path
                )

                total_json += 1

        duplicate_count = sum(
            1
            for paths in json_index.values()
            if len(paths) > 1
        )

        print()
        print(
            f"전체 JSON           : "
            f"{total_json:,}개"
        )

        print(
            f"고유 파일명         : "
            f"{len(json_index):,}개"
        )

        print(
            f"중복 파일명 종류    : "
            f"{duplicate_count:,}개"
        )

        return json_index

    # ================================================================
    # 이미지에 대응하는 JSON 찾기
    #
    # 1순위:
    # 이미지와 동일한 상대경로 사용
    #
    # 예:
    #
    # IMG:
    # A/0087/JPG/frame.jpg
    #
    # LABEL:
    # A/0087/JSON/frame.json
    #
    # 2순위:
    # JSON 인덱스 사용
    # ================================================================

    def _find_json(
        self,
        img_path,
        img_root,
        lbl_root,
        json_index,
    ):

        # ------------------------------------------------------------
        # 1. 상대경로 기반 정확한 매칭
        # ------------------------------------------------------------

        try:

            relative = (
                img_path.relative_to(
                    img_root
                )
            )

            parts = list(
                relative.parts
            )

            converted_parts = []

            for part in parts[:-1]:

                if part.lower() in [
                    "jpg",
                    "jpeg",
                    "image",
                    "images",
                ]:

                    converted_parts.append(
                        "JSON"
                    )

                else:

                    converted_parts.append(
                        part
                    )

            candidate = (
                lbl_root
                .joinpath(
                    *converted_parts
                )
                / f"{img_path.stem}.json"
            )

            if candidate.exists():

                return candidate

        except ValueError:

            pass

        # ------------------------------------------------------------
        # 2. 파일명 인덱스
        # ------------------------------------------------------------

        matches = json_index.get(
            img_path.stem,
            [],
        )

        if len(matches) == 1:

            return matches[0]

        if len(matches) > 1:

            # 중복 파일명이 있으면
            # 이미지의 영상 그룹명이 포함된 경로 우선
            group_name = (
                self._get_group_name(
                    img_path,
                    img_root,
                )
            )

            group_parts = [
                part.lower()
                for part in Path(
                    group_name
                ).parts
            ]

            for json_path in matches:

                json_lower = [
                    part.lower()
                    for part in json_path.parts
                ]

                if all(
                    part in json_lower
                    for part in group_parts
                ):

                    return json_path

        return None

    # ================================================================
    # Windows 한글 경로 이미지 읽기
    # ================================================================

    def _read_image(
        self,
        image_path,
    ):

        try:

            image_bytes = np.fromfile(
                str(image_path),
                dtype=np.uint8,
            )

            image = cv2.imdecode(
                image_bytes,
                cv2.IMREAD_COLOR,
            )

            return image

        except Exception:

            return None

    # ================================================================
    # Windows 한글 경로 이미지 저장
    # ================================================================

    def _save_image(
        self,
        image_path,
        image,
    ):

        success, encoded = (
            cv2.imencode(
                ".jpg",
                image,
                [
                    cv2.IMWRITE_JPEG_QUALITY,
                    95,
                ],
            )
        )

        if not success:
            return False

        encoded.tofile(
            str(image_path)
        )

        return True

    # ================================================================
    # 원본 bbox
    #
    # [x, y, width, height]
    #
    # →
    #
    # [x1, y1, x2, y2]
    # ================================================================

    def _bbox_to_xyxy(
        self,
        bbox,
    ):

        x = float(
            bbox[0]
        )

        y = float(
            bbox[1]
        )

        width = float(
            bbox[2]
        )

        height = float(
            bbox[3]
        )

        return [
            x,
            y,
            x + width,
            y + height,
        ]

    # ================================================================
    # 640 x 640 Letterbox
    #
    # 비율 유지
    # 남는 영역은 (114,114,114)
    # ================================================================

    def _letterbox(
        self,
        image,
        boxes,
    ):

        original_height, original_width = (
            image.shape[:2]
        )

        target_size = (
            self.image_size
        )

        scale = min(
            target_size / original_width,
            target_size / original_height,
        )

        new_width = int(
            round(
                original_width
                * scale
            )
        )

        new_height = int(
            round(
                original_height
                * scale
            )
        )

        resized_image = cv2.resize(
            image,
            (
                new_width,
                new_height,
            ),
            interpolation=cv2.INTER_LINEAR,
        )

        pad_width = (
            target_size
            - new_width
        )

        pad_height = (
            target_size
            - new_height
        )

        left = (
            pad_width // 2
        )

        right = (
            pad_width - left
        )

        top = (
            pad_height // 2
        )

        bottom = (
            pad_height - top
        )

        # YOLO에서 일반적으로 사용하는
        # 회색 Letterbox
        letterboxed = cv2.copyMakeBorder(
            resized_image,
            top,
            bottom,
            left,
            right,
            cv2.BORDER_CONSTANT,
            value=(
                114,
                114,
                114,
            ),
        )

        converted_boxes = []

        for box in boxes:

            class_id = (
                box[0]
            )

            x1 = (
                box[1]
                * scale
                + left
            )

            y1 = (
                box[2]
                * scale
                + top
            )

            x2 = (
                box[3]
                * scale
                + left
            )

            y2 = (
                box[4]
                * scale
                + top
            )

            x1 = float(
                np.clip(
                    x1,
                    0,
                    target_size,
                )
            )

            y1 = float(
                np.clip(
                    y1,
                    0,
                    target_size,
                )
            )

            x2 = float(
                np.clip(
                    x2,
                    0,
                    target_size,
                )
            )

            y2 = float(
                np.clip(
                    y2,
                    0,
                    target_size,
                )
            )

            if (
                x2 <= x1
                or y2 <= y1
            ):
                continue

            converted_boxes.append(
                [
                    class_id,
                    x1,
                    y1,
                    x2,
                    y2,
                ]
            )

        return (
            letterboxed,
            converted_boxes,
        )

    # ================================================================
    # 픽셀 bbox → YOLO 정규화
    # ================================================================

    def _xyxy_to_yolo(
        self,
        box,
    ):

        class_id = (
            box[0]
        )

        x1 = box[1]
        y1 = box[2]
        x2 = box[3]
        y2 = box[4]

        width = (
            x2 - x1
        )

        height = (
            y2 - y1
        )

        x_center = (
            x1 + x2
        ) / 2

        y_center = (
            y1 + y2
        ) / 2

        size = float(
            self.image_size
        )

        return [
            class_id,
            x_center / size,
            y_center / size,
            width / size,
            height / size,
        ]

    # ================================================================
    # 출력 파일명
    #
    # 경로까지 포함해서 중복 방지
    # ================================================================

    def _make_unique_name(
        self,
        image_path,
        image_root,
        data_type,
    ):

        relative = (
            image_path.relative_to(
                image_root
            )
        )

        parents = "_".join(
            relative.parts[:-1]
        )

        parents = (
            parents
            .replace(" ", "_")
            .replace(".", "_")
            .replace("/", "_")
            .replace("\\", "_")
        )

        return (
            f"{data_type}_"
            f"{parents}_"
            f"{image_path.stem}.jpg"
        )

    # ================================================================
    # Dataset 이미지/라벨 1:1 검사
    # ================================================================

    def _check_dataset_pairs(self):

        print()
        print("=" * 70)
        print("이미지 / 라벨 1:1 검사")
        print("=" * 70)

        for phase in [
            "train",
            "val",
            "test",
        ]:

            image_dir = (
                self.dest_root
                / "images"
                / phase
            )

            label_dir = (
                self.dest_root
                / "labels"
                / phase
            )

            image_files = list(
                image_dir.glob(
                    "*.jpg"
                )
            )

            label_files = list(
                label_dir.glob(
                    "*.txt"
                )
            )

            image_stems = {
                file.stem
                for file in image_files
            }

            label_stems = {
                file.stem
                for file in label_files
            }

            missing_labels = (
                image_stems
                - label_stems
            )

            missing_images = (
                label_stems
                - image_stems
            )

            print()
            print(
                f"[{phase.upper()}]"
            )

            print(
                f"이미지 : "
                f"{len(image_files):,}"
            )

            print(
                f"라벨   : "
                f"{len(label_files):,}"
            )

            print(
                f"라벨 없는 이미지 : "
                f"{len(missing_labels):,}"
            )

            print(
                f"이미지 없는 라벨 : "
                f"{len(missing_images):,}"
            )

            if (
                not missing_labels
                and not missing_images
            ):

                print(
                    "결과 : 정상 (1:1)"
                )

            else:

                print(
                    "결과 : 불일치"
                )

                if missing_labels:

                    print(
                        "라벨 없는 이미지 예시:"
                    )

                    for name in list(
                        missing_labels
                    )[:5]:

                        print(
                            f"  {name}"
                        )

                if missing_images:

                    print(
                        "이미지 없는 라벨 예시:"
                    )

                    for name in list(
                        missing_images
                    )[:5]:

                        print(
                            f"  {name}"
                        )

    # ================================================================
    # 메인 전처리
    # ================================================================

    def run_cleaning(self):

        # ------------------------------------------------------------
        # 기존 dataset 제거
        # ------------------------------------------------------------

        self._clean_dataset()

        # ------------------------------------------------------------
        # 새로운 dataset 생성
        # ------------------------------------------------------------

        self._make_directories()

        tasks = [

            {
                "img": self.src_img_fl,
                "lbl": self.src_lbl_fl,
                "type": "fl",
                "name": "불꽃",
            },

            {
                "img": self.src_img_sm,
                "lbl": self.src_lbl_sm,
                "type": "sm",
                "name": "연기",
            },

            {
                "img": self.src_img_no,
                "lbl": self.src_lbl_no,
                "type": "none",
                "name": "정상",
            },

        ]

        counters = {
            "train": 0,
            "val": 0,
            "test": 0,
        }

        class_counters = {

            "fl": {
                "train": 0,
                "val": 0,
                "test": 0,
            },

            "sm": {
                "train": 0,
                "val": 0,
                "test": 0,
            },

            "none": {
                "train": 0,
                "val": 0,
                "test": 0,
            },
        }

        total_selected = 0
        total_json_found = 0
        total_outdoor = 0

        skipped_json = 0
        skipped_indoor = 0
        skipped_image = 0

        # ============================================================
        # 불꽃 / 연기 / 정상
        # ============================================================

        for task in tasks:

            img_root = (
                task["img"]
            )

            lbl_root = (
                task["lbl"]
            )

            data_type = (
                task["type"]
            )

            data_name = (
                task["name"]
            )

            print()
            print()
            print("=" * 70)
            print(
                f"{data_name} 처리 시작"
            )
            print("=" * 70)

            print(
                f"이미지 : {img_root}"
            )

            print(
                f"라벨   : {lbl_root}"
            )

            # --------------------------------------------------------
            # 폴더 존재 확인
            # --------------------------------------------------------

            if not img_root.exists():

                print(
                    "[오류] 이미지 경로 없음"
                )

                continue

            if not lbl_root.exists():

                print(
                    "[오류] 라벨 경로 없음"
                )

                continue

            # --------------------------------------------------------
            # 이미지 검색
            # --------------------------------------------------------

            all_images = (
                self._find_images(
                    img_root
                )
            )

            if not all_images:

                print(
                    "사용 이미지 없음"
                )

                continue

            total_selected += len(
                all_images
            )

            # --------------------------------------------------------
            # JSON 인덱스
            # --------------------------------------------------------

            json_index = (
                self._build_json_index(
                    lbl_root
                )
            )

            # --------------------------------------------------------
            # 그룹 분할
            # --------------------------------------------------------

            phase_map = (
                self._split_groups(
                    all_images,
                    img_root,
                )
            )

            grouped_images = {}

            for img_path in all_images:

                group_name = (
                    self._get_group_name(
                        img_path,
                        img_root,
                    )
                )

                grouped_images.setdefault(
                    group_name,
                    [],
                ).append(
                    img_path
                )

            # ========================================================
            # 영상 그룹 처리
            # ========================================================

            for (
                group_name,
                images,
            ) in grouped_images.items():

                phase = (
                    phase_map.get(
                        group_name
                    )
                )

                if phase is None:
                    continue

                selected_images = sorted(
                    images
                )

                group_total = len(
                    selected_images
                )

                print()
                print(
                    f"[{phase.upper()}] "
                    f"{group_name}"
                )

                print(
                    f"처리 대상 : "
                    f"{group_total:,}장"
                )

                # ====================================================
                # 이미지 처리
                # ====================================================

                for (
                    image_index,
                    img_path,
                ) in enumerate(
                    selected_images,
                    start=1,
                ):

                    # ------------------------------------------------
                    # 100장마다 진행률 표시
                    # ------------------------------------------------

                    if (
                        image_index == 1
                        or image_index % 100 == 0
                        or image_index == group_total
                    ):

                        progress = (
                            image_index
                            / group_total
                            * 100
                        )

                        print(
                            f"[{phase.upper()}] "
                            f"{image_index:,}/"
                            f"{group_total:,} "
                            f"({progress:.1f}%)"
                        )

                    # ------------------------------------------------
                    # JSON
                    # ------------------------------------------------

                    json_path = (
                        self._find_json(
                            img_path,
                            img_root,
                            lbl_root,
                            json_index,
                        )
                    )

                    if json_path is None:

                        skipped_json += 1
                        continue

                    # ------------------------------------------------
                    # JSON 읽기
                    # ------------------------------------------------

                    try:

                        with open(
                            json_path,
                            "r",
                            encoding="utf-8-sig",
                        ) as file:

                            data = json.load(
                                file
                            )

                    except Exception:

                        skipped_json += 1
                        continue

                    total_json_found += 1

                    # ------------------------------------------------
                    # 실외만 사용
                    # ------------------------------------------------

                    attributes = (
                        data.get(
                            "attributes",
                            {},
                        )
                    )

                    inout = str(
                        attributes.get(
                            "inout",
                            "",
                        )
                    ).strip().lower()

                    if inout != "out":

                        skipped_indoor += 1
                        continue

                    total_outdoor += 1

                    # ------------------------------------------------
                    # 이미지 읽기
                    # ------------------------------------------------

                    image = (
                        self._read_image(
                            img_path
                        )
                    )

                    if image is None:

                        skipped_image += 1
                        continue

                    # ------------------------------------------------
                    # bbox
                    # ------------------------------------------------

                    boxes = []

                    # 정상은 bbox 없음
                    if data_type != "none":

                        category_dict = {}

                        for category in data.get(
                            "categories",
                            [],
                        ):

                            category_index = (
                                category.get(
                                    "category_index"
                                )
                            )

                            category_name = str(
                                category.get(
                                    "category_name",
                                    ""
                                )
                            ).lower()

                            category_dict[
                                category_index
                            ] = category_name

                        for annotation in data.get(
                            "annotations",
                            [],
                        ):

                            category_id = (
                                annotation.get(
                                    "categories_id"
                                )
                            )

                            category_name = str(
                                category_dict.get(
                                    category_id,
                                    data_type,
                                )
                            ).lower()

                            if category_name in [
                                "fl",
                                "fire",
                            ]:

                                class_id = 0

                            elif category_name in [
                                "sm",
                                "smoke",
                            ]:

                                class_id = 1

                            else:

                                continue

                            bbox = (
                                annotation.get(
                                    "bbox"
                                )
                            )

                            if (
                                not bbox
                                or len(bbox) < 4
                            ):

                                continue

                            xyxy = (
                                self._bbox_to_xyxy(
                                    bbox
                                )
                            )

                            boxes.append(
                                [
                                    class_id,
                                    xyxy[0],
                                    xyxy[1],
                                    xyxy[2],
                                    xyxy[3],
                                ]
                            )

                    # ------------------------------------------------
                    # 640x640 Letterbox
                    # ------------------------------------------------

                    image, boxes = (
                        self._letterbox(
                            image,
                            boxes,
                        )
                    )

                    # ------------------------------------------------
                    # YOLO 좌표
                    # ------------------------------------------------

                    yolo_boxes = []

                    for box in boxes:

                        yolo_boxes.append(
                            self._xyxy_to_yolo(
                                box
                            )
                        )

                    # ------------------------------------------------
                    # 출력 파일명
                    # ------------------------------------------------

                    output_filename = (
                        self._make_unique_name(
                            img_path,
                            img_root,
                            data_type,
                        )
                    )

                    output_stem = (
                        Path(
                            output_filename
                        ).stem
                    )

                    dest_img = (
                        self.dest_root
                        / "images"
                        / phase
                        / output_filename
                    )

                    dest_lbl = (
                        self.dest_root
                        / "labels"
                        / phase
                        / f"{output_stem}.txt"
                    )

                    # ------------------------------------------------
                    # 이미지 저장
                    # ------------------------------------------------

                    if not self._save_image(
                        dest_img,
                        image,
                    ):

                        skipped_image += 1
                        continue

                    # ------------------------------------------------
                    # YOLO TXT
                    # ------------------------------------------------

                    lines = []

                    for box in yolo_boxes:

                        class_id = int(
                            box[0]
                        )

                        lines.append(
                            f"{class_id} "
                            f"{box[1]:.6f} "
                            f"{box[2]:.6f} "
                            f"{box[3]:.6f} "
                            f"{box[4]:.6f}"
                        )

                    # 정상은 lines가 비어 있으므로
                    # 빈 TXT가 생성됨
                    with open(
                        dest_lbl,
                        "w",
                        encoding="utf-8",
                    ) as file:

                        file.write(
                            "\n".join(
                                lines
                            )
                        )

                    counters[
                        phase
                    ] += 1

                    class_counters[
                        data_type
                    ][
                        phase
                    ] += 1

        # ============================================================
        # YAML
        # ============================================================

        self._create_yaml()

        # ============================================================
        # 이미지 / 라벨 검사
        # ============================================================

        self._check_dataset_pairs()

        # ============================================================
        # 최종 통계
        # ============================================================

        total_saved = (
            counters["train"]
            + counters["val"]
            + counters["test"]
        )

        print()
        print()
        print("=" * 70)
        print("전처리 완료")
        print("=" * 70)

        print()
        print("[처리 과정]")

        print(
            f"끝자리 1 선택 : "
            f"{total_selected:,}장"
        )

        print(
            f"JSON 발견     : "
            f"{total_json_found:,}장"
        )

        print(
            f"실외(out)     : "
            f"{total_outdoor:,}장"
        )

        print(
            f"최종 저장     : "
            f"{total_saved:,}장"
        )

        print()
        print("[Train / Val / Test]")

        print(
            f"Train : "
            f"{counters['train']:,}장"
        )

        print(
            f"Val   : "
            f"{counters['val']:,}장"
        )

        print(
            f"Test  : "
            f"{counters['test']:,}장"
        )

        if total_saved > 0:

            print()
            print("[실제 이미지 비율]")

            print(
                f"Train : "
                f"{counters['train'] / total_saved * 100:.2f}%"
            )

            print(
                f"Val   : "
                f"{counters['val'] / total_saved * 100:.2f}%"
            )

            print(
                f"Test  : "
                f"{counters['test'] / total_saved * 100:.2f}%"
            )

        print()
        print("[불꽃]")

        print(
            f"Train : "
            f"{class_counters['fl']['train']:,}"
        )

        print(
            f"Val   : "
            f"{class_counters['fl']['val']:,}"
        )

        print(
            f"Test  : "
            f"{class_counters['fl']['test']:,}"
        )

        print()
        print("[연기]")

        print(
            f"Train : "
            f"{class_counters['sm']['train']:,}"
        )

        print(
            f"Val   : "
            f"{class_counters['sm']['val']:,}"
        )

        print(
            f"Test  : "
            f"{class_counters['sm']['test']:,}"
        )

        print()
        print("[정상]")

        print(
            f"Train : "
            f"{class_counters['none']['train']:,}"
        )

        print(
            f"Val   : "
            f"{class_counters['none']['val']:,}"
        )

        print(
            f"Test  : "
            f"{class_counters['none']['test']:,}"
        )

        print()
        print("[제외 데이터]")

        print(
            f"JSON 없음/오류 : "
            f"{skipped_json:,}"
        )

        print(
            f"실내 제외      : "
            f"{skipped_indoor:,}"
        )

        print(
            f"이미지 오류    : "
            f"{skipped_image:,}"
        )

        print()
        print("[전처리 설정]")

        print(
            "이미지 선택 : "
            "파일명 마지막 문자가 1"
        )

        print(
            "영상 분할   : "
            "JPG 폴더 상위 경로 기준"
        )

        print(
            "분할 비율   : "
            "Train / Val / Test = 8 : 1 : 1"
        )

        print(
            "Resize      : "
            "640 x 640 Letterbox"
        )

        print(
            "Padding     : "
            "(114, 114, 114)"
        )

        print(
            "증강        : 없음"
        )

        print(
            "정상 이미지 : 빈 TXT 라벨"
        )

        print()
        print(
            f"Dataset 위치 : "
            f"{self.dest_root.resolve()}"
        )


# ================================================================
# 실행
# ================================================================

if __name__ == "__main__":

    preparer = YoloDataPreparer(

        # Train 80%
        train_ratio=0.8,

        # Validation 10%
        val_ratio=0.1,

        # Test 10%
        test_ratio=0.1,

        # 최종 크기
        image_size=640,

        # 기존 dataset 삭제 후 새로 생성
        clean_output=True,
    )

    preparer.run_cleaning()

