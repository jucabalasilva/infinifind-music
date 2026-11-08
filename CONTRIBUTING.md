# Contributing

Thanks for wanting to help! Issues and pull requests are welcome.

## Setting up

```bash
git clone https://github.com/jucabalasilva/infinifind-music.git
cd infinifind-music
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[app,dev]"        # editable install + pywebview + pytest + ruff
ruff check .                       # lint (style, bugs and security rules)
pytest                             # run the tests
```

## Project layout

The project follows the [PyPA](https://packaging.python.org/) recommendations: a
`pyproject.toml` and the code in a `src/` layout.

| Path | What it is |
|---|---|
| `pyproject.toml` | Metadata, dependencies (`app` and `dev` extras) and the `infinifind*` commands. |
| `src/infinifind_music/finder.py` | Reads the Takeout CSV and builds the HTML page (and the `.txt` list in `--youtube-only` mode). |
| `src/infinifind_music/availability.py` | Checks each link in a `.txt` list and moves unavailable ones to `<list>_unavailable.txt`. |
| `src/infinifind_music/i18n.py` | Translations for the command line and the generated pages. |
| `src/infinifind_music/paths.py` | Downloads, cache and app-data folders for each operating system. |
| `src/infinifind_music/server.py` | Local server behind the interface; runs the tools and reports progress. |
| `src/infinifind_music/web/ui.html` | The interface (Frutiger Aero style, light/dark themes, translations in `STRINGS`). |
| `src/infinifind_music/app.py` | Desktop app: runs the server and shows the interface in a native window (pywebview). |
| `src/infinifind_music/assets/` | App icon: `icon.svg` is the source; `icon.png` and `icon.icns` are generated from it. |
| `scripts/` | `build_macos_app.sh` builds `InfiniFind Music.app`; the `.command` file opens it from Finder. |
| `examples/` | Example CSVs in the Takeout format, for testing. |
| `tests/` | Automated tests (pytest). They don't use the network. |

## Guidelines

- Run `ruff check .` and `pytest` before every commit; both must pass. Ruff is configured in
  `pyproject.toml` (`[tool.ruff]`) and also checks the flake8-bandit security rules (`S`).
  `ruff check --fix .` fixes the simple issues (unused imports, import order) for you.
  If you silence a rule with `# noqa`, say why on the same line.
- Keep the core tools on the Python standard library. The desktop window only uses `pywebview`,
  pinned in the `app` extra of `pyproject.toml`.
- Code, comments and docs are in English. User-facing text must exist in all supported
  languages (`en-US`, `pt-BR`, `es`): add it to `i18n.py` and/or to `STRINGS` in `ui.html`.
  `tests/test_i18n.py` fails if a translation is missing.
- Generated files go to `~/Downloads`; ask before overwriting.
- Caches and app data go to the folders in `paths.py`, never inside the project.
- The project helps people find music legally. Do not add features that download audio from
  YouTube or bypass any protection.
- Use original artwork. Don't use YouTube, YouTube Music or other companies' logos.

## Security checklist

Before opening a pull request that touches the server or the interface, check:

- [ ] New API route? It requires the token (`_token_ok`) and, for POST, the origin and JSON checks.
- [ ] Receives a file path? Normalize it with `realpath` and restrict it to the allowed folder.
- [ ] Runs a program? Argument list, no shell, no command built from user text.
- [ ] Shows data from a file or the network? Escape it (Python) or use `textContent` (JS).
- [ ] New script on the page? It needs `nonce="__NONCE__"`; no external CDNs.
- [ ] New dependency? Only if essential; pin the version in `pyproject.toml`.
- [ ] New external service? Document in the README what is sent (privacy).
- [ ] Writes to Downloads? Confirm before overwriting.
- [ ] Add or update tests in `tests/test_server.py` for the protections you touched.
- [ ] `ruff check .` passes (it includes the `S` security rules).

See [SECURITY.md](SECURITY.md) for the protections already in place.

## Testing by hand

```bash
infinifind-find examples/library_example.csv --youtube-only --output /tmp/test.html
infinifind-web --no-browser --port 8799      # open the printed URL (it includes the token)
```

Use test output names (e.g. `test.html`) so you don't overwrite your real lists in Downloads.
