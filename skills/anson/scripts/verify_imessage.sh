#!/usr/bin/env bash
# verify_imessage.sh — confirm Full Disk Access is granted to the terminal so
# we can read ~/Library/Messages/chat.db.
#
# macOS only.

set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "verify_imessage: skipped — not macOS"
  exit 0
fi

DB="${IMESSAGE_DB:-$HOME/Library/Messages/chat.db}"

if [[ ! -f "$DB" ]]; then
  echo "verify_imessage: FAIL — $DB not found"
  exit 1
fi

# Try a trivial read.
if ! sqlite3 "$DB" "SELECT COUNT(*) FROM chat;" >/dev/null 2>&1; then
  cat >&2 <<'EOF'
verify_imessage: FAIL — could not read chat.db.

Grant Full Disk Access:
  System Settings → Privacy & Security → Full Disk Access →
  add your terminal app (Terminal / iTerm / etc.) and restart it.
EOF
  exit 1
fi

count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM chat;")
echo "verify_imessage: ok ($count chats accessible)"
