"""관리자 알림 발송 서비스 (동시 발송 확정 설계).

- 알림은 해당 CCTV 의 소유 사용자(cctv.user_no)에게만 간다.
  ADMIN 브로드캐스트 없음 — 감지→알림→신고 루프에 관리자는 관여하지 않는다.
- 이벤트가 확정되면 PUSH 와 SMS 를 **한 트랜잭션에서 동시에** 만든다.
  두 채널 모두 같은 사람의 같은 휴대폰으로 가므로 단계를 나눠 승격시키면
  화재 상황에서 유예 시간만 두 배로 낭비된다 (단계 승격 개념 폐기).
- 전달: 바깥으로 나가는 한 건은 services/notify.py 가 채널을 정해 여기서 실제로
  보내고(연동한 사용자는 텔레그램, 아니면 문자), PUSH 는 프론트 폴링이 가져간다.
- 마감: alert_deadline_at = alert_sent_at + ALERT_DEADLINE_SEC 초. 두 행이 동일하다.
  이 유예까지 무응답이면 에스컬레이션이 두 알림을 NO_RESPONSE 로 닫고 119 로 넘긴다.
- 승격 단계는 폐기됐고 alert_level 컬럼도 2026-08-10 삭제됐다.
- 점검 모드(event_is_test) 이벤트는 어떤 알림도 만들지 않는다.
"""
import logging

import config
import db
from services import notify

logger = logging.getLogger("fireguard.alert")

# 확정 시 동시에 나가는 채널 (PUSH = 프론트 폴링, SMS = 바깥 전달용 행)
# 'SMS' 는 alert_channel 컬럼 값(=행 이름)일 뿐 실제 전달 수단이 아니다 — 연동한
# 사용자에게는 이 행에 대해 텔레그램으로 나간다(services/notify.py). 컬럼 값을 바꾸면
# 기존 데이터와 프론트 표시가 함께 깨지므로 이름은 그대로 둔다.
CHANNELS = ("PUSH", "SMS")

# 이벤트 클래스 → 알림 문구용 한글 표기
CLASS_LABEL = {"FLAME": "불꽃", "SMOKE": "연기", "FLAME_SMOKE": "불꽃·연기"}


def send_alerts(event_no: int) -> list[int] | None:
    """이벤트의 CCTV 소유자에게 PUSH·SMS 알림을 동시에 만든다.

    - 반환: 생성(또는 이미 존재)한 alert_no 목록(오름차순). 발송 불가 상황이면 None.
    - 멱등: 이벤트 단위. 해당 이벤트에 알림이 하나라도 있으면 새로 만들지 않고
      기존 번호들을 돌려준다 (SMS 재발송도 하지 않는다).
    """
    row = db.query_one(
        """
        SELECT e.event_class, e.event_is_test,
               c.cctv_name, c.cctv_location,
               u.user_no, u.user_phone, u.user_telegram_chat_id
        FROM fire_event e
        JOIN cctv c ON c.cctv_no = e.cctv_no
        LEFT JOIN users u ON u.user_no = c.user_no
        WHERE e.event_no = %s
        """,
        (event_no,),
    )
    if row is None or row["user_no"] is None:
        # 이벤트가 없거나 CCTV 소유자가 없다 — 알림을 만들 수 없지만 죽지는 않는다
        logger.warning("알림 발송 불가 — 이벤트/소유자 없음 (event_no=%s)", event_no)
        return None
    if row["event_is_test"]:
        # 점검 모드: 알림 파이프라인 전체를 건너뛴다
        logger.info("점검 모드 이벤트 — 알림 생략 (event_no=%s)", event_no)
        return None

    # 멱등 가드: 훅이 중복 호출돼도 이벤트당 알림 묶음은 1회만
    existing = db.query(
        "SELECT alert_no FROM alert WHERE event_no = %s ORDER BY alert_no",
        (event_no,),
    )
    if existing:
        return [r["alert_no"] for r in existing]

    # 두 행을 한 INSERT 로 — now() 는 트랜잭션 시각이라 발송·마감 시각이 완전히 같다
    with db.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO alert (event_no, user_no, alert_channel,
                               alert_status, alert_sent_at, alert_deadline_at)
            VALUES (%(event_no)s, %(user_no)s, 'PUSH', 'SENT',
                    now(), now() + make_interval(secs => %(secs)s)),
                   (%(event_no)s, %(user_no)s, 'SMS', 'SENT',
                    now(), now() + make_interval(secs => %(secs)s))
            RETURNING alert_no, alert_channel
            """,
            {"event_no": event_no, "user_no": row["user_no"],
             "secs": config.ALERT_DEADLINE_SEC},
        )
        created = cur.fetchall()
        alert_nos = sorted(r["alert_no"] for r in created)
        # 버튼을 붙일 대상은 SMS 행이다 — 텔레그램은 그 자리를 대신하는 채널이고,
        # PUSH 행은 프론트 폴링이 따로 가져간다.
        # (응답은 어차피 이벤트 단위로 형제 알림까지 함께 닫는다 — alert_respond.py)
        outbound_no = next(r["alert_no"] for r in created if r["alert_channel"] == "SMS")

    # 바깥으로 실제 전달 (PUSH 는 프론트가 폴링으로 가져가므로 여기서 다루지 않는다).
    # 어느 채널로 나갈지는 notify 가 정한다 — 연동한 사용자는 텔레그램, 아니면 문자.
    label = CLASS_LABEL.get(row["event_class"], row["event_class"] or "화재")
    message = (f"[파이어가드] {row['cctv_name']}({row['cctv_location']}) "
               f"{label} 감지! 앱에서 확인해주세요.")
    channel = notify.send_fire_alert(
        chat_id=row["user_telegram_chat_id"], phone=row["user_phone"],
        message=message, alert_no=outbound_no,
    )
    logger.info("알림 전달 (event_no=%s, alert_no=%s, 채널=%s)",
                event_no, outbound_no, channel)

    return alert_nos
