"""좌표 → 주소 역지오코딩 (카카오 Local API).

**언제 부르나**: CCTV 를 등록할 때 한 번. 그 결과를 cctv.cctv_address 에 저장해
두고, 신고할 때는 저장된 값을 읽기만 한다. 119 신고는 동기 경로라(alert_routes 의
respond 핸들러가 요청 스레드에서 start_report 를 끝낸다) 신고 순간에 외부 API 를
부르면 그 지연이 그대로 HTTP 응답 지연이 되고, 카카오가 죽으면 신고가 늦어진다.
카메라 좌표는 변하지 않으므로 미리 채워 두는 편이 옳다.

**왜 카카오인가**: 소셜 로그인용 REST 키(KAKAO_CLIENT_ID)를 그대로 쓸 수 있어 새
키 발급이 없다. OSM Nominatim 도 검토했으나 결과 첫머리에 POI 이름이 붙고
('Happy Plus Cafe, 110, 세종대로, …') 고속도로 지점은 번지 없이 동까지만 나와,
119 로 보내려면 문자열 가공이 따로 든다.

**선행 조건**: 카카오 개발자 콘솔에서 그 앱의 '카카오맵' 서비스가 켜져 있어야
한다. 꺼져 있으면 키가 유효해도 403 NotAuthorizedError 가 온다.

**실패는 전부 None 이다.** 예외를 밖으로 던지지 않는다 — 주소 하나 때문에 카메라
등록이 막히면 안 된다. 호출자는 None 을 받으면 주소 없이 진행한다.
"""
import logging

import requests

import config

logger = logging.getLogger("fireguard.geocode")

KAKAO_COORD2ADDRESS_URL = "https://dapi.kakao.com/v2/local/geo/coord2address.json"


def reverse_geocode(lat, lng) -> str | None:
    """좌표를 주소 문자열로 바꾼다. 실패하면 None.

    반환 우선순위: 도로명주소 → 지번주소 → None.

    도로명이 없는 것은 오류가 아니다 — 도로명주소는 건물에 부여되는 체계라
    고속도로 본선·분기점에는 애초에 없다. ITS 카메라가 대부분 그렇다.
    그러니 도로명 부재를 경고로 쌓거나 예외로 다루지 말 것.
    """
    if not config.KAKAO_CLIENT_ID:
        logger.info("KAKAO_CLIENT_ID 미설정 — 역지오코딩을 건너뛴다")
        return None

    try:
        resp = requests.get(
            KAKAO_COORD2ADDRESS_URL,
            # x 가 경도, y 가 위도다. 뒤집으면 에러 없이 엉뚱한 주소가 나온다.
            params={"x": lng, "y": lat},
            headers={"Authorization": f"KakaoAK {config.KAKAO_CLIENT_ID}"},
            timeout=config.GEOCODE_HTTP_TIMEOUT_SEC,
        )
    except requests.exceptions.RequestException as exc:
        logger.warning("역지오코딩 요청 실패 (lat=%s, lng=%s): %s", lat, lng, exc)
        return None

    if resp.status_code != 200:
        # 403 NotAuthorizedError 면 콘솔에서 '카카오맵' 서비스가 꺼진 것이다.
        logger.warning("역지오코딩 응답 %s (lat=%s, lng=%s): %s",
                       resp.status_code, lat, lng, resp.text[:200])
        return None

    try:
        documents = resp.json().get("documents") or []
    except ValueError:
        logger.warning("역지오코딩 응답이 JSON 이 아니다 (lat=%s, lng=%s)", lat, lng)
        return None

    if not documents:
        return None

    doc = documents[0]
    road = (doc.get("road_address") or {}).get("address_name")
    if road:
        return road
    return (doc.get("address") or {}).get("address_name") or None
