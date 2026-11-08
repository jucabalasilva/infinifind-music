"""Security checks of the local server (no network access needed)."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from infinifind_music import server


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


def test_open_only_inside_downloads(base_url):
    status, _, body = request(base_url + "/api/open", {"path": "~/Downloads/../.ssh/config"}, api_headers())
    assert status == 400 and json.loads(body)["error"] == "open_only_downloads"


def test_missing_csv_is_reported(base_url):
    status, _, body = request(base_url + "/api/find", {"csv": "/nope.csv"}, api_headers())
    assert status == 400 and json.loads(body)["error"] == "csv_not_found"
