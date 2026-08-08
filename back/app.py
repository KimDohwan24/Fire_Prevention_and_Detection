"""파이어가드 백엔드 진입점.

실행:
    cd back
    python app.py        # http://localhost:5000
"""
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


def create_app() -> Flask:
    app = Flask(__name__)
    app.json = ApiJSONProvider(app)
    app.json.ensure_ascii = False  # 한글 메시지를 그대로 내보낸다

    CORS(app)  # 개발용: 모든 오리진 허용. 배포 시 프론트 도메인으로 제한할 것.

    register_error_handlers(app)
    register_blueprints(app)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=config.APP_PORT, debug=True)
