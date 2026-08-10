"""검출 결과를 백엔드 내부 API 로 보낸다.

상대: `POST /api/internal/detections` (back/routes/internal_routes.py)
인증: JWT 가 아니라 `X-Internal-Key` 헤더.
"""
from datetime import datetime

ENDPOINT = "/api/internal/detections"

# 계속 보내봐야 결과가 같은 상태 — 설정이 틀린 것이므로 즉시 멈춘다
FATAL_STATUSES = {400, 401, 403, 404}


class SenderConfigError(RuntimeError):
    """설정이 틀려서 재시도가 무의미한 경우."""


def now() -> datetime:
    """시각을 함수로 뽑아 둔다 — 테스트에서 갈아끼운다."""
    return datetime.now()


class DetectionSender:
    """프레임 1장분 검출 결과를 백엔드에 넘긴다.

    일시적 실패(5xx, 연결 끊김)는 삼키고 계속 간다. 시연 도중 백엔드가 잠깐
    비틀거려도 검출까지 멈출 이유는 없다. 대신 실패 횟수를 세어 마지막에 보고한다.
    """

    def __init__(self, base_url: str, internal_key: str, session=None,
                 timeout: float = 3.0):
        self.base_url = base_url.rstrip("/")
        self.internal_key = internal_key
        self.timeout = timeout
        self.failures = 0
        self.consecutive_failures = 0
        self.sent = 0

        if session is not None:
            self._session = session
        else:
            import requests

            self._session = requests.Session()

    @property
    def url(self) -> str:
        return f"{self.base_url}{ENDPOINT}"

    def send(self, cctv_no: int, detections: list, media_url: str | None = None,
             captured_at: datetime | None = None) -> dict | None:
        """전송하고 백엔드 응답을 돌려준다. 일시적 실패면 None."""
        body = {
            "cctv_no": cctv_no,
            "captured_at": (captured_at or now()).isoformat(),
            "media_url": media_url,
            "detections": detections,
        }

        try:
            response = self._session.post(
                self.url,
                json=body,
                headers={"X-Internal-Key": self.internal_key},
                timeout=self.timeout,
            )
        except Exception as exc:  # 연결 거부·타임아웃 등
            self._record_failure()
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None

        if response.status_code in FATAL_STATUSES:
            raise SenderConfigError(self._fatal_message(response))

        if response.status_code >= 400:
            self._record_failure()
            self.last_error = f"HTTP {response.status_code}"
            return None

        self.consecutive_failures = 0
        self.sent += 1
        return response.json()

    def _record_failure(self):
        self.failures += 1
        self.consecutive_failures += 1

    def _fatal_message(self, response) -> str:
        try:
            payload = response.json()
        except Exception:
            payload = {}
        detail = payload.get("message") or payload.get("code") or ""

        if response.status_code in (401, 403):
            return (f"인증 실패 (HTTP {response.status_code}) — X-Internal-Key 가 "
                    f"백엔드 INTERNAL_API_KEY 와 다릅니다. {detail}")
        if response.status_code == 404:
            return (f"카메라를 찾을 수 없습니다 (HTTP 404) — cctv_no 가 DB 에 "
                    f"있는 번호인지 확인하세요. {detail}")
        return f"요청 형식 오류 (HTTP {response.status_code}) — {detail}"
