"""파이어가드 백엔드 진입점.

실행:
    cd back
    python app.py        # http://localhost:5000
"""
import logging
import os
import re
from datetime import date, datetime
from decimal import Decimal
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

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


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


class _PlainFormatter(logging.Formatter):
    """파일에 쓸 때만 색상 이스케이프를 벗긴다.

    werkzeug 는 접근 로그의 메서드·상태코드에 색을 입혀 보낸다. 콘솔에서는
    그게 도움이 되지만 파일에는 색상 이스케이프가 글자로 박혀 grep 이 어긋난다.
    콘솔 핸들러는 색을 그대로 두고 파일 쪽만 이 포매터를 쓴다.
    """

    def format(self, record: logging.LogRecord) -> str:
        return _ANSI.sub("", super().format(record))


# 우리가 붙인 핸들러임을 표시한다. 다시 부를 때 이것만 골라 걷어내면
# 남(Flask·APScheduler 등)이 붙여 놓은 핸들러를 건드리지 않는다.
_HANDLER_MARK = "_fireguard_handler"


def setup_logging(log_dir=None, level: str | None = None) -> None:
    """서비스 코드가 남기는 로그를 콘솔과 파일 양쪽에 받는다.

    `logging.getLogger("fireguard.*")` 로 접수된 로그는 부모를 타고 루트까지
    올라오므로, 루트에 핸들러를 붙이면 12개 로거 44곳이 한꺼번에 살아난다.
    남기는 쪽 코드는 한 줄도 고치지 않는다 — 그게 print 가 아니라 logging 을
    쓰는 이유다.

    create_app() 안이 아니라 밖에 둔 이유: 테스트가 create_app() 을 여러 번
    부르는데(conftest.py, test_escalation.py), 그때마다 핸들러가 붙으면 같은
    로그가 N 줄씩 찍힌다. 그래서 진입점에서 딱 한 번 부르고, 실수로 두 번
    불려도 기존 것을 걷어내고 다시 깔아 결과가 같게 만든다.
    """
    LAYOUT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    DATEFMT = "%Y-%m-%d %H:%M:%S"
    fmt = logging.Formatter(LAYOUT, datefmt=DATEFMT)

    root = logging.getLogger()
    for old in [h for h in root.handlers if getattr(h, _HANDLER_MARK, False)]:
        root.removeHandler(old)
        old.close()   # 윈도우는 파일을 연 채로 두면 이름 변경·삭제가 막힌다

    console = logging.StreamHandler()          # 개발 중 눈으로 본다
    console.setFormatter(fmt)

    # 자정마다 fireguard.log.2026-08-22 로 넘기고 LOG_BACKUP_DAYS 일치만 남긴다.
    # 크기 기준(RotatingFileHandler)이 아니라 날짜 기준인 이유는 "그날 밤에
    # 무슨 일이 있었나"로 찾는 일이 대부분이라서다.
    directory = Path(log_dir or config.LOG_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    daily = TimedRotatingFileHandler(
        directory / "fireguard.log", when="midnight",
        backupCount=config.LOG_BACKUP_DAYS, encoding="utf-8",
    )
    daily.setFormatter(_PlainFormatter(LAYOUT, datefmt=DATEFMT))

    for h in (console, daily):
        setattr(h, _HANDLER_MARK, True)
        root.addHandler(h)
    root.setLevel(level or config.LOG_LEVEL)

    # APScheduler 는 잡을 돌릴 때마다 INFO 2줄을 남긴다. 에스컬레이션 스윕은
    # ESCALATION_INTERVAL_SEC(기본 5초)마다 도니 하루 3만 줄이 넘고, 실제
    # 화재 로그가 그 밑에 묻힌다. 성공한 틱은 버리고 사고(WARNING 이상)만 남긴다.
    logging.getLogger("apscheduler.executors").setLevel(logging.WARNING)


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
    setup_logging()
    _print_effective_config()
    # 디버그 리로더는 프로세스를 2개 띄워 create_app 이 두 번 불리고
    # 스케줄러도 이중으로 돌게 되므로 리로더를 끈다 (WERKZEUG_RUN_MAIN 가드 대신).
    create_app(start_scheduler=True).run(
        host="0.0.0.0", port=config.APP_PORT, debug=True, use_reloader=False,
    )


