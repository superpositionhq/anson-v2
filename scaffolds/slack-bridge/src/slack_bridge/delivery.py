"""Outbound Slack delivery with durable queue + retry.

Rate-limit retries are delegated to the SDK's `RateLimitErrorRetryHandler`
(registered on the WebClient in the listener). Here we handle:

- chunk long responses onto paragraph/line boundaries
- attempt each chunk; on failure, enqueue the remainder
- background worker retries due items with exponential backoff
- dead-letter after MAX_ATTEMPTS or on a fatal error
- startup recovery: `recover_and_start()` scans outbox once then kicks
  off the worker thread
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from slack_sdk.errors import SlackApiError
from slack_sdk.web import WebClient

from ._io import atomic_write_json, now_iso

log = logging.getLogger(__name__)

CHUNK = 3800
MAX_ATTEMPTS = 7
BACKOFF = [30, 60, 120, 300, 900, 1800, 3600]
WORKER_INTERVAL = 30

# Errors that will never succeed on retry — short-circuit to dead-letter.
FATAL_ERRORS = frozenset({
    "channel_not_found",
    "not_in_channel",
    "is_archived",
    "msg_too_long",
    "invalid_auth",
    "token_revoked",
    "account_inactive",
})


@dataclass
class PostTarget:
    channel: str
    thread_ts: str | None = None


@dataclass
class OutboxEntry:
    id: str
    channel: str
    thread_ts: str | None
    chunks: list[str]
    sent_chunks: int
    attempts: int
    created_at: str
    last_attempt_at: str | None
    last_error: str | None
    next_attempt_at: str


def _split(text: str, n: int = CHUNK) -> list[str]:
    """Split on paragraph then line boundary so code fences survive."""
    if len(text) <= n:
        return [text]
    chunks, buf = [], ""
    for para in text.split("\n\n"):
        candidate = buf + ("\n\n" if buf else "") + para
        if len(candidate) <= n:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
            buf = ""
        if len(para) <= n:
            buf = para
            continue
        for line in para.split("\n"):
            candidate = buf + ("\n" if buf else "") + line
            if len(candidate) <= n:
                buf = candidate
            else:
                if buf:
                    chunks.append(buf)
                while len(line) > n:
                    chunks.append(line[:n])
                    line = line[n:]
                buf = line
    if buf:
        chunks.append(buf)
    return chunks


def _backoff_at(attempt: int) -> str:
    idx = min(attempt, len(BACKOFF)) - 1
    delay = BACKOFF[max(idx, 0)]
    return (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()


class DeliveryQueue:
    def __init__(self, outbox_dir: Path, web: WebClient):
        self.dir = outbox_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.dead_dir = self.dir / "dead"
        self.dead_dir.mkdir(parents=True, exist_ok=True)
        self.web = web
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None

    def try_post(self, target: PostTarget, text: str) -> bool:
        """Best-effort immediate post. Returns True if all chunks delivered.
        Any remainder is enqueued unless the failure is fatal (then dead-lettered)."""
        if not text.strip():
            return True

        chunks = _split(text)
        sent = 0
        last_error: str | None = None

        for piece in chunks:
            ok, err = self._send_one(target, piece)
            if ok:
                sent += 1
                continue
            last_error = err
            break

        if sent == len(chunks):
            return True

        remainder = chunks[sent:]
        if last_error in FATAL_ERRORS:
            self._dead_letter_new(target, remainder, last_error=last_error)
            log.error(
                "delivery fatal for %s: %d/%d sent, reason=%s — dead-lettered",
                target.channel, sent, len(chunks), last_error,
            )
            return False

        self._enqueue_new(target, remainder, last_error=last_error)
        log.warning(
            "enqueued remainder for %s: %d/%d sent, reason=%s",
            target.channel, sent, len(chunks), last_error,
        )
        return False

    def _send_one(self, target: PostTarget, piece: str) -> tuple[bool, str | None]:
        """Send one chunk. `RateLimitErrorRetryHandler` on the WebClient
        already handles 429/Retry-After transparently."""
        try:
            self.web.chat_postMessage(
                channel=target.channel,
                thread_ts=target.thread_ts,
                text=piece,
            )
            return True, None
        except SlackApiError as e:
            err = e.response.get("error", "unknown")
            if err in FATAL_ERRORS:
                log.error("fatal post error: %s", err)
            return False, err

    def _make_entry(self, target: PostTarget, chunks: list[str], *, last_error: str | None) -> OutboxEntry:
        return OutboxEntry(
            id=str(uuid.uuid4()),
            channel=target.channel,
            thread_ts=target.thread_ts,
            chunks=chunks,
            sent_chunks=0,
            attempts=1,
            created_at=now_iso(),
            last_attempt_at=now_iso(),
            last_error=last_error,
            next_attempt_at=_backoff_at(1),
        )

    def _enqueue_new(self, target: PostTarget, chunks: list[str], *, last_error: str | None) -> None:
        entry = self._make_entry(target, chunks, last_error=last_error)
        self._write(entry)

    def _dead_letter_new(self, target: PostTarget, chunks: list[str], *, last_error: str | None) -> None:
        entry = self._make_entry(target, chunks, last_error=last_error)
        p = self.dead_dir / f"{entry.id}.json"
        atomic_write_json(p, asdict(entry))

    def _path(self, entry_id: str) -> Path:
        return self.dir / f"{entry_id}.json"

    def _write(self, entry: OutboxEntry) -> None:
        atomic_write_json(self._path(entry.id), asdict(entry))

    def recover_and_start(self) -> None:
        pending = list(self.dir.glob("*.json"))
        if pending:
            log.info("outbox recovery: %d pending entries", len(pending))
        self._drain_once()
        self._worker = threading.Thread(
            target=self._worker_loop, daemon=True, name="delivery-worker",
        )
        self._worker.start()

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._drain_once()
            except Exception:
                log.exception("delivery worker tick failed")
            self._stop.wait(WORKER_INTERVAL)

    def _drain_once(self) -> None:
        now = datetime.now(timezone.utc)
        for path in sorted(self.dir.glob("*.json")):
            try:
                entry = OutboxEntry(**json.loads(path.read_text()))
            except (OSError, json.JSONDecodeError, TypeError) as e:
                log.warning("outbox file %s malformed, moving to dead: %s", path.name, e)
                self._dead_letter_raw(path)
                continue

            try:
                next_at = datetime.fromisoformat(entry.next_attempt_at)
            except ValueError:
                next_at = now
            if now < next_at:
                continue

            self._retry_entry(path, entry)

    def _retry_entry(self, path: Path, entry: OutboxEntry) -> None:
        target = PostTarget(channel=entry.channel, thread_ts=entry.thread_ts)
        sent = entry.sent_chunks
        last_error: str | None = None

        for piece in entry.chunks[sent:]:
            ok, err = self._send_one(target, piece)
            if ok:
                sent += 1
                continue
            last_error = err
            break

        if sent == len(entry.chunks):
            path.unlink(missing_ok=True)
            log.info("outbox cleared: %s → %s", entry.id[:8], entry.channel)
            return

        entry.sent_chunks = sent
        entry.attempts += 1
        entry.last_attempt_at = now_iso()
        entry.last_error = last_error

        if entry.attempts >= MAX_ATTEMPTS or last_error in FATAL_ERRORS:
            dest = self.dead_dir / path.name
            path.replace(dest)
            log.error(
                "outbox dead-lettered %s → %s after %d attempts (last=%s)",
                entry.id[:8], dest, entry.attempts, last_error,
            )
            return

        entry.next_attempt_at = _backoff_at(entry.attempts)
        self._write(entry)
        log.info(
            "outbox retry scheduled: %s attempt=%d next=%s error=%s",
            entry.id[:8], entry.attempts, entry.next_attempt_at, last_error,
        )

    def _dead_letter_raw(self, path: Path) -> None:
        try:
            path.replace(self.dead_dir / path.name)
        except OSError:
            log.exception("could not dead-letter %s", path)

    def stop(self) -> None:
        self._stop.set()
