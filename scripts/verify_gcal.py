#!/usr/bin/env python3
"""verify_gcal.py — confirm Google Calendar credentials work.

Lists today's events for each account. Empty calendar is fine; auth error stops.
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
            "or see references/oauth_google_cal.md for alternatives."
        )


def list_today(account: str) -> None:
    print(f"\n=== {account} ===")
    result = subprocess.run(
        ["gog", "-a", account, "calendar", "list", "--today"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        sys.exit(f"FAIL ({account}): {result.stderr.strip() or 'unknown error'}")
    print(result.stdout.strip() or "(no events today)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("accounts", nargs="+")
    args = ap.parse_args()

    check_gog_present()
    for account in args.accounts:
        list_today(account)
    print("\nverify_gcal: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
