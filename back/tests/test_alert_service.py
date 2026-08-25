"""알림 발송 서비스 테스트 — services/alert_service.py + services/sms.py.

알림 정책 (동시 발송 확정):
- 알림은 해당 CCTV 의 소유 사용자(cctv.user_no)에게만 간다. ADMIN 브로드캐스트 없음.
- 이벤트 확정 시 PUSH 와 SMS 를 **동시에** 한 트랜잭션으로 만든다 (단계 승격 없음).
  두 채널 모두 같은 사람의 같은 휴대폰으로 가므로 단계를 나누면 시간만 낭비된다.
- 두 행 모두 alert_status='SENT', alert_sent_at/alert_deadline_at 동일.
- alert_deadline_at = alert_sent_at + ALERT_DEADLINE_SEC 초. 유예는 이 한 번뿐이고,
  마감까지 무응답이면 에스컬레이션이 곧바로 119 신고로 넘어간다.
- 점검 모드(event_is_test) 이벤트는 알림을 만들지 않는다.
- 확정 훅(on_event_confirmed)은 두 알림을 만들고, 예외를 절대 밖으로 던지지 않는다.
"""
from datetime import timedelta

from conftest import make_event, make_media

import config
import db
from services import alert_service, hooks, sms


FLAME = {"cls": "flame", "conf": 0.91, "box": [0.238, 0.259, 0.047, 0.113]}


def post_frame(client, cctv_no=1, captured_at="2026-08-08T14:30:00"):
    """내부 검출 API 로 화재 프레임 1장을 보낸다 (훅 경로 테스트용)."""
    return client.post(
        "/api/internal/detections",
        json={"cctv_no": cctv_no, "detections": [FLAME], "captured_at": captured_at},
        headers={"X-Internal-Key": config.INTERNAL_API_KEY},
    )


def get_alert_rows(event_no=None):
    if event_no is None:
        return db.query("SELECT * FROM alert ORDER BY alert_no")
    return db.query(
        "SELECT * FROM alert WHERE event_no = %s ORDER BY alert_no", (event_no,)
    )


def spy_send_sms(monkeypatch):
    """sms.send_sms 를 기록용 스파이로 바꾼다."""
    calls = []
    monkeypatch.setattr("services.sms.send_sms",
                        lambda phone, message: calls.append((phone, message)) or True)
    return calls


# ---------- sms 모의 발송기 ----------

def test_send_sms_with_phone_returns_true():
    """전화번호가 있으면 (모의) 발송 성공 True."""
    assert sms.send_sms("01011111111", "테스트 메시지") is True


def test_send_sms_without_phone_returns_false():
    """전화번호가 None/빈 문자열이면 경고 로그 후 False (예외 없음)."""
    assert sms.send_sms(None, "테스트 메시지") is False
    assert sms.send_sms("", "테스트 메시지") is False


# ---------- send_alerts 기본 동작 ----------

def test_send_alerts_creates_push_and_sms_rows(monkeypatch):
    """확정 알림 = PUSH 1행 + SMS 1행. 둘 다 level 1 / SENT, 발송·마감 시각이 동일."""
    monkeypatch.setattr(config, "ALERT_DEADLINE_SEC", 45)
    spy_send_sms(monkeypatch)
    event_no = make_event(cctv_no=1)

    alert_nos = alert_service.send_alerts(event_no)

    rows = get_alert_rows(event_no)
    assert len(rows) == 2
    assert sorted(alert_nos) == [r["alert_no"] for r in rows]
    assert {r["alert_channel"] for r in rows} == {"PUSH", "SMS"}

    for a in rows:
        assert a["user_no"] == 1          # cctv 1 의 소유자
        assert "alert_level" not in a     # 승격 폐기 — 컬럼 자체를 삭제함
        assert a["alert_status"] == "SENT"
        assert a["alert_sent_at"] is not None
        assert a["alert_responded_at"] is None
        # 마감은 발송 시각 + 정확히 ALERT_DEADLINE_SEC 초
        assert a["alert_deadline_at"] - a["alert_sent_at"] == timedelta(seconds=45)

    # 두 행은 같은 트랜잭션에서 만들어지므로 시각이 완전히 같아야 한다
    push, sms_row = rows if rows[0]["alert_channel"] == "PUSH" else rows[::-1]
    assert push["alert_sent_at"] == sms_row["alert_sent_at"]
    assert push["alert_deadline_at"] == sms_row["alert_deadline_at"]


def test_deadline_supports_sub_minute_grace(monkeypatch):
    """유예를 1분 미만으로 잡을 수 있다 — 발표 슬라이드 11 의 타임라인이 30초다.

    분 단위 설정으로는 표현 자체가 불가능했던 값이라 회귀로 남긴다.
    """
    monkeypatch.setattr(config, "ALERT_DEADLINE_SEC", 30)
    spy_send_sms(monkeypatch)
    event_no = make_event(cctv_no=1)

    alert_service.send_alerts(event_no)

    for a in get_alert_rows(event_no):
        assert a["alert_deadline_at"] - a["alert_sent_at"] == timedelta(seconds=30)


def test_default_deadline_is_60_seconds():
    """기본 유예는 60초.

    2026-08-13 에 30 → 60 으로 올렸다. 알림을 받고 링크를 열어 취소까지 누르는
    실제 동선이 30초로는 빠듯했다. 발표 슬라이드 11 타임라인
    (알림 02:14:08 → 신고 02:14:38)은 30초 기준이라 이제 덱과 어긋난다.
    """
    assert config.ALERT_DEADLINE_SEC == 60


def test_send_alerts_sends_sms_once_to_owner_phone(monkeypatch):
    """SMS 행에 대해서만 send_sms 를 1회 호출한다 (PUSH 는 프론트 폴링이 가져감)."""
    calls = spy_send_sms(monkeypatch)
    event_no = make_event(cctv_no=1)

    alert_service.send_alerts(event_no)

    assert len(calls) == 1
    phone, message = calls[0]
    assert phone == "01011111111"  # admin01 (user_no=1) 의 전화번호
    assert "정문 카메라" in message
    assert "서울특별시 중구 세종대로 110" in message


# ---------- 멱등성 · 예외 상황 ----------

def test_send_alerts_idempotent_per_event(monkeypatch):
    """이벤트 단위 멱등: 두 번 호출해도 행은 2개뿐이고 SMS 재발송도 없다."""
    calls = spy_send_sms(monkeypatch)
    event_no = make_event()

    first = alert_service.send_alerts(event_no)
    second = alert_service.send_alerts(event_no)

    assert sorted(first) == sorted(second)
    assert len(get_alert_rows(event_no)) == 2
    assert len(calls) == 1  # SMS 는 최초 1회만


def test_send_alerts_owner_without_phone_still_creates_both_rows():
    """소유자 전화번호가 NULL 이어도 두 행 모두 생성된다 (send_sms 가 False 처리)."""
    db.execute("UPDATE users SET user_phone = NULL WHERE user_no = 1")
    event_no = make_event(cctv_no=1)

    alert_nos = alert_service.send_alerts(event_no)  # 실제 sms.send_sms 사용

    rows = get_alert_rows(event_no)
    assert len(rows) == 2
    assert sorted(alert_nos) == [r["alert_no"] for r in rows]
    assert {r["alert_channel"] for r in rows} == {"PUSH", "SMS"}


def test_send_alerts_unknown_event_returns_none():
    """존재하지 않는 이벤트(→ 소유자 조회 불가)는 경고 로그 후 None, 예외 없음."""
    assert alert_service.send_alerts(99999) is None
    assert get_alert_rows() == []


def test_send_alerts_test_event_skipped():
    """점검 모드(event_is_test) 이벤트는 알림을 만들지 않는다."""
    event_no = make_event(is_test=True, status="CONFIRMED")
    assert alert_service.send_alerts(event_no) is None
    assert get_alert_rows() == []


# ---------- 확정 훅 경로 ----------

def test_hook_creates_both_alerts_on_confirm(client, monkeypatch):
    """내부 검출 API 로 확정까지 가면 소유자(user_no=1) 앞 PUSH+SMS 알림이 생긴다."""
    monkeypatch.setattr(config, "EVENT_THRESHOLD_FRAMES", 2)
    calls = spy_send_sms(monkeypatch)

    post_frame(client, captured_at="2026-08-08T14:30:00")
    body = post_frame(client, captured_at="2026-08-08T14:30:01").get_json()
    assert body["event_status"] == "CONFIRMED"

    rows = get_alert_rows(body["event_no"])
    assert len(rows) == 2
    assert {r["alert_channel"] for r in rows} == {"PUSH", "SMS"}
    for a in rows:
        assert a["user_no"] == 1
        assert "alert_level" not in a
        assert a["alert_status"] == "SENT"
    assert len(calls) == 1


def test_hook_test_event_creates_no_alert():
    """점검 모드 이벤트가 확정돼도 훅은 아무 것도 만들지 않는다."""
    event_no = make_event(is_test=True, status="CONFIRMED")
    hooks.on_event_confirmed(event_no)
    assert get_alert_rows() == []


def test_hook_exception_does_not_break_detection_api(client, monkeypatch):
    """알림 발송이 죽어도 AI 의 검출 요청은 200 이어야 한다 (훅이 예외를 삼킨다)."""
    monkeypatch.setattr(config, "EVENT_THRESHOLD_FRAMES", 2)

    def boom(event_no):
        raise RuntimeError("알림 발송 실패 시뮬레이션")

    monkeypatch.setattr("services.alert_service.send_alerts", boom)

    post_frame(client, captured_at="2026-08-08T14:30:00")
    r = post_frame(client, captured_at="2026-08-08T14:30:01")
    assert r.status_code == 200
    body = r.get_json()
    assert body["event_status"] == "CONFIRMED"  # 확정 자체는 그대로
    assert get_alert_rows() == []


# ---------- 알림 목록 API 연동 (회귀) ----------

def test_sent_alerts_visible_in_owner_alert_list(client, admin_headers, monkeypatch):
    """send_alerts 로 만든 두 알림이 모두 소유자의 GET /api/alerts 목록에 보인다."""
    spy_send_sms(monkeypatch)
    event_no = make_event(cctv_no=1)
    alert_nos = alert_service.send_alerts(event_no)

    r = client.get("/api/alerts", headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["total_count"] == 2
    assert sorted(i["alert_no"] for i in body["items"]) == sorted(alert_nos)
    assert {i["alert_channel"] for i in body["items"]} == {"PUSH", "SMS"}
    assert all(i["event_no"] == event_no for i in body["items"])
    assert all(i["cctv_name"] == "정문 카메라" for i in body["items"])


# ---------- 전달 채널 (텔레그램 연동 시) ----------
# 연동한 사용자에게는 문자 대신 텔레그램으로 나간다. 이유는 services/notify.py 주석 참고
# — 우리 알림은 유예 안에 '확인/취소'를 되받아야 하는데 문자는 회신을 받을 수 없다.

def spy_telegram(monkeypatch):
    """telegram.send_message 를 기록용 스파이로 바꾼다."""
    from services import telegram

    calls = []
    monkeypatch.setattr(telegram, "send_message",
                        lambda chat_id, text, buttons=None:
                            calls.append((chat_id, text, buttons)) or True)
    return calls


def link_telegram(user_no=1, chat_id=555):
    db.execute("UPDATE users SET user_telegram_chat_id = %s WHERE user_no = %s",
               (chat_id, user_no))


def test_linked_owner_gets_the_alert_on_telegram(monkeypatch):
    tg = spy_telegram(monkeypatch)
    sms_calls = spy_send_sms(monkeypatch)
    link_telegram(1, 555)

    alert_service.send_alerts(make_event(cctv_no=1))

    assert len(tg) == 1
    chat_id, message, _ = tg[0]
    assert chat_id == 555
    assert "정문 카메라" in message
    assert sms_calls == [], "텔레그램으로 나갔으면 문자는 보내지 않는다"


def test_telegram_alert_carries_the_response_buttons(monkeypatch):
    """알림에 붙은 버튼이 곧 응답 경로다 — 그 버튼으로 유예 안에 확인/취소를 한다."""
    tg = spy_telegram(monkeypatch)
    link_telegram(1, 555)
    event_no = make_event(cctv_no=1)

    alert_service.send_alerts(event_no)

    _, _, buttons = tg[0]
    data = [b["callback_data"] for row in buttons for b in row]
    # 버튼은 이 이벤트의 실제 알림 번호를 가리켜야 한다
    alert_nos = {r["alert_no"] for r in get_alert_rows(event_no)}
    assert {int(d.split(":")[1]) for d in data} <= alert_nos
    assert any(d.endswith(":READ") for d in data)
    assert any(d.endswith(":CANCEL") for d in data)


def test_the_telegram_button_actually_closes_the_alert(monkeypatch):
    """버튼을 누르면 웹 화면과 같은 처리를 지나 알림이 닫힌다 (앱 조작의 핵심 경로)."""
    from services import telegram_bot

    tg = spy_telegram(monkeypatch)
    link_telegram(1, 555)
    event_no = make_event(cctv_no=1)
    alert_service.send_alerts(event_no)
    _, _, buttons = tg[0]
    cancel = next(b for row in buttons for b in row
                  if b["callback_data"].endswith(":CANCEL"))

    telegram_bot.handle_update({
        "update_id": 1,
        "callback_query": {"id": "q-1", "data": cancel["callback_data"],
                           "message": {"chat": {"id": 555}, "message_id": 7}},
    })

    statuses = {r["alert_status"] for r in get_alert_rows(event_no)}
    assert statuses == {"CANCELED"}, "PUSH·SMS 두 행 모두 닫혀야 한다"


def test_unlinked_owner_still_gets_sms(monkeypatch):
    """연동하지 않은 사용자는 기존 경로 그대로다."""
    tg = spy_telegram(monkeypatch)
    sms_calls = spy_send_sms(monkeypatch)

    alert_service.send_alerts(make_event(cctv_no=1))

    assert tg == []
    assert len(sms_calls) == 1


# ---------- 알림 문구 ----------
#
# 문구 하나로 "어디서 무슨 일이 났나"가 서야 한다. 알림을 받은 사람은 유예
# (ALERT_DEADLINE_SEC) 안에 확인/취소를 판단해야 하고, 그 판단을 위해 앱을 열어
# 카메라 목록을 뒤져야 한다면 유예가 그것만으로 끝난다.
#
# 위치는 **주소**로 적는다. cctv_location 은 사람이 붙인 설치 위치 설명이거나 ITS
# 카메라 이름이라 처음 보는 사람에게는 아무 정보도 아니다("본관 후문"이 어느 건물인가).
# 좌표는 넣지 않는다 — 사람이 읽고 바로 움직일 수 있는 형태가 아니다.

def first_message(monkeypatch, cctv_no=1):
    """알림 1건을 내보내고 그 문구를 돌려준다 (SMS 경로로 관찰)."""
    calls = spy_send_sms(monkeypatch)
    alert_service.send_alerts(make_event(cctv_no=cctv_no))
    return calls[0][1]


def test_message_names_the_camera_and_what_was_detected(monkeypatch):
    message = first_message(monkeypatch)

    assert "정문 카메라" in message
    assert "불꽃" in message          # CLASS_LABEL["FLAME"]


def test_message_carries_the_address_as_the_location(monkeypatch):
    message = first_message(monkeypatch)

    assert "서울특별시 중구 세종대로 110" in message


def test_message_never_carries_coordinates(monkeypatch):
    """좌표는 사람이 읽고 움직일 수 있는 형태가 아니다 — 어떤 경우에도 넣지 않는다.

    119 신고(report_service._report_address)는 주소가 없으면 좌표 문자열로 떨어지지만,
    그건 받는 쪽이 지도에 찍는 상황이라 다르다. 사용자 알림은 그 폴백을 쓰지 않는다.
    """
    db.execute("UPDATE cctv SET cctv_address = NULL WHERE cctv_no = 1")

    message = first_message(monkeypatch)

    assert "37.5" not in message
    assert "126.9" not in message


def test_message_falls_back_to_the_install_note_without_an_address(monkeypatch):
    """주소 컬럼이 생기기 전에 등록된 카메라는 주소가 비어 있다 (cctv 2 가 그 상태).

    그럴 때는 설치 위치 설명이라도 적는다 — 빈 칸보다는 쓸모 있다.
    """
    message = first_message(monkeypatch, cctv_no=2)

    assert "본관 후문" in message


def test_message_says_so_when_there_is_no_location_at_all(monkeypatch):
    """주소도 설치 설명도 없으면 그렇다고 적는다 — 빈 괄호가 남으면 오류처럼 보인다."""
    db.execute("UPDATE cctv SET cctv_address = NULL, cctv_location = NULL "
               "WHERE cctv_no = 1")

    message = first_message(monkeypatch)

    assert "위치 정보 없음" in message
    assert "None" not in message


def test_message_labels_smoke_events(monkeypatch):
    calls = spy_send_sms(monkeypatch)

    alert_service.send_alerts(make_event(cctv_no=1, event_class="SMOKE"))

    assert "연기" in calls[0][1]


# ---------- 검출 이미지 동봉 ----------
#
# 사용자가 유예 안에 오탐 여부를 가리려면 무엇이 찍혔는지 봐야 한다. 대표 프레임
# (event_media.media_is_primary = 최고 신뢰도 프레임)에 검출 상자를 그려 알림에 붙인다.
# 이미지를 못 구했다고 알림이 늦거나 빠지면 안 된다 — 이미지는 곁들이고 알림이 본체다.

def spy_telegram_photo(monkeypatch):
    """telegram.send_photo 를 기록용 스파이로 바꾼다."""
    from services import telegram

    calls = []
    monkeypatch.setattr(telegram, "send_photo",
                        lambda chat_id, image, caption, buttons=None:
                            calls.append((chat_id, image, caption, buttons)) or True)
    return calls


def store_primary_frame(event_no, tmp_path):
    """대표 프레임 파일 1장을 MEDIA_ROOT 아래에 심는다."""
    from PIL import Image

    img = tmp_path / "events" / str(event_no) / "frame.jpg"
    img.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 100), (0, 0, 0)).save(img, "JPEG")
    make_media(event_no, is_primary=True, url=f"/media/events/{event_no}/frame.jpg")


def test_linked_owner_gets_the_detection_image(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MEDIA_ROOT", str(tmp_path))
    photos = spy_telegram_photo(monkeypatch)
    tg = spy_telegram(monkeypatch)
    link_telegram(1, 555)
    event_no = make_event(cctv_no=1)
    store_primary_frame(event_no, tmp_path)

    alert_service.send_alerts(event_no)

    assert len(photos) == 1
    chat_id, image, caption, buttons = photos[0]
    assert chat_id == 555
    assert image, "대표 프레임 바이트가 실리지 않았다"
    assert "정문 카메라" in caption
    assert "서울특별시 중구 세종대로 110" in caption
    assert buttons, "사진 알림에도 확인/취소 버튼이 붙어야 응답 경로가 산다"
    assert tg == [], "사진으로 나갔으면 같은 내용을 본문으로 또 보내지 않는다"


def test_alert_goes_out_as_text_when_the_event_has_no_frame(monkeypatch, tmp_path):
    """프레임이 없는 이벤트(수집 실패·이미지 미저장)도 알림은 그대로 나간다."""
    monkeypatch.setattr(config, "MEDIA_ROOT", str(tmp_path))
    photos = spy_telegram_photo(monkeypatch)
    tg = spy_telegram(monkeypatch)
    link_telegram(1, 555)

    alert_service.send_alerts(make_event(cctv_no=1))

    assert photos == []
    assert len(tg) == 1


def test_alert_rows_survive_a_broken_frame_loader(monkeypatch):
    """이미지 로딩이 터져도 알림 행 생성과 발송은 막히지 않는다 (이 모듈의 기존 원칙)."""
    def boom(event_no):
        raise RuntimeError("디스크가 사라졌다")

    monkeypatch.setattr("services.event_frame.load_primary_frame", boom)
    sms_calls = spy_send_sms(monkeypatch)
    event_no = make_event(cctv_no=1)

    alert_nos = alert_service.send_alerts(event_no)

    assert len(get_alert_rows(event_no)) == 2
    assert sorted(alert_nos) == [r["alert_no"] for r in get_alert_rows(event_no)]
    assert len(sms_calls) == 1
