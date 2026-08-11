"""CLI 배선 테스트 — 설정을 어디서 읽는가.

백엔드와 같은 값을 봐야 하는 것이 둘 있다.
- INTERNAL_API_KEY : 다르면 401
- MEDIA_ROOT       : 다르면 프레임 JPG 를 저장해도 GET /media/<path> 가 404
"""
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


def test_falls_back_to_the_backend_default(monkeypatch, tmp_path):
    """back/config.py 의 기본값과 같아야 조용히 401 이 나지 않는다."""
    monkeypatch.setattr(run_video, "PROJECT_ROOT", tmp_path)

    assert run_video.load_internal_key("") == "dev-internal-key"


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


# ---------------------------------------------------------------- 인자 검증


def test_send_requires_cctv_no():
    with pytest.raises(SystemExit):
        run_video.parse_args(["--video", "x.mp4", "--send"])


def test_dry_run_does_not_require_cctv_no():
    args = run_video.parse_args(["--video", "x.mp4"])

    assert args.send is False
