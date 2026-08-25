"""영상 파일 하나를 끝까지 분석해 FIRE/NO_FIRE 결과를 DB에 저장한다.

예시:
    python validate_video.py --video samples/fire.mp4 --cctv-no 1
    python validate_video.py --video samples/fire.mp4 --weights other_best.pt
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from fireguard_detect.detector import (
    DEFAULT_CONF,
    DEFAULT_IMGSZ,
    DEFAULT_IOU,
    DEFAULT_MAX_DET,
    DEFAULT_WEIGHTS,
    Detector,
)
from fireguard_detect.video_source import VideoSource
from fireguard_detect.video_test import VideoDecisionEngine, build_manifest
from fireguard_detect.video_test_sender import VideoTestSender, VideoTestSenderError
from run_video import load_internal_key

DEFAULT_INFERENCE_FPS = 3.0
DEFAULT_WINDOW_SEC = 60.0
DEFAULT_THRESHOLD_FRAMES = 10


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="영상 전체 화재 판정 및 테스트 이력 저장",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--video", required=True, help="입력 영상 경로")
    parser.add_argument("--weights", default=str(DEFAULT_WEIGHTS), help="YOLO 가중치(.pt)")
    parser.add_argument("--cctv-no", type=int,
                        help="연결할 등록 CCTV 번호. 생략하면 ACTIVE 목록에서 선택")
    parser.add_argument("--api", default=os.getenv("FIREGUARD_API", "http://localhost:5000"),
                        help="백엔드 주소")
    parser.add_argument("--key", default="", help="X-Internal-Key")
    parser.add_argument(
        "--job-id",
        default="",
        help="백그라운드 영상 테스트 job_id (분석 중 감지 진행상황 전송용)",
    )
    parser.add_argument(
        "--result-json",
        default="",
        help="분석 결과 응답을 JSON 파일로 저장 (백엔드 연동용)",
    )
    parser.add_argument("--fps", type=float, default=DEFAULT_INFERENCE_FPS,
                        help="초당 추론 프레임 수")
    parser.add_argument("--window-sec", type=float, default=DEFAULT_WINDOW_SEC,
                        help="최초 양성 프레임 기준 고정 관측 창")
    parser.add_argument("--threshold-frames", type=int, default=DEFAULT_THRESHOLD_FRAMES,
                        help="관측 창 안에서 FIRE로 확정할 양성 프레임 수")
    parser.add_argument("--conf", type=float, default=DEFAULT_CONF)
    parser.add_argument("--iou", type=float, default=DEFAULT_IOU)
    parser.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ)
    parser.add_argument("--device", default="auto", help="auto | cpu | cuda:0")
    parser.add_argument("--max-det", type=int, default=DEFAULT_MAX_DET)
    args = parser.parse_args(argv)

    if args.cctv_no is not None and args.cctv_no <= 0:
        parser.error("--cctv-no 는 1 이상이어야 합니다")
    if args.fps <= 0 or args.window_sec <= 0:
        parser.error("--fps 와 --window-sec 는 0보다 커야 합니다")
    if args.threshold_frames <= 0 or args.imgsz <= 0 or args.max_det <= 0:
        parser.error("--threshold-frames, --imgsz, --max-det 는 1 이상이어야 합니다")
    if not 0 <= args.conf <= 1 or not 0 <= args.iou <= 1:
        parser.error("--conf 와 --iou 는 0~1 범위여야 합니다")
    return args


def choose_cctv(sender: VideoTestSender, cctv_no: int | None, input_fn=input) -> int:
    if cctv_no is not None:
        return cctv_no
    items = sender.list_active_cctvs()
    if not items:
        raise VideoTestSenderError("선택할 수 있는 ACTIVE CCTV가 없습니다.")

    print("\nACTIVE CCTV 목록")
    for item in items:
        location = item.get("cctv_location") or "위치 미등록"
        print(f"  {item['cctv_no']:>4}  {item.get('cctv_name') or '이름 없음'} · {location}")
    valid = {int(item["cctv_no"]) for item in items}
    try:
        selected = int(input_fn("사용할 CCTV 번호: ").strip())
    except (EOFError, ValueError, AttributeError) as exc:
        raise VideoTestSenderError("CCTV 번호를 올바르게 입력해야 합니다.") from exc
    if selected not in valid:
        raise VideoTestSenderError("ACTIVE 목록에 있는 CCTV 번호를 선택해야 합니다.")
    return selected


def _print_decision(decision, response):
    print("\n" + "=" * 62)
    print(f"최종 판정        : {decision.result}")
    print(f"처리 프레임      : {decision.processed_frames}")
    print(f"양성 프레임      : {decision.positive_frames}")
    print(f"관측 기준        : {decision.window_sec:g}초 안에 "
          f"{decision.threshold_frames}프레임")
    print(f"첫 검출 시점     : {decision.first_detected_offset_sec}")
    print(f"확정 시점        : {decision.confirmed_offset_sec}")
    print(f"증거 이미지      : {len(decision.evidence)}장")
    print(f"저장 이벤트 번호 : {response['event_no']}")
    print("=" * 62)


def main(argv=None) -> int:
    args = parse_args(argv)
    video_path = Path(args.video)
    weights_path = Path(args.weights)
    if not video_path.is_file():
        print(f"[오류] 영상 파일을 찾을 수 없습니다: {video_path}", file=sys.stderr)
        return 2
    if not weights_path.is_file():
        print(f"[오류] 모델 가중치를 찾을 수 없습니다: {weights_path}", file=sys.stderr)
        return 2

    sender = VideoTestSender(args.api, load_internal_key(args.key))
    try:
        cctv_no = choose_cctv(sender, args.cctv_no)
        detector = Detector(
            weights=weights_path, conf=args.conf, iou=args.iou,
            imgsz=args.imgsz, device=args.device, max_det=args.max_det,
        )
        source = VideoSource(video_path, target_fps=args.fps)
        engine = VideoDecisionEngine(
            window_sec=args.window_sec,
            threshold_frames=args.threshold_frames,
        )
        started_at = datetime.now()
        print(f"모델: {weights_path.name} ({detector.device})")
        print(f"영상: {video_path.name} — 길이 제한 없이 끝까지 분석합니다.")

        first_progress_sent = False
        confirmation_progress_sent = False
        try:
            for frame in source:
                detections = detector.detect(frame.image)
                engine.add(frame, detections)
                fire = [item for item in detections
                        if item.get("cls") in ("flame", "smoke")]
                if fire:
                    top = max(fire, key=lambda item: item["conf"])
                    print(f"  {frame.timestamp_sec:8.2f}s  "
                          f"{top['cls']} {top['conf']:.3f}")

                if args.job_id and fire:
                    phase = None
                    if engine.is_confirmed and not confirmation_progress_sent:
                        phase = "FIRE_CONFIRMED"
                        confirmation_progress_sent = True
                    elif engine.positive_frames == 1 and not first_progress_sent:
                        phase = "DETECTING"
                        first_progress_sent = True

                    if phase:
                        classes = {
                            "FLAME" if item["cls"] == "flame" else "SMOKE"
                            for item in fire
                        }
                        event_class = (
                            "FLAME_SMOKE" if len(classes) == 2
                            else next(iter(classes), "FLAME")
                        )
                        progress = {
                            "phase": phase,
                            "frame_index": int(frame.index),
                            "offset_sec": float(frame.timestamp_sec),
                            "event_class": event_class,
                            "confidence": float(engine.max_confidence or top["conf"]),
                            "processed_frames": engine.processed_frames,
                            "positive_frames": engine.positive_frames,
                            "threshold_frames": engine.threshold_frames,
                            "first_detected_offset_sec": engine.first_detected_offset_sec,
                            "confirmed_offset_sec": engine.confirmed_offset_sec,
                            "detections": fire,
                        }
                        try:
                            sender.send_progress(args.job_id, progress, frame)
                        except VideoTestSenderError as exc:
                            # 진행상황 전송 실패가 최종 분석·저장을 중단시키지는 않는다.
                            print(f"[경고] 영상 테스트 진행상황 전송 실패: {exc}",
                                  file=sys.stderr)
        finally:
            source.close()

        finished_at = datetime.now()
        decision = engine.finish(
            duration_sec=source.duration_sec,
            source_fps=source.source_fps,
        )
        manifest = build_manifest(
            decision=decision, cctv_no=cctv_no, video_path=video_path,
            weights_path=weights_path, detector=detector, inference_fps=args.fps,
            started_at=started_at, finished_at=finished_at,
            job_id=args.job_id or None,
        )
        response = sender.submit(manifest, decision.evidence)
        if args.result_json:
            result_path = Path(args.result_json)
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(
                json.dumps(response, ensure_ascii=False),
                encoding="utf-8",
            )
        _print_decision(decision, response)
        return 0
    except VideoTestSenderError as exc:
        print(f"[오류] 백엔드 저장 실패: {exc}", file=sys.stderr)
        return 3
    except (FileNotFoundError, ImportError, OSError, RuntimeError, ValueError) as exc:
        print(f"[오류] 영상 분석 실패: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n[중단] 사용자 종료", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
