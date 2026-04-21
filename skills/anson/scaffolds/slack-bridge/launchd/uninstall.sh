#!/bin/bash
# Uninstall the slack-bridge launchd unit.

PLIST_DST="$HOME/Library/LaunchAgents/ai.slack-bridge.gateway.plist"

if [ ! -f "$PLIST_DST" ]; then
    echo "Not installed: $PLIST_DST"
    exit 0
fi

if launchctl list ai.slack-bridge.gateway >/dev/null 2>&1; then
    launchctl unload "$PLIST_DST"
    echo "Unloaded ai.slack-bridge.gateway"
fi

rm "$PLIST_DST"
echo "Removed $PLIST_DST"
