#!/usr/bin/env bash
# Install the DSA Web UI as a macOS LaunchAgent so it auto-starts on login
# and keeps running in the background. Idempotent: re-running re-renders
# the plist, reloads the agent, and restarts the service.
#
# Usage:
#   ./scripts/launchd/install-webui.sh                 # use detected python3.11
#   PYTHON_BIN=/path/to/python ./scripts/launchd/install-webui.sh
#
# Uninstall: ./scripts/launchd/uninstall-webui.sh

set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "ERROR: This installer targets macOS LaunchAgents only." >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMPLATE="$REPO_ROOT/scripts/launchd/com.dsa.webui.plist.template"
LABEL="com.dsa.webui"
TARGET_DIR="$HOME/Library/LaunchAgents"
TARGET_PLIST="$TARGET_DIR/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "ERROR: template not found at $TEMPLATE" >&2
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done
fi
if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: no usable python interpreter found." >&2
  echo "Set PYTHON_BIN=/full/path/to/python and re-run." >&2
  exit 1
fi

# Smoke-check: imports that main.py needs at startup.
if ! "$PYTHON_BIN" -c "import fastapi, uvicorn, pandas" >/dev/null 2>&1; then
  echo "ERROR: $PYTHON_BIN is missing required modules (fastapi / uvicorn / pandas)." >&2
  echo "Run: $PYTHON_BIN -m pip install -r $REPO_ROOT/requirements.txt" >&2
  exit 1
fi

mkdir -p "$TARGET_DIR" "$LOG_DIR"

echo "==> Rendering plist for $LABEL"
echo "    Python : $PYTHON_BIN"
echo "    Repo   : $REPO_ROOT"
echo "    Logs   : $LOG_DIR/dsa-webui.log"

sed \
  -e "s|{{PYTHON_BIN}}|$PYTHON_BIN|g" \
  -e "s|{{REPO_ROOT}}|$REPO_ROOT|g" \
  -e "s|{{LOG_DIR}}|$LOG_DIR|g" \
  "$TEMPLATE" >"$TARGET_PLIST"

# Validate the rendered plist before loading it — saves a confusing
# "launchctl bootstrap failed" later.
if ! plutil -lint "$TARGET_PLIST" >/dev/null; then
  echo "ERROR: rendered plist failed plutil -lint:" >&2
  plutil -lint "$TARGET_PLIST" >&2 || true
  exit 1
fi

DOMAIN="gui/$(id -u)"

if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  echo "==> Unloading existing agent (will reload below)"
  launchctl bootout "$DOMAIN" "$TARGET_PLIST" 2>/dev/null || true
fi

echo "==> Bootstrapping $LABEL"
launchctl bootstrap "$DOMAIN" "$TARGET_PLIST"
launchctl enable "$DOMAIN/$LABEL"
launchctl kickstart -k "$DOMAIN/$LABEL"

echo
echo "Installed. The DSA Web UI now runs in the background and auto-starts on login."
echo
echo "  Status : launchctl print $DOMAIN/$LABEL | head"
echo "  Logs   : tail -f $LOG_DIR/dsa-webui.log"
echo "  Stop   : launchctl bootout $DOMAIN $TARGET_PLIST"
echo "  Remove : ./scripts/launchd/uninstall-webui.sh"
echo
echo "Open http://127.0.0.1:8000 once the log shows 'Uvicorn running'."
