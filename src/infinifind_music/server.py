"""
Local server for the InfiniFind Music interface (web/ui.html). Runs the finder and
availability modules and lets the page follow their progress.

Usage:
    infinifind-web                     (opens the interface in your browser)
    infinifind-web --port 9000 --no-browser
    (or: python -m infinifind_music.server ...)

The desktop app (app.py) uses this same server inside a native window.
Uses only the Python standard library. Only accepts connections from this computer.
"""

import argparse
import glob
import hmac
import json
import os
import secrets
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import i18n, paths

DOWNLOADS = paths.DOWNLOADS
PAGE = os.path.join(paths.WEB_DIR, "ui.html")
# Folder that contains the package, so "python -m infinifind_music..." works in subprocesses
# even when the package is not installed.
SRC_DIR = os.path.dirname(paths.PACKAGE_DIR)
MAX_BODY = 64 * 1024  # maximum request body (bytes)

# Secret token created on every run. Only whoever opened the interface through the
# full address (with ?t=...) can use it; other programs on this computer cannot.
TOKEN = secrets.token_urlsafe(32)

# Page security policy: only the app's own code, nothing loaded from outside.
CSP = ("default-src 'none'; script-src 'nonce-{nonce}'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; "
       "frame-ancestors 'none'")


def start_url(port):
    return f"http://127.0.0.1:{port}/?t={TOKEN}"


class Task:
    """One script run at a time, with its log kept for the page to read."""

    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.kind = ""
        self.log = []
        self.files = []

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, kind, command):
        with self.lock:
            if self.running():
                return False
            self.kind, self.log, self.files = kind, [], []
            env = dict(os.environ, INFINIFIND_MACHINE="1", PYTHONIOENCODING="utf-8")
            env["PYTHONPATH"] = os.pathsep.join(p for p in (SRC_DIR, env.get("PYTHONPATH")) if p)
            self.proc = subprocess.Popen(
                [sys.executable, "-u", "-m", *command], cwd=SRC_DIR, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", bufsize=1)
        threading.Thread(target=self._read_output, daemon=True).start()
        return True

    def _read_output(self):
        for line in self.proc.stdout:
            line = line.rstrip("\n")
            if line.startswith("@@file "):
                self.files.append(line[7:].strip())
            else:
                self.log.append(line)
        self.proc.wait()

    def stop(self):
        if self.running():
            self.proc.terminate()

    def state(self):
        code = None if self.proc is None else self.proc.poll()
        return {
            "kind": self.kind,
            "running": self.running(),
            "code": code,
            "log": self.log[-400:],
            "files": [f for f in self.files if os.path.exists(f)],
        }


task = Task()


def list_csvs():
    patterns = [os.path.join(DOWNLOADS, "Takeout", "**", "*.csv"), os.path.join(DOWNLOADS, "*.csv")]
    found = sorted({c for p in patterns for c in glob.glob(p, recursive=True)})
    return [{"path": c, "name": os.path.relpath(c, DOWNLOADS)} for c in found
            if not c.endswith("playlists.csv")]  # playlists.csv is only the playlist index


def list_txts():
    return sorted(glob.glob(os.path.join(DOWNLOADS, "*.txt")), key=os.path.getmtime, reverse=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep the terminal clean

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code, status, **extra):
        # The page translates the error code into the chosen language.
        self._json({"error": code, **extra}, status)

    def _security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")

    def _token_ok(self):
        return hmac.compare_digest(self.headers.get("X-Token", ""), TOKEN)

    def _origin_ok(self):
        # Blocks requests coming from other websites open in the browser (CSRF / DNS rebinding).
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        return (host.startswith(("127.0.0.1:", "localhost:"))
                and (origin is None or origin == f"http://{host}"))

    def do_GET(self):
        if not self._origin_ok():
            return self._error("access_denied", 403)
        url = urlsplit(self.path)
        if url.path == "/":
            token = parse_qs(url.query).get("t", [""])[0]
            if not hmac.compare_digest(token, TOKEN):
                message = "Open the interface using the full address shown in the terminal."
                return self._json({"error": message}, 403)
            nonce = secrets.token_urlsafe(16)
            with open(PAGE, encoding="utf-8") as f:
                body = f.read().replace("__NONCE__", nonce).replace("__TOKEN__", TOKEN).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Security-Policy", CSP.format(nonce=nonce))
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)
            return
        if not self._token_ok():
            return self._error("access_denied", 403)
        if self.path == "/api/files":
            self._json({"csvs": list_csvs(), "txts": list_txts()})
        elif self.path == "/api/state":
            self._json(task.state())
        else:
            self._error("not_found", 404)

    def do_POST(self):
        if (not self._origin_ok() or not self._token_ok()
                or self.headers.get("Content-Type") != "application/json"):
            return self._error("access_denied", 403)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._error("invalid_request", 400)
        if length > MAX_BODY:
            return self._error("too_large", 413)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._error("invalid_request", 400)
        if not isinstance(data, dict):
            return self._error("invalid_request", 400)
        lang = i18n.normalize(data.get("lang"))

        if self.path == "/api/find":
            csv_path = os.path.expanduser(str(data.get("csv", "")))
            if not os.path.isfile(csv_path):
                return self._error("csv_not_found", 400)
            output = os.path.basename(str(data.get("output") or "my_songs.html"))
            if not output.endswith(".html"):
                output += ".html"
            existing = [n for n in (output, output[:-5] + ".txt")
                        if os.path.exists(os.path.join(DOWNLOADS, n))]
            if existing and not data.get("overwrite"):
                return self._error("exists", 409, existing=existing)
            command = ["infinifind_music.finder", csv_path, "--output", output, "--lang", lang]
            mode = data.get("mode")
            if mode == "youtube":
                command.append("--youtube-only")
            elif mode == "search":
                command.append("--no-itunes")
            if data.get("exclude"):
                command += ["--exclude-artists", str(data["exclude"])]
            ok = task.start("find", command)
        elif self.path == "/api/check":
            path = os.path.expanduser(str(data.get("list", "")))
            if not os.path.isfile(path):
                return self._error("list_not_found", 400)
            ok = task.start("check", ["infinifind_music.availability", path, "--lang", lang])
        elif self.path == "/api/stop":
            task.stop()
            return self._json({"ok": True})
        elif self.path == "/api/open":
            path = os.path.realpath(os.path.expanduser(str(data.get("path", ""))))
            # Only opens files inside the Downloads folder.
            if not path.startswith(os.path.realpath(DOWNLOADS) + os.sep) or not os.path.isfile(path):
                return self._error("open_only_downloads", 400)
            if os.name == "nt":
                os.startfile(path)  # noqa: S606 - no shell; path already checked to be inside Downloads
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])
            return self._json({"ok": True})
        else:
            return self._error("not_found", 404)

        if not ok:
            return self._error("busy", 409)
        self._json({"ok": True})


def main():
    p = argparse.ArgumentParser(description="Web interface for the InfiniFind Music tools.")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    args = p.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = start_url(args.port)
    print(f"Interface running at {url}  (Ctrl+C to quit)", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        task.stop()
        print("\nInterface closed.")


if __name__ == "__main__":
    main()
