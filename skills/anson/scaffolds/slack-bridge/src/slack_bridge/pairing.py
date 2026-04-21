"""DM pairing gate — reads `config/allowlist.json`.

The allowlist file is consulted on every DM, so we mtime-cache it: reload
only when the file actually changes. A future `pair` skill can write to
it; we never mutate it from here.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_cache: tuple[float, frozenset[str]] | None = None


def load_allowlist(path: Path) -> frozenset[str]:
    """Return approved Slack user IDs. Empty set on any failure — fail closed."""
    global _cache
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        if _cache is not None:
            log.warning("allowlist %s vanished — DMs will be rejected", path)
            _cache = None
        return frozenset()
    except OSError as e:
        log.error("allowlist stat failed: %s", e)
        return frozenset()

    if _cache is not None and _cache[0] == mtime:
        return _cache[1]

    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        log.error("allowlist unreadable: %s — DMs will be rejected", e)
        return frozenset()

    allow = frozenset(u for u in (data.get("allowFrom") or []) if isinstance(u, str))
    _cache = (mtime, allow)
    return allow


REJECTION_TEXT = (
    "Sorry — I can only chat with users on the paired list. "
    "Ask the workspace owner to add you to the slack-bridge allowlist."
)
