"""블루프린트 모음. app.py 에서 register_blueprints(app) 한 번만 부르면 된다."""
from flask import Flask

from routes.auth_routes import bp as auth_bp
from routes.user_routes import bp as user_bp
from routes.me_routes import bp as me_bp
from routes.cctv_routes import bp as cctv_bp
from routes.event_routes import bp as event_bp
from routes.alert_routes import bp as alert_bp
from routes.agency_routes import bp as agency_bp
from routes.its_routes import bp as its_bp
from routes.report_routes import bp as report_bp
from routes.internal_routes import bp as internal_bp
from routes.video_test_routes import bp as video_test_bp
from routes.media_routes import bp as media_bp
from routes.docs_routes import bp as docs_bp, swagger_ui_blueprint


def register_blueprints(app: Flask):
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(user_bp, url_prefix="/api/users")
    # 토큰 주인 전용 — user_no 를 URL 로 받지 않아 권한 검사가 필요 없다
    app.register_blueprint(me_bp, url_prefix="/api/me")
    app.register_blueprint(cctv_bp, url_prefix="/api/cctvs")
    app.register_blueprint(event_bp, url_prefix="/api/events")
    app.register_blueprint(alert_bp, url_prefix="/api/alerts")
    app.register_blueprint(agency_bp, url_prefix="/api/agencies")
    # ITS 공공 CCTV 조회 — DB 가 아니라 외부 개방 데이터를 그때그때 읽어온다
    app.register_blueprint(its_bp, url_prefix="/api/its")
    app.register_blueprint(report_bp, url_prefix="/api/reports")
    app.register_blueprint(internal_bp, url_prefix="/api/internal")
    app.register_blueprint(video_test_bp, url_prefix="/api/video-tests")
    # 미디어만 /api 아래가 아니다 — media_url 값이 곧 URL 이 되도록 /media 로 붙인다
    app.register_blueprint(media_bp, url_prefix="/media")
    # API 문서 — 스펙 원본과 Swagger UI 화면
    app.register_blueprint(docs_bp, url_prefix="/api")
    app.register_blueprint(swagger_ui_blueprint(), url_prefix="/api/docs")
