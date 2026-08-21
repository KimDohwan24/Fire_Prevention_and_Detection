import fireguard_ci_trial_missing_module  # CI 검증용 의도적 import 에러 — 이 브랜치는 머지하지 않는다
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
    # 디버그 리로더는 프로세스를 2개 띄워 create_app 이 두 번 불리고
    # 스케줄러도 이중으로 돌게 되므로 리로더를 끈다 (WERKZEUG_RUN_MAIN 가드 대신).
    create_app(start_scheduler=True).run(
        host="0.0.0.0", port=config.APP_PORT, debug=True, use_reloader=False,
    )


