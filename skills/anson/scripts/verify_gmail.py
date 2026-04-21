#!/usr/bin/env python3
"""verify_gmail.py — confirm Gmail credentials work for one or more accounts.

Run after Stage D (Gmail step) of anson-v2. Lists last 3 unread subjects per account.
Empty inbox is fine; auth error stops the install.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys


def check_gog_present() -> None:
    if shutil.which("gog") is None:
        sys.exit(
            "gog CLI not found in PATH. Install with `brew install gog` (macOS) "
            "or see references/oauth_gmail.md for alternatives."
        )


def list_unread(account: str, limit: int = 3) -> None:
    print(f"\n=== {account} ===")
    result = subprocess.run(
        ["gog", "-a", account, "gmail", "list", "--unread", "--limit", str(limit)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        sys.exit(f"FAIL ({account}): {result.stderr.strip() or 'unknown error'}")
    print(result.stdout.strip() or "(no unread mail — that's fine)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("accounts", nargs="+", help="Gmail addresses to verify")
    ap.add_argument("--limit", type=int, default=3)
    args = ap.parse_args()

    check_gog_present()
    for account in args.accounts:
        list_unread(account, args.limit)
    print("\nverify_gmail: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
