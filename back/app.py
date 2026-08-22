"""파이어가드 백엔드 진입점.

실행:
    cd back
    python app.py        # http://localhost:5000
"""
import os
from datetime import date, datetime
from decimal import Decimal

from flask import Flask
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS

import config
from errors import register_error_handlers
from routes import register_blueprints
from request_role import request_role_bp

class ApiJSONProvider(DefaultJSONProvider):
    """명세서 공통 규칙: 날짜는 ISO 8601, numeric 은 숫자로 내보낸다."""
    @staticmethod
    def default(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        return DefaultJSONProvider.default(obj)


# 이 프로세스에서 돌고 있는 스케줄러. _start_escalation_scheduler 주석 참고.
_scheduler = None


def _start_escalation_scheduler():
    """백그라운드 작업을 띄운다. **프로세스당 하나씩.**

    1) 무응답 에스컬레이션 스윕 — APScheduler 잡, ESCALATION_INTERVAL_SEC 간격 (항상)
    2) 텔레그램 버튼 응답 폴링 — **전용 데몬 스레드**, 롱폴링 (봇 토큰이 있을 때만)

    이름이 escalation_scheduler 인 채로 남아 있는 것은 app.escalation_scheduler 를
    보는 기존 코드·테스트를 깨지 않기 위해서다. 반환값도 스케줄러 그대로다.

    **왜 텔레그램만 스케줄러 밖으로 나갔나** (2026-08-22, 실측 후 교체).
    getUpdates 는 직전 요청과 3초 안에 붙으면 서버가 정확히 3초를 붙잡는다. 그래서
    2초 간격 잡은 매번 자기 주기를 넘겨 `skipped: maximum number of running
    instances reached (1)` 를 찍었다 — 코드로 고칠 수 있는 값이 아니었다. 지금은
    롱폴링(timeout=25)을 전용 스레드에서 돌린다. 25초를 붙잡는 호출을 간격 잡에
    얹으면 같은 병이 더 크게 재발하므로 잡으로는 둘 수 없다.
    선택 근거와 실측값은 services/telegram_bot.py 의 '폴링 루프' 주석에 있다.

    **왜 여기서 이중 기동을 막나.** 이중 기동은 느려지는 문제가 아니라 기능이
    깨지는 문제다 — 텔레그램은 getUpdates 를 한 소비자에게만 온전히 주므로 폴링이
    두 벌 돌면 업데이트가 둘로 갈리거나 서로를
    `Conflict: terminated by other getUpdates request` 로 끊는다.
    그러면 버튼 응답이 사라져 유예 안에 '오탐 취소'를 받을 수 없고,
    취소를 못 받는다는 건 오탐에도 119 가 나간다는 뜻이다.
    그런데 앱 팩토리는 누구나 다시 부를 수 있다(WSGI 진입점, 테스트, 실수로 끼어든
    임포트). '한 번만' 을 호출부 규율에 맡기지 않고 직접 건다.

    기준을 '이미 띄웠나'가 아니라 **'지금 돌고 있나'**로 잡은 이유: 전자로 잡으면
    내려간 스케줄러를 그대로 물려주게 되어 잡이 하나도 안 도는데 앱은 멀쩡해 보인다.
    띄웠다 내리기를 반복하는 테스트가 서로를 오염시키지 않는 것도 같은 이유다.
    폴링 스레드도 같은 기준을 쓴다 (telegram_bot.start_polling).

    ⚠️ 가드가 막는 건 **같은 프로세스 안의** 중복이다. 프로세스가 갈리면(디버그
    리로더 등) 서로를 볼 수 없으므로 아래 __main__ 의 use_reloader=False 가 함께
    있어야 '한 번' 이 성립한다.
    """
    global _scheduler
    from apscheduler.schedulers.background import BackgroundScheduler

    from services import escalation, telegram_bot

    # 스케줄러 가드보다 **먼저**, 조건 없이 부른다. 둘은 이제 수명이 따로라
    # 스케줄러는 살아 있는데 폴링만 죽은 상태가 가능한데, 여기서 early return 하면
    # 그 상태에서 create_app 을 다시 불러도 폴링이 되살아나지 않는다.
    # start_polling 자체가 '지금 살아 있나' 가드를 갖고 있어 중복 기동은 안 된다.
    telegram_bot.start_polling()

    if _scheduler is not None and _scheduler.running:
        return _scheduler

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        escalation.run_escalation_tick, "interval",
        seconds=config.ESCALATION_INTERVAL_SEC,
        id="escalation_tick",
        max_instances=1, coalesce=True,  # 틱이 밀려도 겹쳐 돌거나 몰아서 돌지 않게
    )
    scheduler.start()
    _scheduler = scheduler
    return scheduler


def _print_effective_config():
    """지금 뜬 서버가 실제로 어떤 기준으로 도는지 한눈에 남긴다.

    판정·알림 기준은 전부 환경변수로 덮을 수 있는데(`config.py`), 덮였는지
    확인할 방법이 없어 "이 서버는 임계값 몇으로 떠 있나"를 매번 되짚어야 했다.
    기본값과 다른 값으로 띄워 놓고 잊는 사고를 막는 것이 목적이다.
    """
    print(f"판정 기준 : 확정 {config.EVENT_THRESHOLD_FRAMES}프레임 / "
          f"관측 창 {config.EVENT_WINDOW_SEC}초 (창은 최초 감지 시각에 고정)")
    print(f"알림·신고 : 응답 유예 {config.ALERT_DEADLINE_SEC}초 / "
          f"에스컬레이션 스윕 {config.ESCALATION_INTERVAL_SEC}초 / "
          f"119 최대 {config.MAX_REPORT_ATTEMPTS}회, 타임아웃 "
          f"{config.REPORT_HTTP_TIMEOUT_SEC}초")
    from services import telegram
    print(f"텔레그램  : " + (f"롱폴링 {config.TELEGRAM_LONG_POLL_SEC}초 (전용 스레드)"
                             if telegram.is_enabled()
                             else "꺼짐 (TELEGRAM_BOT_TOKEN 없음 — 모의 SMS 로만 발송)"))
    print(f"DB · 미디어: {config.DB_NAME}@{config.DB_HOST}:{config.DB_PORT} · "
          f"{config.MEDIA_ROOT}")


def create_app(start_scheduler: bool = False) -> Flask:
    """앱 팩토리."""
    app = Flask(__name__)
    
    # 💡 1. 302 리다이렉트 문제 해결을 위해 전역 설정 추가
    app.url_map.strict_slashes = False

    app.json = ApiJSONProvider(app)
    app.json.ensure_ascii = False  # 한글 메시지를 그대로 내보낸다

    CORS(app)  # 개발용: 모든 오리진 허용. 배포 시 프론트 도메인으로 제한할 것.

    # 미디어 저장 루트를 미리 만들어 둔다 (새로 클론한 환경에서도 바로 뜨게)
    os.makedirs(config.MEDIA_ROOT, exist_ok=True)

    register_error_handlers(app)
    
    # 기존 블루프린트들 등록
    register_blueprints(app)
    app.register_blueprint(request_role_bp)
    
    # 💡 2. 방금 만든 signup_bp 등록 추가
    from Signup import signup_bp
    app.register_blueprint(signup_bp)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    app.escalation_scheduler = _start_escalation_scheduler() if start_scheduler else None
    return app


if __name__ == "__main__":
    _print_effective_config()
    # 리로더를 끄는 이유: 리로더를 켜면 감시 부모와 작업 자식이 **각각 다른
    # 프로세스로** app.py 를 처음부터 실행한다. 아래 create_app(...) 은 .run() 보다
    # 먼저 평가되므로 양쪽에서 스케줄러가 뜨고, 프로세스가 갈렸으니
    # _start_escalation_scheduler 의 가드도 서로를 보지 못한다.
    # (2026-08-22 실측: use_reloader=True 로 두면 스케줄러 기동이 2회 — 한 번은
    #  WERKZEUG_RUN_MAIN 없이, 한 번은 =true 로 찍힌다. False 면 1회.)
    #
    # ⚠️ 작업관리자에 python.exe 가 2개 보이는 건 **이것과 무관하다.** 윈도우
    # venv 의 Scripts\python.exe 는 기반 인터프리터를 자식으로 띄우고 기다리는
    # 실행기(redirector)라, 파이썬 코드는 자식에서 한 번만 도는데도 프로세스는
    # 늘 2개로 보인다 (파이어가드를 하나도 임포트하지 않는 빈 Flask 앱도 똑같다).
    # 이걸 리로더 탓으로 읽고 여기를 건드리면 엉뚱한 곳을 고치게 된다.
    #
    # WERKZEUG_RUN_MAIN 가드로 리로더를 되살리는 선택지도 있으나 택하지 않았다 —
    # 119 신고가 진행 중인데 파일 저장 한 번으로 서버가 갈아끼워지는 편이 더 나쁘다.
    create_app(start_scheduler=True).run(
        host="0.0.0.0", port=config.APP_PORT, debug=True, use_reloader=False,
    )


