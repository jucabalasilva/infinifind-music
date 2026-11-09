"""
Sign-in with a Google account, read-only access to the user's YouTube data.

OAuth 2.0 for desktop apps ("installed apps"), as recommended by Google:
- the consent page opens in the user's own browser (Google blocks sign-in inside embedded
  web views) and comes back to the local server at http://127.0.0.1:<port>/oauth/callback;
- PKCE (S256) protects the authorization code, and a one-time `state` blocks forged callbacks;
- only the `youtube.readonly` scope is requested: the app can read playlists, never change them.

Tokens stay inside the local server process. They are never sent to the page, written to logs
or to generated files. The refresh token is remembered in the system keychain (macOS Keychain,
Windows Credential Manager, Secret Service) when the optional `keyring` package is installed;
otherwise the user signs in again on every launch. Signing out revokes the token at Google.

The OAuth client (client ID) comes from google_client.json in the app-data folder (imported by
the user from Google Cloud) or, in packaged releases, from the same file inside the package.
"""

import base64
import contextlib
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.parse

from . import net, paths

SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - endpoint URL, not a password
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
CLIENT_FILE_NAME = "google_client.json"
PENDING_SECONDS = 600  # a sign-in started more than 10 minutes ago is no longer accepted
KEYRING_SERVICE = "InfiniFind Music"
KEYRING_USER = "google-refresh-token"


class AuthError(Exception):
    """Sign-in problem; `code` is translated by the interface (err_<code>)."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


# ---------- OAuth client (client ID) ----------

def _client_paths():
    return [os.path.join(paths.data_dir(), CLIENT_FILE_NAME),
            os.path.join(paths.PACKAGE_DIR, CLIENT_FILE_NAME)]


def parse_client(data):
    """Accepts the JSON downloaded from Google Cloud ({"installed": {...}}) or a flat object."""
    if not isinstance(data, dict):
        return None
    info = data.get("installed", data)
    if not isinstance(info, dict):
        return None
    client_id = str(info.get("client_id", ""))
    if not client_id.endswith(".apps.googleusercontent.com"):
        return None
    return {"client_id": client_id, "client_secret": str(info.get("client_secret", ""))}


def load_client():
    for path in _client_paths():
        try:
            with open(path, encoding="utf-8") as f:
                client = parse_client(json.load(f))
        except (OSError, ValueError):
            continue
        if client:
            return client
    return None


def import_client(source_path):
    """Validates the JSON chosen by the user and saves a copy readable only by them."""
    try:
        with open(source_path, encoding="utf-8") as f:
            client = parse_client(json.load(f))
    except (OSError, ValueError):
        client = None
    if not client:
        raise AuthError("client_invalid")
    target = os.path.join(paths.data_dir(), CLIENT_FILE_NAME)
    fd = os.open(target + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"installed": client}, f)
    os.replace(target + ".tmp", target)
    return client


# ---------- Refresh token storage (system keychain) ----------

def _keyring():
    if os.environ.get("INFINIFIND_NO_KEYRING") == "1":  # tests and test servers never touch it
        return None
    try:
        import keyring  # optional dependency ("app" extra)
    except ImportError:
        return None
    return keyring


def _keyring_get():
    kr = _keyring()
    if kr is None:
        return None
    try:
        return kr.get_password(KEYRING_SERVICE, KEYRING_USER)
    except Exception:  # no usable keychain backend
        return None


def _keyring_set(token):
    kr = _keyring()
    if kr is None:
        return False
    try:
        kr.set_password(KEYRING_SERVICE, KEYRING_USER, token)
        return True
    except Exception:
        return False


def _keyring_delete():
    kr = _keyring()
    if kr is None:
        return
    try:
        kr.delete_password(KEYRING_SERVICE, KEYRING_USER)
    except Exception:  # nothing stored, or no backend
        return


# ---------- PKCE ----------

def new_verifier():
    return secrets.token_urlsafe(64)  # 86 URL-safe characters (RFC 7636 allows 43-128)


def challenge_for(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ---------- Session ----------

class Session:
    """The signed-in account of this app run (one user, one computer)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._pending = {}  # state -> {"verifier", "redirect_uri", "lang", "created"}
        self._access_token = None
        self._expires_at = 0.0
        self._refresh_token = None
        self._channel = None
        self._restored = False

    # -- sign-in --

    def start_login(self, redirect_uri, lang="en-US"):
        """Returns the Google consent URL to open in the user's browser."""
        client = load_client()
        if not client:
            raise AuthError("not_configured")
        state = secrets.token_urlsafe(32)
        verifier = new_verifier()
        with self._lock:
            now = time.time()
            self._pending = {s: p for s, p in self._pending.items() if now - p["created"] < PENDING_SECONDS}
            self._pending[state] = {"verifier": verifier, "redirect_uri": redirect_uri,
                                    "lang": lang, "created": now}
        query = {
            "client_id": client["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "state": state,
            "code_challenge": challenge_for(verifier),
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }
        return AUTH_URL + "?" + urllib.parse.urlencode(query)

    def pending_lang(self, state):
        with self._lock:
            pending = self._pending.get(state)
        return pending["lang"] if pending else "en-US"

    def finish_login(self, state, code):
        """Handles the callback: checks `state`, exchanges the code and loads the channel name."""
        with self._lock:
            pending = self._pending.pop(state, None) if state else None
        if not pending or time.time() - pending["created"] >= PENDING_SECONDS:
            raise AuthError("invalid_state")
        if not code:
            raise AuthError("denied")
        client = load_client()
        if not client:
            raise AuthError("not_configured")
        try:
            tokens = net.request_json(TOKEN_URL, form={
                "client_id": client["client_id"],
                "client_secret": client["client_secret"],
                "code": code,
                "code_verifier": pending["verifier"],
                "grant_type": "authorization_code",
                "redirect_uri": pending["redirect_uri"],
            })
        except (net.HttpError, OSError, ValueError):
            raise AuthError("exchange_failed") from None
        if tokens.get("scope") and SCOPE not in tokens["scope"].split():
            raise AuthError("denied")  # the user unticked the YouTube permission
        self._store(tokens)
        if self._refresh_token:
            _keyring_set(self._refresh_token)
        self._load_channel()

    def _store(self, tokens):
        with self._lock:
            self._access_token = tokens.get("access_token")
            self._expires_at = time.time() + float(tokens.get("expires_in", 3600)) - 60
            if tokens.get("refresh_token"):
                self._refresh_token = tokens["refresh_token"]

    def _load_channel(self):
        try:
            data = self.api_get(CHANNELS_URL, {"part": "snippet", "mine": "true"})
            items = data.get("items") or []
            self._channel = items[0]["snippet"]["title"] if items else ""
        except (AuthError, net.HttpError, OSError, ValueError, KeyError):
            self._channel = ""

    # -- using the token --

    def _restore(self):
        """Loads the remembered refresh token once, at first use."""
        if self._restored:
            return
        self._restored = True
        if not load_client():  # not set up: don't even open the keychain (it may ask the user)
            return
        token = _keyring_get()
        if token:
            self._refresh_token = token
            try:
                self._refresh()
                self._load_channel()
            except AuthError:
                self._refresh_token = None

    def _refresh(self):
        client = load_client()
        if not client or not self._refresh_token:
            raise AuthError("not_signed_in")
        try:
            tokens = net.request_json(TOKEN_URL, form={
                "client_id": client["client_id"],
                "client_secret": client["client_secret"],
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            })
        except net.HttpError as error:
            if error.status in (400, 401):  # revoked or expired (7 days while the Google app is in Testing)
                self._forget()
            raise AuthError("expired") from None
        except (OSError, ValueError):
            raise AuthError("network") from None
        self._store(tokens)

    def access_token(self):
        self._restore()
        if self._access_token and time.time() < self._expires_at:
            return self._access_token
        self._refresh()
        return self._access_token

    def api_get(self, url, params):
        """GET on the YouTube Data API with the user's token (read-only scope)."""
        query = urllib.parse.urlencode(params)
        return net.request_json(f"{url}?{query}", headers={"Authorization": "Bearer " + self.access_token()})

    # -- status / sign-out --

    def status(self):
        """What the interface may know. Never includes tokens."""
        self._restore()
        signed_in = bool(self._refresh_token or (self._access_token and time.time() < self._expires_at))
        return {
            "configured": load_client() is not None,
            "signed_in": signed_in,
            "channel": self._channel if signed_in else None,
            "remembered": signed_in and _keyring() is not None,
        }

    def logout(self):
        """Revokes the token at Google and forgets it here and in the keychain."""
        token = self._refresh_token or self._access_token
        if token:
            # Already revoked or offline: the token is still forgotten locally below.
            with contextlib.suppress(net.HttpError, OSError, ValueError):
                net.request_json(REVOKE_URL, form={"token": token}, method="POST")
        self._forget()

    def _forget(self):
        with self._lock:
            self._access_token = None
            self._expires_at = 0.0
            self._refresh_token = None
            self._channel = None
        _keyring_delete()


session = Session()
