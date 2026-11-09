"""Security checks of the local server (no network access needed)."""

import json
import os
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from infinifind_music import paths, picker, server


@pytest.fixture(scope="module")
def base_url():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def request(url, data=None, headers=None):
    body = None if data is None else (data if isinstance(data, bytes) else json.dumps(data).encode())
    req = urllib.request.Request(url, data=body, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, dict(resp.headers), resp.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read().decode()


def api_headers(**extra):
    return {"X-Token": server.TOKEN, "Content-Type": "application/json", **extra}


def test_page_requires_token(base_url):
    assert request(base_url + "/")[0] == 403
    assert request(base_url + "/?t=wrong")[0] == 403


def test_page_with_token_has_security_headers(base_url):
    status, headers, body = request(f"{base_url}/?t={server.TOKEN}")
    assert status == 200
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "__TOKEN__" not in body and "__NONCE__" not in body


def test_api_requires_token(base_url):
    assert request(base_url + "/api/state")[0] == 403
    assert request(base_url + "/api/state", headers={"X-Token": server.TOKEN})[0] == 200


def test_post_from_another_site_is_rejected(base_url):
    status, _, _ = request(base_url + "/api/stop", {}, api_headers(Origin="https://evil.example"))
    assert status == 403


def test_post_needs_json(base_url):
    headers = {"X-Token": server.TOKEN, "Content-Type": "text/plain"}
    assert request(base_url + "/api/stop", b"{}", headers)[0] == 403


def test_large_body_is_rejected(base_url):
    assert request(base_url + "/api/stop", b"a" * 70_000, api_headers())[0] == 413


def test_open_only_inside_allowed_folders(base_url):
    status, _, body = request(base_url + "/api/open", {"path": "~/Downloads/../.ssh/config"}, api_headers())
    assert status == 400 and json.loads(body)["error"] == "open_not_allowed"


def test_missing_csv_is_reported(base_url):
    status, _, body = request(base_url + "/api/find", {"csv": "/nope.csv"}, api_headers())
    assert status == 400 and json.loads(body)["error"] == "csv_not_found"


def test_output_folder_comes_only_from_the_dialog(base_url, tmp_path, monkeypatch):
    chosen = tmp_path / "my results"
    chosen.mkdir()
    # Simulates the user picking a folder in the native dialog.
    monkeypatch.setattr(picker, "_native", lambda kind, start: str(chosen))
    status, _, body = request(base_url + "/api/pick", {"kind": "folder"}, api_headers())
    assert status == 200 and json.loads(body)["path"] == str(chosen.resolve())
    assert paths.output_dir() == str(chosen.resolve())

    # Files in the chosen folder can be opened; elsewhere they still can't.
    (chosen / "result.txt").write_text("x", encoding="utf-8")
    assert server.is_inside(str((chosen / "result.txt").resolve()), server.allowed_roots())
    assert not server.is_inside(str(tmp_path.resolve() / "other.txt"), server.allowed_roots())

    # Going back to Downloads.
    status, _, body = request(base_url + "/api/output/reset", {}, api_headers())
    downloads = os.path.realpath(paths.DOWNLOADS)
    assert status == 200 and json.loads(body)["output_dir"] == downloads == paths.output_dir()


def test_cancelled_dialog_changes_nothing(base_url, monkeypatch):
    before = paths.output_dir()
    monkeypatch.setattr(picker, "_native", lambda kind, start: None)
    status, _, body = request(base_url + "/api/pick", {"kind": "folder"}, api_headers())
    assert status == 200 and json.loads(body)["path"] is None
    assert paths.output_dir() == before


def test_separate_list_check_was_removed(base_url):
    # The availability check now runs while the page is generated; there is no separate route.
    status, _, body = request(base_url + "/api/check", {"list": "links.txt"}, api_headers())
    assert status == 404 and json.loads(body)["error"] == "not_found"
    status, _, _ = request(base_url + "/api/pick", {"kind": "list"}, api_headers())
    assert status == 400


def test_unknown_dialog_kind_is_rejected(base_url):
    status, _, _ = request(base_url + "/api/pick", {"kind": "anything"}, api_headers())
    assert status == 400
