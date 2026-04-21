#!/usr/bin/env python3
"""directives.py — unified surfacing rules.

Store: state/directives.json (flat array of objects, workspace root).
Shape: {id, action, match[], scope[], until, note}.
Actions: suppress, snooze, archive, remind.

Use as CLI or import `should_surface` / `add_directive` from Python.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STORE = ROOT / "state" / "directives.json"

ACTIONS = {"suppress", "snooze", "archive", "remind"}


# ---------- storage ----------

def load() -> list[dict]:
    if not STORE.exists():
        return []
    data = json.loads(STORE.read_text())
    if not isinstance(data, list):
        raise ValueError(f"{STORE} must be a JSON array")
    return data


def save(directives: list[dict]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(directives, indent=2, ensure_ascii=False) + "\n")


# ---------- matching ----------

def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _token_set_ratio(a: str, b: str) -> float:
    sa = set(_normalize(a).split())
    sb = set(_normalize(b).split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa), len(sb))


def _item_text(item) -> str:
    """Flatten any item (str / dict / list) to one searchable string."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return " ".join(str(v) for v in item.values() if v is not None)
    if isinstance(item, list):
        return " ".join(str(x) for x in item if x is not None)
    return str(item)


def _matches(query: str, patterns: list[str], threshold: float = 0.6) -> tuple[bool, str]:
    nq = _normalize(query)
    for pat in patterns:
        npat = _normalize(pat)
        if not npat:
            continue
        if nq == npat or nq in npat or npat in nq:
            return True, pat
        if _token_set_ratio(query, pat) >= threshold:
            return True, pat
    return False, ""


def _in_scope(directive: dict, scope: str) -> bool:
    scopes = directive.get("scope") or ["*"]
    return "*" in scopes or scope in scopes


def _is_active(directive: dict, today: date | None = None) -> bool:
    """Active = "should be consulted right now".

    - suppress / archive: always active.
    - snooze: active while today < until (suppressing); past that, inactive.
    - remind: active only when today == until (surface exactly on that date).
    """
    action = directive.get("action")
    until = directive.get("until")
    today = today or date.today()

    if action == "snooze":
        if not until:
            return True
        try:
            return date.fromisoformat(until) > today
        except ValueError:
            return True

    if action == "remind":
        if not until:
            return False
        try:
            return date.fromisoformat(until) == today
        except ValueError:
            return False

    return True


# ---------- public API ----------

def should_surface(item, scope: str = "*") -> dict:
    """Return {surface, action?, directive_id?, note?, matched_via?}.

    `surface: True` = no matching suppressive directive → surface normally.
    `surface: False` = matched a suppress / snooze / archive directive.

    `remind` directives are additive, not suppressive; they're retrieved via
    `reminders()` and never block surfacing here.
    """
    query = _item_text(item)
    if not query.strip():
        return {"surface": True}
    for d in load():
        if d.get("action") == "remind":
            continue
        if not _in_scope(d, scope):
            continue
        if not _is_active(d):
            continue
        hit, via = _matches(query, d.get("match", []))
        if hit:
            return {
                "surface": False,
                "action": d["action"],
                "directive_id": d["id"],
                "note": d.get("note", ""),
                "matched_via": via,
            }
    return {"surface": True}


def add_directive(
    *,
    action: str,
    match: list[str],
    scope: list[str] | None = None,
    until: str | None = None,
    note: str = "",
    id: str | None = None,
) -> dict:
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {sorted(ACTIONS)}")
    if action in ("snooze", "remind") and not until:
        raise ValueError(f"{action} requires --until YYYY-MM-DD")
    if action not in ("snooze", "remind") and until:
        raise ValueError("only snooze and remind use --until")

    directives = load()
    did = id or _slugify(match[0] if match else action)
    # uniqueness
    existing_ids = {d["id"] for d in directives}
    base, n = did, 1
    while did in existing_ids:
        n += 1
        did = f"{base}-{n}"

    entry = {
        "id": did,
        "action": action,
        "match": match,
        "scope": scope or ["*"],
        "until": until,
        "note": note,
    }
    directives.append(entry)
    save(directives)
    return entry


def reminders(scope: str = "*", today: date | None = None) -> list[dict]:
    """Return active remind directives for the given scope on `today`."""
    today = today or date.today()
    out = []
    for d in load():
        if d.get("action") != "remind":
            continue
        if not _in_scope(d, scope):
            continue
        if not _is_active(d, today):
            continue
        out.append(d)
    return out


def remove_directive(did: str) -> bool:
    directives = load()
    kept = [d for d in directives if d["id"] != did]
    if len(kept) == len(directives):
        return False
    save(kept)
    return True


def expire(today: date | None = None) -> list[dict]:
    """Remove directives that have outlived their window. Returns removed entries.

    - snooze with `until <= today`: expired (suppression window has passed;
      item resurfaces via normal flow)
    - remind with `until < today`: expired (reminder date has passed)
    """
    today = today or date.today()
    directives = load()
    dropped, kept = [], []
    for d in directives:
        action = d.get("action")
        until = d.get("until")
        if not until:
            kept.append(d)
            continue
        try:
            udate = date.fromisoformat(until)
        except ValueError:
            kept.append(d)
            continue
        if action == "snooze" and udate <= today:
            dropped.append(d)
            continue
        if action == "remind" and udate < today:
            dropped.append(d)
            continue
        kept.append(d)
    if dropped:
        save(kept)
    return dropped


def _slugify(text: str) -> str:
    return _normalize(text).replace(" ", "-")[:60] or "directive"


# ---------- CLI ----------

def cmd_list(args: argparse.Namespace) -> int:
    directives = load()
    if args.scope:
        directives = [d for d in directives if _in_scope(d, args.scope)]
    if args.action:
        directives = [d for d in directives if d.get("action") == args.action]
    print(json.dumps(directives, indent=2, ensure_ascii=False))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    result = should_surface(args.query, scope=args.scope or "*")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    entry = add_directive(
        action=args.action,
        match=args.match or [],
        scope=args.scope or ["*"],
        until=args.until,
        note=args.note or "",
        id=args.id,
    )
    print(json.dumps(entry, indent=2, ensure_ascii=False))
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    ok = remove_directive(args.id)
    print(json.dumps({"removed": ok, "id": args.id}))
    return 0 if ok else 1


def cmd_expire(args: argparse.Namespace) -> int:
    dropped = expire()
    print(json.dumps({"expired": dropped}, indent=2, ensure_ascii=False))
    return 0


def cmd_reminders(args: argparse.Namespace) -> int:
    out = reminders(scope=args.scope or "*")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Unified surfacing directives")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list")
    pl.add_argument("--scope")
    pl.add_argument("--action", choices=sorted(ACTIONS))
    pl.set_defaults(func=cmd_list)

    pc = sub.add_parser("check")
    pc.add_argument("query")
    pc.add_argument("--scope")
    pc.set_defaults(func=cmd_check)

    pa = sub.add_parser("add")
    pa.add_argument("--action", required=True, choices=sorted(ACTIONS))
    pa.add_argument("--match", action="append", required=True)
    pa.add_argument("--scope", action="append")
    pa.add_argument("--until")
    pa.add_argument("--note", default="")
    pa.add_argument("--id")
    pa.set_defaults(func=cmd_add)

    pr = sub.add_parser("remove")
    pr.add_argument("id")
    pr.set_defaults(func=cmd_remove)

    pe = sub.add_parser("expire")
    pe.set_defaults(func=cmd_expire)

    pre = sub.add_parser("reminders", help="list active remind directives for today")
    pre.add_argument("--scope")
    pre.set_defaults(func=cmd_reminders)

    return p


if __name__ == "__main__":
    args = _parser().parse_args()
    raise SystemExit(args.func(args))
