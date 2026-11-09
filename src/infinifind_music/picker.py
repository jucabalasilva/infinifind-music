"""
Native "choose a file / folder" dialogs for the interface.

The browser can't give the server a real file path, so the server opens the operating
system's own dialog and returns the path the user picked:

- desktop app: pywebview's dialog (app.py registers it with `set_native`);
- browser version on macOS: AppleScript's `choose file` / `choose folder` (osascript);
- browser version on Linux/Windows: tkinter's file dialog, in a separate process.

Every call returns the chosen path, or None when the user cancels.
Kinds: "csv" (Takeout CSV), "folder" (where to save results) and
"client" (the OAuth client JSON downloaded from Google Cloud).
"""

import os
import subprocess
import sys

KINDS = ("csv", "folder", "client")
EXTENSIONS = {"csv": ("csv",), "client": ("json",)}

_native = None  # set by the desktop app: callable(kind, start_dir) -> path | None


class PickerUnavailable(RuntimeError):
    """No dialog could be shown on this system."""


def set_native(func):
    global _native
    _native = func


# AppleScript receives the prompt and the start folder as arguments (never pasted into the
# script), so text chosen by the user can't change what the script does.
_APPLESCRIPT = {
    "csv": 'on run argv\nactivate\nreturn POSIX path of (choose file with prompt (item 1 of argv) '
           'of type {"csv", "public.comma-separated-values-text"} '
           'default location (POSIX file (item 2 of argv)))\nend run',
    "folder": 'on run argv\nactivate\nreturn POSIX path of (choose folder with prompt (item 1 of argv) '
              'default location (POSIX file (item 2 of argv)))\nend run',
    "client": 'on run argv\nactivate\nreturn POSIX path of (choose file with prompt (item 1 of argv) '
              'of type {"json", "public.json"} default location (POSIX file (item 2 of argv)))\nend run',
}

_TKINTER = r"""
import sys, tkinter as tk
from tkinter import filedialog
kind, prompt, start = sys.argv[1:4]
root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
if kind == "folder":
    path = filedialog.askdirectory(title=prompt, initialdir=start, mustexist=True)
else:
    ext = {"csv": "csv", "client": "json"}[kind]
    path = filedialog.askopenfilename(title=prompt, initialdir=start,
                                      filetypes=[(ext.upper(), "*." + ext), ("*", "*")])
print(path or "")
"""


def _osascript(kind, prompt, start_dir):
    result = subprocess.run(["/usr/bin/osascript", "-e", _APPLESCRIPT[kind], prompt, start_dir],
                            capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        if "-128" in result.stderr:  # user cancelled
            return None
        raise PickerUnavailable(result.stderr.strip() or "osascript failed")
    return result.stdout.strip() or None


def _tkinter(kind, prompt, start_dir):
    result = subprocess.run([sys.executable, "-c", _TKINTER, kind, prompt, start_dir],
                            capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise PickerUnavailable(result.stderr.strip().splitlines()[-1:] or "tkinter failed")
    return result.stdout.strip() or None


def pick(kind, prompt, start_dir):
    """Opens the dialog and returns the absolute path the user chose, or None."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind}")
    if not os.path.isdir(start_dir):
        start_dir = os.path.expanduser("~")
    if _native is not None:
        path = _native(kind, start_dir)
    elif sys.platform == "darwin" and os.path.exists("/usr/bin/osascript"):
        path = _osascript(kind, prompt, start_dir)
    else:
        path = _tkinter(kind, prompt, start_dir)
    if not path:
        return None
    path = os.path.realpath(path)
    if kind == "folder":
        return path if os.path.isdir(path) else None
    if not os.path.isfile(path) or not path.lower().endswith(tuple("." + e for e in EXTENSIONS[kind])):
        return None
    return path
