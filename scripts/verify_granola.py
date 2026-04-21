#!/usr/bin/env python3
"""verify_granola.py — confirm Granola desktop app is installed + logged in.

Reads the local Granola token cache, calls the Granola REST API for the last
3 documents. Empty = no meetings yet (fine). Auth error = open the Granola
app and let it refresh, then retry.

macOS / Windows only.
"""
from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path

import requests


def token_path() -> Path:
    sysname = platform.system()
    if sysname == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Granola" / "supabase.json"
    if sysname == "Windows":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            sys.exit("APPDATA env var missing on Windows — can't locate Granola token cache")
        return Path(appdata) / "Granola" / "supabase.json"
    sys.exit(f"verify_granola: unsupported OS ({sysname}) — Granola desktop is macOS/Windows only")


def load_token() -> str:
    p = token_path()
    if not p.exists():
        sys.exit(
            f"Granola token cache not found at {p}.\n"
            "Install Granola from https://granola.ai and sign in once."
        )
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"Granola token cache malformed: {e}")
    token = (data.get("workos_tokens") or {}).get("access_token")
    if not token:
        sys.exit(
            "Granola token cache present but no workos_tokens.access_token. "
            "Open the Granola app and sign in to refresh."
        )
    return token


def main() -> int:
    token = load_token()
    r = requests.post(
        "https://api.granola.ai/v2/get-documents",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"limit": 3, "offset": 0},
        timeout=20,
    )
    if r.status_code in (401, 403):
        sys.exit(
            f"Granola auth failed ({r.status_code}). Open the Granola desktop app, "
            "let it refresh, then retry."
        )
    r.raise_for_status()
    docs = r.json().get("docs") or []
    print(f"verify_granola: ok ({len(docs)} recent docs)")
    for d in docs:
        title = d.get("title") or "(untitled)"
        when = d.get("created_at", "")[:10]
        print(f"  • {when}  {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
