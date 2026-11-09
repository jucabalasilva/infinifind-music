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
import contextlib
import csv
import glob
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import unicodedata
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import finder, i18n, net, paths, picker, youtube_api, youtube_auth

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
    """One task at a time: an optional preparation step (run inside this process, e.g. reading
    playlists with the user's token, which must never reach a subprocess) followed by one or
    more script runs. The log is kept for the page to read."""

    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.worker = None
        self.kind = ""
        self.log = []
        self.files = []
        self.code = None
        self.stopped = False
        self.cleanup = []  # temporary files deleted when the task ends

    def running(self):
        return self.worker is not None and self.worker.is_alive()

    def start(self, kind, commands):
        """`commands` is a list of module commands, or a callable(log) that prepares and returns
        that list. Returns False if another task is still running."""
        with self.lock:
            if self.running():
                return False
            self.kind, self.log, self.files, self.code, self.stopped = kind, [], [], None, False
            self.cleanup = []
            self.worker = threading.Thread(target=self._run, args=(commands,), daemon=True)
            self.worker.start()
        return True

    def _run(self, commands):
        code = 0
        try:
            if callable(commands):
                commands = commands(self.log.append)
            for command in commands:
                if self.stopped:
                    code = -1
                    break
                code = self._run_one(command)
                if code != 0:
                    break
        except youtube_auth.AuthError as error:
            self.log.append("@@error " + error.code)
            code = 1
        except Exception as error:  # preparation failed (network, quota...)
            self.log.append(str(error))
            code = 1
        finally:
            for path in self.cleanup:
                with contextlib.suppress(OSError):
                    os.remove(path)
        self.code = -1 if self.stopped else code

    def _run_one(self, command):
        env = dict(os.environ, INFINIFIND_MACHINE="1", PYTHONIOENCODING="utf-8")
        env["PYTHONPATH"] = os.pathsep.join(p for p in (SRC_DIR, env.get("PYTHONPATH")) if p)
        self.proc = subprocess.Popen(
            [sys.executable, "-u", "-m", *command], cwd=SRC_DIR, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", bufsize=1)
        for line in self.proc.stdout:
            line = line.rstrip("\n")
            if line.startswith("@@file "):
                self.files.append(line[7:].strip())
            else:
                self.log.append(line)
        return self.proc.wait()

    def stop(self):
        self.stopped = True
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()

    def wait(self, timeout=None):
        if self.worker is not None:
            self.worker.join(timeout)

    def state(self):
        return {
            "kind": self.kind,
            "running": self.running(),
            "code": None if self.running() else self.code,
            "log": self.log[-400:],
            "files": [f for f in self.files if os.path.exists(f)],
        }


task = Task()


def list_csvs():
    patterns = [os.path.join(DOWNLOADS, "Takeout", "**", "*.csv"), os.path.join(DOWNLOADS, "*.csv")]
    found = sorted({c for p in patterns for c in glob.glob(p, recursive=True)})
    return [{"path": c, "name": os.path.relpath(c, DOWNLOADS)} for c in found
            if not c.endswith("playlists.csv")]  # playlists.csv is only the playlist index


_picker_lock = threading.Lock()


def allowed_roots():
    """Folders the interface may write to and open files from: Downloads and the output folder
    the user chose in the folder dialog. Never a path that only came in a request."""
    return {os.path.realpath(DOWNLOADS), paths.output_dir()}


def is_inside(path, roots):
    return any(path == root or path.startswith(root + os.sep) for root in roots)


def pick_start_dir(kind):
    if kind == "client":
        return DOWNLOADS
    if kind == "csv":
        takeout = os.path.join(DOWNLOADS, "Takeout")
        return takeout if os.path.isdir(takeout) else DOWNLOADS
    return paths.output_dir()


def finder_flags(data):
    """Options chosen in the interface, as finder.py arguments."""
    flags = []
    if data.get("check") is False:
        flags.append("--skip-availability")
    mode = data.get("mode")  # "complete" (default), "youtube" or "search"
    if mode == "youtube":
        flags.append("--youtube-only")
    elif mode == "search":
        flags.append("--no-itunes")
    if data.get("exclude"):
        flags += ["--exclude-artists", str(data["exclude"])]
    return flags


def output_names(output):
    stem = output[:-5]
    return [output, stem + ".txt", stem + "_unavailable.txt"]


def slugify(text, default="playlist"):
    """Command-line friendly file name part: lowercase ASCII letters, digits and "_" only
    (no spaces, accents or symbols). Same rule as slugify() in ui.html."""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii").lower()
    name = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return name[:80] or default


def playlist_title(playlist, lang):
    return playlist["title"] or i18n.t(lang, "liked_videos")


def write_private_csv(rows, columns=None):
    """Temporary CSV (Takeout-like columns + Playlist/Availability) readable only by the user."""
    path = os.path.join(paths.cache_dir(), f"account-{secrets.token_hex(8)}.csv")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    columns = columns or ["Video ID", "Song Title", "Artist Name 1", "Album Title", "Playlist",
                          "Availability"]
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def api_availability(video_ids, lang, log):
    """Availability (and title/channel) of many videos through the official YouTube API, 50 per
    call. Returns None when it can't be used (not signed in, quota, network): the finder then
    falls back to checking each video page."""
    ids = [i for i in video_ids if i]
    if not ids:
        return {}
    try:
        region = youtube_api.user_region(i18n.COUNTRY[lang])
        log(i18n.t(lang, "checking_api", n=len(ids), region=region))
        return youtube_api.videos_info(ids, region)
    except Exception as error:  # AuthError, HttpError (quota), network...
        log(i18n.t(lang, "api_fallback", error=getattr(error, "code", None) or error))
        return None


def signed_in():
    try:
        return youtube_auth.session.status()["signed_in"]
    except Exception:
        return False


def takeout_job(csv_path, out_path, lang, flags):
    """Takeout CSV. When the user is signed in and the availability check is on, the official API
    checks the videos (and gives the titles of playlist exports, which only have IDs) before the
    finder runs; otherwise the CSV goes to the finder as it is."""
    command = ["infinifind_music.finder", csv_path, "--output", out_path, "--lang", lang, *flags]

    def prepare(log):
        if "--skip-availability" in flags or not signed_in():
            return [command]
        _, songs = finder.read_csv(csv_path)
        info = api_availability([s["id"] for s in songs], lang, log)
        if info is None:
            return [command]
        most = max((len(s.get("artists") or []) for s in songs), default=1) or 1
        rows = []
        for song in songs:
            details = info.get(song["id"], {})
            title, artists, album = song["title"], list(song.get("artists") or []), song["album"]
            if not title and details.get("title"):  # playlist export: only the video ID
                cleaned = finder.clean_youtube_title(details["title"], details["channel"])
                title, album = cleaned["title"], cleaned["album"]
                artists = [cleaned["artist"]] if cleaned["artist"] else []
            row = {"Video ID": song["id"], "Song Title": title, "Album Title": album,
                   "Availability": details.get("status", "")}
            for n in range(max(most, 1)):
                row[f"Artist Name {n + 1}"] = artists[n] if n < len(artists) else ""
            rows.append(row)
        artist_columns = [f"Artist Name {n + 1}" for n in range(max(most, 1))]
        columns = ["Video ID", "Song Title", "Album Title", *artist_columns, "Availability"]
        path = write_private_csv(rows, columns)
        task.cleanup.append(path)
        return [["infinifind_music.finder", path, "--output", out_path, "--lang", lang,
                 "--source-name", os.path.basename(csv_path), *flags]]
    return prepare


def account_job(outputs, out_dir, lang, flags):
    """Preparation step for playlists read from the user's account: reads the videos with the
    user's token (here, never in the subprocess) and writes one temporary CSV per output."""
    def prepare(log):
        commands = []
        for name, playlists in outputs:
            rows, seen = [], {}
            titles = []
            for playlist in playlists:
                title = playlist_title(playlist, lang)
                titles.append(title)
                videos = youtube_api.playlist_videos(playlist["id"])
                log(i18n.t(lang, "reading_playlist", name=title, n=len(videos)))
                for video in videos:
                    if video["id"] in seen:  # same video in several playlists: one row
                        row = seen[video["id"]]
                        if title not in row["Playlist"].split(" · "):
                            row["Playlist"] += " · " + title
                        continue
                    if video["gone"]:
                        info = {"title": video["title"], "artist": "", "album": ""}
                    else:
                        info = finder.clean_youtube_title(video["title"], video["channel"])
                    row = {"Video ID": video["id"], "Song Title": info["title"],
                           "Artist Name 1": info["artist"], "Album Title": info["album"], "Playlist": title,
                           "Availability": youtube_api.GONE if video["gone"] else ""}
                    seen[video["id"]] = row
                    rows.append(row)
            if "--skip-availability" not in flags:
                pending = [r["Video ID"] for r in rows if not r["Availability"]]
                info = api_availability(pending, lang, log)
                for row in rows:
                    if info and row["Video ID"] in info and not row["Availability"]:
                        row["Availability"] = info[row["Video ID"]]["status"]
            path = write_private_csv(rows)
            task.cleanup.append(path)
            source_name = ", ".join(titles)
            if len(source_name) > 120:
                source_name = source_name[:117] + "…"
            commands.append(["infinifind_music.finder", path, "--output", os.path.join(out_dir, name),
                             "--lang", lang, "--source-name", source_name, *flags])
        return commands
    return prepare


CALLBACK_TEXT = {
    "en-US": ("Signed in", "You can close this tab and go back to InfiniFind Music.",
              "Sign-in failed", "Go back to InfiniFind Music and try again."),
    "pt-BR": ("Login concluído", "Pode fechar esta aba e voltar para o InfiniFind Music.",
              "Não foi possível entrar", "Volte para o InfiniFind Music e tente de novo."),
    "es": ("Sesión iniciada", "Puedes cerrar esta pestaña y volver a InfiniFind Music.",
           "No se pudo iniciar sesión", "Vuelve a InfiniFind Music e inténtalo de nuevo."),
}


def callback_page(lang, ok):
    title_ok, text_ok, title_err, text_err = CALLBACK_TEXT.get(lang, CALLBACK_TEXT["en-US"])
    title, text = (title_ok, text_ok) if ok else (title_err, text_err)
    color = "#2a8a12" if ok else "#c4291c"
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><title>{title}</title>'
            "<style>body{font-family:system-ui,sans-serif;display:grid;place-items:center;min-height:90vh;"
            "margin:0;background:linear-gradient(#49b6f2,#e9f8ff);color:#0c2a43}"
            "main{background:#fff;padding:32px 40px;border-radius:18px;box-shadow:0 10px 30px #0003;"
            f"text-align:center}}h1{{color:{color};margin:0 0 8px}}</style></head>"
            f"<body><main><h1>{title}</h1><p>{text}</p></main></body></html>")


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
        if url.path == "/oauth/callback":
            return self._oauth_callback(parse_qs(url.query))
        if not self._token_ok():
            return self._error("access_denied", 403)
        if self.path == "/api/account":
            return self._json(youtube_auth.session.status())
        if self.path == "/api/playlists":
            try:
                playlists = youtube_api.list_playlists()
            except youtube_auth.AuthError as error:
                return self._error(error.code, 401)
            except (net.HttpError, OSError, ValueError):
                return self._error("playlists_failed", 502)
            return self._json({"playlists": playlists})
        if self.path == "/api/files":
            self._json({"csvs": list_csvs(), "output_dir": paths.output_dir(),
                        "downloads": os.path.realpath(DOWNLOADS),
                        "home": os.path.expanduser("~")})
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
            stem = os.path.basename(str(data.get("output") or "my_songs.html"))
            stem = stem[:-5] if stem.lower().endswith(".html") else stem
            output = slugify(stem, "my_songs") + ".html"
            out_dir = paths.output_dir()
            if data.get("source") == "account":
                ids = data.get("playlists")
                if not isinstance(ids, list) or not 0 < len(ids) <= 500:
                    return self._error("need_playlists", 400)
                try:  # only the user's own playlists are accepted
                    known = {p["id"]: p for p in youtube_api.list_playlists()}
                except youtube_auth.AuthError as error:
                    return self._error(error.code, 401)
                except (net.HttpError, OSError, ValueError):
                    return self._error("playlists_failed", 502)
                chosen = [known[i] for i in ids if isinstance(i, str) and i in known]
                if not chosen:
                    return self._error("need_playlists", 400)
                if data.get("per_playlist") and len(chosen) > 1:
                    # Suggested name: just each playlist's name; a typed name becomes a prefix.
                    prefix = "" if data.get("auto_name") else output[:-5] + "_"
                    outputs = [(f"{prefix}{slugify(playlist_title(p, lang))}.html", [p]) for p in chosen]
                else:
                    outputs = [(output, chosen)]
                names = [n for name, _ in outputs for n in output_names(name)]
                job = account_job(outputs, out_dir, lang, finder_flags(data))
            else:
                csv_path = os.path.expanduser(str(data.get("csv", "")))
                if not os.path.isfile(csv_path):
                    return self._error("csv_not_found", 400)
                names = output_names(output)
                job = takeout_job(csv_path, os.path.join(out_dir, output), lang, finder_flags(data))
            existing = [n for n in names if os.path.exists(os.path.join(out_dir, n))]
            if existing and not data.get("overwrite"):
                return self._error("exists", 409, existing=existing, folder=out_dir)
            ok = task.start("find", job)
        elif self.path == "/api/stop":
            task.stop()
            return self._json({"ok": True})
        elif self.path == "/api/open":
            path = os.path.realpath(os.path.expanduser(str(data.get("path", ""))))
            # Only opens files inside Downloads or the output folder chosen by the user.
            if not is_inside(path, allowed_roots()) or not os.path.isfile(path):
                return self._error("open_not_allowed", 400)
            if os.name == "nt":
                os.startfile(path)  # noqa: S606 - no shell; path checked to be inside an allowed folder
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])
            return self._json({"ok": True})
        elif self.path == "/api/pick":
            return self._pick(str(data.get("kind", "")), lang)
        elif self.path == "/api/account/login":
            port = self.server.server_address[1]
            try:
                url = youtube_auth.session.start_login(f"http://127.0.0.1:{port}/oauth/callback", lang)
            except youtube_auth.AuthError as error:
                return self._error(error.code, 400)
            # Google blocks sign-in inside embedded windows, so it opens in the user's browser.
            webbrowser.open(url)
            return self._json({"ok": True})
        elif self.path == "/api/account/logout":
            youtube_auth.session.logout()
            return self._json(youtube_auth.session.status())
        elif self.path == "/api/output/reset":
            settings = paths.load_settings()
            settings.pop("output_dir", None)
            paths.save_settings(settings)
            return self._json({"output_dir": paths.output_dir()})
        else:
            return self._error("not_found", 404)

        if not ok:
            return self._error("busy", 409)
        self._json({"ok": True})


def _pick(handler, kind, lang):
    """Opens the native file/folder dialog (picker.py) and records the user's choice."""
    if kind not in picker.KINDS:
        return handler._error("invalid_request", 400)
    if not _picker_lock.acquire(blocking=False):
        return handler._error("picker_busy", 409)
    try:
        path = picker.pick(kind, i18n.t(lang, "pick_" + kind), pick_start_dir(kind))
    except (picker.PickerUnavailable, OSError, subprocess.SubprocessError):
        return handler._error("picker_unavailable", 500)
    finally:
        _picker_lock.release()
    if path and kind == "client":
        try:
            youtube_auth.import_client(path)
        except youtube_auth.AuthError as error:
            return handler._error(error.code, 400)
    elif path and kind == "folder":
        settings = paths.load_settings()
        settings["output_dir"] = path
        paths.save_settings(settings)
    return handler._json({"path": path, "output_dir": paths.output_dir()})


Handler._pick = _pick


def _oauth_callback(handler, query):
    """Google redirects the user's browser here after the consent screen. No interface token
    is needed (the request comes from the browser tab), but the one-time `state` must match."""
    state = query.get("state", [""])[0]
    lang = youtube_auth.session.pending_lang(state)
    ok = True
    try:
        if query.get("error"):
            youtube_auth.session.finish_login(state, None)
        youtube_auth.session.finish_login(state, query.get("code", [""])[0])
    except youtube_auth.AuthError:
        ok = False
    body = callback_page(lang, ok).encode("utf-8")
    handler.send_response(200 if ok else 400)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
    handler._security_headers()
    handler.end_headers()
    handler.wfile.write(body)


Handler._oauth_callback = _oauth_callback


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
