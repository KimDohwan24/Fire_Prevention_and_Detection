
# prepare_data.py

import os
import json
import random
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
    ):


        # 원천 이미지 ROOT 경로
        self.src_img_fl = Path(
            r"C:\Users\admin\Desktop\fire_sample\Sample\01.원천데이터\화재현상\불꽃"
        )


        self.src_img_sm = Path(
            r"C:\Users\admin\Desktop\fire_sample\Sample\01.원천데이터\화재현상\연기"
        )

        self.src_img_no = Path(
            r"C:\Users\admin\Desktop\fire_sample\Sample\01.원천데이터\화재현상\정상"
        )

        # JSON 라벨 ROOT 경로
        self.src_lbl_fl = Path(
            r"C:\Users\admin\Desktop\fire_sample\Sample\02.라벨링데이터\화재현상\불꽃"
        )

        self.src_lbl_sm = Path(
            r"C:\Users\admin\Desktop\fire_sample\Sample\02.라벨링데이터\화재현상\연기"
        )

        self.src_lbl_no = Path(
            r"C:\Users\admin\Desktop\fire_sample\Sample\02.라벨링데이터\화재현상\정상"
        )



        # ============================================================
        # 3. 결과 저장 경로
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

        ratio_sum = (
            self.train_ratio
            + self.val_ratio
            + self.test_ratio
        )

        if abs(ratio_sum - 1.0) > 1e-6:
            raise ValueError(
                "train_ratio + val_ratio + test_ratio의 합은 1이어야 합니다."
            )

        # 결과 재현용
        random.seed(42)
        np.random.seed(42)

    # ================================================================
    # 결과 폴더 생성
    # ================================================================

    def _make_directories(self):

        for phase in ["train", "val", "test"]:

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

            image_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            label_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

    # ================================================================
    # data.yaml 생성
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

            file.write(yaml_content)

        print()
        print("data.yaml 생성 완료")

    # ================================================================
    # 이미지 재귀 검색
    #
    # ROOT 아래의 모든 하위폴더를 탐색합니다.
    #
    # 그리고 파일명의 마지막 문자가 1인 이미지만 선택합니다.
    #
    # 예:
    #
    # image000001.jpg  -> 선택
    # image000011.jpg  -> 선택
    # image000021.jpg  -> 선택
    #
    # image000002.jpg  -> 제외
    # image000010.jpg  -> 제외
    # ================================================================

    def _find_images(self, root):

        extensions = {
            ".jpg",
            ".jpeg",
            ".png",
            ".bmp",
        }

        images = []

        total_image_count = 0
        selected_count = 0

        print()
        print("=" * 70)
        print("이미지 검색 시작")
        print(root)
        print("=" * 70)

        # ------------------------------------------------------------
        # os.walk()를 사용해서
        # 모든 하위 폴더를 재귀적으로 탐색
        # ------------------------------------------------------------

        for current_folder, _, files in os.walk(root):

            current_folder = Path(
                current_folder
            )

            print(
                f"[폴더 탐색] {current_folder}"
            )

            for filename in files:

                file_path = (
                    current_folder
                    / filename
                )

                # ----------------------------------------------------
                # 이미지 확장자가 아니면 제외
                # ----------------------------------------------------

                if (
                    file_path.suffix.lower()
                    not in extensions
                ):
                    continue

                total_image_count += 1

                # ----------------------------------------------------
                # 확장자를 제외한 파일명
                #
                # 예:
                #
                # FL_000001.JPG
                #
                # stem:
                #
                # FL_000001
                # ----------------------------------------------------

                stem = file_path.stem

                # ----------------------------------------------------
                # 파일명 마지막 문자가 1인지 검사
                # ----------------------------------------------------

                if not stem.endswith("1"):
                    continue

                images.append(
                    file_path
                )

                selected_count += 1

        # 파일 정렬
        images = sorted(images)

        print()
        print(
            f"발견된 전체 이미지 : "
            f"{total_image_count}장"
        )

        print(
            f"마지막 숫자 1 선택 : "
            f"{selected_count}장"
        )

        # ------------------------------------------------------------
        # 이미지가 제대로 발견됐는지 예시 출력
        # ------------------------------------------------------------

        if len(images) > 0:

            print()
            print("[선택된 이미지 예시]")

            for image_path in images[:5]:

                print(
                    image_path
                )

        else:

            print()
            print(
                "[경고] 조건에 맞는 이미지를 찾지 못했습니다."
            )

            print(
                "위에 출력된 [폴더 탐색] 경로를 확인해주세요."
            )

        return images

    # ================================================================
    # 영상 그룹 이름 찾기
    #
    # 예:
    #
    # 불꽃\0087\JPG\000001.jpg
    #
    # 그룹 = 0087
    #
    # 같은 영상에서 추출한 이미지들이
    # Train과 Val에 동시에 들어가지 않게 합니다.
    # ================================================================

    def _get_group_name(
        self,
        img_path,
        img_root,
    ):

        relative = img_path.relative_to(
            img_root
        )

        parts = relative.parts

        # 예:
        #
        # parts =
        # (
        #   "0087",
        #   "JPG",
        #   "000001.jpg"
        # )
        #
        # 따라서 parts[0] = 0087

        if len(parts) >= 3:
            return parts[0]

        # 구조가 예상과 다른 경우
        return img_path.parent.name

    # ================================================================
    # Train / Val / Test
    #
    # 영상 그룹 단위로 8 : 1 : 1 분리
    # ================================================================

    def _split_groups(
        self,
        img_list,
        img_root,
    ):

        groups = {}

        # ------------------------------------------------------------
        # 같은 영상끼리 그룹 생성
        # ------------------------------------------------------------

        for img_path in img_list:

            group_name = (
                self._get_group_name(
                    img_path,
                    img_root,
                )
            )

            if group_name not in groups:
                groups[group_name] = []

            groups[group_name].append(
                img_path
            )

        group_names = list(
            groups.keys()
        )

        random.shuffle(
            group_names
        )

        total_groups = len(
            group_names
        )

        # ------------------------------------------------------------
        # 8 : 1 : 1
        # ------------------------------------------------------------

        train_count = int(
            total_groups
            * self.train_ratio
        )

        val_count = int(
            total_groups
            * self.val_ratio
        )

        train_end = train_count

        val_end = (
            train_count
            + val_count
        )

        train_groups = group_names[
            :train_end
        ]

        val_groups = group_names[
            train_end:val_end
        ]

        test_groups = group_names[
            val_end:
        ]

        # ------------------------------------------------------------
        # 데이터가 적을 때
        # Val/Test에 최소 1그룹씩 배정
        # ------------------------------------------------------------

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

        # ------------------------------------------------------------
        # 그룹별 phase 지정
        # ------------------------------------------------------------

        phase_map = {}

        for group in train_groups:
            phase_map[group] = "train"

        for group in val_groups:
            phase_map[group] = "val"

        for group in test_groups:
            phase_map[group] = "test"

        print()
        print("[영상 그룹 분할]")

        print(
            f"전체 그룹 : {total_groups}"
        )

        print(
            f"Train     : {len(train_groups)}"
        )

        print(
            f"Val       : {len(val_groups)}"
        )

        print(
            f"Test      : {len(test_groups)}"
        )

        return phase_map

    # ================================================================
    # 이미지와 동일한 JSON 찾기
    #
    # 예:
    #
    # 이미지
    #
    # 불꽃\0087\JPG\abc.jpg
    #
    # JSON
    #
    # 불꽃\0087\JSON\abc.json
    # ================================================================

    def _find_json(
        self,
        img_path,
        img_root,
        lbl_root,
    ):

        try:

            relative_path = (
                img_path.relative_to(
                    img_root
                )
            )

        except ValueError:

            return None

        parts = list(
            relative_path.parts
        )

        converted_parts = []

        # ------------------------------------------------------------
        # JPG 폴더를 JSON으로 변경
        # ------------------------------------------------------------

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

        json_candidate = (
            lbl_root
            .joinpath(
                *converted_parts
            )
            / f"{img_path.stem}.json"
        )

        # 정확한 위치에서 발견
        if json_candidate.exists():
            return json_candidate

        # ------------------------------------------------------------
        # 구조가 예상과 다르면
        # 라벨 ROOT 전체에서 같은 파일명을 재귀 검색
        # ------------------------------------------------------------

        matches = list(
            lbl_root.rglob(
                f"{img_path.stem}.json"
            )
        )

        if len(matches) > 0:
            return matches[0]

        return None

    # ================================================================
    # 이미지 읽기
    #
    # Windows 한글 경로 대응
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

        except Exception as error:

            print(
                f"[이미지 읽기 오류] {image_path}"
            )

            print(error)

            return None

    # ================================================================
    # 이미지 저장
    #
    # Windows 한글 경로 대응
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
    # bbox 변환
    #
    # 원본:
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

        x1 = x
        y1 = y

        x2 = (
            x + width
        )

        y2 = (
            y + height
        )

        return [
            x1,
            y1,
            x2,
            y2,
        ]

    # ================================================================
    # 640 x 640 Letterbox
    #
    # 원본 비율을 유지합니다.
    #
    # 예:
    #
    # 1920 x 1080
    #
    # ↓
    #
    # 640 x 360
    #
    # ↓
    #
    # 위/아래 회색 padding
    #
    # ↓
    #
    # 640 x 640
    # ================================================================

    def _letterbox(
        self,
        image,
        boxes,
    ):

        original_height, original_width = (
            image.shape[:2]
        )

        target_size = self.image_size

        # ------------------------------------------------------------
        # 축소 비율
        # ------------------------------------------------------------

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

        # ------------------------------------------------------------
        # 비율 유지 Resize
        # ------------------------------------------------------------

        resized_image = cv2.resize(
            image,
            (
                new_width,
                new_height,
            ),
            interpolation=cv2.INTER_LINEAR,
        )

        # ------------------------------------------------------------
        # Padding 크기
        # ------------------------------------------------------------

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
            pad_width
            - left
        )

        top = (
            pad_height // 2
        )

        bottom = (
            pad_height
            - top
        )

        # ------------------------------------------------------------
        # 회색 padding
        # ------------------------------------------------------------

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

        # ------------------------------------------------------------
        # bbox도 Letterbox 위치에 맞게 변경
        # ------------------------------------------------------------

        converted_boxes = []

        for box in boxes:

            class_id = box[0]

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

            # 이미지 영역 안으로 제한
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

            # 잘못된 bbox 제외
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
    # xyxy 픽셀 좌표
    #
    # →
    #
    # YOLO 좌표
    #
    # class x_center y_center width height
    #
    # 0 ~ 1 정규화
    # ================================================================

    def _xyxy_to_yolo(
        self,
        box,
    ):

        class_id = box[0]

        x1 = box[1]
        y1 = box[2]
        x2 = box[3]
        y2 = box[4]

        box_width = (
            x2 - x1
        )

        box_height = (
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
            box_width / size,
            box_height / size,
        ]

    # ================================================================
    # 파일명 중복 방지
    #
    # 서로 다른 영상 폴더에 같은 이미지 이름이 있을 수 있으므로
    # 상위 폴더 이름까지 출력 파일명에 포함
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
        )

        if parents:

            return (
                f"{data_type}_"
                f"{parents}_"
                f"{image_path.stem}.jpg"
            )

        return (
            f"{data_type}_"
            f"{image_path.stem}.jpg"
        )

    # ================================================================
    # 메인 실행
    # ================================================================

    def run_cleaning(self):

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

        # ============================================================
        # 전체 카운터
        # ============================================================

        counters = {
            "train": 0,
            "val": 0,
            "test": 0,
        }

        # 클래스별 카운터
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

        skipped_indoor = 0
        skipped_json = 0
        skipped_image = 0
        skipped_empty_bbox = 0

        # ============================================================
        # 불꽃 / 연기 / 정상
        # ============================================================

        for task in tasks:

            img_root = task["img"]
            lbl_root = task["lbl"]
            data_type = task["type"]
            data_name = task["name"]

            print()
            print()
            print("=" * 70)
            print(
                f"{data_name} 데이터 처리 시작"
            )
            print("=" * 70)

            print(
                f"이미지 ROOT : {img_root}"
            )

            print(
                f"라벨 ROOT   : {lbl_root}"
            )

            # --------------------------------------------------------
            # 이미지 ROOT 존재 확인
            # --------------------------------------------------------

            if not img_root.exists():

                print()
                print(
                    "[오류] 이미지 ROOT 폴더가 존재하지 않습니다."
                )

                print(
                    img_root
                )

                continue

            # --------------------------------------------------------
            # 라벨 ROOT 존재 확인
            # --------------------------------------------------------

            if not lbl_root.exists():

                print()
                print(
                    "[오류] 라벨 ROOT 폴더가 존재하지 않습니다."
                )

                print(
                    lbl_root
                )

                continue

            # --------------------------------------------------------
            # 하위폴더까지 재귀적으로 이미지 검색
            # --------------------------------------------------------

            all_images = (
                self._find_images(
                    img_root
                )
            )

            if len(all_images) == 0:

                print()
                print(
                    f"{data_name}: 사용할 이미지가 없습니다."
                )

                continue

            # --------------------------------------------------------
            # 영상 그룹 단위
            # Train / Val / Test 분할
            # --------------------------------------------------------

            phase_map = (
                self._split_groups(
                    all_images,
                    img_root,
                )
            )

            # --------------------------------------------------------
            # 영상 그룹별 이미지 묶기
            # --------------------------------------------------------

            grouped_images = {}

            for img_path in all_images:

                group_name = (
                    self._get_group_name(
                        img_path,
                        img_root,
                    )
                )

                if group_name not in grouped_images:

                    grouped_images[
                        group_name
                    ] = []

                grouped_images[
                    group_name
                ].append(
                    img_path
                )

            # ========================================================
            # 그룹 처리
            # ========================================================

            for group_name, images in (
                grouped_images.items()
            ):

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

                print()
                print(
                    f"[{phase.upper()}] "
                    f"그룹 {group_name} "
                    f"- {len(selected_images)}장"
                )

                # ====================================================
                # 이미지 개별 처리
                # ====================================================

                for img_path in selected_images:

                    # ------------------------------------------------
                    # JSON 찾기
                    # ------------------------------------------------

                    json_path = (
                        self._find_json(
                            img_path,
                            img_root,
                            lbl_root,
                        )
                    )

                    if json_path is None:

                        skipped_json += 1

                        print(
                            f"[JSON 없음] "
                            f"{img_path}"
                        )

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

                    except Exception as error:

                        skipped_json += 1

                        print(
                            f"[JSON 읽기 오류] "
                            f"{json_path}"
                        )

                        print(error)

                        continue

                    # ------------------------------------------------
                    # 실외 데이터만 사용
                    # ------------------------------------------------

                    attributes = (
                        data.get(
                            "attributes",
                            {},
                        )
                    )

                    inout = (
                        attributes.get(
                            "inout"
                        )
                    )

                    if inout != "out":

                        skipped_indoor += 1

                        continue

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
                    # Bounding Box
                    # ------------------------------------------------

                    boxes = []

                    # 정상 이미지는 bbox를 만들지 않습니다.
                    if data_type != "none":

                        # --------------------------------------------
                        # category_index
                        # →
                        # category_name
                        # --------------------------------------------

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

                        # --------------------------------------------
                        # annotation 처리
                        # --------------------------------------------

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

                            # ----------------------------------------
                            # Fire
                            # ----------------------------------------

                            if category_name in [
                                "fl",
                                "fire",
                            ]:

                                class_id = 0

                            # ----------------------------------------
                            # Smoke
                            # ----------------------------------------

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

                        # --------------------------------------------
                        # 화재/연기 이미지인데 bbox가 하나도 없으면
                        # 경고용 카운터 증가
                        # --------------------------------------------

                        if len(boxes) == 0:

                            skipped_empty_bbox += 1

                    # ------------------------------------------------
                    # 640 x 640 Letterbox
                    # ------------------------------------------------

                    image, boxes = (
                        self._letterbox(
                            image,
                            boxes,
                        )
                    )

                    # ------------------------------------------------
                    # YOLO 정규화
                    # ------------------------------------------------

                    yolo_boxes = []

                    for box in boxes:

                        yolo_box = (
                            self._xyxy_to_yolo(
                                box
                            )
                        )

                        yolo_boxes.append(
                            yolo_box
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

                    # ------------------------------------------------
                    # 이미지 저장 경로
                    # ------------------------------------------------

                    dest_img = (
                        self.dest_root
                        / "images"
                        / phase
                        / output_filename
                    )

                    # ------------------------------------------------
                    # 라벨 저장 경로
                    # ------------------------------------------------

                    dest_lbl = (
                        self.dest_root
                        / "labels"
                        / phase
                        / f"{output_stem}.txt"
                    )

                    # ------------------------------------------------
                    # 이미지 저장
                    # ------------------------------------------------

                    success = (
                        self._save_image(
                            dest_img,
                            image,
                        )
                    )

                    if not success:

                        skipped_image += 1

                        print(
                            f"[이미지 저장 실패] "
                            f"{dest_img}"
                        )

                        continue

                    # ------------------------------------------------
                    # YOLO TXT 생성
                    # ------------------------------------------------

                    lines = []

                    for box in yolo_boxes:

                        class_id = int(
                            box[0]
                        )

                        x_center = box[1]
                        y_center = box[2]
                        bbox_width = box[3]
                        bbox_height = box[4]

                        lines.append(
                            f"{class_id} "
                            f"{x_center:.6f} "
                            f"{y_center:.6f} "
                            f"{bbox_width:.6f} "
                            f"{bbox_height:.6f}"
                        )

                    # ------------------------------------------------
                    # 정상 이미지는 boxes가 없기 때문에
                    # 자동으로 빈 TXT 파일 생성
                    # ------------------------------------------------

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

                    # ------------------------------------------------
                    # 카운터 증가
                    # ------------------------------------------------

                    counters[
                        phase
                    ] += 1

                    class_counters[
                        data_type
                    ][
                        phase
                    ] += 1

        # ============================================================
        # YAML 생성
        # ============================================================

        self._create_yaml()

        # ============================================================
        # 결과 출력
        # ============================================================

        total = (
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
        print("[전체 데이터]")

        print(
            f"전체  : {total}장"
        )

        print(
            f"Train : {counters['train']}장"
        )

        print(
            f"Val   : {counters['val']}장"
        )

        print(
            f"Test  : {counters['test']}장"
        )

        if total > 0:

            print()
            print("[실제 비율]")

            print(
                f"Train : "
                f"{counters['train'] / total * 100:.2f}%"
            )

            print(
                f"Val   : "
                f"{counters['val'] / total * 100:.2f}%"
            )

            print(
                f"Test  : "
                f"{counters['test'] / total * 100:.2f}%"
            )

        print()
        print("[불꽃]")

        print(
            f"Train : "
            f"{class_counters['fl']['train']}장"
        )

        print(
            f"Val   : "
            f"{class_counters['fl']['val']}장"
        )

        print(
            f"Test  : "
            f"{class_counters['fl']['test']}장"
        )

        print()
        print("[연기]")

        print(
            f"Train : "
            f"{class_counters['sm']['train']}장"
        )

        print(
            f"Val   : "
            f"{class_counters['sm']['val']}장"
        )

        print(
            f"Test  : "
            f"{class_counters['sm']['test']}장"
        )

        print()
        print("[정상]")

        print(
            f"Train : "
            f"{class_counters['none']['train']}장"
        )

        print(
            f"Val   : "
            f"{class_counters['none']['val']}장"
        )

        print(
            f"Test  : "
            f"{class_counters['none']['test']}장"
        )

        print()
        print("[제외 / 확인 데이터]")

        print(
            f"실내 데이터        : "
            f"{skipped_indoor}장"
        )

        print(
            f"JSON 없음/오류     : "
            f"{skipped_json}장"
        )

        print(
            f"이미지 읽기/저장 오류 : "
            f"{skipped_image}장"
        )

        print(
            f"화재/연기 bbox 없음 : "
            f"{skipped_empty_bbox}장"
        )

        print()
        print("[현재 설정]")

        print(
            "이미지 검색 : "
            "모든 하위 폴더 재귀 탐색"
        )

        print(
            "이미지 선택 : "
            "파일명 마지막 문자가 1인 이미지"
        )

        print(
            "분할 방식   : "
            "영상 폴더 단위 Train/Val/Test"
        )

        print(
            "분할 비율   : "
            "8 : 1 : 1"
        )

        print(
            "사용 데이터 : "
            "실외(out)"
        )

        print(
            "이미지 크기 : "
            f"{self.image_size} x {self.image_size}"
        )

        print(
            "Resize      : "
            "Letterbox"
        )

        print(
            "증강        : "
            "없음"
        )

        print(
            "정상 라벨   : "
            "빈 TXT"
        )

        print()
        print("[데이터셋 저장 위치]")

        print(
            self.dest_root.resolve()
        )

        print()
        print("=" * 70)


# ================================================================
# 프로그램 실행
# ================================================================

if __name__ == "__main__":

    preparer = YoloDataPreparer(

        # Train
        train_ratio=0.8,

        # Validation
        val_ratio=0.1,

        # Test
        test_ratio=0.1,

        # Letterbox 크기
        image_size=640,
    )

    preparer.run_cleaning()
