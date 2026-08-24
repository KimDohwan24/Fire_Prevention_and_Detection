"""mock-119 — 119 소방청 접수 서버 모의(Mock).

백엔드(back/)의 report_service 가 신고를 POST 하는 상대방 역할을 한다.
승계(takeover) 시나리오를 라이브로 시연하기 위한 데모/테스트 전용 서버.

실행 방법 (별도 requirements 없음 — back/.venv 를 그대로 재사용한다):

    cd mock-119
    ../back/.venv/Scripts/python app.py            # 기본 포트 8119

환경변수:
    MOCK119_PORT          리스닝 포트 (기본 8119)
    MOCK119_DEFAULT_MODE  mode 쿼리 파라미터가 없을 때의 기본 동작 (기본 "ok")
    MOCK119_SLEEP_SEC     mode=timeout 일 때 잠드는 초 (기본 10)

    ⚠️ 포트를 6000 으로 되돌리지 말 것. 2026-08-18 시연 리허설에서 걸렸다.
       크롬 계열 브라우저는 6000 번(X11 예약)을 안전하지 않은 포트로 보고 접속
       자체를 거부한다(ERR_UNSAFE_PORT). 서버는 멀쩡히 떠 있고 curl 도 되는데
       주소창에서만 안 열려서 원인을 찾기 어렵다. 접수 콘솔을 브라우저로 여는 것이
       이 서버의 용도이므로 차단 목록에 없는 포트를 쓴다.

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
                               image_base64 는 빼고 index/has_image/image_url 을 붙인다
                               — 접수 콘솔이 2초마다 이 목록을 폴링하는데 매 폴링마다
                               수 MB base64 를 실어 보내면 브라우저가 멈춘다
    GET  /reports/<index>/image  그 신고의 대표 프레임을 image/jpeg 로 돌려준다
                               (범위 밖·이미지 없음·디코딩 실패는 모두 404 JSON)
    GET  /                     접수 콘솔 화면 — 좌측에 수신한 신고 목록(카드),
                               우측에 선택한 신고의 대표 프레임을 크게 보여주고
                               [출동 지령] 버튼으로 백엔드에 출동 통지를 되쏜다.
                               POST 는 **브라우저가 직접** 백엔드로 보낸다 (이 서버는
                               중계하지 않는다 — 백엔드가 CORS 전 오리진 허용이다)
    GET  /health               {"status": "ok"}

두 기관 승계(승계 시연) 데모:
    1. 이 서버를 한 개 띄운다 (포트 8119).
    2. DB agency 테이블에서 기관 1 endpoint 를
       'http://localhost:8119/report?mode=timeout&station=1' (또는 mode=fail),
       기관 2 endpoint 를 'http://localhost:8119/report?mode=ok&station=2' 로 설정한다.
    3. 백엔드에서 신고를 트리거하면: 기관 1은 4회 시도 모두 실패(NO_RESPONSE)
       → 기관 2로 승계되어 접수(ACCEPTED). 이 서버 콘솔에서 수신 로그로 확인한다.
       mode=timeout 이면 기관 1도 실제로는 접수하므로, GET /reports 에서
       기관 1 수신 4건 중 1건만 접수이고 나머지는 duplicate 인 것을 보여줄 수 있다.
"""
import base64
import itertools
import os
import sys
import time
from datetime import datetime

from flask import Flask, Response, jsonify, request

# Windows 콘솔 기본 인코딩(cp949)은 일부 문자(—)를 못 써서 기동 즉시 죽는다.
# 로그가 전부 한글이므로 출력 인코딩을 UTF-8 로 고정한다.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

app = Flask(__name__)


def _agency_key() -> str:
    """접수 콘솔 입력칸에 미리 채워 둘 X-Agency-Key 값.

    2026-08-24 이전에는 화면에 `dev-agency-key` 를 박아 뒀는데, 그건 백엔드가
    키 미설정 시 조용히 쓰던 기본값이었다. 이제 백엔드는 기본값이면 아예 뜨지
    않으므로(back/config.py 의 시크릿 가드) 박아 둔 값은 항상 틀린 값이 된다.
    그래서 백엔드와 같은 곳(루트 .env)에서 읽어 온다 — 시연자가 매번 키를
    복사해 붙여넣지 않아도 되고, 두 곳에 값이 갈라지지도 않는다.

    못 찾으면 빈 칸으로 둔다. 틀린 값을 채워 두는 것보다 비어 있는 편이
    "여기에 무언가 넣어야 한다"가 분명하다.
    """
    from pathlib import Path

    if os.environ.get("AGENCY_CALLBACK_KEY"):
        return os.environ["AGENCY_CALLBACK_KEY"]
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, _, value = line.strip().partition("=")
        if name.strip() == "AGENCY_CALLBACK_KEY":
            return value.strip()
    return ""


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
    """이번 세션에 수신한 신고 전체 목록 (데모/디버그용).

    대표 프레임(`image_base64`)만 빼고 내보낸다. 접수 콘솔이 2초마다 이 목록을
    통째로 폴링하는데, 신고 한 건의 base64 가 수 MB 라 그대로 실으면 폴링마다
    수십 MB 를 파싱하게 되어 브라우저가 멈춘다. 이미지는 있다/없다(`has_image`)만
    알리고 실물은 `image_url` 로 한 장씩 따로 받아가게 한다 — 그쪽은 브라우저가
    캐시할 수 있는 진짜 이미지 응답이다.
    """
    slim = []
    for index, entry in enumerate(RECEIVED):
        item = {key: value for key, value in entry.items() if key != "image_base64"}
        item["index"] = index
        item["has_image"] = bool(entry.get("image_base64"))
        item["image_url"] = f"/reports/{index}/image"
        slim.append(item)
    return jsonify(slim)


@app.get("/reports/<int:index>/image")
def report_image(index: int):
    """그 신고에 실려 온 대표 프레임(bbox 그려진 것)을 이미지로 돌려준다.

    백엔드는 JPEG 만 싣기 때문에 형식 판별 없이 image/jpeg 로 고정한다.
    깨진 base64 도 404 로 처리한다 — 시연 중에 500 이 뜨면 화면 전체가 멎은
    것처럼 보이지만, 404 면 그 칸만 깨진 이미지로 남고 나머지는 계속 돈다.
    """
    if not 0 <= index < len(RECEIVED):
        return jsonify({"error": "no such report"}), 404
    raw = RECEIVED[index].get("image_base64")
    if not raw:
        return jsonify({"error": "no image in report"}), 404
    try:
        data = base64.b64decode(raw)
    except (ValueError, TypeError):
        return jsonify({"error": "broken image data"}), 404
    return Response(data, mimetype="image/jpeg")


# 접수 콘솔 화면. 시연에서 "소방서가 받은 것"을 눈으로 보여주는 화면이라
# 좌측에 신고 데이터(카드 목록), 우측에 선택한 신고의 대표 프레임을 크게 띄운다.
# 인라인 CSS 뿐이고 프레임워크·빌드 단계는 여전히 없다 — 파일 하나로 완결된다.
# 출동 지령 POST 는 이 서버를 거치지 않고 브라우저가 백엔드로 직접 쏜다.
# 중계를 넣으면 mock 서버가 백엔드 주소를 알아야 하는데, 백엔드가 CORS 로 전
# 오리진을 열어 두었으므로 그럴 이유가 없다 — 화면에서 주소를 바꿔 끼우는 쪽이
# 시연 중 대응도 빠르다.
CONSOLE_HTML = """<!doctype html>
<meta charset="utf-8">
<title>모의 119 접수 콘솔</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
    background: #12151c; color: #e8eaf0;
    display: flex; flex-direction: column; overflow: hidden;
  }
  header {
    background: linear-gradient(90deg, #7f1d1d, #b91c1c);
    padding: 10px 16px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    border-bottom: 1px solid #450a0a;
  }
  header h1 { font-size: 17px; letter-spacing: 1px; white-space: nowrap; }
  #status { font-size: 12px; color: #fecaca; white-space: nowrap; }
  /* 콜백 주소·인증키는 시연 화면에 안 보이게 접어 둔다 — ⚙ 를 누르면 펼쳐진다.
     값 자체는 출동 지령에 계속 쓰이므로 입력칸을 없애지 않고 숨기기만 한다. */
  #cfg { margin-left: auto; position: relative; }
  #cfg > summary {
    list-style: none; cursor: pointer; font-size: 15px; color: #fecaca;
    padding: 2px 6px; border-radius: 4px; user-select: none;
  }
  #cfg > summary::-webkit-details-marker { display: none; }
  #cfg > summary:hover { background: rgba(0,0,0,.25); }
  #cfg[open] > summary { background: rgba(0,0,0,.35); }
  .cfg-panel {
    position: absolute; right: 0; top: 100%; margin-top: 6px; z-index: 10;
    background: #1a1f2b; border: 1px solid #2a2f3a; border-radius: 8px;
    padding: 10px 12px; display: flex; flex-direction: column; gap: 8px;
    font-size: 12px; color: #d1d5db; box-shadow: 0 6px 18px rgba(0,0,0,.5);
  }
  .cfg-panel label { display: flex; gap: 6px; align-items: center; white-space: nowrap; }
  .cfg-panel input {
    background: rgba(0,0,0,.35); border: 1px solid rgba(255,255,255,.25);
    color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 12px;
  }
  main { flex: 1; display: flex; min-height: 0; }

  /* ── 좌측: 신고 목록 ── */
  #list {
    width: 420px; flex-shrink: 0; overflow-y: auto;
    border-right: 1px solid #2a2f3a; padding: 12px;
    display: flex; flex-direction: column; gap: 10px;
  }
  #empty { color: #6b7280; text-align: center; padding: 40px 0; font-size: 13px; }
  .card {
    background: #1a1f2b; border: 1px solid #2a2f3a; border-radius: 8px;
    padding: 10px 12px; cursor: pointer;
  }
  .card:hover { border-color: #4b5563; }
  .card.selected { border-color: #ef4444; box-shadow: 0 0 0 1px #ef4444; }
  .card-top { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
  .card-top .rid { font-weight: bold; font-size: 14px; color: #fca5a5; }
  .card-top .time { margin-left: auto; font-size: 11px; color: #9ca3af; }
  .badge {
    font-size: 10px; padding: 1px 7px; border-radius: 9px;
    background: #374151; color: #d1d5db; white-space: nowrap;
  }
  .badge.dup { background: #78350f; color: #fcd34d; }
  .field { display: flex; font-size: 12px; line-height: 1.7; }
  .field .k { width: 68px; flex-shrink: 0; color: #9ca3af; }
  .field .v { color: #e5e7eb; word-break: break-all; }
  .conf { color: #f87171; font-weight: bold; }
  .card-foot { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
  .card-foot button {
    background: #dc2626; color: #fff; border: 0; border-radius: 5px;
    padding: 5px 14px; font-size: 12px; font-weight: bold; cursor: pointer;
  }
  .card-foot button:hover { background: #ef4444; }
  .card-foot button:disabled {
    background: #374151; color: #9ca3af; cursor: default;
  }
  .result { font-size: 11px; color: #a7f3d0; word-break: break-all; }
  .result.error { color: #fca5a5; }

  /* ── 우측: 대표 프레임 ── */
  #viewer {
    flex: 1; min-width: 0; display: flex; flex-direction: column;
    padding: 14px; gap: 10px; background: #0d1017;
  }
  #caption { font-size: 13px; color: #d1d5db; }
  #caption b { color: #fca5a5; }
  #stage {
    flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center;
    background: #000; border: 1px solid #2a2f3a; border-radius: 8px; overflow: hidden;
  }
  #preview { max-width: 100%; max-height: 100%; object-fit: contain; display: none; }
  #noimage { color: #4b5563; font-size: 14px; }
</style>
<header>
  <h1>&#128680; 모의 119 접수 콘솔</h1>
  <span id="status">불러오는 중...</span>
  <details id="cfg">
    <summary title="연결 설정">&#9881;&#65039;</summary>
    <div class="cfg-panel">
      <label>콜백 주소
        <input id="cb" size="46" value="http://localhost:5000/api/reports/dispatch"></label>
      <label>인증키(X-Agency-Key)
        <input id="key" size="45" value="__AGENCY_KEY__"></label>
    </div>
  </details>
</header>
<main>
  <div id="list"><p id="empty">수신한 신고가 없다. 백엔드에서 화재를 트리거하면 여기에 뜬다.</p></div>
  <div id="viewer">
    <p id="caption">신고를 선택하면 대표 프레임이 여기에 표시된다.</p>
    <div id="stage">
      <img id="preview" alt="대표 프레임">
      <p id="noimage">이미지 없음</p>
    </div>
  </div>
</main>
<script>
var DEFAULT_CALLBACK = "http://localhost:5000/api/reports/dispatch";
// 결과 문구는 목록 밖에 따로 둔다 — 2초마다 목록을 다시 그리므로 카드 안에만 두면 지워진다.
var results = {};
// 출동 접수에 성공한 카드. 다시 그려도 버튼이 잠긴 채로 남아야 해서 목록 밖에 둔다.
// (백엔드는 멱등이라 또 눌러도 사고는 없지만, 화면에서 이중 지령처럼 보이면 혼란스럽다)
var done = {};
// 사용자가 콜백 칸을 한 번이라도 건드렸으면 자동 채움을 그만둔다 (타이핑 중에 덮어쓰면 못 쓴다).
var cbTouched = false;
// 직전 폴링 결과. 같으면 다시 그리지 않는다 — 매번 그리면 <img> 가 재요청되어 깜빡인다.
var lastSnapshot = null;
// 우측에 띄운 신고. 새 신고가 오면 자동으로 최신 건을 따라가되,
// 사용자가 카드를 클릭했으면(manualSelect) 그 선택을 유지한다.
var selectedIndex = null;
var manualSelect = false;
var lastImageUrl = null;

document.getElementById("cb").addEventListener("input", function () { cbTouched = true; });

function text(v) {
  return (v === null || v === undefined || v === "") ? "-" : String(v);
}

// 출동 시각은 **로컬 시각**으로 보낸다. toISOString() 은 UTC 라 KST 에서 9시간
// 이른 값이 되는데, 백엔드의 timestamp 컬럼은 타임존이 없는 로컬 시각이라
// 그대로 저장된다. 그러면 화면에 "접수 18:11 → 출동 09:12" 처럼 출동이 접수보다
// 먼저 일어난 것으로 찍힌다 (2026-08-18 시연 리허설에서 실제로 나온 증상).
function localIso() {
  var now = new Date();
  return new Date(now - now.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
}

function dispatch(row) {
  var url = document.getElementById("cb").value || DEFAULT_CALLBACK;
  var body = {
    report_uid: row.report_uid,
    external_id: row.external_id,
    agency_name: "모의소방서 " + row.station,
    dispatch_no: "D-" + (row.external_id || row.report_uid),
    vehicles: 3,
    crew: 12,
    eta_sec: 240,
    dispatched_at: localIso(),
    note: "펌프차 2 · 구급차 1 출동"
  };
  var btn = document.getElementById("btn-" + row.index);
  if (btn) { btn.disabled = true; }
  show(row.index, "전송 중...", false);
  fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Agency-Key": document.getElementById("key").value
    },
    body: JSON.stringify(body)
  }).then(function (res) {
    return res.text().then(function (t) {
      if (res.ok) {
        // 성공 — 원문 JSON 대신 사람이 읽는 문구로. 다시 못 누르게 잠근다.
        var at = "";
        try { at = (JSON.parse(t).report_dispatched_at || "").replace("T", " "); }
        catch (e) { /* 형식이 달라도 성공 표시는 해야 한다 */ }
        done[row.index] = true;
        show(row.index, "\\u2705 출동 접수됨" + (at ? " \\u00b7 " + at : ""), false);
        if (btn) { btn.textContent = "출동 완료"; }
      } else {
        var msg = "실패 (" + res.status + ")";
        if (res.status === 401) { msg = "인증키가 틀렸다 (401) — \\u2699 에서 키를 확인"; }
        if (res.status === 404) { msg = "백엔드에 진행 중인 신고가 없다 (404)"; }
        show(row.index, "\\u26a0 " + msg, true);
        if (btn) { btn.disabled = false; }
      }
    });
  }).catch(function (err) {
    // 백엔드가 죽어 있어도 폴링은 계속 돌아야 한다. 이 줄에만 실패를 적고 넘어간다.
    show(row.index, "\\u26a0 전송 실패 — 백엔드(콜백 주소)가 떠 있는지 확인", true);
    if (btn) { btn.disabled = false; }
  });
}

function show(index, message, isError) {
  results[index] = { text: message, error: !!isError };
  var out = document.getElementById("out-" + index);
  if (out) {
    out.textContent = message;
    out.classList.toggle("error", !!isError);
  }
}

function autofillCallback(rows) {
  if (cbTouched) { return; }
  // 신고에 실려 온 callback_url 을 그대로 쓴다 — 백엔드 포트가 바뀌어도 화면이 따라간다.
  var url = DEFAULT_CALLBACK;
  for (var i = rows.length - 1; i >= 0; i--) {
    if (rows[i].callback_url) { url = rows[i].callback_url; break; }
  }
  document.getElementById("cb").value = url;
}

function field(parent, key, value, valueClass) {
  var p = document.createElement("div");
  p.className = "field";
  var k = document.createElement("span");
  k.className = "k";
  k.textContent = key;
  var v = document.createElement("span");
  v.className = "v" + (valueClass ? " " + valueClass : "");
  v.textContent = value;
  p.appendChild(k);
  p.appendChild(v);
  parent.appendChild(p);
}

function badge(parent, label, extraClass) {
  var b = document.createElement("span");
  b.className = "badge" + (extraClass ? " " + extraClass : "");
  b.textContent = label;
  parent.appendChild(b);
}

// 우측 패널에 그 신고의 대표 프레임을 띄운다. src 는 바뀔 때만 건드린다 —
// 같은 값을 다시 넣어도 브라우저에 따라 재요청되어 깜빡일 수 있다.
function showPreview(row) {
  var img = document.getElementById("preview");
  var noimage = document.getElementById("noimage");
  var caption = document.getElementById("caption");

  if (!row) {
    caption.textContent = "신고를 선택하면 대표 프레임이 여기에 표시된다.";
    img.style.display = "none";
    noimage.style.display = "";
    lastImageUrl = null;
    return;
  }
  caption.innerHTML = "";
  var b = document.createElement("b");
  b.textContent = text(row.external_id);
  caption.appendChild(b);
  caption.appendChild(document.createTextNode(
    "  " + text(row.address) + " · " + text(row.place) +
    " · " + text(row.event_class) + " " + text(row.confidence)));

  if (row.has_image) {
    if (lastImageUrl !== row.image_url) {
      img.src = row.image_url;
      lastImageUrl = row.image_url;
    }
    // 스타일시트가 #preview 를 display:none 으로 시작하므로 "" 로는 안 보인다 —
    // 인라인 block 으로 명시해야 스타일시트를 이긴다.
    img.style.display = "block";
    noimage.style.display = "none";
  } else {
    img.style.display = "none";
    noimage.style.display = "";
    lastImageUrl = null;
  }
}

function select(rows, index, manual) {
  selectedIndex = index;
  if (manual) { manualSelect = true; }
  var cards = document.querySelectorAll(".card");
  cards.forEach(function (card) {
    card.classList.toggle("selected", Number(card.dataset.index) === index);
  });
  var row = rows.filter(function (r) { return r.index === index; })[0];
  showPreview(row || null);
}

function card(rows, row) {
  var el = document.createElement("div");
  el.className = "card";
  el.dataset.index = row.index;
  el.onclick = function () { select(rows, row.index, true); };

  var top = document.createElement("div");
  top.className = "card-top";
  var rid = document.createElement("span");
  rid.className = "rid";
  rid.textContent = text(row.external_id);
  top.appendChild(rid);
  if (row.duplicate) { badge(top, "중복", "dup"); }
  badge(top, "소방서 " + text(row.station));
  badge(top, text(row.mode));
  var time = document.createElement("span");
  time.className = "time";
  time.textContent = text(row.received_at).replace("T", " ");
  top.appendChild(time);
  el.appendChild(top);

  field(el, "분류/신뢰도", text(row.event_class) + " / " + text(row.confidence), "conf");
  field(el, "주소", text(row.address));
  field(el, "설치위치", text(row.place));
  var cctv = row.cctv || {};
  field(el, "카메라", text(cctv.name) + " (" + text(cctv.width) + "x" + text(cctv.height) + ")");

  var foot = document.createElement("div");
  foot.className = "card-foot";
  var btn = document.createElement("button");
  btn.id = "btn-" + row.index;
  // 이미 접수된 출동은 다시 못 내리게 잠근 채로 그린다 (2초마다 다시 그려지므로)
  if (done[row.index]) {
    btn.textContent = "출동 완료";
    btn.disabled = true;
  } else {
    btn.textContent = "출동 지령";
  }
  btn.onclick = function (e) {
    e.stopPropagation();  // 버튼 클릭이 카드 선택으로 번지지 않게
    dispatch(row);
  };
  foot.appendChild(btn);
  var out = document.createElement("span");
  out.className = "result" + (results[row.index] && results[row.index].error ? " error" : "");
  out.id = "out-" + row.index;
  out.textContent = results[row.index] ? results[row.index].text : "";
  foot.appendChild(out);
  el.appendChild(foot);

  return el;
}

function draw(rows) {
  var snapshot = JSON.stringify(rows);
  if (snapshot === lastSnapshot) { return; }
  lastSnapshot = snapshot;

  var list = document.getElementById("list");
  list.innerHTML = "";
  if (rows.length === 0) {
    var empty = document.createElement("p");
    empty.id = "empty";
    empty.textContent = "수신한 신고가 없다. 백엔드에서 화재를 트리거하면 여기에 뜬다.";
    list.appendChild(empty);
  }
  // 최신 신고가 위로 오게 역순으로 그린다 — 시연 중에는 방금 온 것만 본다.
  for (var i = rows.length - 1; i >= 0; i--) {
    list.appendChild(card(rows, rows[i]));
  }

  // 새 신고가 오면 자동으로 최신 건을 우측에 띄운다.
  // 사용자가 직접 고른 게 있으면 그 선택을 유지한다 (사라진 경우만 최신으로 복귀).
  var validSelection = rows.some(function (r) { return r.index === selectedIndex; });
  if (rows.length === 0) {
    select(rows, null, false);
  } else if (manualSelect && validSelection) {
    select(rows, selectedIndex, false);
  } else {
    manualSelect = false;
    select(rows, rows[rows.length - 1].index, false);
  }

  document.getElementById("status").textContent =
    "신고 " + rows.length + "건 · 2초마다 갱신";
  autofillCallback(rows);
}

function poll() {
  fetch("/reports")
    .then(function (res) { return res.json(); })
    .then(draw)
    .catch(function (err) {
      document.getElementById("status").textContent = "접수 목록을 못 읽었다: " + err;
    });
}

poll();
setInterval(poll, 2000);
</script>
"""


def _agency_key() -> str:
    """출동 지령에 실을 X-Agency-Key 기본값.

    백엔드의 AGENCY_CALLBACK_KEY 와 같아야 통지가 접수된다. 키를 소스에 박아
    두면 저장소에 비밀값이 남으므로, 환경변수 → 저장소 루트 .env 순서로 읽고
    둘 다 없으면 개발용 더미를 쓴다 (그때는 ⚙ 에서 직접 바꿔 넣으면 된다).
    """
    key = os.environ.get("AGENCY_CALLBACK_KEY")
    if key:
        return key
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                name, _, value = line.strip().partition("=")
                if name == "AGENCY_CALLBACK_KEY" and value:
                    return value
    except OSError:
        pass
    return "dev-agency-key"


@app.get("/")
def console():
    """소방서 접수 콘솔 화면 (시연용).

    콘솔 print 만으로는 "소방서가 무엇을 받았는지"를 보여줄 수 없어서 붙인 화면이다.
    좌측이 신고 목록(데이터), 우측이 선택한 신고의 대표 프레임이다.
    인라인 CSS 뿐이고 프레임워크·빌드 단계는 없다 — 이 파일 하나로 완결된다.
    """
    # charset 은 적지 않는다 — werkzeug 3 이 text/* 에 charset=utf-8 을 무조건
    # 덧붙여서, 여기에 또 쓰면 Content-Type 에 charset 이 두 번 들어간다.
    # 인증키는 매 요청 채워 넣는다 — 서버 기동 뒤에 .env 를 고쳐도 새로고침만
    # 하면 반영된다. CONSOLE_HTML 은 JS 중괄호가 가득해서 .format 을 쓸 수 없다.
    return Response(CONSOLE_HTML.replace("__AGENCY_KEY__", _agency_key()),
                    mimetype="text/html")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("MOCK119_PORT", "8119"))
    print(f"[mock-119] 소방청 모의 서버 기동 — http://localhost:{port} "
          f"(기본 mode={os.environ.get('MOCK119_DEFAULT_MODE', 'ok')})", flush=True)
    # 리로더 없이 단일 프로세스로 실행 (테스트가 subprocess.terminate 로 종료한다)
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
