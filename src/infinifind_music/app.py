"""
InfiniFind Music — desktop application (native window).

Runs the same server as the browser version on a free port, reachable only from
this computer, and shows the interface in its own window using pywebview.

Usage:
    infinifind                  (or: python -m infinifind_music)
or open "InfiniFind Music.app" (created by scripts/build_macos_app.sh on macOS).

Without pywebview installed (pip install "infinifind-music[app]"), it falls back to
the browser version.
"""

import os
import sys
import threading
from http.server import ThreadingHTTPServer

from . import paths, server

NAME = "InfiniFind Music"
ICON = os.path.join(paths.ASSETS_DIR, "icon.png")


def set_name_and_icon():
    """On macOS, show the app's name and icon in the Dock and menu instead of 'Python'."""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication, NSImage
        from Foundation import NSBundle

        info = NSBundle.mainBundle().localizedInfoDictionary() or NSBundle.mainBundle().infoDictionary()
        if info is not None:
            info["CFBundleName"] = NAME
        if os.path.exists(ICON):
            image = NSImage.alloc().initWithContentsOfFile_(ICON)
            NSApplication.sharedApplication().setApplicationIconImage_(image)
    except Exception as error:  # cosmetic only
        print("Warning: could not set the app name/icon:", error)


def main():
    try:
        import webview
    except ImportError:
        print("pywebview is not installed, so the interface will open in your browser.\n"
              'For the desktop window, run: pip install "infinifind-music[app]"')
        return server.main()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    set_name_and_icon()
    window = webview.create_window(
        NAME, server.start_url(port),
        width=1120, height=860, min_size=(560, 600),
        background_color="#49b6f2",
    )
    window.events.closed += server.task.stop  # closing the app stops any running task

    # private_mode=False + storage_path: remembers the chosen theme and language.
    webview.start(private_mode=False, storage_path=paths.data_dir())
    httpd.shutdown()


if __name__ == "__main__":
    main()
