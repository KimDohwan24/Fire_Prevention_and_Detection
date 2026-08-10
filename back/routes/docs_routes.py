"""API 문서 서빙 — Swagger UI 와 OpenAPI 스펙 원본.

GET /api/docs/         Swagger UI 화면 (프론트가 Try it out 으로 직접 호출)
GET /api/openapi.yaml  스펙 원본 (TS 타입 생성기 입력으로 쓴다)

스펙 본문은 back/openapi.yaml 이며 손으로 관리한다.
라우트를 고쳤는데 스펙을 안 고치면 tests/test_openapi.py 가 잡아준다.
"""
from pathlib import Path

from flask import Blueprint, Response
from flask_swagger_ui import get_swaggerui_blueprint

SPEC_PATH = Path(__file__).resolve().parents[1] / "openapi.yaml"

SWAGGER_UI_URL = "/api/docs"
SPEC_URL = "/api/openapi.yaml"

bp = Blueprint("docs", __name__)


@bp.get("/openapi.yaml")
def openapi_spec():
    # 개발 중 스펙을 고치면 서버 재시작 없이 반영되도록 매번 읽는다
    return Response(
        SPEC_PATH.read_text(encoding="utf-8"),
        mimetype="application/yaml",
    )


def swagger_ui_blueprint() -> Blueprint:
    return get_swaggerui_blueprint(
        SWAGGER_UI_URL,
        SPEC_URL,
        blueprint_name="docs_ui",
        config={
            "app_name": "파이어가드 API",
            "docExpansion": "list",      # 태그는 펼치고 오퍼레이션은 접어둔다
            "defaultModelsExpandDepth": 1,
            "persistAuthorization": True,  # 새로고침해도 넣어둔 토큰이 유지된다
        },
    )
