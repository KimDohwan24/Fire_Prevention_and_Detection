"""소방 시설(IF_0038) -> agency 테이블 적재 (일회성 · 재실행 안전)

**무엇을 하나**
    생활안전지도(safemap.go.kr)가 공개하는 전국 소방시설 목록을 받아,
    그중 소방서만 골라 fireguard DB 의 agency 표에 넣는다.
    이름·좌표뿐 아니라 주소·전화번호와 출처 고유번호까지 함께 저장한다.

**왜 앱 안이 아니라 따로 실행하는 파일인가**
    이 데이터는 갱신주기가 1년이다. 요청마다 외부 API 를 부를 이유가 없다.
    게다가 119 신고는 동기 경로다 — alert_routes 의 respond 핸들러가 요청 스레드
    안에서 report_service.start_report 를 끝낸다. 그 경로에서 외부 API 를 부르면
    그 지연이 그대로 사용자 응답 지연이 된다. 그래서 미리 받아 DB 에 넣어 두고
    앱은 DB 만 읽는다. services/geocode.py 가 CCTV 등록 때 한 번만 역지오코딩하고
    신고 때는 저장된 주소를 읽기만 하는 것과 같은 판단이다.

**좌표 주의 — 이 파일에서 제일 중요한 부분**
    응답의 x/y 는 위도·경도가 아니라 EPSG:3857(웹 메르카토르) 미터 값이다.
        x=14166076.3786, y=4439165.18531  ->  위도 37.0004190, 경도 127.2560293
                                              (= 경기도 안성시 미양로 855, 안성소방서)
    그대로 넣으면 agency_lat 이 numeric(10,7) 이라 저장 자체가 실패하고,
    설령 들어가도 지구상에 없는 지점이 된다. to_wgs84() 가 이걸 환산한다.

**대조 열쇠는 이름이 아니라 출처 고유번호(objt_id)다 — 2026-08-21 실측 근거**
    전국 소방서 235건 중 서로 다른 이름은 214개뿐이다. 같은 이름이 여러 지역에
    실재한다: 중부소방서 5곳(대구·울산·인천·서울·부산), 서부소방서 5곳(제주·대전·
    대구·인천·광주), 동부 5 · 북부 4 · 남부 3 · 강서 3 · 강북 2 · 고성 2.
    이름으로 대조하면 이 21건이 서로를 덮어써 사라진다. 그래서 마이그레이션 008 로
    agency_source_id 컬럼(+ 부분 유니크 인덱스)을 두고 그 값으로 기존 행을 찾는다.
    출처가 기관 이름을 바꿔도 같은 행을 계속 따라간다는 이점도 있다.

**인증키**
    루트 .env 의 `AGENCY` 항목에서 온다 (config.SAFEMAP_SERVICE_KEY 가 그 이름으로
    읽는다). 주석(`# AGENCY=...`)으로 두면 읽히지 않으니 주의.

**선행 조건**
    db/migrations/008-2026-08-21-agency-source-address-phone.sql 이 적용돼 있어야
    한다. 안 되어 있으면 첫 조회에서 'column agency_source_id does not exist' 로
    멈춘다 — 그때는 마이그레이션부터 돌리면 된다.

실행:
    cd back
    .venv/Scripts/python services/agencies_safemap.py --dry-run       # DB 안 건드리고 확인만
    .venv/Scripts/python services/agencies_safemap.py                 # 실제 저장
    .venv/Scripts/python services/agencies_safemap.py --with-centers  # 119안전센터까지 포함
"""
import math
import sys
from pathlib import Path

# 이 파일을 `python services/agencies_safemap.py` 로 직접 실행하면 파이썬은
# services/ 폴더만 모듈 검색 경로에 올린다. config·db 는 그 한 층 위(back/)에
# 평평하게 놓인 모듈이라 이 줄이 없으면 import 가 실패한다.
# parents[0] 이 services, parents[1] 이 back 이다. (parent 는 한 칸 위 하나뿐이라
# 번호를 붙일 수 없다 — parents 로 써야 한다.)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 윈도우 콘솔 기본 인코딩(cp949)은 일부 문자를 못 써서 출력하는 순간 죽는다.
# 진행 로그가 전부 한글이므로 출력 인코딩을 UTF-8 로 고정한다
# (scripts/backfill_cctv_address.py 와 같은 이유).
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests  # noqa: E402

# config 가 임포트되는 순간 루트 .env 를 읽는다(config.py 의 load_dotenv).
# 그래서 여기서 dotenv 를 따로 부를 필요가 없다 — 두 번 읽어도 결과는 같지만,
# 키를 어디서 읽는지가 두 곳으로 갈리면 나중에 값이 안 맞을 때 원인을 찾기 어렵다.
import config  # noqa: E402
import db  # noqa: E402

# ---------------------------------------------------------------------------
# 설정값 — 바꿀 만한 것은 전부 여기 모은다
# ---------------------------------------------------------------------------

# 한 번에 몇 건씩 받을지. safemap 은 전국 데이터를 페이지로 나눠 준다.
# 실측(2026-08-21): 전체 2136건이라 1000이면 3페이지에 끝난다.
PAGE_SIZE = 1000

# 시설 종류 코드. 데이터에는 소방서·119안전센터·소방기타가 섞여 있다.
FIRE_STATION = "511010"   # 소방서 (실측 235건)
SAFETY_CENTER = "511020"  # 119안전센터 (나머지 대부분)

# 기본은 소방서만 넣는다. 안전센터까지 넣으면 기관이 수백 개로 불어나고,
# PostGIS 최근접 기관 탐색이 소방서 대신 안전센터를 고를 수 있다.
ONLY = {FIRE_STATION}
if "--with-centers" in sys.argv:
    ONLY.add(SAFETY_CENTER)

# 119 신고를 실제로 쏘는 주소. safemap 데이터에는 없는 값이라 우리가 채운다.
# localhost 대신 127.0.0.1 인 이유: 윈도우에서 localhost 는 IPv6 를 먼저 시도하다
# 연결에만 2초를 까먹어, 신고 타임아웃(기본 3초)을 거의 다 잡아먹는다.
DEFAULT_ENDPOINT = "http://127.0.0.1:8119/report?mode=ok"

# 연습 모드. 붙여서 실행하면 DB 에 아무것도 쓰지 않고 결과만 보여준다.
# 처음 돌릴 때 데이터가 예상과 달라도 장부가 더러워지지 않는다.
DRY_RUN = "--dry-run" in sys.argv

# 외부 호출 타임아웃(초). 사람이 화면 앞에서 기다리는 요청 경로가 아니라
# 일회성 배치라 신고 경로(3초)보다 넉넉하게 둔다.
HTTP_TIMEOUT_SEC = 10


def to_wgs84(x, y):
    """EPSG:3857(Web Mercator) -> WGS84 위경도. safemap 의 x/y 는 위경도가 아니다.

    경도는 x 에 선형 비례한다. 20037508.342789244 는 파이 × 지구반지름(6378137m),
    즉 이 평면에서 경도 180도에 해당하는 x 값이다.

    위도는 선형이 아니다. 메르카토르가 고위도를 늘려 그리기 때문에(세계지도에서
    그린란드가 아프리카만 하게 나오는 그 현상), 되돌리려면 그 늘림을 푸는
    역함수 계산이 필요하다. 두 줄이면 끝나므로 pyproj 같은 지오 라이브러리를
    의존성에 더하지 않는다.

    입력이 문자열로 온다 — 응답 항목 타입이 전부 STRING 이라 float() 없이는
    나눗셈에서 TypeError 가 난다.

    돌려주는 순서는 (위도, 경도)다. safemap 은 x(경도)를 먼저 주지만 우리 DB 는
    lat 을 먼저 쓴다. 뒤바뀌면 에러 없이 전 기관이 엉뚱한 곳에 찍힌다.

    소수점 7자리에서 끊는 이유는 agency_lat/lng 가 numeric(10,7) 이라 어차피
    그 이상은 저장되지 않기 때문이다 (7자리면 약 1cm 정밀도).
    """
    lon = float(x) / 20037508.342789244 * 180.0
    lat = math.degrees(2 * math.atan(math.exp(float(y) / 6378137.0)) - math.pi / 2)
    return round(lat, 7), round(lon, 7)


def fetch(page):
    """safemap 에서 한 페이지를 받아 소방시설 목록만 꺼내 돌려준다.

    returnType 을 명시하는 이유: safemap 문서가 자기모순이다. 요청변수 표에는
    'Default : JSON', 바로 아래 자바 예제 주석에는 'xml(기본값)' 이라 적혀 있다.
    어느 쪽이 진짜인지 모르니 기본값에 기대지 않는다. (철자도 주의 — returnType
    이다. retunType 처럼 틀리면 safemap 이 그 조건을 무시한 채 응답한다.)

    timeout 이 없으면 상대가 침묵할 때 아무 메시지 없이 영원히 매달린다.
    raise_for_status() 는 인증 실패 같은 응답을 데이터로 착각해 한참 뒤 엉뚱한
    곳에서 죽는 대신, 실패한 자리에서 바로 멈추게 한다.

    resp.json() 은 괄호가 있어야 실제로 변환이 일어난다. 괄호 없이 resp.json 이라
    쓰면 '변환하는 기능 그 자체'를 가리킬 뿐이라 다음 줄에서 AttributeError 가 난다.

    아래 세 줄(껍데기 벗기기)은 실제 응답으로 확인했다(2026-08-21) —
    response → body → items → item 구조가 맞다. 마지막 줄은 결과가 1건일 때
    item 이 목록이 아니라 낱개로 오는 흔한 함정에 대비한 것이다.
    """
    resp = requests.get(
        config.SAFEMAP_API_URL,
        params={
            "serviceKey": config.SAFEMAP_SERVICE_KEY,
            "pageNo": page,
            "numOfRows": PAGE_SIZE,
            "returnType": "json",
        },
        timeout=HTTP_TIMEOUT_SEC,
    )
    resp.raise_for_status()

    payload = resp.json()
    body = payload.get("response", payload).get("body", payload)
    items = body.get("items", [])
    return items.get("item", []) if isinstance(items, dict) else items


def collect():
    """전 페이지를 돌며 쓸 수 있는 행만 모아 돌려준다. -> (목록, 버린 수, 중복 수)

    페이지마다 바로 저장하지 않고 일단 다 모으는 이유는 고유번호 중복을 미리
    걸러내기 위해서다. 같은 objt_id 가 두 번 오면 UX_agency_source_id 유니크
    인덱스에 걸려 적재 도중에 죽는다 — 절반만 들어간 상태로 멈추는 것보다
    시작 전에 걸러내는 편이 낫다. 소방서만 추리면 235건이라 메모리는 문제없다.
    """
    rows = {}       # 고유번호 -> 행. 딕셔너리라 같은 번호가 다시 오면 자연히 하나만 남는다
    skipped = 0     # 소방서가 아니거나 값이 빠진 행
    duplicated = 0  # 고유번호가 겹쳐 버린 행
    page = 1

    # 전국에 몇 건인지 미리 모르므로 '빈손이 올 때까지' 반복한다.
    while True:
        items = fetch(page)
        if not items:
            break

        for it in items:
            # 소방서가 아니면 버린다 (119안전센터·소방기타).
            if it.get("fclty_cd") not in ONLY:
                skipped += 1
                continue
            # 좌표가 빈 행이 섞여 있다. 그대로 환산하면 죽으므로 걸러낸다.
            if not it.get("x") or not it.get("y"):
                skipped += 1
                continue
            # 고유번호가 없으면 대조할 열쇠가 없다 — 넣어 봐야 다음 실행 때
            # 같은 기관인지 알 수 없어 중복만 쌓인다.
            source_id = str(it.get("objt_id") or "").strip()
            if not source_id:
                skipped += 1
                continue

            if source_id in rows:
                duplicated += 1
                continue
            rows[source_id] = it

        # 요청한 개수보다 적게 왔으면 마지막 페이지다. totalCount 를 쓰지 않는 것은
        # 이 조건이 응답 껍데기 구조와 무관하게 항상 성립하기 때문이다.
        if len(items) < PAGE_SIZE:
            break
        page += 1

    return rows, skipped, duplicated


def upsert(source_id, name, lat, lng, address, phone):
    """출처 고유번호로 대조해 있으면 갱신, 없으면 새로 넣는다.

    돌려주는 값은 "신규" 또는 "갱신" — 부른 쪽에서 세고 화면에 찍는 데 쓴다.

    **이름이 아니라 agency_source_id 로 찾는다.** 같은 이름의 소방서가 전국에
    여럿이라(파일 머리말 참고) 이름으로 찾으면 서로를 덮어쓴다. 고유번호로 찾으면
    이름이 겹쳐도 각자 다른 행으로 남고, 출처가 개명해도 같은 행을 따라간다.

    ON CONFLICT 를 쓰지 않는 이유: 유니크 인덱스가 부분 인덱스(WHERE ... IS NOT
    NULL)라 추론이 애매하고, 여기서는 신규·갱신을 세어 화면에 알려 줘야 해서
    어느 쪽이었는지 알아야 한다.

    갱신할 때 이름·주소·전화까지 함께 덮는 것은 의도적이다 — 출처가 고친 값을
    받아 오는 것이 이 스크립트의 목적이다. 다만 **agency_endpoint 는 건드리지
    않는다.** 그건 우리가 시연용으로 정한 값이라(mock-119 의 ?mode=fail /
    ?mode=ok 승계 시연) 덮으면 맞춰 둔 설정이 날아간다.

    SQL 의 %s 는 값이 들어갈 빈칸이고 실제 값은 뒤에 따로 넘긴다. 문자열을 직접
    이어붙이면 이름에 든 따옴표에 문장이 깨지고 SQL 인젝션에도 열린다.
    """
    row = db.query_one(
        "SELECT agency_no FROM agency WHERE agency_source_id = %s", (source_id,)
    )

    # 연습 모드에서는 조회까지만 하고 쓰기는 건너뛴다.
    if DRY_RUN:
        return "갱신" if row else "신규"

    if row:
        db.execute(
            """
            UPDATE agency
               SET agency_name    = %s,
                   agency_lat     = %s,
                   agency_lng     = %s,
                   agency_address = %s,
                   agency_phone   = %s
             WHERE agency_no = %s
            """,
            (name, lat, lng, address, phone, row["agency_no"]),
        )
        return "갱신"

    db.execute(
        """
        INSERT INTO agency (agency_source_id, agency_name, agency_lat, agency_lng,
                            agency_address, agency_phone, agency_endpoint)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (source_id, name, lat, lng, address, phone, DEFAULT_ENDPOINT),
    )
    return "신규"


def main() -> int:
    # 키가 없으면 여기서 끝낸다. 이 확인이 없으면 한참 뒤 인증 실패 응답만 보고
    # 원인을 찾아 헤매게 된다.
    if not config.SAFEMAP_SERVICE_KEY:
        print("인증키가 없다 — 루트 .env 에 `AGENCY=발급받은키` 를 넣고 다시 실행할 것")
        print("(주석 처리된 `# AGENCY=...` 는 읽히지 않는다)")
        return 1

    print(f"대상 시설코드: {sorted(ONLY)}"
          + (" · 연습 모드(--dry-run): DB 는 건드리지 않는다" if DRY_RUN else ""))

    # 1단계 — 전국 데이터를 다 받아 쓸 수 있는 행만 모은다
    rows, skipped, duplicated = collect()
    print(f"수집 {len(rows)}건 · 건너뜀 {skipped}건(안전센터·소방기타·값 빠진 행)"
          + (f" · 고유번호 중복 {duplicated}건" if duplicated else ""))

    # 2단계 — 한 건씩 저장한다
    new = updated = 0
    for source_id, it in rows.items():
        name = it.get("fclty_nm")
        lat, lng = to_wgs84(it["x"], it["y"])
        # 주소는 도로명이 우선이다. 없는 곳이 있어 지번으로 물러선다.
        # 값이 없을 때 '-' 를 그대로 넣지 않도록 걸러 낸다 — DB 에는 NULL 이 맞다.
        address = (it.get("rn_adres") or it.get("adres") or "").strip() or None
        if address == "-":
            address = None
        phone = (it.get("telno") or "").strip() or None

        how = upsert(source_id, name, lat, lng, address, phone)
        if how == "신규":
            new += 1
        else:
            updated += 1

        # 한 건마다 한 줄씩 찍는다 — 수백 건이 도는 동안 화면이 조용하면
        # 진행 중인지 멈춘 것인지 구분할 수 없다.
        print(f"  [{how}] {name}  {lat}, {lng}  {address or '주소없음'}")

    tail = " (--dry-run 이라 DB 는 건드리지 않았다)" if DRY_RUN else ""
    print(f"완료: 신규 {new}건 · 갱신 {updated}건{tail}")
    return 0


# 이 파일을 직접 실행했을 때만 main 이 돈다. 다른 모듈이 to_wgs84 같은 함수만
# 빌려 쓰려고 import 할 때 전국 데이터를 긁어오는 일이 벌어지면 안 된다.
if __name__ == "__main__":
    raise SystemExit(main())
