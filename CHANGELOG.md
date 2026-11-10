# Changelog

All notable changes to InfiniFind Music. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Links to the YouTube Terms of Service and the Google Privacy Policy under the account panel
  (English, Portuguese and Spanish).

### Fixed
- SECURITY.md: the macOS app log is the only log file; the wording about stored data is more precise.

## [2.0.0] - 2026-11-09

A big rework of the app: it can now read your playlists straight from your YouTube account.

### Added
- **Sign in with Google** (read-only YouTube access, OAuth 2.0 with PKCE). The sign-in opens in your
  browser, is remembered in the system keychain and is revoked when you sign out. A guide explains
  how to create the Google Cloud client ID ([docs/google-cloud-setup.md](docs/google-cloud-setup.md)).
- **Playlists from your account**: choose the source (Takeout file or YouTube account), tick the
  playlists you want (liked videos included) or select all, and build one page with a Playlist label
  on each song or one file per playlist. The app shows how many videos are selected and roughly how
  long it will take.
- **Complete mode** (new default): one page with YouTube links, the iTunes Store match (link and
  price) and search buttons for Bandcamp, Amazon Music, Deezer and Spotify.
- **Availability check while building the page**: unavailable videos are marked and moved to a
  separate `_unavailable.txt` list. When signed in, the check uses the official YouTube Data API
  (50 videos per request, regional blocks for your country); otherwise it reads each video page.
- **Choose files and folders**: pick the Takeout CSV anywhere on your computer and choose (and
  remember) the folder where results are saved.
- **File names suggested automatically** from the selected playlists or Takeout file, always
  command-line friendly (lowercase letters, digits and `_`).
- **New scenery** in both themes: sun, clouds and textured hills by day; moon, stars, Milky Way,
  aurora and moonlit clouds at night.
- New app icon (original artwork) and the InfiniFind Music name.
- `CHANGELOG.md`, Dependabot, private vulnerability reporting, ruff and 52 automated tests.

### Changed
- Store searches use only the main artist and the song title, which finds far more results.
- Titles of YouTube videos are cleaned (official channels, anime/game fan uploads, full-width
  characters, notes such as "FULL" or "Lyrics").
- The project follows the PyPA layout (`pyproject.toml` + `src/`) with installable commands
  (`infinifind`, `infinifind-web`, `infinifind-find`, `infinifind-check`).
- The macOS app takes its version from the package.
- Caches expire after 30 days, as YouTube's developer policies require.

### Removed
- The separate "Check availability" panel: the check now runs while the page is built. Older `.txt`
  lists can still be checked from the command line with `infinifind-check`.

### Security
- The local interface requires a per-run token, uses a strict Content Security Policy, rejects
  requests from other websites and only writes or opens files in Downloads or the folder you chose.
- Google tokens never leave the app process (never sent to the page, logs, files or subprocesses).

## [1.0.0] - 2026-11-07

First public release: reads the Google Takeout CSV, builds pages with YouTube Music links, iTunes
Store matches and store search buttons, checks which videos still play, Frutiger Aero desktop app
in English, Portuguese (Brazil) and Spanish.

[2.0.0]: https://github.com/jucabalasilva/infinifind-music/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/jucabalasilva/infinifind-music/releases/tag/v1.0.0
