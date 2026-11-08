# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Use this repository's
**Security → Report a vulnerability** (private vulnerability reporting) on GitHub.

If you can, include:

- what the issue allows someone to do;
- steps to reproduce;
- your Python version and operating system.

This is a personal project maintained in spare time, so replies are best effort.

## Scope

The project only runs on the user's own computer. The most sensitive parts are:

- the local interface server (`src/infinifind_music/server.py`): token, origin checks, API routes;
- reading and writing files (the Downloads folder);
- running the scripts (`subprocess`).

## Current protections

The automated tests in `tests/test_server.py` check most of these.

- The server listens only on `127.0.0.1`.
- **Session token:** `secrets.token_urlsafe(32)` on every run. The page only opens with
  `/?t=<token>`, and the API requires the `X-Token` header (compared with `hmac.compare_digest`).
  The server injects the token and a nonce into the HTML (`__TOKEN__`, `__NONCE__`).
- **Content Security Policy** with a per-response nonce: `default-src 'none'`, scripts only with
  the nonce, `connect-src 'self'`, `frame-ancestors 'none'`. Also `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer` and `Cache-Control: no-store` (the HTML carries the token).
- POST requests need `Content-Type: application/json` and an `Origin` matching the host, which
  blocks CSRF and DNS rebinding. Request bodies are limited to 64 KB.
- Output names are reduced to a `basename`, so nothing is written outside Downloads.
  `/api/open` only opens files whose `realpath` is inside `~/Downloads`.
- Subprocesses get an argument list and never `shell=True` (`os.startfile` on Windows).
- Generated HTML uses `html.escape`, and the interface uses `textContent` (no `innerHTML` with data).
- External links use `rel="noopener noreferrer"`.
- `curl` is called by its full system path (`paths.curl_path()`), only with `https://` URLs
  (`--proto =https`), and `urlopen` only receives `https://` URLs.

## Checking for vulnerabilities

No software can be guaranteed free of vulnerabilities, so check regularly:

```bash
pip install pip-audit bandit
pip-audit                    # known vulnerabilities in the installed dependencies
bandit -r src -ll            # common security issues in the project's code
```

On GitHub, Dependabot (`.github/dependabot.yml`) checks the dependencies every week and opens
a pull request when an update is available.

Also keep Python itself up to date with the latest patch release of your version
(see [python.org/downloads](https://www.python.org/downloads/)): patch releases often include
security fixes. On macOS, run `scripts/build_macos_app.sh` again after updating Python, since the
app bundles a copy of the Python executable.

## Known limitations

- The macOS `.app` is ad-hoc signed and has no hardened runtime (it is not notarized).
- The search cache (in the system cache folder, see `paths.py`) and the log are stored in plain
  text on the user's computer.
- The availability check reads public YouTube pages, a grey area of YouTube's terms.
