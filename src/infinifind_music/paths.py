"""Folders used by InfiniFind Music, following each operating system's conventions."""

import json
import os
import sys

APP_NAME = "InfiniFindMusic"
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(PACKAGE_DIR, "web")
ASSETS_DIR = os.path.join(PACKAGE_DIR, "assets")

# Generated pages and lists are saved here.
DOWNLOADS = os.path.expanduser("~/Downloads")


def curl_path():
    """Full path to the system curl. Prefers the system copy over whatever comes first in
    PATH, so a program named "curl" placed earlier in PATH cannot be run instead."""
    for candidate in ("/usr/bin/curl", r"C:\Windows\System32\curl.exe"):
        if os.path.isfile(candidate):
            return candidate
    import shutil
    return shutil.which("curl")


def cache_dir():
    """Search cache (lets an interrupted iTunes search resume).
    INFINIFIND_CACHE_DIR overrides it (used by the tests)."""
    override = os.environ.get("INFINIFIND_CACHE_DIR")
    if override:
        os.makedirs(override, exist_ok=True)
        return override
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Caches")
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def data_dir():
    """App data: the desktop window's storage (theme, language) and settings.json.
    INFINIFIND_DATA_DIR overrides it (used by the tests)."""
    override = os.environ.get("INFINIFIND_DATA_DIR")
    if override:
        os.makedirs(override, exist_ok=True)
        return override
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~/AppData/Roaming")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def _settings_file():
    return os.path.join(data_dir(), "settings.json")


def load_settings():
    """User settings saved by the interface (for now only the output folder)."""
    try:
        with open(_settings_file(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings):
    path = _settings_file()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def output_dir():
    """Folder where generated pages and lists are saved: the one the user chose in the
    interface, or Downloads. A chosen folder that no longer exists falls back to Downloads."""
    chosen = load_settings().get("output_dir")
    if isinstance(chosen, str) and os.path.isdir(chosen):
        return os.path.realpath(chosen)
    return os.path.realpath(DOWNLOADS)
