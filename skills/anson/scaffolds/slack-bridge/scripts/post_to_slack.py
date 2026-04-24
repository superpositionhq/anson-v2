#!/usr/bin/env python3
"""Post text (and optional file attachment) to a Slack user DM or channel as
the bot (xoxb-).

Used by scheduled tasks to ship their output to the user's DM without
invoking the slack-bridge daemon.

Usage:
    post_to_slack.py --user U0XXXXXXXXX --text-file /tmp/out.md
    post_to_slack.py --channel C0XXXXXXXXX < /tmp/out.md
    post_to_slack.py --user U0XXXXXXXXX --text-file /tmp/out.md --file /tmp/brief.mp3
    post_to_slack.py --user U0XXXXXXXXX --file /tmp/brief.mp3 --file-comment "audio brief"
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from slack_sdk.errors import SlackApiError
from slack_sdk.web import WebClient

from slack_bridge._io import load_bot_token, open_dm
from slack_bridge.delivery import split_chunks


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
    ap.add_argument("--text-file", help="Read text from file (default: stdin if no --file)")
    ap.add_argument("--file", dest="file_path", help="Upload a file attachment (e.g. mp3)")
    ap.add_argument("--file-comment", help="Initial comment shown alongside the uploaded file")
    ap.add_argument("--file-title", help="Display title for the uploaded file (defaults to filename)")
    ap.add_argument("--thread-ts", help="Post as a reply in this thread")
    ap.add_argument("--env-file", default=DEFAULT_ENV)
    args = ap.parse_args()

    try:
        token = load_bot_token(args.env_file)
    except ValueError as e:
        print(f"post_to_slack: {e}", file=sys.stderr)
        return 2

    text = ""
    if args.text_file:
        text = Path(args.text_file).read_text().strip()
    elif not args.file_path and sys.stdin is not None and not sys.stdin.isatty():
        text = sys.stdin.read().strip()

    if not text and not args.file_path:
        print("post_to_slack: nothing to post (no text and no --file)", file=sys.stderr)
        return 0

    file_path = Path(args.file_path) if args.file_path else None
    if file_path and not file_path.is_file():
        print(f"post_to_slack: file not found: {file_path}", file=sys.stderr)
        return 2

    web = WebClient(token=token)
    channel = args.channel
    if args.user:
        try:
            channel = open_dm(web, args.user)
        except SlackApiError as e:
            print(f"post_to_slack: conversations.open failed: {e.response.get('error')}", file=sys.stderr)
            return 1

    try:
        if text:
            for piece in split_chunks(text):
                web.chat_postMessage(channel=channel, thread_ts=args.thread_ts, text=piece)
        if file_path:
            web.files_upload_v2(
                channel=channel,
                file=str(file_path),
                filename=file_path.name,
                title=args.file_title or file_path.name,
                initial_comment=args.file_comment,
                thread_ts=args.thread_ts,
            )
    except SlackApiError as e:
        print(f"post_to_slack: slack api failed: {e.response.get('error')}", file=sys.stderr)
        return 1

    parts = []
    if text:
        parts.append(f"{len(text)} chars")
    if file_path:
        parts.append(f"file {file_path.name}")
    print(f"posted {' + '.join(parts)} to {channel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
