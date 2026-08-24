"""동영상에서 화재를 검출한다 — 검증용(dry-run)과 시연용(send) 두 모드.

실시간 CCTV 로 화재를 만들 수 없으므로, 화재가 찍힌 동영상 파일을 카메라 대신 쓴다.

    # 검증: 백엔드 없이 검출만 보고, 박스 그린 영상 저장
    python run_video.py --video samples/house_fire.webm --annotate out/house.mp4

    # 시연: 검출을 백엔드로 보내 이벤트 → 알림 → 119 파이프라인을 돌린다
    python run_video.py --video samples/house_fire.webm --send --cctv-no 1 --realtime
"""
import argparse
import os
import sys
import time
from collections import Counter, defaultdict
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
from fireguard_detect.sender import DetectionSender, SenderConfigError
from fireguard_detect.video_source import VideoSource

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 박스 색 (BGR)
BOX_COLORS = {"flame": (0, 80, 255), "smoke": (200, 200, 200)}
DEFAULT_COLOR = (0, 255, 0)

# 백엔드가 프레임을 서빙하는 경로 접두어 (back/routes/media_routes.py)
MEDIA_URL_PREFIX = "/media/"


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="동영상 화재 검출 (검증 / 백엔드 전송)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--video", required=True, help="입력 동영상 경로")
    p.add_argument("--weights", default=str(DEFAULT_WEIGHTS), help="YOLO 가중치(.pt)")

    p.add_argument("--conf", type=float, default=DEFAULT_CONF, help="검출 신뢰도 임계값")
    p.add_argument("--iou", type=float, default=DEFAULT_IOU, help="NMS IoU")
    p.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ, help="추론 해상도")
    p.add_argument("--device", default="auto",
                   help="auto | cpu | cuda:0 — auto 는 GPU 있으면 GPU")
    p.add_argument("--max-det", type=int, default=DEFAULT_MAX_DET,
                   help="프레임당 남길 검출 개수 상한 (신뢰도 높은 순)")

    p.add_argument("--fps", type=float, default=3.0, help="초당 추론할 프레임 수")
    p.add_argument("--realtime", action="store_true",
                   help="원본 속도로 재생 (시연용). 없으면 최대 속도로 훑는다")
    p.add_argument("--max-frames", type=int, default=0,
                   help="이 개수만 처리하고 멈춘다 (0 이면 끝까지)")

    p.add_argument("--annotate", default="", help="박스 그린 영상 저장 경로 (검증용)")

    p.add_argument("--send", action="store_true", help="백엔드로 전송한다")
    p.add_argument("--cctv-no", type=int, help="전송 시 필수 — DB 에 있는 카메라 번호")
    p.add_argument("--api", default=os.getenv("FIREGUARD_API", "http://localhost:5000"),
                   help="백엔드 주소")
    p.add_argument("--key", default="", help="X-Internal-Key (미지정 시 .env 에서 읽음)")
    p.add_argument("--media-root", default="",
                   help="프레임 JPG 저장 위치. 미지정 시 MEDIA_ROOT 환경변수 → 루트 .env → "
                        "<루트>/media. 백엔드가 서빙하는 곳과 같아야 한다")
    p.add_argument("--send-empty", action="store_true",
                   help="검출 없는 프레임도 보낸다 (윈도우 만료 동작 확인용)")

    args = p.parse_args(argv)
    if args.send and args.cctv_no is None:
        p.error("--send 를 쓰려면 --cctv-no 가 필요합니다")
    return args


def read_dotenv(name: str) -> str:
    """루트 .env 에서 값을 하나 읽는다. 백엔드가 python-dotenv 로 읽는 그 파일이다."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip() 
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        if key.strip() == name:
            return value.strip()
    return ""


def load_internal_key(explicit: str) -> str:
    """--key > 환경변수 > 루트 .env 순으로 찾는다. **없으면 에러다.**

    예전에는 마지막에 `"dev-internal-key"` 로 폴백했다. 백엔드가 키 미설정 시
    조용히 쓰던 기본값과 짝을 맞춰 둔 것이었는데, 2026-08-24 부로 백엔드는
    기본값이면 아예 뜨지 않는다(back/config.py 의 시크릿 가드). 그래서 그 폴백은
    **항상 틀린 키**가 됐다 — 살려 두면 전송이 프레임마다 401 로 깨지는데,
    원인은 '키를 안 넣었다'인데 화면에는 '인증 실패'로만 보인다.
    보낼 것도 없이 시작할 때 멈추는 편이 낫다.
    """
    key = (explicit or os.getenv("INTERNAL_API_KEY")
           or read_dotenv("INTERNAL_API_KEY"))
    if not key:
        # ⚠️ 이 메시지에 em-dash(—) 같은 cp949 밖 문자를 쓰지 말 것.
        # 이 파일은 mock-119 와 달리 stdout/stderr 인코딩을 고정하지 않아서,
        # 윈도우 기본 콘솔에서는 '키가 없다'고 알리려는 print 자체가
        # UnicodeEncodeError 로 죽는다. 원인 대신 엉뚱한 예외만 보게 된다.
        raise ValueError(
            "INTERNAL_API_KEY 를 찾을 수 없습니다. --key 인자, 환경변수, "
            f"루트 .env({PROJECT_ROOT / '.env'}) 어디에도 없습니다.\n"
            "  백엔드와 같은 값이어야 합니다. .env 에 넣어 두면 양쪽이 함께 읽습니다."
        )
    return key


def load_media_root(explicit: str) -> Path:
    """프레임 JPG 를 어디에 저장할지.

    백엔드(`back/config.py:MEDIA_ROOT`)가 서빙하는 곳과 **같아야** 한다.
    다르면 저장은 되는데 `GET /media/<path>` 가 404 를 낸다.
    """
    return Path(explicit or os.getenv("MEDIA_ROOT") or read_dotenv("MEDIA_ROOT")
                or PROJECT_ROOT / "media")


def draw_boxes(image, detections):
    import cv2

    for det in detections:
        x1, y1, x2, y2 = (int(v) for v in det["bbox"])
        color = BOX_COLORS.get(det["cls"], DEFAULT_COLOR)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        label = f"{det['cls']} {det['conf']:.2f}"
        cv2.putText(image, label, (x1, max(y1 - 8, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return image


def save_frame_jpg(image, media_root: Path, cctv_no: int, when: datetime) -> str:
    """프레임을 MEDIA_ROOT 아래에 저장하고 백엔드에 넘길 URL 을 돌려준다.

    반환값은 event_media.media_url 에 그대로 저장되고 프론트의 <img src> 가 되므로,
    백엔드가 서빙하는 경로와 같은 "/media/<상대경로>" 형태여야 한다
    (back/routes/media_routes.py 의 GET /media/<path>).
    """
    import cv2

    rel = Path("events") / when.strftime("%Y-%m-%d") / \
        f"{cctv_no}_{when.strftime('%H%M%S_%f')}.jpg"
    target = media_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(target), image)
    return MEDIA_URL_PREFIX + rel.as_posix()


class Stats:
    """검출 결과를 모아 마지막에 사람이 읽을 수 있게 요약한다."""

    def __init__(self):
        self.frames = 0
        self.frames_with_detection = 0
        self.class_counts = Counter()
        self.confs = defaultdict(list)
        self.first_detection_sec = None
        self.backend_status = None
        self.confirmed_at_frame = None

    def add(self, frame, detections):
        self.frames += 1
        if not detections:
            return
        self.frames_with_detection += 1
        if self.first_detection_sec is None:
            self.first_detection_sec = frame.timestamp_sec
        for det in detections:
            self.class_counts[det["cls"]] += 1
            self.confs[det["cls"]].append(det["conf"])

    def report(self, elapsed: float, sender=None) -> str:
        lines = ["", "=" * 62, "검출 요약", "=" * 62]
        hit_rate = (self.frames_with_detection / self.frames * 100) if self.frames else 0
        lines.append(f"처리 프레임      : {self.frames}")
        lines.append(f"검출된 프레임    : {self.frames_with_detection} ({hit_rate:.1f}%)")
        if self.first_detection_sec is not None:
            lines.append(f"첫 검출 시점     : 영상 {self.first_detection_sec:.2f}초")
        else:
            lines.append("첫 검출 시점     : 없음 — 이 영상에서는 아무것도 못 잡았다")

        if self.class_counts:
            lines.append("")
            lines.append(f"{'클래스':<10}{'검출수':>8}{'평균conf':>10}"
                         f"{'최소':>8}{'최대':>8}")
            for cls, count in self.class_counts.most_common():
                confs = self.confs[cls]
                lines.append(f"{cls:<10}{count:>8}{sum(confs) / len(confs):>10.3f}"
                             f"{min(confs):>8.3f}{max(confs):>8.3f}")

        lines.append("")
        fps = self.frames / elapsed if elapsed else 0
        lines.append(f"소요 시간        : {elapsed:.1f}초 (추론 {fps:.1f} frame/s)")

        if sender is not None:
            lines.append(f"백엔드 전송      : 성공 {sender.sent} / 실패 {sender.failures}")
            if self.backend_status:
                lines.append(f"이벤트 상태      : {self.backend_status}")
            if self.confirmed_at_frame is not None:
                lines.append(f"CONFIRMED        : 전송 {self.confirmed_at_frame}번째 프레임")
        lines.append("=" * 62)
        return "\n".join(lines)


def main(argv=None) -> int:
    args = parse_args(argv)

    try:
        detector = Detector(weights=args.weights, conf=args.conf, iou=args.iou,
                            imgsz=args.imgsz, device=args.device,
                            max_det=args.max_det)
    except FileNotFoundError as exc:
        print(f"[오류] {exc}", file=sys.stderr)
        return 2

    try:
        source = VideoSource(args.video, target_fps=args.fps, realtime=args.realtime)
    except FileNotFoundError as exc:
        print(f"[오류] {exc}", file=sys.stderr)
        return 2

    sender = None
    media_root = None
    if args.send:
        # 키가 없으면 여기서 끝낸다 — 위의 FileNotFoundError 들과 같은 취급이다.
        # 트레이스백 대신 한 줄로 알려야 "무엇을 넣어야 하는지"가 보인다.
        try:
            internal_key = load_internal_key(args.key)
        except ValueError as exc:
            print(f"[오류] {exc}", file=sys.stderr)
            return 2
        sender = DetectionSender(base_url=args.api, internal_key=internal_key)
        media_root = load_media_root(args.media_root)
        media_root.mkdir(parents=True, exist_ok=True)

    print(f"모델   : {args.weights}  (device={detector.device}, conf={args.conf})")
    print(f"영상   : {args.video}  (초당 {args.fps} 프레임 추론"
          f"{', 실시간 재생' if args.realtime else ''})")
    if sender:
        print(f"전송   : {sender.url}  cctv_no={args.cctv_no}")
    else:
        print("전송   : 안 함 (검증 모드)")
    print("-" * 62)

    stats = Stats()
    writer = None
    started = time.monotonic()
    exit_code = 0

    try:
        for frame in source:
            detections = detector.detect(frame.image)
            stats.add(frame, detections)

            if detections:
                top = max(detections, key=lambda d: d["conf"])
                print(f"  {frame.timestamp_sec:6.2f}s  검출 {len(detections)}개  "
                      f"최고 {top['cls']} {top['conf']:.3f}")

            if args.annotate:
                writer = write_annotated(writer, args.annotate, frame, detections,
                                         args.fps)

            if sender and (detections or args.send_empty):
                media_url = None
                when = datetime.now()
                if detections:
                    media_url = save_frame_jpg(draw_boxes(frame.image.copy(), detections),
                                               media_root, args.cctv_no, when)
                result = sender.send(cctv_no=args.cctv_no, detections=detections,
                                     media_url=media_url, captured_at=when)
                note_backend_result(stats, sender, result)

            if args.max_frames and stats.frames >= args.max_frames:
                break
    except SenderConfigError as exc:
        print(f"\n[중단] {exc}", file=sys.stderr)
        exit_code = 3
    except KeyboardInterrupt:
        print("\n[중단] 사용자 종료")
    finally:
        source.close()
        if writer is not None:
            writer.release()

    print(stats.report(time.monotonic() - started, sender))
    if args.annotate and writer is not None:
        print(f"주석 영상 저장   : {args.annotate}")
    return exit_code


def note_backend_result(stats, sender, result):
    """백엔드 응답에서 이벤트 진행 상황을 뽑아 화면에 흘린다."""
    if not result:
        return
    status = result.get("event_status")
    if status:
        detected = result.get("event_detected_frames")
        threshold = result.get("event_threshold_frames")
        stats.backend_status = f"{status} (누적 {detected}/{threshold} 프레임)"
        if status == "CONFIRMED" and stats.confirmed_at_frame is None:
            stats.confirmed_at_frame = sender.sent
            print(f"  >>> 화재 확정 CONFIRMED  event_no={result.get('event_no')}")


def write_annotated(writer, path, frame, detections, fps):
    """첫 프레임에서 크기를 알아내 writer 를 만든다."""
    import cv2

    image = draw_boxes(frame.image.copy(), detections)
    if writer is None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        height, width = image.shape[:2]
        writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps,
                                 (width, height))
    writer.write(image)
    return writer


if __name__ == "__main__":
    sys.exit(main())
