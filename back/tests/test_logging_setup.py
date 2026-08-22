"""로깅 설정 테스트 — app.setup_logging().

배경: 서비스 코드 12곳이 `logging.getLogger("fireguard.*")` 로 로그를 남기고
있었는데 핸들러가 한 개도 없어서 INFO 는 버려지고 WARNING 만 서식 없이
콘솔에 잠깐 떴다 사라졌다. 서버가 밤새 돌다 생긴 일을 아침에 확인할 방법이
없다는 뜻이다. 남기는 쪽(44개 호출)은 그대로 두고 받는 쪽만 붙인다.

핵심 제약:
- create_app() 은 테스트에서 여러 번 불린다 → 설정은 create_app 밖에 두고,
  여러 번 불러도 핸들러가 쌓이지 않아야 한다 (같은 로그가 N줄씩 찍힌다).
"""
import logging
from pathlib import Path

import pytest

from app import setup_logging

MARK = "_fireguard_handler"   # 우리가 붙인 핸들러임을 표시하는 속성


def our_handlers():
    return [h for h in logging.getLogger().handlers if getattr(h, MARK, False)]


@pytest.fixture(autouse=True)
def restore_root_logger():
    """루트 로거는 전역이다 — 이 파일이 건드린 흔적을 반드시 되돌린다.

    안 되돌리면 뒤에 도는 다른 테스트의 로그까지 파일로 새어 나가고,
    윈도우에서는 파일이 열린 채라 tmp_path 정리가 실패한다.
    """
    root = logging.getLogger()
    saved, saved_level = root.handlers[:], root.level
    yield
    for h in root.handlers[:]:
        if h not in saved:
            root.removeHandler(h)
            h.close()
    root.handlers[:] = saved
    root.setLevel(saved_level)


def test_핸들러가_없던_루트에_콘솔과_파일_두_개가_붙는다(tmp_path):
    assert our_handlers() == []

    setup_logging(log_dir=tmp_path)

    kinds = {type(h).__name__ for h in our_handlers()}
    assert len(our_handlers()) == 2
    assert "StreamHandler" in kinds          # 콘솔
    assert any("File" in k for k in kinds)   # 파일


def test_로그_디렉터리가_없으면_만든다(tmp_path):
    target = tmp_path / "logs"
    assert not target.exists()

    setup_logging(log_dir=target)

    assert target.is_dir()


def test_두_번_불러도_핸들러가_늘지_않는다(tmp_path):
    """create_app 이 여러 번 불려도 같은 로그가 두 줄씩 찍히면 안 된다."""
    setup_logging(log_dir=tmp_path)
    setup_logging(log_dir=tmp_path)
    setup_logging(log_dir=tmp_path)

    assert len(our_handlers()) == 2


def test_서비스_코드를_안_고쳐도_INFO_가_파일에_남는다(tmp_path):
    """이 테스트가 이 작업의 전부다 — 남기는 쪽 코드는 손대지 않는다."""
    setup_logging(log_dir=tmp_path)

    logging.getLogger("fireguard.alert").info("SMS 발송 시도 event_no=42")
    for h in our_handlers():
        h.flush()

    written = (tmp_path / "fireguard.log").read_text(encoding="utf-8")
    assert "SMS 발송 시도 event_no=42" in written
    assert "fireguard.alert" in written   # 어느 모듈이 남겼는지 구분된다
    assert "INFO" in written


def test_예외는_트레이스백까지_파일에_남는다(tmp_path):
    setup_logging(log_dir=tmp_path)

    try:
        1 / 0
    except ZeroDivisionError:
        logging.getLogger("fireguard.report").exception("119 신고 중 오류")
    for h in our_handlers():
        h.flush()

    written = (tmp_path / "fireguard.log").read_text(encoding="utf-8")
    assert "119 신고 중 오류" in written
    assert "ZeroDivisionError" in written


def test_레벨을_올리면_INFO_는_걸러진다(tmp_path):
    setup_logging(log_dir=tmp_path, level="WARNING")

    log = logging.getLogger("fireguard.alert")
    log.info("이건 안 남아야 한다")
    log.warning("이건 남아야 한다")
    for h in our_handlers():
        h.flush()

    written = (tmp_path / "fireguard.log").read_text(encoding="utf-8")
    assert "이건 안 남아야 한다" not in written
    assert "이건 남아야 한다" in written


def test_알림_로거_이름이_응답과_발송에서_같다():
    """알림 경로가 fireguard.alerts(복수)/fireguard.alert 두 이름으로 갈려 있었다.

    이름이 갈리면 레벨을 한 번에 조절할 수 없다 — 한쪽만 조용해진다.

    응답 쪽 로거는 원래 routes/alert_routes.py 에 있었는데, 텔레그램 버튼도 같은
    처리를 부르게 되면서 본체가 services/alert_respond.py 로 옮겨갔다(라우트는
    이제 그 함수를 부르기만 해서 자기 로거가 없다). 그래서 여기서 보는 대상도
    옮겨간 모듈이다.
    """
    import services.alert_respond as alert_respond
    import services.alert_service as alert_service

    assert alert_respond.logger.name == alert_service.logger.name == "fireguard.alert"


def test_색상_이스케이프는_파일에_들어가지_않는다(tmp_path):
    """werkzeug 는 접근 로그에 ANSI 색을 입혀 보낸다.

    콘솔에서는 색으로 보이지만 파일에는 `\x1b[31m` 같은 글자가 박혀서
    grep 이 어긋나고 눈으로 읽기도 나빠진다. 파일 쪽만 벗겨 낸다.
    """
    setup_logging(log_dir=tmp_path)

    logging.getLogger("werkzeug").info("\x1b[31m\x1b[1mGET /api/alerts\x1b[0m 401")
    for h in our_handlers():
        h.flush()

    written = (tmp_path / "fireguard.log").read_text(encoding="utf-8")
    assert "\x1b" not in written
    assert "GET /api/alerts" in written


def test_에스컬레이션_틱_소음은_파일에_쌓이지_않는다(tmp_path):
    """APScheduler 는 잡을 돌릴 때마다 INFO 2줄을 남긴다.

    ESCALATION_INTERVAL_SEC=5 면 하루 3만 줄이 넘어 실제 화재 로그가 묻힌다.
    틱 성공은 안 남기고, 잡이 터졌을 때(WARNING 이상)는 남겨야 한다.
    """
    setup_logging(log_dir=tmp_path)

    executors = logging.getLogger("apscheduler.executors.default")
    executors.info('Running job "run_escalation_tick"')
    executors.error("Job raised an exception")
    for h in our_handlers():
        h.flush()

    written = (tmp_path / "fireguard.log").read_text(encoding="utf-8")
    assert "run_escalation_tick" not in written      # 평상시 소음은 버린다
    assert "Job raised an exception" in written      # 사고는 남긴다
