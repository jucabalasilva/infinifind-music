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

from . import availability, i18n, paths

USER_AGENT = "infinifind-music/1.0"
ITUNES_PAUSE = 3.1  # the iTunes Search API allows ~20 requests per minute
CHECK_PAUSE = 1.0  # pause between YouTube availability checks when iTunes is not queried
AVAILABILITY_CACHE_HOURS = 24  # availability can change, so cached results expire
CACHE_MAX_DAYS = 30  # the whole cache file is discarded after this
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
    cols = {"title": None, "artists": [], "album": None, "id": None, "playlist": None, "availability": None}
    for name in header:
        n = normalize(name)
        # Extra columns written by the app when it reads playlists from the user's account.
        if n == "playlist" and cols["playlist"] is None:
            cols["playlist"] = name
        elif n == "availability" and cols["availability"] is None:
            cols["availability"] = name
        elif "video" in n and "id" in n and cols["id"] is None:
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
            artists = [a for a in ((row.get(c) or "").strip() for c in cols["artists"]) if a]
            songs.append({
                "title": (row.get(cols["title"]) or "").strip() if cols["title"] else "",
                "artist": ", ".join(artists),
                "artists": artists,
                "album": (row.get(cols["album"]) or "").strip() if cols["album"] else "",
                "id": (row.get(cols["id"]) or "").strip() if cols["id"] else "",
            })
            if cols["playlist"] and (row.get(cols["playlist"]) or "").strip():
                songs[-1]["playlist"] = row[cols["playlist"]].strip()
            if cols["availability"] and (row.get(cols["availability"]) or "").strip():
                songs[-1]["availability"] = row[cols["availability"]].strip()
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


# Words that mark a bracketed part of a YouTube title as noise, e.g. "(Official Video)",
# "[Lyrics]", "(4K Remaster)", "[EPIC METAL COVER]", "(Legendado PT-BR)", "[AMV]", "(OP 4)".
_NOISE_WORDS = (
    r"official|oficial|video|vídeo|clipe|lyrics?|letra|audio|áudio|remaster(?:ed)?|4k|hd|"
    r"1080p|720p|full|legendad[oa]|subtitulad[oa]|(?:viet|eng)?sub(?:s|bed|titles)?|amv|cover|"
    r"tv[ -]?size|opening|ending|abertura|encerramento|apertura|mv|pv|pt[ -]?br|"
    r"OP\s*\d+|ED\s*\d+"
)
NOISE_IN_TITLE = re.compile(r"\s*[\(\[][^\)\]]*\b(?:" + _NOISE_WORDS + r")\b[^\)\]]*[\)\]]", re.IGNORECASE)
# 【...】 blocks are almost always notes like 【Legendado PT-BR】 or 【Golden Wind OP 2】.
LENTICULAR_BRACKETS = re.compile(r"\s*【[^】]*】\s*")
# "Opening 4", "OP 2", "ED3"... outside brackets: they separate the anime name from the song.
ANIME_MARKER = re.compile(
    r"\b(?:(?:opening|ending|abertura|encerramento|apertura)(?:\s*\d+)?|(?:OP|ED)\s*\d+)\b",
    re.IGNORECASE,
)
# Other loose noise outside brackets.
LOOSE_NOISE = re.compile(
    r"\b(?:full(?:\s+(?:version|size))?|tv[ -]?size|hd|4k|lyrics?|"
    r"em\s+portugu[eê]s|in\s+english|(?:english|portuguese|spanish)\s+(?:version|ver\.?))\b"
    r"|\b(?:english\s+)?cover\s+by\b.*$",
    re.IGNORECASE,
)
SEPARATOR = re.compile(r"\s+[-–—|]\s+|\s*~\s*")
_PLACEHOLDER = "\x00"


def _split_outside_brackets(text):
    """Splits "A - B - C" on separators, ignoring separators inside (...) or [...]."""
    protected = re.sub(r"[\(\[][^\)\]]*[\)\]]", lambda m: m.group(0).replace("-", _PLACEHOLDER), text)
    parts = [p.replace(_PLACEHOLDER, "-") for p in SEPARATOR.split(protected)]
    # Quotes around song names ("I Wish") only get in the way of store searches.
    parts = [re.sub(r"\s{2,}", " ", p.replace('"', "")).strip(" -–—|~") for p in parts]
    return [p for p in parts if p]


def clean_youtube_title(title, author):
    """Turns a YouTube video title and channel into {"title", "artist", "album"} for searching.

    - Official channels ("Artist - Topic", "...VEVO") keep the channel as the artist.
    - "Anime - Opening 5 - Song" becomes title "Song" with "Anime" as the album (the uploader
      is usually a fan, not the artist, so the artist is left empty).
    - Other "Artist - Song" titles are split into artist and song.
    The video link never changes: it comes from the video ID, not from the title.
    """
    title = unicodedata.normalize("NFKC", title)  # "ＴＩＭ　ＭＡＩＡ" -> "TIM MAIA"
    author = unicodedata.normalize("NFKC", author)
    official = author.endswith(" - Topic") or "vevo" in author.lower()
    artist = author[:-8] if author.endswith(" - Topic") else author
    if "vevo" in artist.lower():
        artist = re.sub(r"vevo$", "", artist, flags=re.IGNORECASE).strip()

    text = LENTICULAR_BRACKETS.sub(" - ", title)
    text = NOISE_IN_TITLE.sub("", text)
    is_anime = bool(ANIME_MARKER.search(title))
    text = ANIME_MARKER.sub(" - ", text)
    text = LOOSE_NOISE.sub("", text)
    text = text.replace("「", " ").replace("」", " ")
    parts = _split_outside_brackets(text)
    if not parts:
        return {"title": title.strip(), "artist": artist, "album": ""}
    if len(parts) == 1 and re.fullmatch(r"\(([^()]*)\)", parts[0]):
        parts = [parts[0][1:-1]]

    if official:
        # "Artist - Song" on an official channel: drop the repeated artist name.
        # VEVO channels drop the spaces ("SomeArtistVEVO" vs. "Some Artist - Song").
        if len(parts) > 1 and normalize(parts[0]).replace(" ", "") == normalize(artist).replace(" ", ""):
            parts = parts[1:]
        return {"title": " - ".join(parts), "artist": artist, "album": ""}
    if is_anime and len(parts) > 1:
        song = parts[-1]
        if re.fullmatch(r"\(([^()]*)\)", song):
            song = song[1:-1]
        return {"title": song, "artist": "", "album": " - ".join(parts[:-1])}
    if len(parts) > 1:
        return {"title": " - ".join(parts[1:]), "artist": parts[0], "album": ""}
    return {"title": parts[0], "artist": artist, "album": ""}


def fill_from_youtube(song):
    """Playlist files only have the video ID: get title and channel from YouTube (oEmbed)."""
    url = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(
        "https://music.youtube.com/watch?v=" + song["id"], safe="")
    try:
        data = fetch_json(url)
    except Exception:
        return
    song.update(clean_youtube_title(data.get("title", ""), data.get("author_name", "")))


def main_artist(song):
    """First credited artist. Takeout lists every musician of a track, which breaks store searches.
    Names that contain a comma ("Fear, and Loathing in Las Vegas") stay whole."""
    artists = song.get("artists")
    if artists:
        return artists[0]
    return song["artist"].strip()


def search_term(song):
    """Text used to search the stores: main artist + song title."""
    return f"{main_artist(song)} {song['title']}".strip()


def search_itunes(song, country, lang):
    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(
        {"term": search_term(song), "entity": "song", "limit": 10, "country": country})
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
    q = urllib.parse.quote(search_term(song))
    return {i18n.t(lang, "search_ytm"): f"https://music.youtube.com/search?q={q}"}


def search_links(song, lang):
    """Search buttons for the stores (the YouTube links have their own column)."""
    q = urllib.parse.quote(search_term(song))
    return {
        # No item_type filter: Bandcamp then also shows artist pages and albums.
        "Bandcamp": f"https://bandcamp.com/search?q={q}",
        "Amazon Music": f"https://{i18n.AMAZON[lang]}/search/{q}",
        "Deezer": f"https://www.deezer.com/search/{q}",
        "Spotify": f"https://open.spotify.com/search/{q}",
    }


def is_unavailable(song):
    return song.get("availability") in availability.UNAVAILABLE


def build_html(songs, output_path, source, lang, youtube_only=False, stores=True):
    """Page with one row per song: YouTube links (+ availability), iTunes match and store buttons.
    youtube_only=True keeps only the YouTube column; stores=False hides the store columns."""
    e = html.escape
    t = lambda key, **kw: e(i18n.t(lang, key, **kw))  # noqa: E731
    link = 'target="_blank" rel="noopener noreferrer"'
    show_itunes = not youtube_only and any("itunes" in s for s in songs)
    show_stores = not youtube_only and stores
    rows = []
    found = unavailable = 0
    for i, s in enumerate(songs, 1):
        yt = " ".join(f'<a class="btn" href="{e(u)}" {link}>{e(n)}</a>'
                      for n, u in youtube_links(s, lang).items())
        if is_unavailable(s):
            unavailable += 1
            yt += f'<br><span class="bad">{t("unavailable")}</span>'
        cells = f'<td class="links">{yt}</td>'
        if show_itunes:
            it = s.get("itunes")
            if it:
                found += 1
                price = ""
                if it["price"] is not None and it["price"] >= 0:
                    price = " — " + i18n.price(lang, it["currency"], it["price"])
                cells += (f'<td><a href="{e(it["link"])}" {link}>{e(it["track"])}</a>'
                          f'<br><small>{e(it["artist"])} · {e(it["album"])}{e(price)}</small></td>')
            elif "itunes" in s:
                cells += f'<td><span class="none">{t("not_found")}</span></td>'
            else:
                cells += '<td><span class="none">—</span></td>'
        if show_stores:
            buttons = " ".join(f'<a class="btn" href="{e(u)}" {link}>{e(n)}</a>'
                               for n, u in search_links(s, lang).items())
            cells += f'<td class="links">{buttons}</td>'
        row_class = ' class="off"' if is_unavailable(s) else ""
        rows.append(
            f'<tr{row_class}><td class="n">{i}</td>'
            f'<td><strong>{e(s["title"]) or t("no_title")}</strong><br>'
            f'<small>{e(s["artist"])}{" · " + e(s["album"]) if s["album"] else ""}</small>'
            + (f'<br><small class="pl">▸ {e(s["playlist"])}</small>' if s.get("playlist") else "")
            + "</td>"
            f"{cells}</tr>")

    summary = t("songs", n=len(songs))
    if show_itunes:
        summary += " · " + t("found_itunes", n=found)
    if any("availability" in s for s in songs):
        summary += " · " + t("unavailable_count", n=unavailable)
    summary += " · " + t("source", name=os.path.basename(source))
    header = f"<th>{t('col_youtube')}</th>"
    if show_itunes:
        header += f"<th>{t('col_itunes')}</th>"
    if show_stores:
        header += f"<th>{t('col_search')}</th>"

    page = f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t("page_title")}</title>
<style>
:root {{ --bg:#fafafa; --fg:#1d1d1f; --mut:#6e6e73; --line:#e5e5ea; --btn:#ececf0; --link:#0060df;
        --bad:#c4291c; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#1c1c1e; --fg:#f2f2f7; --mut:#a1a1a6; --line:#3a3a3c; --btn:#2c2c2e; --link:#6aa8ff;
          --bad:#ff7b6e; }} }}
body {{ font-family: system-ui, sans-serif; background:var(--bg); color:var(--fg);
       margin:0; padding:24px 16px; }}
main {{ max-width:1200px; margin:auto; }}
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
.links {{ min-width:180px; }}
.bad {{ color:var(--bad); font-size:.8rem; font-weight:600; }}
.pl {{ font-size:.75rem; }}
tr.off strong {{ text-decoration: line-through; text-decoration-color: var(--bad); }}
</style></head><body><main>
<h1>{t("page_title")}</h1>
<p class="summary">{summary}</p>
<input id="filter" placeholder="{t("filter")}" oninput="filterRows(this.value)">
<div class="table"><table>
<thead><tr><th>#</th><th>{t("col_song")}</th>{header}</tr></thead>
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


def write_link_lists(songs, output, lang):
    """Writes <output>.txt with the playable YouTube links and, when availability was checked,
    <output>_unavailable.txt with the others. Returns the paths written."""
    base = os.path.splitext(output)[0]
    written = []

    def line(s):
        name = " – ".join(x for x in (s["artist"], s["title"]) if x)
        return f"{name}: {next(iter(youtube_links(s, lang).values()))}\n"

    with open(base + ".txt", "w", encoding="utf-8") as f:
        f.writelines(line(s) for s in songs if not is_unavailable(s))
    written.append(base + ".txt")
    if any("availability" in s for s in songs):
        with open(base + "_unavailable.txt", "w", encoding="utf-8") as f:
            f.writelines(line(s) for s in songs if is_unavailable(s))
        written.append(base + "_unavailable.txt")
    return written


def cached_availability(cache, video_id, lang):
    key = "av:" + video_id
    hit = cache.get(key)
    if isinstance(hit, list) and len(hit) == 2 and time.time() - hit[1] < AVAILABILITY_CACHE_HOURS * 3600:
        return hit[0], True
    status, _reason = availability.video_status(video_id, lang)
    if status not in ("LOOKUP_FAILED", "NO_ID"):
        cache[key] = [status, time.time()]
    return status, False


def main():
    p = argparse.ArgumentParser(description="Find where to buy or stream the songs in a Google Takeout CSV.")
    p.add_argument("csv", help=".csv file exported by Google Takeout")
    p.add_argument("--output", default="my_songs.html",
                   help="HTML file to create; without a folder it is saved in ~/Downloads "
                        "(default: my_songs.html). A .txt list of YouTube links is written next to it.")
    p.add_argument("--lang", default=i18n.DEFAULT, help="language: en-US (default), pt-BR or es")
    p.add_argument("--source-name", default=None,
                   help="name shown as the source (default: the CSV file name)")
    p.add_argument("--country", default=None,
                   help="iTunes Store country (default depends on --lang: US, BR or ES)")
    p.add_argument("--no-itunes", action="store_true",
                   help="do not query iTunes (fast): YouTube links + store search buttons")
    p.add_argument("--youtube-only", action="store_true", help="only YouTube/YouTube Music links (fast)")
    p.add_argument("--skip-availability", action="store_true",
                   help="do not check which videos still play in your region (saves ~1 s per song)")
    p.add_argument("--exclude-artists", default="",
                   help='artists to leave out, comma-separated (e.g. "Artist A,Artist B")')
    args = p.parse_args()
    lang = i18n.normalize(args.lang)
    country = (args.country or i18n.COUNTRY[lang]).upper()
    if args.youtube_only:
        args.no_itunes = True
    check = not args.skip_availability
    if not os.path.dirname(args.output):  # no folder in the name: save to Downloads
        args.output = os.path.join(paths.DOWNLOADS, args.output)

    if not os.path.isfile(args.csv):
        sys.exit(i18n.t(lang, "file_not_found", path=args.csv))

    cols, songs = read_csv(args.csv)
    if not songs:
        sys.exit(i18n.t(lang, "no_songs", columns=json.dumps(cols, ensure_ascii=False)))
    source_name = args.source_name or args.csv
    print(i18n.t(lang, "songs_read", n=len(songs), path=source_name), flush=True)
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
    # YouTube's developer policies: don't keep API-derived data for more than 30 days.
    if not isinstance(cache, dict) or time.time() - cache.get("_created", 0) > CACHE_MAX_DAYS * 86400:
        cache = {"_created": time.time()}

    def save_cache():
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)

    untitled = [s for s in songs if not s["title"] and s["id"]]
    if untitled:
        print(i18n.t(lang, "fetching_titles", n=len(untitled)), flush=True)
        for s in untitled:
            key = "yt2:" + s["id"]  # v2: cleaned with clean_youtube_title()
            if key in cache:
                s.update(cache[key])
            else:
                fill_from_youtube(s)
                cache[key] = {k: s[k] for k in ("title", "artist", "album")}

    try:
        if check or not args.no_itunes:
            if check:
                print(i18n.t(lang, "checking"), flush=True)
            total = len(songs)
            for i, s in enumerate(songs, 1):
                waited = False
                notes = []
                if not args.no_itunes:
                    key = f'it:{country}:{search_term(s)}'
                    if key in cache:
                        s["itunes"] = cache[key]
                    else:
                        s["itunes"] = search_itunes(s, country, lang)
                        cache[key] = s["itunes"]
                        waited = True
                if check and s["id"] and "availability" not in s:  # status from the API is kept
                    s["availability"], from_cache = cached_availability(cache, s["id"], lang)
                    if s["availability"] in availability.UNAVAILABLE:
                        notes.append(i18n.t(lang, "unavailable"))
                    waited = waited or not from_cache
                note = f" ({', '.join(notes)})" if notes else ""
                print(f"[{i}/{total}] {s['artist']} – {s['title']}{note}", flush=True)
                if waited:
                    save_cache()
                    # iTunes allows ~20 requests/min; the availability check fits inside that pause.
                    time.sleep(ITUNES_PAUSE if not args.no_itunes else CHECK_PAUSE)
    except KeyboardInterrupt:
        print(i18n.t(lang, "interrupted"), flush=True)

    save_cache()
    build_html(songs, args.output, source_name, lang, youtube_only=args.youtube_only)
    output = os.path.abspath(args.output)
    print(i18n.t(lang, "done", path=output), flush=True)
    report_file(output)
    for path in write_link_lists(songs, output, lang):
        key = "unavailable_list" if path.endswith("_unavailable.txt") else "text_list"
        print(i18n.t(lang, key, path=path), flush=True)
        report_file(path)


if __name__ == "__main__":
    main()
