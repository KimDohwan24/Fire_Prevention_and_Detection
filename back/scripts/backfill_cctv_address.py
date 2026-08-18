"""cctv_address 가 비어 있는 카메라를 역지오코딩으로 메운다 (일회성 · 재실행 안전).

cctv_address 컬럼은 나중에 추가됐으므로, 그 전에 등록된 카메라는 값이 없다.
등록 경로(routes/cctv_routes.create_cctv)는 앞으로 들어오는 것만 채우니 과거분은
이 스크립트로 한 번 메운다. 마이그레이션 007 의 후속 작업이다.

대상은 `cctv_address IS NULL` 이고 좌표가 있는 행뿐이라 몇 번을 돌려도 같다.
실패(주소를 못 구함)한 행은 NULL 로 남으므로 다음 실행이 다시 시도한다.

실행:
    cd back
    .venv/Scripts/python scripts/backfill_cctv_address.py
"""
import sys
from pathlib import Path

# scripts/ 에서 실행해도 back/ 의 config·db 를 찾게 한다 (패키지가 아니라 평평한
# 모듈들이라 back/ 자체가 import 경로에 있어야 한다).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Windows 콘솔 기본 인코딩(cp949)은 일부 문자(—)를 못 써서 출력 즉시 죽는다.
# 로그가 전부 한글이므로 출력 인코딩을 UTF-8 로 고정한다 (mock-119/app.py 와 같은 이유).
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import db  # noqa: E402
from services import geocode  # noqa: E402


def main() -> int:
    rows = db.query(
        """
        SELECT cctv_no, cctv_name, cctv_lat, cctv_lng
          FROM cctv
         WHERE cctv_address IS NULL
           AND cctv_lat IS NOT NULL
           AND cctv_lng IS NOT NULL
         ORDER BY cctv_no
        """
    )
    if not rows:
        print("채울 카메라가 없다 (cctv_address 가 비고 좌표가 있는 행 0건).")
        return 0

    print(f"대상 {len(rows)}건")
    filled = failed = 0
    for row in rows:
        address = geocode.reverse_geocode(row["cctv_lat"], row["cctv_lng"])
        if not address:
            failed += 1
            print(f"  [실패] cctv_no={row['cctv_no']} {row['cctv_name']} "
                  f"({row['cctv_lat']}, {row['cctv_lng']}) — 주소를 못 구했다")
            continue
        db.execute("UPDATE cctv SET cctv_address = %s WHERE cctv_no = %s",
                   (address, row["cctv_no"]))
        filled += 1
        print(f"  [채움] cctv_no={row['cctv_no']} {row['cctv_name']} → {address}")

    print(f"완료: 채움 {filled}건 · 실패 {failed}건")
    if failed:
        # 키가 유효해도 '카카오맵' 서비스가 꺼져 있으면 403 이 오고 전 건이 실패한다.
        # 가장 흔한 원인이라 실패가 있을 때만 짚어 준다.
        print("실패가 있으면 카카오 개발자 콘솔에서 그 앱의 '카카오맵' 서비스가 "
              "켜져 있는지 확인할 것 (꺼져 있으면 403).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
