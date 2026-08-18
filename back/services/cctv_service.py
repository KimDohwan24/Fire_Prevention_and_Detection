"""카메라 조회 — 응답 컬럼 정본과 목록·단건 질의.

공개 API(routes/cctv_routes)와 AI 내부 API(routes/internal_routes)가 같은 카메라
목록을 내려준다. 전에는 내부 라우트가 공개 라우트에서 COLUMNS 를 직접 import 했는데,
라우트끼리 끌어다 쓰는 유일한 지점이었던 데다 "어떤 컬럼을 내보내는가"는 라우트의
관심사가 아니라 스키마 지식이라 이리로 내렸다.

스트림 주소 최신화(its_cctv.refresh_stream_urls)까지 여기서 끝낸다. 두 라우트가
각자 부르던 것을 합친 것으로, 한쪽만 빠뜨려 만료된 주소가 나가는 일을 막는다.
"""
import db
from services import its_cctv

# 응답에 내보내는 컬럼을 명시한다 — SELECT * 를 쓰면 나중에 컬럼이 추가될 때
# 의도치 않은 값이 조용히 API 응답에 섞여 나간다 (명세서 4번 섹션 기준)
COLUMNS = """cctv_no, user_no, cctv_name, cctv_location, cctv_lat, cctv_lng,
             cctv_stream_url, cctv_width, cctv_height, cctv_status, cctv_created_at"""


def list_cctvs(cctv_status: str | None = None,
               user_no: int | None = None) -> list[dict]:
    """카메라 목록 (스트림 주소 최신화 포함).

    cctv_status: 가동 상태 필터. 빈 값이면 걸지 않는다.
    user_no: 담당(소유) 사용자 필터. None 이면 걸지 않는다 — 관리자 화면에서 쓴다.
    """
    conds = []
    params: list = []
    if cctv_status:
        conds.append("cctv_status = %s")
        params.append(cctv_status)
    if user_no is not None:
        conds.append("user_no = %s")
        params.append(user_no)

    where = f"WHERE {' AND '.join(conds)}" if conds else ""

    rows = db.query(
        f"SELECT {COLUMNS} FROM cctv {where} ORDER BY cctv_no", tuple(params)
    )
    # ITS 카메라의 스트림 주소는 토큰이 만료되므로 응답 직전에 최신 값으로 갈아끼운다
    # (외부 API 가 죽어 있으면 저장된 주소 그대로 내려간다)
    return its_cctv.refresh_stream_urls(rows)


def get_cctv(cctv_no: int) -> dict | None:
    """카메라 단건 (없으면 None). 스트림 주소는 목록과 같은 규칙으로 최신화한다."""
    row = db.query_one(
        f"SELECT {COLUMNS} FROM cctv WHERE cctv_no = %s", (cctv_no,)
    )
    if row is None:
        return None
    return its_cctv.refresh_stream_urls([row])[0]
