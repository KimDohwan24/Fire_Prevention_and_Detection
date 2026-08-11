"""mock-119 — 119 소방청 접수 서버 모의(Mock).

백엔드(back/)의 report_service 가 신고를 POST 하는 상대방 역할을 한다.
승계(takeover) 시나리오를 라이브로 시연하기 위한 데모/테스트 전용 서버.

실행 방법 (별도 requirements 없음 — back/.venv 를 그대로 재사용한다):

    cd mock-119
    ../back/.venv/Scripts/python app.py            # 기본 포트 6000

환경변수:
    MOCK119_PORT          리스닝 포트 (기본 6000)
    MOCK119_DEFAULT_MODE  mode 쿼리 파라미터가 없을 때의 기본 동작 (기본 "ok")
    MOCK119_SLEEP_SEC     mode=timeout 일 때 잠드는 초 (기본 10)

중복 접수 방지:
    백엔드는 신고마다 `report_uid`(화재 하나에 하나)를 실어 보낸다. 재전송이든
    기관 승계든 같은 값이다. 이 서버는 접수한 uid 를 기억해 두고, 같은 uid 가
    다시 오면 **새로 접수하지 않고 먼저 발급한 접수번호만 다시 알려준다**.
    3초 타임아웃 뒤의 재전송 4회가 출동 4건이 되는 것을 막는 장치다.

    실제로는 소방서마다 서버가 따로 있으므로 중복 검사도 서버별이다.
    이 데모는 한 프로세스로 여러 소방서를 흉내내야 해서 `station` 쿼리
    파라미터로 구분한다 — station 이 다르면 같은 uid 라도 별개로 접수된다.

    ⚠️ report_uid 는 event_no 에서 만들어진다. DB 를 초기화하면 event_no 가
    1 부터 다시 시작해서 이전 세션의 uid 와 겹치고, 새 화재가 중복으로 처리된다.
    **DB 를 초기화하면 이 서버도 같이 재시작할 것** (접수 대장은 메모리다).

API:
    POST /report?mode=<mode>&station=<id>   신고 접수
        mode: 쿼리 파라미터가 환경변수보다 우선
        mode=ok      → 200 {"external_id": "R-000001", "status": "접수"}
        mode=timeout → MOCK119_SLEEP_SEC 초 대기 후 200
                       (백엔드는 3초에 타임아웃 → 무응답 시뮬레이션)
        mode=fail    → 500 {"error": "system unavailable"}  (시스템 장애)
        mode=reject  → 400 {"error": "invalid report"}      (접수 거절)
        station: 소방서 구분 (기본 "1"). 중복 접수 검사의 범위다.
      이미 접수한 report_uid 가 같은 station 으로 다시 오면
        → 200 {"external_id": <먼저 발급한 번호>, "status": "접수", "duplicate": true}
    GET  /reports              이번 세션에 수신한 요청 전체 목록 (메모리, 디버그용)
                               재전송도 전부 남고 duplicate 플래그로 구분된다
    GET  /health               {"status": "ok"}

두 기관 승계(승계 시연) 데모:
    1. 이 서버를 한 개 띄운다 (포트 6000).
    2. DB agency 테이블에서 기관 1 endpoint 를
       'http://localhost:6000/report?mode=timeout&station=1' (또는 mode=fail),
       기관 2 endpoint 를 'http://localhost:6000/report?mode=ok&station=2' 로 설정한다.
    3. 백엔드에서 신고를 트리거하면: 기관 1은 4회 시도 모두 실패(NO_RESPONSE)
       → 기관 2로 승계되어 접수(ACCEPTED). 이 서버 콘솔에서 수신 로그로 확인한다.
       mode=timeout 이면 기관 1도 실제로는 접수하므로, GET /reports 에서
       기관 1 수신 4건 중 1건만 접수이고 나머지는 duplicate 인 것을 보여줄 수 있다.
"""
import itertools
import os
import sys
import time
from datetime import datetime

from flask import Flask, jsonify, request

# Windows 콘솔 기본 인코딩(cp949)은 일부 문자(—)를 못 써서 기동 즉시 죽는다.
# 로그가 전부 한글이므로 출력 인코딩을 UTF-8 로 고정한다.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

app = Flask(__name__)

# 이번 세션에 수신한 요청 목록 (메모리 보관 — 서버 재시작 시 초기화).
# 재전송도 전부 남는다. 접수된 것만 보려면 duplicate 가 False 인 것을 세면 된다.
RECEIVED: list[dict] = []
# 접수번호 시퀀스: R-000001, R-000002, ...
_SEQ = itertools.count(1)
# 접수 대장: (station, report_uid) → 발급한 접수번호.
# 소방서마다 서버가 따로인 현실을 한 프로세스로 흉내내야 해서 station 을 키에 넣는다.
_LEDGER: dict[tuple[str, str], str] = {}


def _accept(station: str, uid: str | None) -> tuple[str, bool]:
    """접수번호를 돌려준다. 이미 접수한 uid 면 먼저 발급한 번호를 그대로 준다.

    반환: (접수번호, 중복인가). uid 가 없는 요청(구버전 백엔드)은 중복 검사 없이
    매번 새로 접수한다 — 검사할 근거가 없으면 접수하는 쪽이 안전하다.
    """
    if uid is None:
        return f"R-{next(_SEQ):06d}", False
    key = (station, uid)
    if key in _LEDGER:
        return _LEDGER[key], True
    external_id = f"R-{next(_SEQ):06d}"
    _LEDGER[key] = external_id
    return external_id, False


@app.post("/report")
def report():
    """신고 접수 엔드포인트 — mode 에 따라 성공/무응답/장애/거절을 시뮬레이션한다."""
    payload = request.get_json(silent=True) or {}
    mode = request.args.get("mode") or os.environ.get("MOCK119_DEFAULT_MODE", "ok")
    station = request.args.get("station", "1")
    uid = payload.get("report_uid")
    now = datetime.now().isoformat(timespec="seconds")

    # 수신 로그 (데모: "신고가 도착했다"를 콘솔에서 보여주는 부분)
    print(f"[mock-119] 신고 수신 | 수신 시각={now} | station={station} | mode={mode} "
          f"| 신고ID={uid} "
          f"| event_no={payload.get('event_no')} "
          f"| 주소={payload.get('address')} "
          f"| 분류={payload.get('event_class')} "
          f"| 신뢰도={payload.get('confidence')}",
          flush=True)

    entry = {"received_at": now, "mode": mode, "station": station, **payload}
    RECEIVED.append(entry)

    if mode == "fail":
        print("[mock-119] mode=fail — 500 반환 (시스템 장애 시뮬레이션)", flush=True)
        return jsonify({"error": "system unavailable"}), 500

    if mode == "reject":
        print("[mock-119] mode=reject — 400 반환 (접수 거절 시뮬레이션)", flush=True)
        return jsonify({"error": "invalid report"}), 400

    # 여기서부터는 접수하는 경로 (ok / timeout). timeout 도 결국 200 을 주므로
    # 실제로는 접수된 것이다 — 백엔드가 먼저 끊었을 뿐이다. 그래서 대장에 올린다.
    external_id, duplicate = _accept(station, uid)
    entry["external_id"] = external_id
    entry["duplicate"] = duplicate

    if mode == "timeout":
        # 백엔드 타임아웃(3초)보다 오래 잠들어 '무응답 기관'을 흉내낸다
        sleep_sec = float(os.environ.get("MOCK119_SLEEP_SEC", "10"))
        print(f"[mock-119] mode=timeout — {sleep_sec}초 대기 (백엔드는 먼저 타임아웃)",
              flush=True)
        time.sleep(sleep_sec)

    if duplicate:
        print(f"[mock-119] 중복 신고 ID {uid} — 새로 접수하지 않고 "
              f"접수번호 {external_id} 재발신", flush=True)
        return jsonify({"external_id": external_id, "status": "접수",
                        "duplicate": True}), 200

    print(f"[mock-119] 접수 완료 — 접수번호 {external_id}", flush=True)
    return jsonify({"external_id": external_id, "status": "접수"}), 200


@app.get("/reports")
def list_reports():
    """이번 세션에 수신한 신고 전체 목록 (데모/디버그용)."""
    return jsonify(RECEIVED)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("MOCK119_PORT", "6000"))
    print(f"[mock-119] 소방청 모의 서버 기동 — http://localhost:{port} "
          f"(기본 mode={os.environ.get('MOCK119_DEFAULT_MODE', 'ok')})", flush=True)
    # 리로더 없이 단일 프로세스로 실행 (테스트가 subprocess.terminate 로 종료한다)
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
