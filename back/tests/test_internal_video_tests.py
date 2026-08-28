"""POST /api/internal/video-tests — 영상 전체 판정 저장 API."""
import io
import json

from PIL import Image
import pytest

import config
import db
from services import video_test_service


def _headers():
    return {"X-Internal-Key": config.INTERNAL_API_KEY}


def _jpeg(color="red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 12), color=color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _detection(confidence):
    return {
        "cls": "flame",
        "conf": confidence,
        "bbox": [0.5, 0.5, 0.25, 0.4],
        "bbox_format": "xywhn",
    }


def fire_manifest():
    return {
        "cctv_no": 1,
        "result": "FIRE",
        "started_at": "2026-08-19T10:00:00",
        "finished_at": "2026-08-19T10:00:03",
        "video": {"name": "sample.mp4", "duration_sec": 90.0, "source_fps": 30.0},
        "model": {
            "filename": "yolo11n_best.pt",
            "sha256": "a" * 64,
            "confidence": 0.25,
            "iou": 0.7,
            "imgsz": 640,
            "device": "cpu",
            "inference_fps": 3.0,
            "max_det": 10,
        },
        "statistics": {
            "processed_frames": 270,
            "positive_frames": 10,
            "threshold_frames": 10,
            "window_sec": 60.0,
            "first_detected_offset_sec": 5.0,
            "confirmed_offset_sec": 20.0,
            "max_confidence": 0.95,
            "detected_classes": ["FLAME"],
        },
        "evidence": [
            {
                "file_field": "evidence_0",
                "frame_index": 150,
                "offset_sec": 5.0,
                "confidence": 0.8,
                "roles": ["FIRST"],
                "detections": [_detection(0.8)],
            },
            {
                "file_field": "evidence_1",
                "frame_index": 600,
                "offset_sec": 20.0,
                "confidence": 0.9,
                "roles": ["CONFIRMATION"],
                "detections": [_detection(0.9)],
            },
            {
                "file_field": "evidence_2",
                "frame_index": 900,
                "offset_sec": 30.0,
                "confidence": 0.95,
                "roles": ["PEAK"],
                "detections": [_detection(0.95)],
            },
        ],
    }


def no_fire_manifest():
    manifest = fire_manifest()
    manifest["result"] = "NO_FIRE"
    manifest["statistics"].update({
        "positive_frames": 0,
        "first_detected_offset_sec": None,
        "confirmed_offset_sec": None,
        "max_confidence": None,
        "detected_classes": [],
    })
    manifest["evidence"] = []
    return manifest


def post_manifest(client, manifest, *, images=None, headers=None):
    data = {"manifest": json.dumps(manifest)}
    for field, image in (images or {}).items():
        data[field] = (io.BytesIO(image), f"{field}.jpg", "image/jpeg")
    return client.post(
        "/api/internal/video-tests",
        data=data,
        content_type="multipart/form-data",
        headers=_headers() if headers is None else headers,
    )


@pytest.fixture(autouse=True)
def isolated_media_root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEDIA_ROOT", str(tmp_path))


def test_requires_internal_key(client):
    response = post_manifest(client, no_fire_manifest(), headers={})

    assert response.status_code == 401
    assert response.get_json()["code"] == "INTERNAL_UNAUTHORIZED"


def test_fire_result_and_three_raw_evidence_images_are_saved(client, tmp_path):
    images = {f"evidence_{index}": _jpeg(color)
              for index, color in enumerate(("red", "orange", "yellow"))}

    response = post_manifest(client, fire_manifest(), images=images)

    assert response.status_code == 201
    body = response.get_json()
    assert body["result"] == "FIRE"
    assert body["event_status"] == "CONFIRMED"
    assert body["event_detected_frames"] == 10
    assert len(body["media"]) == 3

    event = db.query_one("SELECT * FROM fire_event WHERE event_no = %s", (body["event_no"],))
    assert event["event_is_test"] is True
    assert event["event_source_type"] == "VIDEO_TEST"
    assert event["event_status"] == "CONFIRMED"
    assert event["event_processed_frames"] == 270
    assert float(event["event_confirmed_offset_sec"]) == pytest.approx(20.0)
    assert event["event_source_metadata"]["model"]["filename"] == "yolo11n_best.pt"
    assert event["event_cctv_snapshot"]["cctv_name"] == "정문 카메라"

    media = db.query(
        "SELECT * FROM event_media WHERE event_no = %s ORDER BY media_no",
        (body["event_no"],),
    )
    assert [row["media_is_first"] for row in media] == [True, False, False]
    assert [row["media_is_confirmation"] for row in media] == [False, True, False]
    assert [row["media_is_primary"] for row in media] == [False, False, True]
    assert media[0]["media_detections"][0]["bbox_format"] == "xywhn"
    for row in media:
        relative = row["media_url"].removeprefix("/media/")
        assert (tmp_path / relative).is_file()


def test_saved_evidence_images_have_detection_boxes_drawn(client, tmp_path):
    """증거 파일은 디스크 원본이 그대로 서빙되므로 저장 시점에 상자를 그린다.

    검출은 xywhn 비율 + bbox_format 마커 형식이다. 원본 프레임은 ai-model/samples
    의 영상에 그대로 남아 있어 저장본에 그려도 증거 원본성 문제는 없다.
    """
    original = _jpeg("black")
    images = {f"evidence_{index}": original for index in range(3)}

    response = post_manifest(client, fire_manifest(), images=images)

    assert response.status_code == 201
    for row in response.get_json()["media"]:
        relative = row["media_url"].removeprefix("/media/")
        saved = (tmp_path / relative).read_bytes()
        assert saved != original, f"{row['media_url']} 에 검출 상자가 그려지지 않았다"


def test_no_fire_without_detections_still_creates_dismissed_history(client):
    response = post_manifest(client, no_fire_manifest())

    assert response.status_code == 201
    body = response.get_json()
    assert body["result"] == "NO_FIRE"
    assert body["event_status"] == "DISMISSED"
    assert body["event_class"] is None
    assert body["media"] == []
    event = db.query_one("SELECT * FROM fire_event WHERE event_no = %s", (body["event_no"],))
    assert event["event_detected_frames"] == 0
    assert event["event_detected_at"] is None


def test_video_test_never_calls_confirmation_hook(client, monkeypatch):
    calls = []
    monkeypatch.setattr("services.hooks.on_event_confirmed", calls.append)

    post_manifest(
        client,
        fire_manifest(),
        images={f"evidence_{i}": _jpeg() for i in range(3)},
    )

    assert calls == []
    assert db.query_one("SELECT count(*) AS count FROM alert")["count"] == 0
    assert db.query_one("SELECT count(*) AS count FROM report_119")["count"] == 0


def test_unknown_cctv_rolls_back_without_files(client, tmp_path):
    manifest = no_fire_manifest()
    manifest["cctv_no"] = 999

    response = post_manifest(client, manifest)

    assert response.status_code == 404
    assert response.get_json()["code"] == "CCTV_NOT_FOUND"
    assert db.query_one("SELECT count(*) AS count FROM fire_event")["count"] == 0
    assert not (tmp_path / "video-tests").exists()


def test_rejects_non_normalized_bbox(client):
    manifest = fire_manifest()
    manifest["evidence"][0]["detections"][0]["bbox"] = [10, 20, 30, 40]

    response = post_manifest(client, manifest)

    assert response.status_code == 400
    assert response.get_json()["field"].endswith("bbox")


def test_rejects_missing_uploaded_image(client):
    response = post_manifest(client, fire_manifest(), images={})

    assert response.status_code == 400
    assert response.get_json()["field"] == "evidence"


def test_rejects_invalid_result_statistics(client):
    manifest = no_fire_manifest()
    manifest["result"] = "FIRE"

    response = post_manifest(client, manifest)

    assert response.status_code == 400
    assert response.get_json()["field"] == "result"


# ---------- 대표프레임(media_is_primary) 경쟁 — 실제 경로와 같은 규칙 ----------
#
# 두 경로(event_service.process_detection / video_test_service)가 같은 함수
# (event_service.promote_primary_if_higher)를 쓴다는 걸 행동으로 증명한다:
# "지금까지 최고 media_confidence 프레임이 대표" (동률이면 기존 유지),
# PEAK 역할이라서 강제로 대표가 되는 경로는 없다.

def _progress_detection(job_id, *, frame_index, confidence, media_url):
    """DETECTING 단계 진행 프레임 1장을 임시 이벤트로 적재한다."""
    return video_test_service.register_video_test_detection(
        job_id=job_id,
        sample_name="fire_test.mp4",
        cctv_no=1,
        started_at="2026-08-19T10:00:00",
        progress={
            "phase": "DETECTING",
            "frame_index": frame_index,
            "offset_sec": 2.0,
            "event_class": "FLAME",
            "confidence": confidence,
            "processed_frames": frame_index,
            "positive_frames": 1,
            "threshold_frames": 10,
            "first_detected_offset_sec": 2.0,
            "detections": [_detection(confidence)],
        },
        media_url=media_url,
    )


def _primary_media_row(event_no):
    rows = db.query(
        "SELECT media_url, media_frame_index, media_is_primary "
        "FROM event_media WHERE event_no = %s AND media_is_primary",
        (event_no,),
    )
    assert len(rows) == 1, "대표 프레임은 항상 정확히 1건이어야 한다"
    return rows[0]


def test_progress_frame_outranks_lower_confidence_peak_evidence(client):
    """진행 프레임(conf 0.9)이 최종 PEAK 증거(conf 0.85)보다 높으면 대표는
    여전히 진행 프레임이다 — PEAK 이면 무조건 대표를 강제하던 구 로직이면
    이 검증이 깨진다.
    """
    job_id = "b" * 32
    progress = _progress_detection(
        job_id, frame_index=60, confidence=0.9,
        media_url="/media/video-tests/jobs/b32/progress_60.jpg",
    )

    manifest = fire_manifest()
    manifest["job_id"] = job_id
    manifest["statistics"]["max_confidence"] = 0.85
    manifest["evidence"][2]["confidence"] = 0.85
    manifest["evidence"][2]["detections"] = [_detection(0.85)]

    images = {f"evidence_{index}": _jpeg(color)
              for index, color in enumerate(("red", "orange", "yellow"))}
    response = post_manifest(client, manifest, images=images)

    assert response.status_code == 201
    body = response.get_json()
    assert body["event_no"] == progress["event_no"]

    primary = _primary_media_row(body["event_no"])
    assert primary["media_url"] == progress["media_url"]
    assert primary["media_frame_index"] == 60


def test_peak_evidence_outranks_progress_frame_by_higher_confidence(client):
    """반대로 PEAK 증거(conf 0.95)가 진행 프레임(conf 0.5)보다 높으면 PEAK
    프레임이 대표가 된다 — 역할 때문이 아니라 경쟁 결과로서.
    """
    job_id = "c" * 32
    _progress_detection(
        job_id, frame_index=60, confidence=0.5,
        media_url="/media/video-tests/jobs/c32/progress_60.jpg",
    )

    manifest = fire_manifest()
    manifest["job_id"] = job_id  # PEAK 증거 conf 0.95 (fire_manifest 기본값)

    images = {f"evidence_{index}": _jpeg(color)
              for index, color in enumerate(("red", "orange", "yellow"))}
    response = post_manifest(client, manifest, images=images)

    assert response.status_code == 201
    body = response.get_json()

    primary = _primary_media_row(body["event_no"])
    assert primary["media_frame_index"] == 900
