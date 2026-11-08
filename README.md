<p align="center">
  <img src="src/infinifind_music/assets/icon.png" alt="InfiniFind Music icon" width="128">
</p>

<h1 align="center">InfiniFind Music</h1>

<p align="center">
  Organize the library you exported from YouTube Music: list your songs, find where to buy or
  stream them legally, and keep a clean list of links.<br>
  Includes a <b>Frutiger Aero</b>-style desktop app with light and dark themes, in
  English, Portuguese (Brazil) and Spanish.
</p>

---

## Features

- **Reads the Google Takeout CSV** (YouTube Music library or playlists), with headers in English,
  Portuguese or Spanish.
- **Looks up each song in the iTunes Store**, with link and price, and builds search buttons for
  Bandcamp, Amazon Music, Deezer and Spotify.
- **Builds a list of YouTube Music links** as a page and as a `.txt` file, optionally leaving
  some artists out.
- **Checks which links still play in your region** and moves the unavailable ones to a
  separate file.
- **Desktop app** with its own window, light/dark theme, language picker (English is the
  default) and a progress bar. It also runs in the browser or from the command line.

Everything runs on your computer: no account, no API key and no data collection.

## Requirements

- **Python 3.9 or newer.** The core tools use only the standard library.
- For the **desktop window**: [pywebview](https://pywebview.flowrl.com/), installed with the
  `app` extra (see below).
- `curl`, used when Python has no HTTPS certificates (common with the python.org installer on macOS).

Tested on **macOS**. The command-line tools and the browser version should work on Linux and
Windows; the `.app` builder is macOS-only.

## Exporting your data with Google Takeout

InfiniFind Music works with the CSV files that Google Takeout creates for YouTube Music. You
can export your **library** (the songs you added or liked), your **playlists**, or both, in a
single export.

> The labels below are from the English version of Takeout. Your Takeout may use your
> account's language, and the names may change slightly over time.

### Step by step

1. Go to [takeout.google.com](https://takeout.google.com) and sign in with the Google account you
   use on YouTube Music.
2. At the top of the list, click **Deselect all**, so you don't export your whole Google account.
3. Scroll down to **YouTube and YouTube Music** and check its box.
4. Click **All YouTube data included**. In the window that opens, click **Deselect all**, then
   check only what you need:
   - `music-library-songs`: the songs in your YouTube Music library.
   - `playlists`: your playlists, one CSV file per playlist.
   - `music-uploads` (optional): songs you uploaded yourself. These are the only ones that come
     with the audio files.

   Click **OK**.
5. Leave **Multiple formats** as it is. Playlists and the library are exported as CSV by default.
6. Click **Next step** and choose:
   - **Destination:** *Send download link via email*.
   - **Frequency:** *Export once*.
   - **File type & size:** `.zip`.
7. Click **Create export**. Google emails you when it is ready, which can take from a few
   minutes to a few days. Download links usually expire after about 7 days.
8. Download the `.zip` and extract it into your **Downloads** folder, so you end up with a
   `Downloads/Takeout` folder.

### Where the files end up

```
Downloads/Takeout/YouTube and YouTube Music/
├── music (library and uploads)/
│   └── music library songs.csv        ← your library
└── playlists/
    ├── playlists.csv                  ← index of your playlists (not used directly)
    ├── Road trip videos.csv           ← one file per playlist
    └── Watch later videos.csv
```

Folder and file names follow your account's language. In Portuguese, for example, they are
`YouTube e YouTube Music/` and `Vídeos da playlist <name>.csv`. The app finds them either way.

### Using a playlist

- **In the app:** every playlist shows up in the **CSV file** list. Pick one, choose what to
  build and click **Start**.
- **On the command line:**

  ```bash
  infinifind-find ~/Downloads/Takeout/"YouTube and YouTube Music/playlists/Road trip videos.csv" --youtube-only
  ```

Playlist files only contain the **video ID** of each song, without title or artist. InfiniFind
Music looks up each title on YouTube (one quick request per song), so you need an internet
connection the first time. The results are cached for the next runs.

### What Takeout does not export

- It never exports the audio of catalog songs, only lists. Songs downloaded in the YouTube Music
  phone app are encrypted and only play inside that app.
- The only audio files you get are the ones you uploaded yourself (`music-uploads`).

## Installation

```bash
git clone https://github.com/jucabalasilva/infinifind-music.git
cd infinifind-music
```

### Desktop app (macOS)

```bash
scripts/build_macos_app.sh
```

This creates a Python environment (`.venv`), installs the project with pywebview and builds
`~/Applications/InfiniFind Music.app`. Open it from Spotlight or Finder, or double-click
`scripts/Open InfiniFind Music.command`. If macOS blocks it the first time, right-click the app
and choose **Open**.

If you move the project folder, run `scripts/build_macos_app.sh` again.

### Any system, with pip

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[app]"            # without "[app]" you get only the command-line tools
infinifind                         # opens the desktop app
```

pywebview may need system packages (GTK or Qt on Linux, WebView2 on Windows). See its
[installation guide](https://pywebview.flowrl.com/guide/installation.html). Without pywebview,
`infinifind` opens the interface in your browser instead.

You can also install it once for your user with [pipx](https://pipx.pypa.io/):
`pipx install ".[app]"`.

### Browser version

```bash
infinifind-web
```

Your browser opens automatically. The address includes a secret code (`?t=...`), so use the
link printed in the terminal.

## Commands

| Command | What it does |
|---|---|
| `infinifind` | Opens the desktop app (or the browser version without pywebview). |
| `infinifind-web` | Opens the interface in your browser. |
| `infinifind-find` | Reads a Takeout CSV and builds the page and link list. |
| `infinifind-check` | Removes links that no longer play in your region. |

Each one also runs as a module, without installing: for example
`PYTHONPATH=src python3 -m infinifind_music.finder ...`.

```bash
# YouTube Music links only (instant), leaving two artists out
infinifind-find "music library songs.csv" --youtube-only --exclude-artists "Artist A,Artist B"

# Look up every song in the iTunes Store (~3 s per song; Ctrl+C stops and a new run resumes)
infinifind-find "music library songs.csv"

# Store search buttons only
infinifind-find "music library songs.csv" --no-itunes

# Check which links still play
infinifind-check ~/Downloads/youtube_links.txt

# Any of them in Portuguese or Spanish
infinifind-find "music library songs.csv" --youtube-only --lang pt-BR
infinifind-check ~/Downloads/youtube_links.txt --lang es
```

Results are saved to **Downloads**. To try it without your own data, use the files in `examples/`.

## Languages

The interface, the generated pages and the command-line messages are available in:

| Language | Code |
|---|---|
| 🇺🇸 English (default) | `en-US` |
| 🇧🇷 Portuguese (Brazil) | `pt-BR` |
| 🇪🇸 Spanish | `es` |

In the app, use the language menu at the top (🇺🇸 English, 🇧🇷 Português, 🇪🇸 Español). Your choice is remembered. On the command line, use
`--lang`. Translations live in `src/infinifind_music/i18n.py` (command line and generated
pages) and in the `STRINGS` object in `src/infinifind_music/web/ui.html` (interface). To add a
language, add it to both.

## Privacy

- Your data stays on your computer. The project has no server, account or telemetry.
- External services it talks to, and what they receive:
  - **iTunes Search (Apple):** artist and title of each song, plus your IP address.
  - **YouTube:** the ID of each video, to get the title (playlists) and check availability,
    plus your IP address.
- Stored on your computer in plain text: the search cache (`~/Library/Caches/InfiniFindMusic`
  on macOS, `~/.cache/InfiniFindMusic` on Linux, `%LOCALAPPDATA%\InfiniFindMusic` on Windows),
  the macOS app log (`~/Library/Logs/InfiniFindMusic.log`) and your theme and language choice.
- The `.gitignore` keeps results, caches and Takeout files from being pushed to GitHub by mistake.

## Security

- The interface only accepts connections from this computer (`127.0.0.1`) and requires a secret
  token created on every run.
- It rejects requests from other websites open in your browser and uses a strict Content
  Security Policy.
- It only writes and opens files in the Downloads folder, and asks before overwriting anything.
- External scripts run without a shell, and all displayed text is escaped.

**Known limitations:** the generated `.app` is signed locally (*ad-hoc*), is not notarized by
Apple and runs without the *hardened runtime*. The availability check reads public YouTube
pages, whose format may change.

Found a security issue? See [SECURITY.md](SECURITY.md).

## Responsible use

This project **does not download music** and must not be used for that. Downloading audio from
YouTube breaks the service's terms of use and, in most cases, copyright. To own the files, buy
them from stores such as iTunes, Bandcamp, Qobuz, 7digital or, for game soundtracks, Steam.

## Project structure

```
infinifind-music/
├── pyproject.toml              project metadata, dependencies and commands
├── src/infinifind_music/       the Python package
│   ├── app.py                  desktop app (pywebview window)
│   ├── server.py               local server behind the interface
│   ├── finder.py               reads the Takeout CSV, builds pages and lists
│   ├── availability.py         checks which links still play
│   ├── i18n.py                 translations (en-US, pt-BR, es)
│   ├── paths.py                Downloads, cache and app-data folders
│   ├── web/ui.html             the interface
│   └── assets/                 app icon (SVG source, PNG, ICNS)
├── scripts/                    macOS app builder and launcher
├── examples/                   sample CSVs in the Takeout format
└── tests/                      automated tests (pytest)
```

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE). You are free to use, copy, modify and distribute it, as long as you keep the
license notice.

Not affiliated with YouTube, Google or Apple.
