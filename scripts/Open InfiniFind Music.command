#!/bin/bash
# Double-click this file in Finder to open the app (macOS). Builds it the first time.
cd "$(dirname "$0")/.."
if [ ! -d "$HOME/Applications/InfiniFind Music.app" ]; then
  scripts/build_macos_app.sh
fi
open "$HOME/Applications/InfiniFind Music.app"
