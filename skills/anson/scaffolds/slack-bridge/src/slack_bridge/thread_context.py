"""Fetch Slack thread/DM history + format as a preamble for new sessions.

Only attached on the *first* turn of a conversation — once the Claude
session is alive, `--resume` carries its own memory.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from slack_sdk.errors import SlackApiError
from slack_sdk.web import WebClient

log = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 30
TRUNCATE_CHARS = 600

# Subtypes whose payloads are meta-events rather than user content.
META_SUBTYPES = frozenset({"message_deleted", "message_changed"})


@dataclass
class ThreadMessage:
    user: str
    ts: str
    text: str
    is_bot: bool


def _truncate(text: str, n: int = TRUNCATE_CHARS) -> str:
    text = text.replace("\r\n", "\n").strip()
    if len(text) <= n:
        return text
    return text[: n - 1] + "…"


def _to_thread_messages(raw: list[dict], exclude_ts: str | None) -> list[ThreadMessage]:
    out: list[ThreadMessage] = []
    for m in raw:
        ts = m.get("ts", "")
        if exclude_ts and ts == exclude_ts:
            continue
        if m.get("subtype") in META_SUBTYPES:
            continue
        out.append(
            ThreadMessage(
                user=m.get("user") or m.get("bot_id") or "?",
                ts=ts,
                text=m.get("text", ""),
                is_bot=bool(m.get("bot_id")),
            )
        )
    return out


def fetch_thread(
    web: WebClient,
    *,
    channel: str,
    thread_ts: str,
    exclude_ts: str | None,
) -> list[ThreadMessage]:
    """Thread replies oldest → newest, excluding the message currently being handled."""
    try:
        resp = web.conversations_replies(
            channel=channel, ts=thread_ts, limit=MAX_HISTORY_MESSAGES,
        )
    except SlackApiError as e:
        log.warning(
            "conversations.replies(%s, %s) failed: %s",
            channel, thread_ts, e.response.get("error"),
        )
        return []
    return _to_thread_messages(resp.get("messages") or [], exclude_ts)


def fetch_dm_history(
    web: WebClient,
    *,
    channel: str,
    exclude_ts: str | None,
    limit: int = 10,
) -> list[ThreadMessage]:
    """Recent DM history oldest → newest."""
    try:
        resp = web.conversations_history(channel=channel, limit=limit, inclusive=False)
    except SlackApiError as e:
        log.warning("conversations.history(%s) failed: %s", channel, e.response.get("error"))
        return []
    # Slack returns newest first.
    return _to_thread_messages(list(reversed(resp.get("messages") or [])), exclude_ts)


def format_preamble(messages: list[ThreadMessage], *, bot_user_id: str) -> str:
    """Short `<who>: <text>` block usable as an ambient-context preamble."""
    if not messages:
        return ""
    lines = ["[Prior thread context — oldest to newest]"]
    for m in messages:
        who = "bot" if (m.is_bot or m.user == bot_user_id) else f"<@{m.user}>"
        lines.append(f"- {who}: {_truncate(m.text)}")
    lines.append("[End prior context]")
    return "\n".join(lines)
