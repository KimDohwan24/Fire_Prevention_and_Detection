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
    GET  /                     접수 콘솔 화면 — 수신한 신고를 표로 보여주고
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


# 접수 콘솔 화면. 시연에서 "소방서가 받은 것"을 눈으로 보여주는 게 전부라
# 꾸미지 않는다 — 표와 이미지와 버튼뿐이고 CSS·프레임워크·빌드 단계가 없다.
# 출동 지령 POST 는 이 서버를 거치지 않고 브라우저가 백엔드로 직접 쏜다.
# 중계를 넣으면 mock 서버가 백엔드 주소를 알아야 하는데, 백엔드가 CORS 로 전
# 오리진을 열어 두었으므로 그럴 이유가 없다 — 화면에서 주소를 바꿔 끼우는 쪽이
# 시연 중 대응도 빠르다.
CONSOLE_HTML = """<!doctype html>
<meta charset="utf-8">
<title>모의 119 접수 콘솔</title>
<h1>모의 119 접수 콘솔</h1>
<p>
  콜백 주소 <input id="cb" size="60" value="http://localhost:5000/api/reports/dispatch">
  인증키(X-Agency-Key) <input id="key" size="45" value="__AGENCY_KEY__">
</p>
<p id="status">불러오는 중...</p>
<table border="1">
<thead>
<tr>
  <th>접수번호</th><th>수신시각</th><th>station</th><th>mode</th>
  <th>화재분류 / 신뢰도</th><th>주소</th><th>설치위치</th><th>카메라</th>
  <th>이미지</th><th>출동</th><th>결과</th>
</tr>
</thead>
<tbody id="rows"></tbody>
</table>
<script>
var DEFAULT_CALLBACK = "http://localhost:5000/api/reports/dispatch";
// 결과 칸 내용은 표 밖에 따로 둔다 — 2초마다 표를 다시 그리므로 행 안에 두면 지워진다.
var results = {};
// 사용자가 콜백 칸을 한 번이라도 건드렸으면 자동 채움을 그만둔다 (타이핑 중에 덮어쓰면 못 쓴다).
var cbTouched = false;
// 직전 폴링 결과. 같으면 다시 그리지 않는다 — 매번 그리면 <img> 가 재요청되어 깜빡인다.
var lastSnapshot = null;

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

function cell(tr, value) {
  var td = document.createElement("td");
  td.textContent = value;
  tr.appendChild(td);
  return td;
}

function dispatch(row) {
  var out = document.getElementById("out-" + row.index);
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
  out.textContent = "전송 중...";
  fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Agency-Key": document.getElementById("key").value
    },
    body: JSON.stringify(body)
  }).then(function (res) {
    return res.text().then(function (t) { show(row.index, res.status + " " + t); });
  }).catch(function (err) {
    // 백엔드가 죽어 있어도 폴링은 계속 돌아야 한다. 이 줄에만 실패를 적고 넘어간다.
    show(row.index, "전송 실패: " + err);
  });
}

function show(index, message) {
  results[index] = message;
  var out = document.getElementById("out-" + index);
  if (out) { out.textContent = message; }
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

function draw(rows) {
  var snapshot = JSON.stringify(rows);
  if (snapshot === lastSnapshot) { return; }
  lastSnapshot = snapshot;

  var tbody = document.getElementById("rows");
  tbody.innerHTML = "";
  rows.forEach(function (row) {
    var tr = document.createElement("tr");
    cell(tr, text(row.external_id) + (row.duplicate ? " (중복)" : ""));
    cell(tr, text(row.received_at));
    cell(tr, text(row.station));
    cell(tr, text(row.mode));
    cell(tr, text(row.event_class) + " / " + text(row.confidence));
    cell(tr, text(row.address));
    cell(tr, text(row.place));
    var cctv = row.cctv || {};
    cell(tr, text(cctv.name) + " (" + text(cctv.width) + "x" + text(cctv.height) + ")");

    var imgTd = document.createElement("td");
    if (row.has_image) {
      var img = document.createElement("img");
      img.src = row.image_url;
      img.width = 240;
      imgTd.appendChild(img);
    } else {
      imgTd.textContent = "-";
    }
    tr.appendChild(imgTd);

    var btnTd = document.createElement("td");
    var btn = document.createElement("button");
    btn.textContent = "출동 지령";
    btn.onclick = function () { dispatch(row); };
    btnTd.appendChild(btn);
    tr.appendChild(btnTd);

    var outTd = cell(tr, results[row.index] || "");
    outTd.id = "out-" + row.index;

    tbody.appendChild(tr);
  });
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


@app.get("/")
def console():
    """소방서 접수 콘솔 화면 (시연용).

    콘솔 print 만으로는 "소방서가 무엇을 받았는지"를 보여줄 수 없어서 붙인 화면이다.
    꾸미지 않는다 — 데이터가 오가는 것만 보이면 되므로 CSS 도 프레임워크도 없다.
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
