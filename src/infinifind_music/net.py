"""
HTTPS requests for the Google/YouTube APIs, using only the standard library.

Unlike the public lookups in finder.py, these requests carry secrets (OAuth codes and
tokens), so they never fall back to running curl: a token on a command line can be seen
by other programs on the computer. When Python has no CA certificates (common with the
python.org installer on macOS), the operating system's bundle is used instead.
"""

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "infinifind-music/1.0"
_SYSTEM_BUNDLES = (
    "/etc/ssl/cert.pem",  # macOS
    "/etc/ssl/certs/ca-certificates.crt",  # Debian/Ubuntu
    "/etc/pki/tls/certs/ca-bundle.crt",  # Fedora/RHEL
)
_context = None


class HttpError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.body = body


def ssl_context():
    """Default certificate checks; adds the system CA bundle when Python has none of its own."""
    global _context
    if _context is None:
        context = ssl.create_default_context()
        if not context.cert_store_stats().get("x509_ca"):
            for bundle in _SYSTEM_BUNDLES:
                if os.path.isfile(bundle):
                    context.load_verify_locations(cafile=bundle)
                    break
        _context = context
    return _context


def request_json(url, form=None, headers=None, method=None, timeout=20):
    """Sends a request to an https:// URL and returns the decoded JSON body (or {} if empty).
    `form` is sent as application/x-www-form-urlencoded. Raises HttpError on HTTP errors."""
    if not url.startswith("https://"):
        raise ValueError("only https:// URLs are allowed")
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    all_headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, method=method, headers=all_headers)  # noqa: S310 - https only
    try:
        context = ssl_context()
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:  # noqa: S310  # nosec B310
            raw = resp.read()
    except urllib.error.HTTPError as error:
        raise HttpError(error.code, error.read().decode("utf-8", "replace")) from None
    return json.loads(raw.decode("utf-8")) if raw.strip() else {}
