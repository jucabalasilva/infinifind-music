"""Folders used by InfiniFind Music, following each operating system's conventions."""

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
    """Desktop app data (remembers the chosen theme and language)."""
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~/AppData/Roaming")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path
