#!/bin/bash
# Install the slack-bridge launchd unit.
# Assumes the venv already exists (uv venv && uv pip install -e .)
# Requires WORKSPACE_ROOT env var (path to your anson workspace).

set -e

if [ -z "${WORKSPACE_ROOT:-}" ]; then
    echo "Error: WORKSPACE_ROOT not set. Export it first:"
    echo "  export WORKSPACE_ROOT=\"\$HOME/Assistant\"  # or wherever your workspace is"
    exit 1
fi

PLIST_TMPL="$(cd "$(dirname "$0")" && pwd)/ai.slack-bridge.gateway.plist.tmpl"
PLIST_DST="$HOME/Library/LaunchAgents/ai.slack-bridge.gateway.plist"

if [ ! -f "${WORKSPACE_ROOT}/slack-bridge/.venv/bin/python" ]; then
    echo "Error: venv not found at ${WORKSPACE_ROOT}/slack-bridge/.venv."
    echo "Run 'uv venv && uv pip install -e .' inside ${WORKSPACE_ROOT}/slack-bridge first."
    exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
# Substitute placeholders in the plist template at install time.
sed -e "s|{{WORKSPACE_ROOT}}|${WORKSPACE_ROOT}|g" \
    -e "s|{{HOME}}|${HOME}|g" \
    "$PLIST_TMPL" > "$PLIST_DST"
echo "Installed plist: $PLIST_DST"

# Load it. If already loaded, unload first.
if launchctl list ai.slack-bridge.gateway >/dev/null 2>&1; then
    echo "Reloading existing unit..."
    launchctl unload "$PLIST_DST"
fi

launchctl load "$PLIST_DST"
echo "Loaded ai.slack-bridge.gateway"
echo ""
echo "Status:"
launchctl list ai.slack-bridge.gateway
echo ""
echo "Logs:"
echo "  tail -f \"${WORKSPACE_ROOT}/slack-bridge/logs/slack-bridge.log\""
echo "  tail -f \"${WORKSPACE_ROOT}/slack-bridge/logs/gateway.err.log\""
echo ""
echo "To unload later:"
echo "  launchctl unload ~/Library/LaunchAgents/ai.slack-bridge.gateway.plist"
