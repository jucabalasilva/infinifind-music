"""
Checks which links in a YouTube / YouTube Music .txt list still play in this
computer's region and moves the unavailable ones to a separate file.

Usage:
    infinifind-check ~/Downloads/youtube_links.txt [--lang pt-BR]
    (or: python -m infinifind_music.availability ...)

Result, next to the list:
    <list>.txt                  (rewritten with the available links only)
    <list>_unavailable.txt      (the removed links)

Reads the "playabilityStatus" of each video page: "OK" = plays;
"UNPLAYABLE"/"ERROR" = unavailable. One request per second.
Uses only the Python standard library (and the system curl).
"""

import argparse
import os
import re
import subprocess
import time

from . import i18n, paths

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 15_0) AppleWebKit/605.1.15 "
              "(KHTML, like Gecko) Version/18.0 Safari/605.1.15")
MACHINE = os.environ.get("INFINIFIND_MACHINE") == "1"
# "playabilityStatus" values that mean the video does not play here. Anything else (OK,
# LOGIN_REQUIRED for age-restricted videos, a failed lookup) keeps the link.
# PRIVATE_OR_DELETED and BLOCKED (country) come from the official API (youtube_api).
UNAVAILABLE = ("UNPLAYABLE", "ERROR", "PRIVATE_OR_DELETED", "BLOCKED")


def video_status(video_id, lang):
    accept = {"pt-BR": "pt-BR", "es": "es"}.get(lang, "en-US")
    curl = paths.curl_path()
    if not curl:
        raise SystemExit("curl not found")
    for _ in range(3):
        page = subprocess.run(
            [curl, "-sL", "--proto", "=https", "-m", "20", "-A", USER_AGENT,
             "-H", f"Accept-Language: {accept}", f"https://www.youtube.com/watch?v={video_id}"],
            capture_output=True).stdout.decode("utf-8", "replace")
        m = re.search(r'"playabilityStatus":\{"status":"([A-Z_]+)"(?:,"reason":"([^"]*)")?', page)
        if m:
            return m.group(1), m.group(2) or ""
        time.sleep(5)
    return "LOOKUP_FAILED", ""


def main():
    p = argparse.ArgumentParser(description="Remove YouTube links that no longer play in your region.")
    p.add_argument("list", help=".txt file with one link per line")
    p.add_argument("--lang", default=i18n.DEFAULT, help="language: en-US (default), pt-BR or es")
    args = p.parse_args()
    lang = i18n.normalize(args.lang)

    path = os.path.abspath(os.path.expanduser(args.list))
    if not os.path.isfile(path):
        raise SystemExit(i18n.t(lang, "file_not_found", path=path))
    with open(path, encoding="utf-8") as f:
        lines = [line for line in f.read().splitlines() if line.strip()]

    ok, removed = [], []
    for i, line in enumerate(lines, 1):
        vid = re.search(r"[?&]v=([\w-]{11})", line)
        status, reason = video_status(vid.group(1), lang) if vid else ("NO_ID", "")
        print(f"[{i}/{len(lines)}] {status} {reason} | {line[:70]}", flush=True)
        # When in doubt (lookup failed, age restriction), keep the link.
        (removed if status in UNAVAILABLE else ok).append(line)
        time.sleep(1)

    unavailable = os.path.splitext(path)[0] + "_unavailable.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(ok) + ("\n" if ok else ""))
    with open(unavailable, "w", encoding="utf-8") as f:
        f.write("\n".join(removed) + ("\n" if removed else ""))
    print(i18n.t(lang, "summary_check", ok=len(ok), bad=len(removed)))
    print(i18n.t(lang, "list_updated", path=path))
    print(i18n.t(lang, "unavailable_list", path=unavailable), flush=True)
    if MACHINE:
        print(f"@@file {path}\n@@file {unavailable}", flush=True)


if __name__ == "__main__":
    main()
