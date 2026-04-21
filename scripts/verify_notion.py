#!/usr/bin/env python3
"""verify_notion.py — confirm Notion API key works and lists bot identity.

Optionally accepts --db <id> to also probe one row from that database.
"""
from __future__ import annotations

import argparse
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
            "  export WORKSPACE_ROOT=\"$HOME/Assistant\"   # or wherever your workspace is"
        )
    return Path(root).expanduser()


def load_env() -> dict[str, str]:
    env_path = workspace_root() / ".env"
    if not env_path.exists():
        sys.exit(f"missing {env_path}")
    out: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def whoami(api_key: str) -> dict:
    r = requests.get("https://api.notion.com/v1/users/me", headers=headers(api_key), timeout=20)
    r.raise_for_status()
    return r.json()


def probe_db(api_key: str, db_id: str) -> dict:
    r = requests.post(
        f"https://api.notion.com/v1/databases/{db_id}/query",
        headers=headers(api_key),
        json={"page_size": 1},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", action="append", default=[], help="DB ID(s) to probe")
    args = ap.parse_args()

    env = load_env()
    api_key = env.get("NOTION_API_KEY")
    if not api_key:
        sys.exit("NOTION_API_KEY missing from .env")

    me = whoami(api_key)
    print(f"verify_notion: ok\n  bot: {me.get('name')} ({me.get('id')})")

    for db_id in args.db:
        try:
            res = probe_db(api_key, db_id)
            count = len(res.get("results", []))
            print(f"  db {db_id}: ok (probed {count} row)")
        except requests.HTTPError as e:
            print(f"  db {db_id}: FAIL ({e.response.status_code}) — share the integration with this database")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
