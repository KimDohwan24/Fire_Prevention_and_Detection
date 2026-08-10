"""공통 에러 형식 { "code", "message" } 를 만드는 도구.

라우트에서는 ApiError 를 raise 하면 된다:
    raise ApiError(404, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")
"""
from flask import Flask, jsonify


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def register_error_handlers(app: Flask):
    @app.errorhandler(ApiError)
    def handle_api_error(e: ApiError):
        return jsonify({"code": e.code, "message": e.message}), e.status

    @app.errorhandler(404)
    def handle_404(e):
        return jsonify({"code": "NOT_FOUND", "message": "리소스를 찾을 수 없습니다."}), 404

    @app.errorhandler(405)
    def handle_405(e):
        return jsonify({"code": "METHOD_NOT_ALLOWED", "message": "허용되지 않은 메서드입니다."}), 405

    @app.errorhandler(Exception)
    def handle_500(e):
        app.logger.exception(e)
        return jsonify({"code": "INTERNAL_ERROR", "message": "서버 내부 오류가 발생했습니다."}), 500
