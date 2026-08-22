"""내 정보 API — 토큰 주인의 것만 다룬다.

GET /api/me/activities   내 활동이력

`/api/users/{user_no}/activities` 와 같은 표를 읽지만 **user_no 를 URL 로 받지
않는다.** 그래서 "남의 번호를 넣어 훔쳐볼 수 있는가"라는 문제가 아예 생기지 않고,
권한 검사도 사용자 존재 검사도 필요 없다 — 토큰이 곧 신원이고, 토큰이 있으면
그 사용자는 존재한다. 저쪽 엔드포인트의 403/404 분기가 여기서는 통째로 사라진다.

관리자가 **남의** 이력을 봐야 하는 화면은 여전히 `/api/users/{user_no}/activities`
를 쓴다. 둘은 대체 관계가 아니라 역할이 다르다.
"""
from flask import Blueprint, g, jsonify

from auth import login_required
from services import activity_service
from utils.pagination import get_page_params

bp = Blueprint("me", __name__)


@bp.get("/activities")
@login_required
def my_activities():
    """내 활동이력을 최신순으로 돌려준다 (페이징 공통 형식)."""
    page, size = get_page_params()
    return jsonify(activity_service.list_for_user(g.user["user_no"], page, size))
