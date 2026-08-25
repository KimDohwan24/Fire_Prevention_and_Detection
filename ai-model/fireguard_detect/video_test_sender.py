"""영상 테스트 결과를 백엔드 내부 API에 multipart로 전송한다."""
import json

VIDEO_TEST_ENDPOINT = "/api/internal/video-tests"
VIDEO_PROGRESS_ENDPOINT = "/api/internal/video-tests/{job_id}/progress"
CCTV_ENDPOINT = "/api/internal/cctvs"


class VideoTestSenderError(RuntimeError):
    """영상 테스트 API 통신 또는 응답 오류."""


class VideoTestSender:
    def __init__(self, base_url: str, internal_key: str, session=None,
                 timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.internal_key = internal_key
        self.timeout = timeout
        if session is None:
            import requests

            session = requests.Session()
        self._session = session

    @property
    def headers(self) -> dict:
        return {"X-Internal-Key": self.internal_key}

    def list_active_cctvs(self) -> list[dict]:
        try:
            response = self._session.get(
                f"{self.base_url}{CCTV_ENDPOINT}",
                params={"cctv_status": "ACTIVE"},
                headers=self.headers,
                timeout=self.timeout,
            )
        except Exception as exc:
            raise VideoTestSenderError(f"CCTV 목록 요청 실패: {exc}") from exc
        self._raise_for_error(response)
        try:
            payload = response.json()
        except Exception as exc:
            raise VideoTestSenderError("CCTV 목록 응답이 JSON이 아닙니다.") from exc
        items = payload.get("items")
        if not isinstance(items, list):
            raise VideoTestSenderError("CCTV 목록 응답 형식이 올바르지 않습니다.")
        return items

    def submit(self, manifest: dict, evidence: list) -> dict:
        metadata = manifest.get("evidence", [])
        if len(metadata) != len(evidence):
            raise VideoTestSenderError("manifest와 증거 이미지 개수가 다릅니다.")

        import cv2

        files = {}
        for item, frame in zip(metadata, evidence):
            ok, encoded = cv2.imencode(".jpg", frame.image)
            if not ok:
                raise VideoTestSenderError(
                    f"프레임 {frame.frame_index}을 JPEG로 변환하지 못했습니다."
                )
            field = item["file_field"]
            files[field] = (f"{field}.jpg", encoded.tobytes(), "image/jpeg")

        try:
            response = self._session.post(
                f"{self.base_url}{VIDEO_TEST_ENDPOINT}",
                data={"manifest": json.dumps(manifest, ensure_ascii=False)},
                files=files,
                headers=self.headers,
                timeout=self.timeout,
            )
        except Exception as exc:
            raise VideoTestSenderError(f"영상 테스트 결과 전송 실패: {exc}") from exc
        self._raise_for_error(response)
        try:
            return response.json()
        except Exception as exc:
            raise VideoTestSenderError("영상 테스트 저장 응답이 JSON이 아닙니다.") from exc

    def send_progress(self, job_id: str, progress: dict, frame) -> dict:
        """분석 중 최초 감지·확정 순간의 JPEG와 상태를 전송한다."""
        import cv2

        ok, encoded = cv2.imencode(".jpg", frame.image)
        if not ok:
            raise VideoTestSenderError(
                f"프레임 {frame.index}을 JPEG로 변환하지 못했습니다."
            )

        endpoint = VIDEO_PROGRESS_ENDPOINT.format(job_id=job_id)
        try:
            response = self._session.post(
                f"{self.base_url}{endpoint}",
                data={"progress": json.dumps(progress, ensure_ascii=False)},
                files={
                    "image": (
                        f"progress_{frame.index}.jpg",
                        encoded.tobytes(),
                        "image/jpeg",
                    )
                },
                headers=self.headers,
                timeout=self.timeout,
            )
        except Exception as exc:
            raise VideoTestSenderError(f"영상 테스트 진행상황 전송 실패: {exc}") from exc
        self._raise_for_error(response)
        try:
            return response.json()
        except Exception as exc:
            raise VideoTestSenderError("영상 테스트 진행상황 응답이 JSON이 아닙니다.") from exc

    @staticmethod
    def _raise_for_error(response):
        if response.status_code < 400:
            return
        try:
            payload = response.json()
        except Exception:
            payload = {}
        detail = payload.get("message") or payload.get("code") or "응답 본문 없음"
        raise VideoTestSenderError(f"백엔드 오류 HTTP {response.status_code}: {detail}")
