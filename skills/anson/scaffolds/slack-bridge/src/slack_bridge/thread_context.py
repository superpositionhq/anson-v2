"""Fetch Slack channel/thread/DM context + format as a preamble for new sessions.

Only attached on the *first* turn of a conversation — once the Claude
session is alive, `--resume` carries its own memory.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal

from slack_sdk.errors import SlackApiError
from slack_sdk.web import WebClient

ChannelKind = Literal["channel", "private_channel", "dm", "mpim", "unknown"]

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


@dataclass
class ChannelInfo:
    id: str
    name: str | None
    kind: ChannelKind
    topic: str
    purpose: str
    member_count: int | None


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


def _lookup_user_name(web: WebClient, uid: str) -> tuple[str, str | None]:
    try:
        resp = web.users_info(user=uid)
    except SlackApiError as e:
        log.warning("users.info(%s) failed: %s", uid, e.response.get("error"))
        return uid, None
    user = resp.get("user") or {}
    profile = user.get("profile") or {}
    name = (
        profile.get("display_name")
        or profile.get("real_name")
        or user.get("real_name")
        or user.get("name")
        or ""
    ).strip()
    return uid, name or None


def fetch_user_names(web: WebClient, user_ids: list[str]) -> dict[str, str]:
    """Resolve Slack user IDs → display names in parallel. Bot IDs are skipped.

    Best-effort: on API failure, the ID is dropped from the map and callers
    fall back to rendering `<@U123>`.
    """
    unique = [uid for uid in dict.fromkeys(user_ids) if uid and uid.startswith("U")]
    if not unique:
        return {}
    out: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(unique))) as pool:
        for uid, name in pool.map(lambda u: _lookup_user_name(web, u), unique):
            if name:
                out[uid] = name
    return out


def fetch_channel_info(web: WebClient, *, channel: str) -> ChannelInfo | None:
    """Channel metadata (name, kind, topic/purpose) for preamble header."""
    try:
        resp = web.conversations_info(channel=channel, include_num_members=True)
    except SlackApiError as e:
        log.warning("conversations.info(%s) failed: %s", channel, e.response.get("error"))
        return None
    info = resp.get("channel") or {}
    if info.get("is_im"):
        kind = "dm"
    elif info.get("is_mpim"):
        kind = "mpim"
    elif info.get("is_private"):
        kind = "private_channel"
    elif info.get("is_channel") or info.get("is_group"):
        kind = "channel"
    else:
        kind = "unknown"
    topic = ((info.get("topic") or {}).get("value") or "").strip()
    purpose = ((info.get("purpose") or {}).get("value") or "").strip()
    return ChannelInfo(
        id=info.get("id") or channel,
        name=info.get("name"),
        kind=kind,
        topic=topic,
        purpose=purpose,
        member_count=info.get("num_members"),
    )


def _format_channel_header(ch: ChannelInfo, *, thread_ts: str | None) -> str:
    bits: list[str] = []
    if ch.kind == "dm":
        bits.append(f"channel: direct message ({ch.id})")
    elif ch.kind == "mpim":
        bits.append(f"channel: group DM ({ch.id})")
    else:
        label = f"#{ch.name}" if ch.name else ch.id
        privacy = "private" if ch.kind == "private_channel" else "public"
        bits.append(f"channel: {label} ({privacy}, id={ch.id})")
    if ch.member_count is not None and ch.kind not in {"dm", "mpim"}:
        bits.append(f"members: {ch.member_count}")
    if thread_ts:
        bits.append(f"thread_ts: {thread_ts}")
    lines = ["[Slack context]", "- " + " · ".join(bits)]
    if ch.purpose:
        lines.append(f"- purpose: {_truncate(ch.purpose, 200)}")
    if ch.topic:
        lines.append(f"- topic: {_truncate(ch.topic, 200)}")
    return "\n".join(lines)


def render_user(uid: str, *, bot_user_id: str, is_bot: bool, names: dict[str, str]) -> str:
    if is_bot or uid == bot_user_id:
        return "bot"
    name = names.get(uid)
    if name:
        return f"{name} (<@{uid}>)"
    return f"<@{uid}>"


def format_preamble(
    messages: list[ThreadMessage],
    *,
    bot_user_id: str,
    channel_info: ChannelInfo | None = None,
    thread_ts: str | None = None,
    user_names: dict[str, str] | None = None,
) -> str:
    """Ambient-context preamble: channel metadata header + prior thread history."""
    names = user_names or {}
    sections: list[str] = []
    if channel_info is not None:
        sections.append(_format_channel_header(channel_info, thread_ts=thread_ts))
    if messages:
        lines = ["[Prior thread context — oldest to newest]"]
        for m in messages:
            who = render_user(
                m.user, bot_user_id=bot_user_id, is_bot=m.is_bot, names=names,
            )
            lines.append(f"- {who}: {_truncate(m.text)}")
        lines.append("[End prior context]")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)
