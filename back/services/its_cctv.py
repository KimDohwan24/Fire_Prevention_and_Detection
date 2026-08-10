"""국가교통정보센터(ITS) CCTV 실시간 스트림 주소 갱신.

왜 필요한가: ITS 가 내려주는 `cctvurl` 에는 시간 제한 인증 토큰(`wmsAuthSign`)이
박혀 있다. 그래서 DB 에 저장해 둔 주소는 시간이 지나면 재생되지 않는다(만료).
카메라를 조회할 때마다 ITS 에서 최신 목록을 받아, `cctv_name` 이 정확히 같은
행의 스트림 주소를 최신 값으로 갈아끼운다.

원칙:
- **절대 예외를 밖으로 내지 않는다.** 외부 API 가 죽어도, 키가 없어도, 응답이
  이상해도 카메라 API 는 저장된 주소로 200 을 내려야 한다 (오프라인 시연 대비).
- 이름이 매칭되지 않는 행(수동 등록한 비-ITS 카메라)은 손대지 않는다.
  스키마에 "ITS 카메라 여부" 같은 플래그를 두지 않아도 이것으로 충분하다.
- 주소가 실제로 바뀐 행만 DB 에 UPDATE 한다 — AI 모델처럼 DB 를 직접 읽는
  소비자도 최신 주소를 보게 하기 위해서.
- 카메라 목록 전체를 덮는 박스(bounding box) 하나로 도로 유형당 1회만 호출하고,
  결과를 CCTV_URL_TTL_SEC 동안 캐시한다 (폴링 UI 가 매초 두드려도 안전하게).
"""
import logging
import time

import requests
import urllib3

import config
import db

logger = logging.getLogger("fireguard.its")

# 외부 API 호출 타임아웃(초) — 조회 응답을 오래 붙잡지 않도록 짧게 둔다
HTTP_TIMEOUT_SEC = 5.0

# 박스 여유(도). 좌표가 딱 경계에 걸린 카메라가 빠지지 않게 사방으로 넓혀 준다
BBOX_PADDING_DEG = 0.05

# 좌표가 하나도 없을 때 쓰는 기본 박스(대한민국 전역) — fetch_its_cctvs 직접 호출용
KOREA_BBOX = (124.0, 132.0, 33.0, 39.0)

# {(도로유형, minX, maxX, minY, maxY): (조회시각, 항목리스트)}
_cache: dict[tuple, tuple[float, list[dict]]] = {}


def clear_cache() -> None:
    """TTL 캐시를 비운다 (테스트/수동 강제 갱신용)."""
    _cache.clear()


def _get(params: dict) -> dict:
    """ITS 오픈 API 호출 — 실제 HTTP 는 이 함수에서만 나간다 (테스트 스텁 지점).

    verify=False 인 이유: openapi.its.go.kr:9443 이 내려주는 인증서 체인이
    일부 환경(사내망·특정 파이썬 인증서 번들)에서 검증에 실패한다. 공개 데이터
    조회 전용이고 우리가 보내는 민감 정보가 없어서 검증을 끄고 호출한다.
    끄면 urllib3 가 매 호출마다 경고를 찍으므로 그 경고도 함께 꺼 둔다.
    """
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    resp = requests.get(config.ITS_API_URL, params=params,
                        timeout=HTTP_TIMEOUT_SEC, verify=False)
    return resp.json()


def _extract_items(payload) -> list[dict]:
    """정상 응답에서 data 배열만 꺼낸다. 오류/이상 응답이면 ValueError.

    실제 응답에서 확인된 두 가지 정상 모양:
      - 결과 있음: {"response": {"coordtype": 1, "data": [ ... ]}}
      - 결과 0건: {"response": {"coordtype": 1, "datacount": 0}}  ← data 키가 없다
    0건은 '실패'가 아니라 '빈 결과'다. 좁은 영역을 조회하면(특히 type=its)
    흔히 나오는 정상 응답이므로 반드시 빈 리스트로 취급해야 한다.
    반면 인증키 오류처럼 response 봉투 자체가 없는 응답은 실패로 본다.
    """
    if not isinstance(payload, dict):
        raise ValueError("ITS 응답이 JSON 객체가 아님")
    response = payload.get("response")
    if not isinstance(response, dict):
        # 인증키 오류 등: {"header": {"resultCode": 4005, "resultMsg": "..."}}
        header = payload.get("header") or {}
        raise ValueError(
            f"ITS 응답 오류 (resultCode={header.get('resultCode')}, "
            f"resultMsg={header.get('resultMsg')})"
        )
    data = response.get("data")
    if data is None:
        return []  # 0건 — response 봉투가 왔으니 조회 자체는 성공이다
    if not isinstance(data, list):
        raise ValueError("ITS 응답의 data 가 배열이 아님")
    return data


def _fetch_road_type(road_type: str, bbox: tuple) -> list[dict]:
    """도로 유형 1종을 조회한다. TTL 안이면 캐시된 결과를 그대로 쓴다."""
    min_x, max_x, min_y, max_y = bbox
    key = (road_type, round(min_x, 4), round(max_x, 4),
           round(min_y, 4), round(max_y, 4))

    now = time.monotonic()
    cached = _cache.get(key)
    if cached and (now - cached[0]) < config.CCTV_URL_TTL_SEC:
        return cached[1]

    items = _extract_items(_get({
        "apiKey": config.CCTV_API_KEY,
        "type": road_type,      # ex=고속도로, its=국도
        "cctvType": 1,          # 1 = 실시간 스트리밍(HLS)
        "minX": f"{min_x:.6f}",
        "maxX": f"{max_x:.6f}",
        "minY": f"{min_y:.6f}",
        "maxY": f"{max_y:.6f}",
        "getType": "json",
    }))
    # 성공한 결과만 캐시한다 — 실패를 '0건 성공'으로 캐시하면 일시적 오류 한 번에
    # TTL(기본 5분) 내내 갱신이 죽는다. 예외는 위에서 이미 빠져나갔다.
    _cache[key] = (now, items)
    return items


def fetch_its_cctvs(bbox: tuple | None = None) -> list[dict]:
    """설정된 도로 유형(ITS_ROAD_TYPES) 전체를 조회해 원본 항목을 합쳐 돌려준다.

    bbox: (minX, maxX, minY, maxY) = (최소경도, 최대경도, 최소위도, 최대위도).

    도로 유형별로 격리한다 — 한 유형(예: 국도)이 실패해도 성공한 유형(고속도로)의
    결과는 그대로 쓴다. 모든 유형이 실패했을 때만 예외를 올린다
    (잡는 쪽은 refresh_stream_urls → 저장된 주소로 폴백).
    """
    bbox = bbox or KOREA_BBOX
    road_types = config.ITS_ROAD_TYPES
    merged: list[dict] = []
    failed: list[str] = []
    for road_type in road_types:
        try:
            merged.extend(_fetch_road_type(road_type, bbox))
        except Exception as exc:
            failed.append(road_type)
            logger.warning("ITS 조회 실패 — 도로 유형 %s 건너뜀: %s", road_type, exc)

    if failed and len(failed) == len(road_types):
        raise RuntimeError(f"ITS 조회 전부 실패 (도로 유형: {', '.join(failed)})")
    return merged


def _bbox_of(rows: list[dict]) -> tuple | None:
    """카메라 행 전체를 덮는 박스를 만든다. 좌표가 NULL 인 행은 건너뛴다."""
    lats: list[float] = []
    lngs: list[float] = []
    for row in rows:
        lat, lng = row.get("cctv_lat"), row.get("cctv_lng")
        if lat is None or lng is None:
            continue
        lats.append(float(lat))
        lngs.append(float(lng))
    if not lats:
        return None
    pad = BBOX_PADDING_DEG
    return (min(lngs) - pad, max(lngs) + pad, min(lats) - pad, max(lats) + pad)


def refresh_stream_urls(rows: list[dict]) -> list[dict]:
    """카메라 행들의 cctv_stream_url 을 ITS 최신 주소로 갱신해 돌려준다 (진입점).

    - 입력 행은 건드리지 않고 복사본을 돌려준다.
    - 매칭 기준은 cctv_name 완전 일치. 매칭 안 되면 저장된 주소 그대로.
    - 주소가 바뀐 행은 DB 에도 반영한다.
    - 어떤 실패든 로그만 남기고 '저장된 주소 그대로'로 폴백한다.
    """
    result = [dict(row) for row in rows]
    if not result:
        return result

    if not config.ITS_REFRESH_ENABLED:
        return result
    if not config.CCTV_API_KEY:
        logger.debug("CCTV_API_KEY 미설정 — 스트림 주소 갱신 건너뜀")
        return result

    bbox = _bbox_of(result)
    if bbox is None:
        logger.debug("좌표가 있는 카메라 없음 — 스트림 주소 갱신 건너뜀")
        return result

    try:
        # 이름 → 최신 주소 (같은 이름이 여러 개면 먼저 온 것을 쓴다)
        by_name: dict[str, str] = {}
        for item in fetch_its_cctvs(bbox):
            name = (item.get("cctvname") or "").strip()
            url = item.get("cctvurl")
            if name and url:
                by_name.setdefault(name, url)

        for row in result:
            fresh = by_name.get((row.get("cctv_name") or "").strip())
            if not fresh or fresh == row.get("cctv_stream_url"):
                continue  # 매칭 없음 또는 그대로 — UPDATE 하지 않는다
            row["cctv_stream_url"] = fresh
            if row.get("cctv_no") is not None:
                db.execute(
                    "UPDATE cctv SET cctv_stream_url = %s WHERE cctv_no = %s",
                    (fresh, row["cctv_no"]),
                )
                logger.info("스트림 주소 갱신 (cctv_no=%s, name=%s)",
                            row["cctv_no"], row.get("cctv_name"))
    except Exception:
        # 네트워크·인증키·응답형식·DB 무엇이 터져도 조회 API 는 살아 있어야 한다
        logger.exception("ITS 스트림 주소 갱신 실패 — 저장된 주소로 응답한다")
        return [dict(row) for row in rows]

    return result
