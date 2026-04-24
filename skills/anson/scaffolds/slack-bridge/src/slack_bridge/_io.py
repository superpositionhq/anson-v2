"""Small shared utilities for JSON-on-disk state + Slack bootstrap."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from slack_sdk.errors import SlackApiError
from slack_sdk.web import WebClient


def atomic_write_json(path: Path, obj: Any) -> None:
    """Serialize obj to path via a `.tmp` sibling and atomic rename."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    tmp.replace(path)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_bot_token(env_file: str | Path) -> str:
    """Load + validate SLACK_BOT_TOKEN from the given .env. Raises ValueError."""
    load_dotenv(env_file, override=False)
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not token.startswith("xoxb-"):
        raise ValueError("SLACK_BOT_TOKEN missing or malformed (want xoxb-...)")
    return token


def open_dm(web: WebClient, user_id: str) -> str:
    """Open (or resolve) a DM channel for the given Slack user. Returns channel id."""
    resp = web.conversations_open(users=user_id)
    channel = (resp.get("channel") or {}).get("id")
    if not channel:
        raise SlackApiError("conversations.open returned no channel id", resp)
    return channel
