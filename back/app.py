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


class ApiJSONProvider(DefaultJSONProvider):
    """명세서 공통 규칙: 날짜는 ISO 8601, numeric 은 숫자로 내보낸다."""
    @staticmethod
    def default(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        return DefaultJSONProvider.default(obj)


def _start_escalation_scheduler():
    """무응답 에스컬레이션 스윕을 ESCALATION_INTERVAL_SEC 간격으로 돌린다."""
    from apscheduler.schedulers.background import BackgroundScheduler

    from services import escalation

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        escalation.run_escalation_tick, "interval",
        seconds=config.ESCALATION_INTERVAL_SEC,
        id="escalation_tick",
        max_instances=1, coalesce=True,  # 틱이 밀려도 겹쳐 돌거나 몰아서 돌지 않게
    )
    scheduler.start()
    return scheduler


def create_app(start_scheduler: bool = False) -> Flask:
    """앱 팩토리.

    start_scheduler: 에스컬레이션 스케줄러 기동 여부. 기본 False —
    테스트/임포트 경로에서는 백그라운드 스레드가 뜨지 않는다.
    `python app.py` 실행 경로(__main__)만 True 로 켠다.
    """
    app = Flask(__name__)
    app.json = ApiJSONProvider(app)
    app.json.ensure_ascii = False  # 한글 메시지를 그대로 내보낸다

    CORS(app)  # 개발용: 모든 오리진 허용. 배포 시 프론트 도메인으로 제한할 것.

    # 미디어 저장 루트를 미리 만들어 둔다 (새로 클론한 환경에서도 바로 뜨게)
    os.makedirs(config.MEDIA_ROOT, exist_ok=True)

    register_error_handlers(app)
    register_blueprints(app)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    app.escalation_scheduler = _start_escalation_scheduler() if start_scheduler else None
    return app


if __name__ == "__main__":
    # 디버그 리로더는 프로세스를 2개 띄워 create_app 이 두 번 불리고
    # 스케줄러도 이중으로 돌게 되므로 리로더를 끈다 (WERKZEUG_RUN_MAIN 가드 대신).
    create_app(start_scheduler=True).run(
        host="0.0.0.0", port=config.APP_PORT, debug=True, use_reloader=False,
    )
