"""Socket Mode listener: Slack events → session routing → claude → delivery.

One dispatch per session runs at a time (per-key lock) so concurrent
Slack events to the same conversation don't race on the same Claude
session file. Different conversations run concurrently.
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from slack_sdk.errors import SlackApiError
from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web import WebClient

ACK_EMOJI = "eyes"

from .config import Config
from .delivery import DeliveryQueue, PostTarget
from .dispatch import run_claude
from .pairing import REJECTION_TEXT, load_allowlist
from .session_visibility import unhide_session
from .sessions import Scope, SessionStore
from .thread_context import META_SUBTYPES, fetch_dm_history, fetch_thread, format_preamble

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class InboundMessage:
    text: str
    user_id: str
    channel: str
    thread_ts: str | None
    ts: str | None
    scope: Scope


def _should_skip_event(event: dict[str, Any], bot_user_id: str) -> bool:
    """True for bot-authored messages and meta events (edits/deletes)."""
    if event.get("bot_id"):
        return True
    if event.get("user") == bot_user_id:
        return True
    if event.get("subtype") in META_SUBTYPES:
        return True
    return False


def _strip_mention(text: str, bot_user_id: str) -> str:
    return text.replace(f"<@{bot_user_id}>", "").strip()


def _session_label(msg: InboundMessage) -> str:
    if msg.scope == "dm":
        return f"Slack DM · {msg.user_id}"
    if msg.channel.startswith("D"):
        return f"Slack DM thread · {msg.thread_ts or '?'}"
    return f"Slack #{msg.channel} · thread {msg.thread_ts or '?'}"


def _channel_allowed(channel: str, config: Config) -> bool:
    if config.group_policy != "allowlist":
        return True
    return channel in config.channels


def _dm_allowed(user_id: str, config: Config) -> bool:
    if config.dm_policy != "pairing":
        return True
    return user_id in load_allowlist(config.allowlist_path)


class Bridge:
    """Holds the long-lived state touched by the listener loop."""

    def __init__(self, config: Config, web: WebClient, bot_user_id: str):
        self.config = config
        self.web = web
        self.bot_user_id = bot_user_id
        self.store = SessionStore(path=config.state_dir / "sessions.json")
        self.queue = DeliveryQueue(outbox_dir=config.state_dir / "outbox", web=web)
        # One lock per session key — different conversations still parallelize.
        self._session_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._locks_mutex = threading.Lock()

    def _lock_for(self, key: str) -> threading.Lock:
        with self._locks_mutex:
            return self._session_locks[key]

    def handle(self, req: SocketModeRequest) -> None:
        if req.type != "events_api":
            return
        event = req.payload.get("event") or {}
        etype = event.get("type")

        if etype == "message":
            self._handle_message(event)
        elif etype == "app_mention":
            self._handle_mention(event)

    def _handle_message(self, event: dict[str, Any]) -> None:
        if _should_skip_event(event, self.bot_user_id):
            return
        text = (event.get("text") or "").strip()
        if not text:
            return
        user_id = event.get("user", "?")
        channel = event.get("channel", "")
        channel_type = event.get("channel_type", "")
        ts = event.get("ts")
        thread_ts = event.get("thread_ts")

        if channel_type == "im":
            if not _dm_allowed(user_id, self.config):
                log.info("DM from %s rejected — not on allowlist", user_id)
                self.queue.try_post(PostTarget(channel=channel), REJECTION_TEXT)
                return
            # Reply inside a DM thread → isolated thread-scoped session so the
            # parent (often a bot-posted heartbeat/alert) is fetched as
            # preamble on first turn. Top-level DMs keep sharing dm:<user>.
            if thread_ts and thread_ts != ts:
                self._dispatch(InboundMessage(
                    text=text, user_id=user_id, channel=channel,
                    thread_ts=thread_ts, ts=ts, scope="thread",
                ))
                return
            self._dispatch(InboundMessage(
                text=text, user_id=user_id, channel=channel,
                thread_ts=thread_ts, ts=ts, scope="dm",
            ))
            return

        # Channel message: treat as thread follow-up only if we already have
        # a live session for this thread (user mentioned us earlier). Strips
        # any leading mention in case the user re-@s us.
        if not thread_ts:
            return
        session_key = SessionStore.key_for(
            channel=channel, user_id=user_id, thread_ts=thread_ts, scope="thread",
        )
        if not self.store.has(session_key):
            return
        if not _channel_allowed(channel, self.config):
            return
        followup = _strip_mention(text, self.bot_user_id) or text
        self._dispatch(InboundMessage(
            text=followup, user_id=user_id, channel=channel,
            thread_ts=thread_ts, ts=ts, scope="thread",
        ))

    def _handle_mention(self, event: dict[str, Any]) -> None:
        channel = event.get("channel", "")
        if not _channel_allowed(channel, self.config):
            log.info(
                "app_mention in %s not allowed by groupPolicy=%s",
                channel, self.config.group_policy,
            )
            return
        text = _strip_mention(event.get("text", ""), self.bot_user_id)
        if not text:
            return
        ts = event.get("ts")
        thread_ts = event.get("thread_ts") or ts
        self._dispatch(
            InboundMessage(
                text=text,
                user_id=event.get("user", "?"),
                channel=channel,
                thread_ts=thread_ts,
                ts=ts,
                scope="thread",
            )
        )

    def _ack_react(self, channel: str, ts: str | None) -> None:
        """React 👀 on the user's message so they see the bridge saw it."""
        if not ts:
            return
        try:
            self.web.reactions_add(channel=channel, timestamp=ts, name=ACK_EMOJI)
        except SlackApiError as e:
            err = e.response.get("error", "?")
            if err != "already_reacted":
                log.warning("ack reaction failed: %s on %s/%s", err, channel, ts)

    def _dispatch(self, msg: InboundMessage) -> None:
        self._ack_react(msg.channel, msg.ts)
        session_key = SessionStore.key_for(
            channel=msg.channel, user_id=msg.user_id,
            thread_ts=msg.thread_ts, scope=msg.scope,
        )
        with self._lock_for(session_key):
            self._run(msg, session_key)

    def _run(self, msg: InboundMessage, session_key: str) -> None:
        target = PostTarget(channel=msg.channel, thread_ts=msg.thread_ts)
        session, is_new = self.store.get_or_create(
            session_key,
            user_id=msg.user_id,
            channel=msg.channel,
            thread_ts=msg.thread_ts,
            scope=msg.scope,
        )
        log.info(
            "dispatch from %s → %s thread=%s key=%s %s",
            msg.user_id, msg.channel, msg.thread_ts or "-", session_key,
            "NEW" if is_new else f"resume({session.turns} prior)",
        )

        prompt = msg.text
        if is_new:
            history = (
                fetch_dm_history(self.web, channel=msg.channel, exclude_ts=msg.ts)
                if msg.scope == "dm"
                else fetch_thread(
                    self.web, channel=msg.channel,
                    thread_ts=msg.thread_ts or "", exclude_ts=msg.ts,
                )
            )
            preamble = format_preamble(history, bot_user_id=self.bot_user_id)
            if preamble:
                prompt = f"{preamble}\n\n[Current message from <@{msg.user_id}>]\n{msg.text}"

        label = _session_label(msg)
        result = run_claude(
            prompt=prompt,
            workspace=self.config.workspace,
            claude_bin=self.config.claude_bin,
            timeout=self.config.claude_timeout,
            session_id=session.claude_session_id,
            is_new_session=is_new,
            session_label=label,
        )

        if result.session_orphaned:
            log.warning(
                "orphan session %s for %s — rotating + retry",
                session.claude_session_id[:8], session_key,
            )
            rotated = self.store.rotate(session_key)
            if rotated is not None:
                result = run_claude(
                    prompt=prompt,
                    workspace=self.config.workspace,
                    claude_bin=self.config.claude_bin,
                    timeout=self.config.claude_timeout,
                    session_id=rotated.claude_session_id,
                    is_new_session=True,
                    session_label=label,
                )

        reply = result.text if result.ok else f"⚠️ {result.text}"
        self.queue.try_post(target, reply)
        if result.ok:
            self.store.touch(session_key)
            current = self.store.get(session_key)
            effective_id = current.claude_session_id if current else session.claude_session_id
            try:
                unhide_session(self.config.workspace, effective_id)
            except Exception:
                log.exception("session_visibility unhide failed")


def run(config: Config, shutdown: threading.Event) -> None:
    web = WebClient(
        token=config.slack_bot_token,
        retry_handlers=[RateLimitErrorRetryHandler(max_retry_count=2)],
    )
    auth = web.auth_test()
    bot_user_id = auth["user_id"]
    log.info("slack-bridge connected as %s (team=%s)", auth.get("user"), auth.get("team"))

    bridge = Bridge(config, web, bot_user_id)
    log.info("session store: %d active", len(bridge.store))
    bridge.queue.recover_and_start()

    sm = SocketModeClient(app_token=config.slack_app_token, web_client=web)

    def on_request(client: SocketModeClient, req: SocketModeRequest) -> None:
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        try:
            bridge.handle(req)
        except Exception:
            log.exception("event handler failed")

    sm.socket_mode_request_listeners.append(on_request)
    log.info("connecting to slack socket mode…")
    sm.connect()

    shutdown.wait()
    log.info("shutdown signal received — stopping worker + disconnecting")
    bridge.queue.stop()
    try:
        sm.disconnect()
    except Exception:
        log.exception("socket mode disconnect failed")
