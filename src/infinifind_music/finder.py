"""
Reads a CSV exported by Google Takeout (YouTube Music) and finds where each
song can be bought or streamed legally.

Builds an HTML page with, for each song:
  - the match in the iTunes Store (link and price), using Apple's public search API;
  - ready-made search links for Bandcamp, Amazon Music, Deezer and Spotify;
  - the original YouTube Music link.

Usage:
    infinifind-find "music library songs.csv"
    infinifind-find file.csv --output result.html --country US
    infinifind-find file.csv --no-itunes        (search links only)
    infinifind-find file.csv --youtube-only     (YouTube links only, instant)
    infinifind-find file.csv --lang pt-BR       (en-US, pt-BR or es)
    (or: python -m infinifind_music.finder ...)

Uses only the Python standard library.
"""

import argparse
import csv
import html
import json
import os
import re
import ssl
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from . import i18n, paths

USER_AGENT = "infinifind-music/1.0"
ITUNES_PAUSE = 3.1  # the iTunes Search API allows ~20 requests per minute
# When run by the app, extra machine-readable lines tell it which files were created.
MACHINE = os.environ.get("INFINIFIND_MACHINE") == "1"


def report_file(path):
    if MACHINE:
        print(f"@@file {path}", flush=True)


def normalize(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.strip().lower()


def detect_columns(header):
    """Finds the title, artist, album and video ID columns.
    Works with English, Portuguese and Spanish headers."""
    cols = {"title": None, "artists": [], "album": None, "id": None}
    for name in header:
        n = normalize(name)
        if "video" in n and "id" in n and cols["id"] is None:
            cols["id"] = name
        elif "album" in n and cols["album"] is None:
            cols["album"] = name
        elif "artist" in n:  # also matches "artista"
            cols["artists"].append(name)
        elif (("title" in n or "titulo" in n or "musica" in n or "cancion" in n or n == "song")
              and cols["title"] is None):
            cols["title"] = name
    return cols


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect)
        cols = detect_columns(reader.fieldnames or [])
        songs = []
        for row in reader:
            artists = [(row.get(c) or "").strip() for c in cols["artists"]]
            songs.append({
                "title": (row.get(cols["title"]) or "").strip() if cols["title"] else "",
                "artist": ", ".join(a for a in artists if a),
                "album": (row.get(cols["album"]) or "").strip() if cols["album"] else "",
                "id": (row.get(cols["id"]) or "").strip() if cols["id"] else "",
            })
    return cols, [s for s in songs if s["title"] or s["id"]]


_use_curl = False


def fetch_json(url):
    """Downloads JSON. If Python has no HTTPS certificates (common on macOS with the
    python.org installer), falls back to the system curl."""
    global _use_curl
    if not url.startswith("https://"):  # only HTTPS URLs built by this module
        raise ValueError("only https:// URLs are allowed")
    curl = paths.curl_path()
    if not _use_curl:
        # Only https:// URLs reach this point (checked above), so file:// and custom schemes can't.
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310  # nosec B310
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as error:
            if not isinstance(error.reason, ssl.SSLError) or not curl:
                raise
            _use_curl = True
    out = subprocess.run([curl, "-sSfL", "--proto", "=https", "-m", "20", "-A", USER_AGENT, url],
                         capture_output=True, check=True)
    return json.loads(out.stdout.decode("utf-8"))


# "(Official Video)", "[Lyrics]", "(4K Remaster)"... removed from YouTube titles.
NOISE_IN_TITLE = re.compile(
    r"\s*[\(\[][^\)\]]*"
    r"(official|oficial|video|vídeo|clipe|lyric|letra|audio|áudio|remaster|4k|hd)"
    r"[^\)\]]*[\)\]]",
    re.IGNORECASE,
)


def fill_from_youtube(song):
    """Playlist files only have the video ID: get title and channel from YouTube (oEmbed)."""
    url = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(
        "https://music.youtube.com/watch?v=" + song["id"], safe="")
    try:
        data = fetch_json(url)
    except Exception:
        return
    title = data.get("title", "")
    author = data.get("author_name", "")
    author = author[:-8] if author.endswith(" - Topic") else author
    # "Artist - Song (Official Video)" -> "Song"
    if author and normalize(title).startswith(normalize(author) + " - "):
        title = title[len(author) + 3:]
    title = NOISE_IN_TITLE.sub("", title).strip()
    song["title"] = title
    song["artist"] = author


def search_itunes(song, country, lang):
    term = f'{song["artist"]} {song["title"]}'.strip()
    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(
        {"term": term, "entity": "song", "limit": 10, "country": country})
    artists = [normalize(a) for a in song["artist"].split(",") if a.strip()]
    for attempt in range(3):
        try:
            results = fetch_json(url).get("results", [])
            if not results:
                return None
            # Prefer a result from the same artist; otherwise take the first one.
            r = next((x for x in results
                      if any(a in normalize(x.get("artistName", "")) for a in artists)),
                     results[0])
            return {
                "track": r.get("trackName", ""),
                "artist": r.get("artistName", ""),
                "album": r.get("collectionName", ""),
                "price": r.get("trackPrice"),
                "currency": r.get("currency", ""),
                "link": r.get("trackViewUrl", ""),
            }
        except Exception as error:
            print(i18n.t(lang, "search_error", error=error), flush=True)
            time.sleep(10 * (attempt + 1))  # rate limit: wait and try again
    return None


def youtube_links(song, lang):
    if song["id"]:
        return {
            "YouTube Music": f"https://music.youtube.com/watch?v={song['id']}",
            "YouTube": f"https://www.youtube.com/watch?v={song['id']}",
        }
    q = urllib.parse.quote(f'{song["artist"]} {song["title"]}'.strip())
    return {i18n.t(lang, "search_ytm"): f"https://music.youtube.com/search?q={q}"}


def search_links(song, lang, youtube_only=False):
    if youtube_only:
        return youtube_links(song, lang)
    q = urllib.parse.quote(f'{song["artist"]} {song["title"]}'.strip())
    links = {
        "Bandcamp": f"https://bandcamp.com/search?q={q}&item_type=t",
        "Amazon Music": f"https://{i18n.AMAZON[lang]}/search/{q}",
        "Deezer": f"https://www.deezer.com/search/{q}",
        "Spotify": f"https://open.spotify.com/search/{q}",
    }
    if song["id"]:
        links["YouTube Music"] = f"https://music.youtube.com/watch?v={song['id']}"
    return links


def build_html(songs, output_path, source, lang, youtube_only=False):
    e = html.escape
    t = lambda key, **kw: e(i18n.t(lang, key, **kw))  # noqa: E731
    link = 'target="_blank" rel="noopener noreferrer"'
    rows = []
    found = 0
    for i, s in enumerate(songs, 1):
        it = s.get("itunes")
        if it:
            found += 1
            price = ""
            if it["price"] is not None and it["price"] >= 0:
                price = " — " + i18n.price(lang, it["currency"], it["price"])
            itunes_cell = (f'<a href="{e(it["link"])}" {link}>{e(it["track"])}</a>'
                           f'<br><small>{e(it["artist"])} · {e(it["album"])}{e(price)}</small>')
        elif "itunes" in s:
            itunes_cell = f'<span class="none">{t("not_found")}</span>'
        else:
            itunes_cell = '<span class="none">—</span>'
        buttons = " ".join(f'<a class="btn" href="{e(u)}" {link}>{e(n)}</a>'
                           for n, u in search_links(s, lang, youtube_only).items())
        rows.append(
            f'<tr><td class="n">{i}</td>'
            f'<td><strong>{e(s["title"]) or t("no_title")}</strong><br>'
            f'<small>{e(s["artist"])}{" · " + e(s["album"]) if s["album"] else ""}</small></td>'
            + ("" if youtube_only else f'<td>{itunes_cell}</td>')
            + f'<td class="links">{buttons}</td></tr>')

    summary = t("songs", n=len(songs))
    if any("itunes" in s for s in songs):
        summary += " · " + t("found_itunes", n=found)
    summary += " · " + t("source", name=os.path.basename(source))
    extra_header = (f"<th>{t('col_link')}</th>" if youtube_only
                    else f"<th>{t('col_itunes')}</th><th>{t('col_search')}</th>")

    page = f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t("page_title")}</title>
<style>
:root {{ --bg:#fafafa; --fg:#1d1d1f; --mut:#6e6e73; --line:#e5e5ea; --btn:#ececf0; --link:#0060df; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#1c1c1e; --fg:#f2f2f7; --mut:#a1a1a6; --line:#3a3a3c; --btn:#2c2c2e; --link:#6aa8ff; }} }}
body {{ font-family: system-ui, sans-serif; background:var(--bg); color:var(--fg);
       margin:0; padding:24px 16px; }}
main {{ max-width:1100px; margin:auto; }}
h1 {{ margin:0 0 4px; font-size:1.5rem; }}
p.summary {{ color:var(--mut); margin:0 0 16px; }}
input {{ width:100%; max-width:360px; padding:8px 10px; font-size:1rem; border:1px solid var(--line);
        border-radius:8px; background:var(--bg); color:var(--fg); margin-bottom:12px;
        box-sizing:border-box; }}
.table {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; }}
td, th {{ text-align:left; padding:10px 8px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ font-size:.8rem; text-transform:uppercase; color:var(--mut); }}
small, .n, .none {{ color:var(--mut); }}
a {{ color:var(--link); }}
.btn {{ display:inline-block; background:var(--btn); color:var(--fg); text-decoration:none;
       padding:3px 8px; border-radius:6px; font-size:.8rem; margin:2px 0; }}
.links {{ min-width:220px; }}
</style></head><body><main>
<h1>{t("page_title")}</h1>
<p class="summary">{summary}</p>
<input id="filter" placeholder="{t("filter")}" oninput="filterRows(this.value)">
<div class="table"><table>
<thead><tr><th>#</th><th>{t("col_song")}</th>{extra_header}</tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
</main>
<script>
function filterRows(text) {{
  text = text.toLowerCase();
  document.querySelectorAll('tbody tr').forEach(function (tr) {{
    tr.style.display = tr.textContent.toLowerCase().includes(text) ? '' : 'none';
  }});
}}
</script></body></html>"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(page)


def main():
    p = argparse.ArgumentParser(description="Find where to buy or stream the songs in a Google Takeout CSV.")
    p.add_argument("csv", help=".csv file exported by Google Takeout")
    p.add_argument("--output", default="my_songs.html",
                   help="HTML file to create; without a folder it is saved in ~/Downloads "
                        "(default: my_songs.html)")
    p.add_argument("--lang", default=i18n.DEFAULT, help="language: en-US (default), pt-BR or es")
    p.add_argument("--country", default=None,
                   help="iTunes Store country (default depends on --lang: US, BR or ES)")
    p.add_argument("--no-itunes", action="store_true", help="do not query iTunes, only build search links")
    p.add_argument("--youtube-only", action="store_true",
                   help="only YouTube/YouTube Music links (fast, no store lookups); also writes a .txt list")
    p.add_argument("--exclude-artists", default="",
                   help='artists to leave out, comma-separated (e.g. "Artist A,Artist B")')
    args = p.parse_args()
    lang = i18n.normalize(args.lang)
    country = (args.country or i18n.COUNTRY[lang]).upper()
    if args.youtube_only:
        args.no_itunes = True
    if not os.path.dirname(args.output):  # no folder in the name: save to Downloads
        args.output = os.path.join(paths.DOWNLOADS, args.output)

    if not os.path.isfile(args.csv):
        sys.exit(i18n.t(lang, "file_not_found", path=args.csv))

    cols, songs = read_csv(args.csv)
    if not songs:
        sys.exit(i18n.t(lang, "no_songs", columns=json.dumps(cols, ensure_ascii=False)))
    print(i18n.t(lang, "songs_read", n=len(songs), path=args.csv), flush=True)
    if args.exclude_artists:
        excluded = [normalize(a) for a in args.exclude_artists.split(",") if a.strip()]
        before = len(songs)
        songs = [s for s in songs if not any(x in normalize(s["artist"]) for x in excluded)]
        print(i18n.t(lang, "excluded", n=before - len(songs)), flush=True)

    # Cache so the search can be interrupted (Ctrl+C) and resumed without repeating lookups.
    cache_path = os.path.join(paths.cache_dir(), os.path.basename(args.output) + ".cache.json")
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)

    untitled = [s for s in songs if not s["title"] and s["id"]]
    if untitled:
        print(i18n.t(lang, "fetching_titles", n=len(untitled)), flush=True)
        for s in untitled:
            key = "yt:" + s["id"]
            if key in cache:
                s["title"], s["artist"] = cache[key]
            else:
                fill_from_youtube(s)
                cache[key] = [s["title"], s["artist"]]

    try:
        if not args.no_itunes:
            total = len(songs)
            for i, s in enumerate(songs, 1):
                key = f'it:{country}:{s["artist"]}|{s["title"]}'
                if key in cache:
                    s["itunes"] = cache[key]
                    continue
                print(f"[{i}/{total}] {s['artist']} – {s['title']}", flush=True)
                s["itunes"] = search_itunes(s, country, lang)
                cache[key] = s["itunes"]
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False)
                time.sleep(ITUNES_PAUSE)
    except KeyboardInterrupt:
        print(i18n.t(lang, "interrupted"), flush=True)

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    build_html(songs, args.output, args.csv, lang, args.youtube_only)
    output = os.path.abspath(args.output)
    print(i18n.t(lang, "done", path=output), flush=True)
    report_file(output)
    if args.youtube_only:
        # Plain list, easy to copy and paste.
        txt = os.path.splitext(output)[0] + ".txt"
        with open(txt, "w", encoding="utf-8") as f:
            for s in songs:
                name = " – ".join(x for x in (s["artist"], s["title"]) if x)
                f.write(f"{name}: {next(iter(youtube_links(s, lang).values()))}\n")
        print(i18n.t(lang, "text_list", path=txt), flush=True)
        report_file(txt)


if __name__ == "__main__":
    main()
