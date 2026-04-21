#!/usr/bin/env python3
"""verify_slack.py — confirm Slack user-session tokens work.

Calls users.identity (if granted) or auth.test as a smoketest.
Reads SLACK_XOXC_TOKEN + SLACK_XOXD_TOKEN from .env at workspace root.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests


def workspace_root() -> Path:
    """User's anson workspace. Required: WORKSPACE_ROOT env var."""
    root = os.environ.get("WORKSPACE_ROOT")
    if not root:
        sys.exit(
            "WORKSPACE_ROOT not set. Export your anson workspace path first:\n"
            "  export WORKSPACE_ROOT=\"$HOME/Assistant\""
        )
    return Path(root).expanduser()


def load_env() -> dict[str, str]:
    env_path = workspace_root() / ".env"
    if not env_path.exists():
        sys.exit(f"missing {env_path} — run anson Stage D Slack first")
    out: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main() -> int:
    env = load_env()
    xoxc = env.get("SLACK_XOXC_TOKEN")
    xoxd = env.get("SLACK_XOXD_TOKEN")
    if not xoxc or not xoxd:
        sys.exit("SLACK_XOXC_TOKEN / SLACK_XOXD_TOKEN missing from .env")

    r = requests.post(
        "https://slack.com/api/auth.test",
        headers={
            "Authorization": f"Bearer {xoxc}",
            "Cookie": f"d={xoxd}",
        },
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        sys.exit(f"slack auth.test failed: {data.get('error')}")
    print(
        f"verify_slack: ok\n"
        f"  workspace: {data.get('team')}\n"
        f"  user:      {data.get('user')} ({data.get('user_id')})\n"
        f"  url:       {data.get('url')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
