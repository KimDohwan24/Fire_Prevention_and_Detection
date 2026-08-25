"""CLI 배선 테스트 — 설정을 어디서 읽는가.

백엔드와 같은 값을 봐야 하는 것이 둘 있다.
- INTERNAL_API_KEY : 다르면 401
- MEDIA_ROOT       : 다르면 프레임 JPG 를 저장해도 GET /media/<path> 가 404
"""
from datetime import datetime

import pytest

import run_video


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
    monkeypatch.delenv("MEDIA_ROOT", raising=False)


def write_env(tmp_path, text):
    (tmp_path / ".env").write_text(text, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------- 내부 키


def test_explicit_key_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERNAL_API_KEY", "from-env")
    monkeypatch.setattr(run_video, "PROJECT_ROOT",
                        write_env(tmp_path, "INTERNAL_API_KEY=from-dotenv\n"))

    assert run_video.load_internal_key("from-flag") == "from-flag"


def test_env_var_beats_dotenv(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERNAL_API_KEY", "from-env")
    monkeypatch.setattr(run_video, "PROJECT_ROOT",
                        write_env(tmp_path, "INTERNAL_API_KEY=from-dotenv\n"))

    assert run_video.load_internal_key("") == "from-env"


def test_dotenv_is_read_when_env_var_is_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(run_video, "PROJECT_ROOT",
                        write_env(tmp_path, "INTERNAL_API_KEY=from-dotenv\n"))

    assert run_video.load_internal_key("") == "from-dotenv"


def test_missing_key_is_an_error(monkeypatch, tmp_path):
    """어디에도 키가 없으면 **에러다.** 예전에는 `dev-internal-key` 로 폴백했다.

    그 값은 백엔드가 키 미설정 시 조용히 쓰던 기본값과 짝을 맞춘 것이었는데,
    2026-08-24 부로 백엔드는 기본값이면 아예 뜨지 않는다(back/config.py 의 시크릿
    가드). 그래서 이 폴백은 **항상 틀린 키**가 됐다 — 폴백이 살아 있으면 전송이
    프레임마다 401 로 깨지고, 원인은 '키를 안 넣었다'인데 증상은 '인증 실패'로만
    보인다. 보낼 것도 없이 시작할 때 멈추는 편이 낫다.
    """
    monkeypatch.setattr(run_video, "PROJECT_ROOT", tmp_path)

    with pytest.raises(ValueError, match="INTERNAL_API_KEY"):
        run_video.load_internal_key("")


def test_missing_key_message_survives_the_windows_console(monkeypatch, tmp_path):
    """에러 메시지가 cp949 로 인코딩돼야 한다.

    이 파일은 mock-119 와 달리 stdout/stderr 인코딩을 고정하지 않는다. 윈도우
    기본 콘솔(cp949)에서 em-dash(—) 같은 문자를 print 하면 UnicodeEncodeError 로
    죽어서, '키가 없다'는 진짜 원인 대신 엉뚱한 예외만 보인다. 실제로 이 메시지를
    처음 쓸 때 em-dash 를 넣었다가 여기서 걸렸다.
    """
    monkeypatch.setattr(run_video, "PROJECT_ROOT", tmp_path)

    with pytest.raises(ValueError) as exc:
        run_video.load_internal_key("")
    str(exc.value).encode("cp949")  # 못 넣는 문자가 있으면 여기서 터진다


def test_dotenv_comments_and_blanks_are_ignored(monkeypatch, tmp_path):
    env = "# INTERNAL_API_KEY=commented-out\n\nINTERNAL_API_KEY=real\n"
    monkeypatch.setattr(run_video, "PROJECT_ROOT", write_env(tmp_path, env))

    assert run_video.load_internal_key("") == "real"


# ---------------------------------------------------------------- 미디어 경로


def test_explicit_media_root_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "from-env"))

    assert run_video.load_media_root(str(tmp_path / "from-flag")) == \
        tmp_path / "from-flag"


def test_media_root_comes_from_env(monkeypatch, tmp_path):
    """백엔드가 MEDIA_ROOT 를 쓰면 우리도 같은 곳에 써야 한다."""
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "shared"))
    monkeypatch.setattr(run_video, "PROJECT_ROOT", tmp_path)

    assert run_video.load_media_root("") == tmp_path / "shared"


def test_media_root_comes_from_dotenv(monkeypatch, tmp_path):
    monkeypatch.setattr(run_video, "PROJECT_ROOT",
                        write_env(tmp_path, f"MEDIA_ROOT={tmp_path / 'shared'}\n"))

    assert run_video.load_media_root("") == tmp_path / "shared"


def test_media_root_defaults_to_project_media(monkeypatch, tmp_path):
    monkeypatch.setattr(run_video, "PROJECT_ROOT", tmp_path)

    assert run_video.load_media_root("") == tmp_path / "media"


# ---------------------------------------------------------------- 프레임 저장


def _blank_frame():
    import numpy as np

    return np.zeros((8, 8, 3), dtype=np.uint8)


WHEN = datetime(2026, 8, 13, 14, 30, 5, 123456)


def test_save_frame_jpg_writes_under_media_root(tmp_path):
    """파일은 MEDIA_ROOT 아래 events/<날짜>/<카메라>_<시각>.jpg 로 떨어진다."""
    run_video.save_frame_jpg(_blank_frame(), tmp_path, cctv_no=7, when=WHEN)

    assert (tmp_path / "events" / "2026-08-13" / "7_143005_123456.jpg").exists()


def test_save_frame_jpg_returns_url_the_backend_serves(tmp_path):
    """반환값은 백엔드 서빙 형태 "/media/<상대경로>" 여야 한다.

    이 값이 event_media.media_url 에 저장되고 그대로 프론트의 <img src> 가 된다.
    접두어 없는 상대경로를 돌려주면 브라우저가 현재 페이지 기준으로 해석해 404 가
    나고, 119 신고 쪽은 대표 프레임을 못 찾아 이미지 없이 나간다.
    """
    url = run_video.save_frame_jpg(_blank_frame(), tmp_path, cctv_no=7, when=WHEN)

    assert url == "/media/events/2026-08-13/7_143005_123456.jpg"


# ---------------------------------------------------------------- 인자 검증


def test_send_requires_cctv_no():
    with pytest.raises(SystemExit):
        run_video.parse_args(["--video", "x.mp4", "--send"])


def test_dry_run_does_not_require_cctv_no():
    args = run_video.parse_args(["--video", "x.mp4"])

    assert args.send is False
