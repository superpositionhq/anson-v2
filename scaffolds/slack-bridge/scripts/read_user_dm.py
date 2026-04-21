#!/usr/bin/env python3
"""Read recent messages from the bot's DM with a user.

Used by scheduled tasks (heartbeat, morning-brief, dream, market-watch,
finance-digest) to dedup against alerts they already posted earlier,
since each run is a fresh Claude session with no prior-turn memory.

Usage:
    read_user_dm.py --user U0XXXXXXXXX --hours 24
    read_user_dm.py --user U0XXXXXXXXX --limit 30

Prints a compact, model-friendly rendering:

    [2026-04-18 21:55 ET] (self) Azure Budget Blowout — $20,061.42 vs $100 ...
    [2026-04-18 21:15 ET] (user) ok thanks
    ...

Only messages posted by the bot itself are tagged `(self)` — those are the
ones to dedup against. Messages from the workspace user are tagged `(user)` so the model sees
context but doesn't treat them as prior flags.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from slack_sdk.errors import SlackApiError
from slack_sdk.web import WebClient

def _default_env() -> str:
    from pathlib import Path
    root = os.environ.get("WORKSPACE_ROOT")
    if root:
        return str(Path(root).expanduser() / ".env")
    return str(Path(__file__).resolve().parents[2] / ".env")


DEFAULT_ENV = _default_env()
ET = ZoneInfo("America/New_York")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True, help="Slack user ID (U...) — DM opened automatically")
    ap.add_argument("--hours", type=float, default=24.0, help="Look-back window in hours (default 24)")
    ap.add_argument("--limit", type=int, default=50, help="Max messages to fetch (default 50)")
    ap.add_argument("--env-file", default=DEFAULT_ENV)
    args = ap.parse_args()

    load_dotenv(args.env_file, override=False)
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not token.startswith("xoxb-"):
        print("read_user_dm: SLACK_BOT_TOKEN missing", file=sys.stderr)
        return 2

    web = WebClient(token=token)

    try:
        bot_user_id = web.auth_test()["user_id"]
    except SlackApiError as e:
        print(f"read_user_dm: auth.test failed: {e.response.get('error')}", file=sys.stderr)
        return 1

    try:
        channel = web.conversations_open(users=args.user)["channel"]["id"]
    except SlackApiError as e:
        print(f"read_user_dm: conversations.open failed: {e.response.get('error')}", file=sys.stderr)
        return 1

    oldest = (datetime.now(timezone.utc) - timedelta(hours=args.hours)).timestamp()

    try:
        resp = web.conversations_history(
            channel=channel, oldest=str(oldest), limit=args.limit, inclusive=False,
        )
    except SlackApiError as e:
        print(f"read_user_dm: conversations.history failed: {e.response.get('error')}", file=sys.stderr)
        return 1

    msgs = list(reversed(resp.get("messages", [])))
    if not msgs:
        print(f"(no messages in last {args.hours}h)")
        return 0

    for m in msgs:
        ts = float(m.get("ts", "0"))
        dt = datetime.fromtimestamp(ts, tz=ET).strftime("%Y-%m-%d %H:%M ET")
        who = "self" if m.get("user") == bot_user_id or m.get("bot_id") else "user"
        text = (m.get("text") or "").replace("\n", " ⏎ ").strip()
        print(f"[{dt}] ({who}) {text}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
