"""사용자 활동이력 적재와 조회.

원래 auth_routes 안의 private 함수였는데, 기록할 지점이 로그인·로그아웃 말고도
계정 변경(user_routes)과 관제 조치(alert_routes)로 늘면서 공용으로 뺐다.
조회 쿼리도 여기 있다 — /api/me/activities 와 /api/users/{user_no}/activities 가
같은 표를 같은 방식으로 읽으므로 한 곳에만 둔다.

**기록 실패는 삼킨다.** 활동이력은 부차적인 기록이고, 이걸 남기지 못했다는 이유로
정작 사용자가 한 일(로그인·화재 확인)이 실패하면 주객이 전도된다.
alert_routes 가 119 신고 시작 실패를 삼키는 것과 같은 판단이다.
"""
import logging

import db
from utils.pagination import paged_response

logger = logging.getLogger("fireguard.activity")

# 남기는 활동 종류. DB 에는 제약이 없고(varchar) 이 목록이 사실상의 정의다 —
# openapi.yaml 의 ActivityType, db/schema.sql 의 상태값 정의 블록과 함께 맞춰야 한다.
LOGIN = "LOGIN"
LOGOUT = "LOGOUT"
PASSWORD_CHANGED = "PASSWORD_CHANGED"
PROFILE_UPDATED = "PROFILE_UPDATED"
FIRE_CONFIRMED = "FIRE_CONFIRMED"
FIRE_DISMISSED = "FIRE_DISMISSED"


def record(user_no: int, activity_type: str,
           target_no: int | None = None, detail: str | None = None) -> None:
    """활동이력 1행을 남긴다.

    성공한 행위만 부른다 — 실패한 로그인이나 거절된 조치는 침입·오조작 기록이지
    활동 이력이 아니고, 한 표에 섞이면 '이 사람이 무엇을 했나'를 읽을 수 없게 된다.

    target_no 는 대상 행의 번호(화재 이벤트·사용자), detail 은 화면에 그대로 띄울
    한 줄 요약이다. 둘 다 없어도 되는 값이라 기본값은 None 이다.
    """
    try:
        db.execute(
            """
            INSERT INTO user_activity (user_no, activity_type,
                                       activity_target_no, activity_detail)
            VALUES (%s, %s, %s, %s)
            """,
            (user_no, activity_type, target_no, detail),
        )
    except Exception:
        # 여기서 예외를 올리면 로그인·화재 확인 자체가 실패한다. 이력 한 줄 때문에
        # 그럴 수는 없으므로 흔적만 남기고 넘어간다.
        logger.exception("활동이력 기록 실패 (user_no=%s, type=%s)", user_no, activity_type)


def list_for_user(user_no: int, page: int, size: int) -> dict:
    """한 사용자의 활동이력을 최신순으로 돌려준다 (페이징 공통 형식).

    권한 검사는 하지 않는다 — 부르는 쪽이 이미 '누구의 이력을 볼 자격이 있는가'를
    판단한 뒤에 온다. /api/me 는 토큰 주인이라 검사가 필요 없고,
    /api/users/{user_no} 는 ADMIN 여부를 따로 본다.
    """
    total = db.query_one(
        "SELECT count(*) AS cnt FROM user_activity WHERE user_no = %s", (user_no,)
    )["cnt"]
    rows = db.query(
        """
        SELECT activity_no, user_no, activity_type,
               activity_target_no, activity_detail, activity_at
        FROM user_activity
        WHERE user_no = %s
        ORDER BY activity_at DESC, activity_no DESC
        LIMIT %s OFFSET %s
        """,
        (user_no, size, (page - 1) * size),
    )
    return paged_response(rows, page, size, total)
