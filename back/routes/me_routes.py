"""내 정보 API — 토큰 주인의 것만 다룬다.

GET    /api/me/activities  내 활동이력
GET    /api/me/telegram    텔레그램 연동 상태 + 연동 딥링크
DELETE /api/me/telegram    텔레그램 연동 해제

`/api/users/{user_no}/activities` 와 같은 표를 읽지만 **user_no 를 URL 로 받지
않는다.** 그래서 "남의 번호를 넣어 훔쳐볼 수 있는가"라는 문제가 아예 생기지 않고,
권한 검사도 사용자 존재 검사도 필요 없다 — 토큰이 곧 신원이고, 토큰이 있으면
그 사용자는 존재한다. 저쪽 엔드포인트의 403/404 분기가 여기서는 통째로 사라진다.

관리자가 **남의** 이력을 봐야 하는 화면은 여전히 `/api/users/{user_no}/activities`
를 쓴다. 둘은 대체 관계가 아니라 역할이 다르다.
"""
from flask import Blueprint, g, jsonify

import config
import db
from auth import login_required
from services import activity_service, telegram, telegram_link
from utils.pagination import get_page_params

bp = Blueprint("me", __name__)


@bp.get("/activities")
@login_required
def my_activities():
    """내 활동이력을 최신순으로 돌려준다 (페이징 공통 형식)."""
    page, size = get_page_params()
    return jsonify(activity_service.list_for_user(g.user["user_no"], page, size))


@bp.get("/telegram")
@login_required
def telegram_status():
    """텔레그램 연동 상태와 연동용 딥링크.

    링크를 누르면 텔레그램이 열리면서 `/start <코드>` 가 자동으로 채워진다 —
    사용자는 시작 버튼만 누르면 되고, 코드를 손으로 옮겨 적을 일이 없다.

    **코드는 저장하지 않는다.** services/telegram_link.py 가 HMAC 으로 매번 계산해
    대조하므로 이 요청은 DB 에 아무것도 쓰지 않는다. 유효시간은 5분이고, 만료되면
    화면을 새로고침해 다시 받으면 된다.

    봇 토큰을 넣지 않은 환경에서도 200 으로 답한다 (configured=false, link_url=null).
    화면이 뜨지 않으면 팀원이 원인을 찾기 어렵기 때문이다.
    """
    user_no = g.user["user_no"]
    row = db.query_one(
        "SELECT user_telegram_chat_id FROM users WHERE user_no = %s", (user_no,)
    )
    configured = bool(telegram.is_enabled() and config.TELEGRAM_BOT_USERNAME)
    link_url = None
    if configured:
        code = telegram_link.issue_code(user_no)
        link_url = f"https://t.me/{config.TELEGRAM_BOT_USERNAME}?start={code}"

    return jsonify({
        "configured": configured,
        "linked": row is not None and row["user_telegram_chat_id"] is not None,
        "link_url": link_url,
        "code_valid_sec": telegram_link.BUCKET_SEC * telegram_link.VALID_BUCKETS,
    })


@bp.delete("/telegram")
@login_required
def telegram_unlink():
    """내 텔레그램 연동을 끊는다. 이미 끊겨 있어도 200 (멱등)."""
    db.execute(
        "UPDATE users SET user_telegram_chat_id = NULL WHERE user_no = %s",
        (g.user["user_no"],),
    )
    return jsonify({"linked": False})
