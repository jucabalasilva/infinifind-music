<p align="center">
  <img src="src/infinifind_music/assets/icon.png" alt="InfiniFind Music icon" width="128">
</p>

<h1 align="center">InfiniFind Music</h1>

<p align="center">
  Bring your YouTube Music playlists anywhere: read them straight from your YouTube account (or
  from a Google Takeout export), find where to buy or stream each song legally, and keep a clean
  list of links.<br>
  Includes a <b>Frutiger Aero</b>-style desktop app with light and dark themes, in
  English, Portuguese (Brazil) and Spanish.
</p>

---

## Features

- **Reads your playlists straight from your YouTube account**: sign in with Google (read-only
  access), see all your playlists and your liked videos with their number of videos, tick the
  ones you want or **select all**.
- **Also reads Google Takeout exports** (your YouTube Music library or playlists), with headers in
  English, Portuguese or Spanish.
- **Builds one complete page** (the default): for each song, its YouTube and YouTube Music
  links, the iTunes Store match with link and price, and search buttons for Bandcamp, Amazon
  Music, Deezer and Spotify. Faster modes skip iTunes or keep only the YouTube links.
- **One page for everything or one file per playlist**, each song labelled with its playlist;
  a video that is in several playlists appears once.
- **Writes a `.txt` list of YouTube Music links**, optionally leaving some artists out.
- **Checks which videos still play in your region** while it builds the page (on by default):
  unavailable ones are marked on the page and moved to a separate `_unavailable.txt` list. When
  you are signed in, the check uses the official YouTube Data API (50 videos per request).
- **Suggests file names** from what you selected, always command-line friendly
  (`animes_e_games.html`, `mpb_rock.html`).
- **Lets you choose your files and folders**: the Takeout CSV anywhere on your computer and the
  folder where results are saved (Downloads by default, remembered).
- **Desktop app** with its own window, an animated day/night scenery, light/dark theme, language
  picker (English is the default), a selection summary with an estimated time and a progress
  bar. It also runs in the browser or from the command line.

Everything runs on your computer: the project has no server of its own and collects no data. The
Google account is optional; without it you can still use Takeout exports.

## Requirements

- **Python 3.9 or newer.** The core tools use only the standard library.
- For the **desktop window**: [pywebview](https://pywebview.flowrl.com/), and
  [keyring](https://pypi.org/project/keyring/) to remember your Google sign-in, both installed with
  the `app` extra (see [Installation](#installation)).
- `curl`, used when Python has no HTTPS certificates (common with the python.org installer on macOS).
- Optional: a Google account to read your playlists directly (see below).

Tested on **macOS**. The command-line tools and the browser version should work on Linux and
Windows; the `.app` builder is macOS-only.

## Getting your songs in

There are two ways, and you can use both:

| | Your YouTube account | Google Takeout export |
|---|---|---|
| **Playlists** (yours and liked videos) | ✅ directly, always up to date | ✅ one CSV per playlist |
| **YouTube Music library** (songs/albums you added) | ❌ not available in the YouTube API | ✅ `music library songs.csv` |
| **Setup** | sign in once (needs a Google Cloud client ID for now) | request an export, wait for the email |

### Option 1: sign in with your YouTube account

The app asks Google only for **read-only** access (`youtube.readonly`): it can read your channel
name and your playlists, and can never change anything.

1. **Set up Google access (once).** For now you need your own Google Cloud client ID (free, about
   15 minutes): follow [docs/google-cloud-setup.md](docs/google-cloud-setup.md), then click
   **Set up Google access…** in the app and choose the downloaded `.json` file. Released builds
   will ship a client ID verified by Google, so regular users won't need this step.
2. **Sign in.** Click **Sign in with Google**. The sign-in opens in your own browser (Google blocks
   sign-in inside app windows) and comes back to the app automatically. You stay signed in on this
   computer; **Sign out** revokes the access at Google.
3. **Choose playlists.** Select **Source → My YouTube account**. Your playlists and liked videos
   are listed with their number of videos: tick the ones you want, or **Select all**. Below the
   list, the app shows how many videos are selected and roughly how long it will take (a big
   liked-videos list can have thousands).
4. Tick **One file per playlist** if you want a separate page and list for each one; otherwise
   you get one page with a **Playlist** label on each song. Deleted and private videos are listed
   as unavailable.

### Option 2: export with Google Takeout

You can export your **library** (the songs you added or liked), your **playlists**, or both, in a
single export.

> The labels below are from the English version of Takeout. Your Takeout may use your
> account's language, and the names may change slightly over time.

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

The files end up like this:

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

In the app, select **Source → Google Takeout file**: the files in `Downloads/Takeout` show up in
the **CSV file** list; if your Takeout folder is somewhere else, click **Choose…**. On the command
line:

```bash
infinifind-find ~/Downloads/Takeout/"YouTube and YouTube Music/playlists/Road trip videos.csv" --youtube-only
```

Playlist files only contain the **video ID** of each song, without title or artist. The app gets
each title from YouTube: through the official API when you are signed in (50 videos per request),
otherwise one quick request per song. The results are cached for the next runs.

**What Takeout does not export:** the audio of catalog songs (only lists). Songs downloaded in
the YouTube Music phone app are encrypted and only play inside that app; the only audio files you
get are the ones you uploaded yourself (`music-uploads`).

## Using the app

1. **Source:** your YouTube account (choose playlists) or a Google Takeout file (choose a CSV).
2. **What to build:**
   - **Complete** (default): YouTube links, iTunes Store match (link and price) and search buttons
     for other stores. About 3 s per song, because of iTunes' rate limit.
   - **YouTube links only**: fast; the page and the `.txt` list.
   - **YouTube + store buttons**: fast; without iTunes prices.
3. **Check which videos still play** (on by default): unavailable videos are marked and moved to a
   separate list. Almost instant when signed in; otherwise about 1 s per song in the fast modes.
4. **Leave out these artists** (optional), comma-separated.
5. **File name:** suggested from what you selected — the playlist name (`animes_e_games.html`), up
   to three names joined (`mpb_rock.html`), "and N more", "all playlists", or the Takeout file name
   (`Vídeos da playlist Aberturas.csv` → `aberturas.html`). Names are always command-line friendly:
   lowercase letters, digits and `_` only. A name you type is kept and normalized the same way
   ("Minhas Músicas" → `minhas_musicas.html`).
6. **Save to:** Downloads by default; **Change…** picks another folder (remembered) and
   **Use Downloads** goes back.
7. Click **Start**, follow the progress, then use the **Open** buttons to see the page and lists.
   The app asks before overwriting existing files.

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
| `infinifind-find` | Reads a Takeout CSV and builds the page, the link list and the unavailable list. (Reading playlists from your account is done in the app.) |
| `infinifind-check` | Command line only: removes links that no longer play from an older `.txt` list. |

Each one also runs as a module, without installing: for example
`PYTHONPATH=src python3 -m infinifind_music.finder ...`.

```bash
# Complete page: YouTube + iTunes + store buttons, checking which videos still play
# (~3 s per song; Ctrl+C stops and a new run resumes)
infinifind-find "music library songs.csv"

# YouTube links only (fast), leaving two artists out
infinifind-find "music library songs.csv" --youtube-only --exclude-artists "Artist A,Artist B"

# YouTube + store search buttons, without iTunes prices (fast)
infinifind-find "music library songs.csv" --no-itunes

# Skip the availability check (saves ~1 s per song in the fast modes)
infinifind-find "music library songs.csv" --youtube-only --skip-availability

# Check a list you already have
infinifind-check ~/Downloads/youtube_links.txt

# Any of them in Portuguese or Spanish
infinifind-find "music library songs.csv" --youtube-only --lang pt-BR
infinifind-check ~/Downloads/youtube_links.txt --lang es
```

The command line saves results to **Downloads** unless `--output` includes a folder. In the app,
use **Save to → Change…** to pick another folder; your choice is remembered (and
**Use Downloads** goes back to the default). To try it without your own data, use the files in
`examples/`.

## Languages

The interface, the generated pages and the command-line messages are available in:

| Language | Code |
|---|---|
| 🇺🇸 English (default) | `en-US` |
| 🇧🇷 Portuguese (Brazil) | `pt-BR` |
| 🇪🇸 Spanish | `es` |

In the app, use the language menu at the top (🇺🇸 English, 🇧🇷 Português, 🇪🇸 Español). Your
choice is remembered. On the command line, use `--lang`. Translations live in `src/infinifind_music/i18n.py` (command line and generated
pages) and in the `STRINGS` object in `src/infinifind_music/web/ui.html` (interface). To add a
language, add it to both.

## Privacy

- Your data stays on your computer. The project has no server, account or telemetry.
- External services it talks to, and what they receive:
  - **iTunes Search (Apple):** artist and title of each song, plus your IP address.
  - **YouTube:** the ID of each video, to get the title (playlists) and check availability,
    plus your IP address. When you are signed in with Google, this goes through the official
    YouTube Data API (50 videos per request, using your country to detect regional blocks);
    otherwise the app reads each public video page.
- **If you sign in with Google:** the app talks to Google's sign-in and YouTube Data API servers
  with your permission, only to read your channel name and playlists. The sign-in token stays in
  the app (never in the page, logs or generated files); the long-lived part is kept in your
  system keychain (macOS Keychain, Windows Credential Manager or Secret Service) so you stay
  signed in. Your Google client file is kept in the app-data folder, readable only by you.
- Stored on your computer in plain text: the search cache (`~/Library/Caches/InfiniFindMusic`
  on macOS, `~/.cache/InfiniFindMusic` on Linux, `%LOCALAPPDATA%\InfiniFindMusic` on Windows),
  the macOS app log (`~/Library/Logs/InfiniFindMusic.log`), your theme and language choice, and
  the output folder you picked (`settings.json` in the app-data folder).
- The account panel links to the YouTube Terms of Service and the Google Privacy Policy.
- The `.gitignore` keeps results, caches and Takeout files from being pushed to GitHub by mistake.

## Security

- The interface only accepts connections from this computer (`127.0.0.1`) and requires a secret
  token created on every run.
- It rejects requests from other websites open in your browser and uses a strict Content
  Security Policy.
- It only writes and opens files in Downloads or in a folder you picked yourself in the
  system's folder window, and asks before overwriting anything.
- External scripts run without a shell, and all displayed text is escaped.
- Google sign-in uses OAuth 2.0 for desktop apps with PKCE, a one-time `state`, the read-only
  YouTube scope only, and token revocation on sign-out.

**Known limitations:** the generated `.app` is signed locally (*ad-hoc*), is not notarized by
Apple and runs without the *hardened runtime*. Without Google sign-in, the availability check
reads public YouTube pages, whose format may change.

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
│   ├── finder.py               reads the songs (CSV), builds pages and lists
│   ├── availability.py         checks which links still play
│   ├── i18n.py                 translations (en-US, pt-BR, es)
│   ├── paths.py                Downloads, cache and app-data folders, settings
│   ├── picker.py               native "choose file / folder" dialogs
│   ├── youtube_auth.py         Google sign-in (OAuth 2.0 + PKCE), read-only YouTube access
│   ├── youtube_api.py          reads the signed-in user's playlists (YouTube Data API v3)
│   ├── net.py                  HTTPS helper for the Google APIs (system certificates)
│   ├── web/ui.html             the interface
│   └── assets/                 app icon (SVG source, PNG, ICNS)
├── docs/                       guides (Google Cloud setup)
├── scripts/                    macOS app builder and launcher
├── examples/                   sample CSVs in the Takeout format
└── tests/                      automated tests (pytest)
```

## Changelog

What changed in each version: [CHANGELOG.md](CHANGELOG.md) and the
[releases](https://github.com/jucabalasilva/infinifind-music/releases).

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE). You are free to use, copy, modify and distribute it, as long as you keep the
license notice.

Not affiliated with YouTube, Google or Apple.
