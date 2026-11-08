#!/bin/bash
# Builds "InfiniFind Music.app" in ~/Applications (macOS), pointing to this project folder.
# Run it again if you move the project folder.
#   scripts/build_macos_app.sh                 -> ~/Applications/InfiniFind Music.app
#   scripts/build_macos_app.sh /some/folder    -> /some/folder/InfiniFind Music.app
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$HOME/Applications}"
APP="$DEST/InfiniFind Music.app"

# Python environment with the package and pywebview (the "app" extra in pyproject.toml)
if [ ! -x "$PROJECT/.venv/bin/python" ]; then
  echo "Creating Python environment (.venv)…"
  python3 -m venv "$PROJECT/.venv"
fi
"$PROJECT/.venv/bin/pip" install -q --disable-pip-version-check -e "$PROJECT[app]"

mkdir -p "$DEST"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$PROJECT/src/infinifind_music/assets/icon.icns" "$APP/Contents/Resources/icon.icns"

cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>InfiniFind Music</string>
  <key>CFBundleDisplayName</key><string>InfiniFind Music</string>
  <key>CFBundleIdentifier</key><string>local.infinifindmusic.app</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>InfiniFindMusic</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
EOF

# Copy of the Python executable inside the app, so macOS shows "InfiniFind Music" in the Dock
# and menu instead of "Python". Ad-hoc signed locally so it can run.
PYBIN="$("$PROJECT/.venv/bin/python" -c 'import sys,os; print(os.path.join(sys.base_prefix, "Resources/Python.app/Contents/MacOS/Python"))')"
SITE="$("$PROJECT/.venv/bin/python" -c 'import site; print(site.getsitepackages()[0])')"
if [ -x "$PYBIN" ]; then
  cp "$PYBIN" "$APP/Contents/MacOS/InfiniFind Music"
  codesign --force -s - "$APP/Contents/MacOS/InfiniFind Music" 2>/dev/null
  PY_APP="$APP/Contents/MacOS/InfiniFind Music"
else
  PY_APP="$PROJECT/.venv/bin/python"   # non-framework Python: use the venv one
fi

cat > "$APP/Contents/MacOS/InfiniFindMusic" <<EOF
#!/bin/bash
LOG="\$HOME/Library/Logs/InfiniFindMusic.log"
cd "$PROJECT" || { osascript -e 'display alert "InfiniFind Music" message "Project folder not found: $PROJECT. Run scripts/build_macos_app.sh again."'; exit 1; }
export PYTHONPATH="$PROJECT/src:$SITE"
exec "$PY_APP" -m infinifind_music >>"\$LOG" 2>&1
EOF
chmod +x "$APP/Contents/MacOS/InfiniFindMusic"
codesign --force -s - "$APP" 2>/dev/null || true

touch "$APP"
echo "Done: $APP"
