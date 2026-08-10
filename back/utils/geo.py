"""지리 좌표 유틸리티."""
import math

# 지구 평균 반지름 (km)
_EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 위경도 좌표 사이의 대권 거리(km)를 하버사인 공식으로 계산한다.

    입력은 십진수 도(degree) 단위. 순수 함수 — 외부 상태 없음.
    """
    rlat1, rlng1, rlat2, rlng2 = map(math.radians, (lat1, lng1, lat2, lng2))
    dlat = rlat2 - rlat1
    dlng = rlng2 - rlng1
    a = (math.sin(dlat / 2) ** 2
         + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2)
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))
