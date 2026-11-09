"""Google sign-in (OAuth 2.0 + PKCE) with Google simulated: no network, no real keychain."""

import base64
import hashlib
import json
import os
import stat
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from infinifind_music import net, paths, server, youtube_auth

CLIENT = {"installed": {"client_id": "123-abc.apps.googleusercontent.com",
                        "client_secret": "not-really-secret"}}


class FakeKeyring:
    def __init__(self):
        self.stored = {}

    def get_password(self, service, user):
        return self.stored.get((service, user))

    def set_password(self, service, user, value):
        self.stored[(service, user)] = value

    def delete_password(self, service, user):
        self.stored.pop((service, user), None)


class FakeGoogle:
    """Answers the token, revoke and channels endpoints like Google would."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, form=None, headers=None, method=None, timeout=20):
        self.calls.append((url, form, headers))
        if url == youtube_auth.TOKEN_URL and form["grant_type"] == "authorization_code":
            if form["code"] != "good-code":
                raise net.HttpError(400, "invalid_grant")
            return {"access_token": "ACCESS-1", "refresh_token": "REFRESH-1", "expires_in": 3599,
                    "scope": youtube_auth.SCOPE, "token_type": "Bearer"}
        if url == youtube_auth.TOKEN_URL and form["grant_type"] == "refresh_token":
            return {"access_token": "ACCESS-2", "expires_in": 3599, "scope": youtube_auth.SCOPE}
        if url.startswith(youtube_auth.CHANNELS_URL):
            assert headers["Authorization"].startswith("Bearer ACCESS-")
            return {"items": [{"snippet": {"title": "My Channel"}}]}
        if url == youtube_auth.REVOKE_URL:
            return {}
        raise AssertionError("unexpected request: " + url)


@pytest.fixture
def google(tmp_path, monkeypatch):
    monkeypatch.setenv("INFINIFIND_DATA_DIR", str(tmp_path / "data"))
    fake = FakeGoogle()
    keyring = FakeKeyring()
    monkeypatch.setattr(net, "request_json", fake)
    monkeypatch.setattr(youtube_auth, "_keyring", lambda: keyring)
    monkeypatch.setattr(youtube_auth, "session", youtube_auth.Session())
    client_file = tmp_path / "client_secret_downloaded.json"
    client_file.write_text(json.dumps(CLIENT), encoding="utf-8")
    youtube_auth.import_client(str(client_file))
    fake.keyring = keyring
    return fake


def query_of(url):
    return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}


def test_client_file_is_validated_and_saved_privately(google, tmp_path):
    saved = os.path.join(paths.data_dir(), youtube_auth.CLIENT_FILE_NAME)
    assert stat.S_IMODE(os.stat(saved).st_mode) == 0o600
    assert youtube_auth.load_client()["client_id"] == CLIENT["installed"]["client_id"]
    bad = tmp_path / "bad.json"
    bad.write_text('{"installed": {"client_id": "someone-else"}}', encoding="utf-8")
    with pytest.raises(youtube_auth.AuthError) as error:
        youtube_auth.import_client(str(bad))
    assert error.value.code == "client_invalid"


def test_login_url_uses_pkce_state_and_read_only_scope(google):
    url = youtube_auth.session.start_login("http://127.0.0.1:5555/oauth/callback", "pt-BR")
    q = query_of(url)
    assert url.startswith(youtube_auth.AUTH_URL)
    assert q["scope"] == "https://www.googleapis.com/auth/youtube.readonly"
    assert q["code_challenge_method"] == "S256" and q["response_type"] == "code"
    assert q["redirect_uri"] == "http://127.0.0.1:5555/oauth/callback"
    verifier = youtube_auth.session._pending[q["state"]]["verifier"]
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert q["code_challenge"] == expected
    assert youtube_auth.session.pending_lang(q["state"]) == "pt-BR"


def test_wrong_or_reused_state_is_rejected(google):
    url = youtube_auth.session.start_login("http://127.0.0.1:5555/oauth/callback")
    state = query_of(url)["state"]
    with pytest.raises(youtube_auth.AuthError) as error:
        youtube_auth.session.finish_login("forged-state", "good-code")
    assert error.value.code == "invalid_state"
    youtube_auth.session.finish_login(state, "good-code")
    with pytest.raises(youtube_auth.AuthError):  # a state works only once
        youtube_auth.session.finish_login(state, "good-code")


def test_successful_login_remembers_refresh_token_and_hides_tokens(google):
    url = youtube_auth.session.start_login("http://127.0.0.1:5555/oauth/callback")
    youtube_auth.session.finish_login(query_of(url)["state"], "good-code")
    exchange = next(form for u, form, _ in google.calls if u == youtube_auth.TOKEN_URL)
    assert exchange["code_verifier"] and exchange["grant_type"] == "authorization_code"
    status = youtube_auth.session.status()
    assert status == {"configured": True, "signed_in": True, "channel": "My Channel", "remembered": True}
    assert "REFRESH-1" not in json.dumps(status) and "ACCESS-1" not in json.dumps(status)
    assert google.keyring.get_password(youtube_auth.KEYRING_SERVICE, youtube_auth.KEYRING_USER) == "REFRESH-1"


def test_remembered_login_is_restored_on_next_launch(google):
    google.keyring.set_password(youtube_auth.KEYRING_SERVICE, youtube_auth.KEYRING_USER, "REFRESH-1")
    fresh = youtube_auth.Session()
    assert fresh.status()["signed_in"] is True
    assert fresh.access_token() == "ACCESS-2"


def test_logout_revokes_and_forgets(google):
    url = youtube_auth.session.start_login("http://127.0.0.1:5555/oauth/callback")
    youtube_auth.session.finish_login(query_of(url)["state"], "good-code")
    youtube_auth.session.logout()
    revoke = [form for u, form, _ in google.calls if u == youtube_auth.REVOKE_URL]
    assert revoke == [{"token": "REFRESH-1"}]
    assert youtube_auth.session.status()["signed_in"] is False
    assert google.keyring.get_password(youtube_auth.KEYRING_SERVICE, youtube_auth.KEYRING_USER) is None


def test_not_configured_blocks_login(tmp_path, monkeypatch):
    monkeypatch.setenv("INFINIFIND_DATA_DIR", str(tmp_path / "empty"))
    monkeypatch.setattr(youtube_auth, "_client_paths", lambda: [str(tmp_path / "missing.json")])
    with pytest.raises(youtube_auth.AuthError) as error:
        youtube_auth.Session().start_login("http://127.0.0.1:1/oauth/callback")
    assert error.value.code == "not_configured"


# ---------- through the local server ----------

@pytest.fixture
def base_url(google, monkeypatch):
    monkeypatch.setattr(server.webbrowser, "open", lambda url: google.calls.append(("browser", url, None)))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def call(url, data=None, token=True):
    headers = {"X-Token": server.TOKEN} if token else {}
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def test_full_sign_in_through_the_server(base_url, google):
    status, _ = call(base_url + "/api/account/login", {"lang": "es"})
    assert status == 200
    browser_url = next(u for kind, u, _ in google.calls if kind == "browser")
    q = query_of(browser_url)
    assert q["redirect_uri"] == base_url + "/oauth/callback"

    # A forged callback (wrong state) is refused; its language is unknown, so the page is in English.
    status, page = call(base_url + "/oauth/callback?state=forged&code=good-code", token=False)
    assert status == 400 and "Sign-in failed" in page

    # Google sends the browser back with the right state.
    status, page = call(f"{base_url}/oauth/callback?state={q['state']}&code=good-code", token=False)
    assert status == 200 and "Sesión iniciada" in page

    status, body = call(base_url + "/api/account")
    assert status == 200 and json.loads(body)["channel"] == "My Channel"
    assert "ACCESS" not in body and "REFRESH" not in body

    status, body = call(base_url + "/api/account/logout", {})
    assert status == 200 and json.loads(body)["signed_in"] is False


def test_account_api_requires_the_interface_token(base_url):
    assert call(base_url + "/api/account", token=False)[0] == 403


def test_user_denied_consent(base_url, google):
    call(base_url + "/api/account/login", {})
    state = query_of(next(u for kind, u, _ in google.calls if kind == "browser"))["state"]
    status, _ = call(f"{base_url}/oauth/callback?state={state}&error=access_denied", token=False)
    assert status == 400
    assert json.loads(call(base_url + "/api/account")[1])["signed_in"] is False
