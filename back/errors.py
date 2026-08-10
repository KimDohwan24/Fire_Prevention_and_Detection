"""공통 에러 형식 { "code", "message" } 를 만드는 도구.

라우트에서는 ApiError 를 raise 하면 된다:
    raise ApiError(404, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")

검증 실패(400)는 어느 입력 때문인지 field 로 함께 알려준다:
    raise ApiError(400, "BAD_REQUEST", "user_pw 는 필수입니다.", field="user_pw")

400 은 code 가 전부 BAD_REQUEST 하나라, field 가 없으면 프론트는 폼의 어느
칸에 메시지를 붙일지 정하려고 한글 문구를 파싱해야 한다. field 는 값이 있을
때만 응답에 실리므로 기존 { code, message } 형식과 하위 호환이다.
"""
from flask import Flask, jsonify


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, field: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.field = field


def register_error_handlers(app: Flask):
    @app.errorhandler(ApiError)
    def handle_api_error(e: ApiError):
        body = {"code": e.code, "message": e.message}
        if e.field:
            body["field"] = e.field
        return jsonify(body), e.status

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
