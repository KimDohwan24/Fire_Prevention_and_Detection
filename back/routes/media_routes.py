"""미디어 파일 서빙 — 검출 프레임(FRAME).

GET /media/<path:filename>   config.MEDIA_ROOT 아래의 파일을 그대로 내려준다.

event_media.media_url 에는 "/media/events/12/frame_001.jpg" 형태로 저장되므로,
프론트는 API 응답의 media_url / thumbnail_url 값을 <img src> 에 그대로 넣으면 된다.

인증을 걸지 않는 이유 (의도된 시연 범위의 결정):
브라우저의 <img>/<video> 태그는 Authorization 헤더를 붙일 수 없어서 JWT 를 요구하면
화면에 이미지가 뜨지 않는다. 우회책인 서명 URL(signed URL)은 이 프로젝트 범위 밖이다.
운영 환경이라면 (1) 만료 시간이 든 서명 URL 을 발급하거나 (2) nginx 같은 리버스
프록시에서 인증 후 내부 리다이렉트(X-Accel-Redirect)로 넘기는 방식을 써야 한다.
"""
from flask import Blueprint, send_from_directory

import config

bp = Blueprint("media", __name__)


@bp.get("/<path:filename>")
def serve_media(filename: str):
    """MEDIA_ROOT 안의 파일만 내려준다.

    send_from_directory 가 안전한 경로 결합(safe_join)을 해주므로
    ../ 나 절대경로로 루트 바깥을 노리는 요청은 404 로 막힌다.
    없는 파일도 404 (공통 에러 핸들러가 {code, message} 형식으로 만들어 준다).

    config.MEDIA_ROOT 를 모듈 로드 시점이 아니라 요청 시점에 읽는다 —
    테스트에서 임시 디렉터리로 갈아끼울 수 있어야 하기 때문.
    """
    return send_from_directory(config.MEDIA_ROOT, filename)
