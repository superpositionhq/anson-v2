#!/usr/bin/env python3
"""Post text to a Slack user DM or channel as the bot (xoxb-).

Used by scheduled tasks to ship their output to the user's DM without
invoking the slack-bridge daemon.

Usage:
    post_to_slack.py --user U0XXXXXXXXX --text-file /tmp/out.md
    post_to_slack.py --channel C0XXXXXXXXX < /tmp/out.md
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from slack_sdk.errors import SlackApiError
from slack_sdk.web import WebClient

CHUNK = 3800


def _default_env() -> str:
    """Workspace `.env`. Honors WORKSPACE_ROOT; falls back to the parent of
    slack-bridge/ (assumes vendored install)."""
    root = os.environ.get("WORKSPACE_ROOT")
    if root:
        return str(Path(root).expanduser() / ".env")
    return str(Path(__file__).resolve().parents[2] / ".env")


DEFAULT_ENV = _default_env()


def main() -> int:
    ap = argparse.ArgumentParser()
    target = ap.add_mutually_exclusive_group(required=True)
    target.add_argument("--user", help="Slack user ID (U...) — DM opened automatically")
    target.add_argument("--channel", help="Slack channel ID (C...) — post directly")
    ap.add_argument("--text-file", help="Read text from file (default: stdin)")
    ap.add_argument("--thread-ts", help="Post as a reply in this thread")
    ap.add_argument("--env-file", default=DEFAULT_ENV)
    args = ap.parse_args()

    load_dotenv(args.env_file, override=False)
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not token.startswith("xoxb-"):
        print("post_to_slack: SLACK_BOT_TOKEN missing", file=sys.stderr)
        return 2

    text = Path(args.text_file).read_text() if args.text_file else sys.stdin.read()
    text = text.strip()
    if not text:
        print("post_to_slack: empty text, nothing to post", file=sys.stderr)
        return 0

    web = WebClient(token=token)
    channel = args.channel
    if args.user:
        try:
            channel = web.conversations_open(users=args.user)["channel"]["id"]
        except SlackApiError as e:
            print(f"post_to_slack: conversations.open failed: {e.response.get('error')}", file=sys.stderr)
            return 1

    try:
        for i in range(0, len(text), CHUNK):
            web.chat_postMessage(
                channel=channel, thread_ts=args.thread_ts, text=text[i : i + CHUNK],
            )
    except SlackApiError as e:
        print(f"post_to_slack: chat.postMessage failed: {e.response.get('error')}", file=sys.stderr)
        return 1

    print(f"posted {len(text)} chars to {channel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
