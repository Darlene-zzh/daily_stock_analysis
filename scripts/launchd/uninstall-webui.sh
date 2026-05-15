#!/usr/bin/env bash
# Stop the DSA Web UI LaunchAgent and remove its plist. Safe to re-run.

set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "ERROR: This uninstaller targets macOS LaunchAgents only." >&2
  exit 1
fi

LABEL="com.dsa.webui"
TARGET_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  echo "==> Stopping $LABEL"
  launchctl bootout "$DOMAIN" "$TARGET_PLIST" 2>/dev/null || \
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
else
  echo "==> $LABEL is not currently loaded"
fi

if [[ -f "$TARGET_PLIST" ]]; then
  echo "==> Removing $TARGET_PLIST"
  rm -f "$TARGET_PLIST"
else
  echo "==> No plist to remove at $TARGET_PLIST"
fi

echo
echo "Uninstalled. To verify nothing still listens on port 8000:"
echo "  lsof -nP -iTCP:8000 -sTCP:LISTEN"
