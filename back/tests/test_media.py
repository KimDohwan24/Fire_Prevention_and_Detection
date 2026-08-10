"""미디어 파일 서빙 테스트 — GET /media/<path:filename>.

event_media.media_url 은 "/media/events/12/frame_001.jpg" 형태로 저장된다.
그 값을 프론트가 <img src> 에 그대로 넣었을 때 실제 파일이 내려와야 한다.

인증은 일부러 걸지 않는다: 브라우저의 <img>/<video> 태그는 JWT 헤더를
붙일 수 없고, 서명 URL 은 이 프로젝트 범위 밖이다.
"""
import pytest

import config


@pytest.fixture()
def media_root(tmp_path, monkeypatch):
    """MEDIA_ROOT 를 테스트용 임시 디렉터리로 바꾼다.

    라우트가 import 시점이 아니라 '요청 시점'에 config.MEDIA_ROOT 를 읽어야
    이 교체가 먹힌다 (app 픽스처가 세션 스코프라 앱은 이미 만들어져 있다).
    """
    monkeypatch.setattr(config, "MEDIA_ROOT", str(tmp_path))
    return tmp_path


def _write(root, relpath: str, data: bytes):
    """MEDIA_ROOT 아래에 파일을 하나 만든다 (중간 디렉터리 포함)."""
    path = root.joinpath(*relpath.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# ---------- 정상 서빙 ----------

def test_serve_existing_file_returns_exact_bytes(client, media_root):
    """MEDIA_ROOT 안의 파일은 바이트 그대로 200 으로 내려온다."""
    body = b"\x89PNG\r\n\x1a\n-fake-frame-bytes"
    _write(media_root, "frame.png", body)

    r = client.get("/media/frame.png")
    assert r.status_code == 200
    assert r.data == body


def test_serve_nested_path_matches_media_url_format(client, media_root):
    """media_url 에 저장되는 중첩 경로(events/<no>/<file>)가 그대로 열린다."""
    body = b"jpeg-bytes-here"
    _write(media_root, "events/12/frame_001.jpg", body)

    r = client.get("/media/events/12/frame_001.jpg")
    assert r.status_code == 200
    assert r.data == body


def test_serve_media_requires_no_auth_header(client, media_root):
    """토큰 없이도 200. (같은 조건에서 일반 API 는 401 이라는 대비까지 확인)"""
    _write(media_root, "events/7/clip.mp4", b"mp4-bytes")

    r = client.get("/media/events/7/clip.mp4")
    assert r.status_code == 200
    assert "Authorization" not in r.request.headers

    assert client.get("/api/cctvs").status_code == 401


# ---------- 없는 파일 ----------

def test_missing_file_returns_404_common_error_shape(client, media_root):
    """없는 파일은 404 + 공통 에러 형식 {code, message}."""
    r = client.get("/media/events/99/nope.jpg")
    assert r.status_code == 404
    body = r.get_json()
    assert set(body.keys()) == {"code", "message"}
    assert body["code"] == "NOT_FOUND"


# ---------- 경로 탈출 (path traversal) ----------

def test_traversal_with_dotdot_does_not_serve_outside_file(client, media_root):
    """../ 로 MEDIA_ROOT 바깥 파일을 읽으려는 시도는 내용을 내주지 않는다."""
    secret = media_root.parent / "secret.txt"
    secret.write_bytes(b"TOP-SECRET-CONTENT")

    r = client.get("/media/../secret.txt")
    assert r.status_code != 200
    assert b"TOP-SECRET-CONTENT" not in r.data


def test_traversal_with_encoded_dotdot_does_not_serve_outside_file(client, media_root):
    """URL 인코딩된 ..%2f 도 마찬가지로 막힌다."""
    secret = media_root.parent / "secret.txt"
    secret.write_bytes(b"TOP-SECRET-CONTENT")

    r = client.get("/media/..%2fsecret.txt")
    assert r.status_code != 200
    assert b"TOP-SECRET-CONTENT" not in r.data


def test_traversal_deep_and_absolute_paths_are_rejected(client, media_root):
    """OS 절대경로/여러 단계 ../ 도 파일 내용을 흘리지 않는다."""
    for path in ("/media/../../etc/passwd",
                 "/media/..%2f..%2fetc%2fpasswd",
                 "/media//etc/passwd",
                 "/media/C:/Windows/win.ini"):
        r = client.get(path)
        assert r.status_code != 200, f"{path} 가 200 으로 열렸다"
        assert b"root:" not in r.data
        assert b"[fonts]" not in r.data
