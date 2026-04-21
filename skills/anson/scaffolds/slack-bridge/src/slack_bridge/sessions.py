"""Per-conversation Claude session tracking.

Each Slack conversation (DM with a user, or a channel thread) maps to a
stable UUID we pass to `claude --session-id` on first message and
`claude --resume` on subsequent ones. Claude Code persists sessions on disk,
so we keep only the mapping + metadata here.

Key shapes:
- DM:             dm:<user_id>
- Channel thread: thread:<channel>:<thread_ts>

TTL: a session idle > TTL rotates on next access. A background sweep at
load-time prunes very-stale entries (> TTL * SWEEP_MULTIPLIER) so the
file doesn't grow forever for one-shot DMs.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Literal

from ._io import atomic_write_json, now_iso

log = logging.getLogger(__name__)

TTL = timedelta(hours=24)
SWEEP_MULTIPLIER = 7  # entries idle > TTL * this get dropped on load

Scope = Literal["dm", "thread"]


@dataclass
class Session:
    key: str
    claude_session_id: str
    created_at: str
    last_activity_at: str
    user_id: str
    channel: str
    thread_ts: str | None
    scope: Scope
    turns: int = 0


@dataclass
class SessionStore:
    path: Path
    _sessions: dict[str, Session] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self):
        self._load()

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._sessions

    def get(self, key: str) -> Session | None:
        with self._lock:
            return self._sessions.get(key)

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text())
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError, TypeError) as e:
            log.warning("session store corrupt, starting fresh: %s", e)
            return

        now = datetime.now(timezone.utc)
        sweep_after = TTL * SWEEP_MULTIPLIER
        pruned = 0
        for k, v in (raw.get("sessions") or {}).items():
            try:
                s = Session(**v)
                last = datetime.fromisoformat(s.last_activity_at)
            except (TypeError, ValueError):
                pruned += 1
                continue
            if now - last > sweep_after:
                pruned += 1
                continue
            self._sessions[k] = s
        if pruned:
            log.info("session load: pruned %d stale entries", pruned)

    def _persist(self) -> None:
        atomic_write_json(
            self.path,
            {"sessions": {k: asdict(v) for k, v in self._sessions.items()}},
        )

    @staticmethod
    def key_for(*, channel: str, user_id: str, thread_ts: str | None, scope: Scope) -> str:
        if scope == "dm":
            return f"dm:{user_id}"
        if thread_ts is None:
            raise ValueError("thread scope requires thread_ts")
        return f"thread:{channel}:{thread_ts}"

    def get_or_create(
        self,
        key: str,
        *,
        user_id: str,
        channel: str,
        thread_ts: str | None,
        scope: Scope,
    ) -> tuple[Session, bool]:
        """Return (session, is_new). Stale sessions are rotated: same key, new UUID."""
        now = datetime.now(timezone.utc)
        with self._lock:
            s = self._sessions.get(key)
            if s is not None:
                last = datetime.fromisoformat(s.last_activity_at)
                if now - last <= TTL:
                    return s, False
                log.info("rotating stale session %s (idle %s)", key, now - last)
            stamp = now.isoformat()
            new = Session(
                key=key,
                claude_session_id=str(uuid.uuid4()),
                created_at=stamp,
                last_activity_at=stamp,
                user_id=user_id,
                channel=channel,
                thread_ts=thread_ts,
                scope=scope,
            )
            self._sessions[key] = new
            self._persist()
            return new, True

    def touch(self, key: str) -> None:
        with self._lock:
            s = self._sessions.get(key)
            if s is None:
                return
            s.last_activity_at = now_iso()
            s.turns += 1
            self._persist()

    def drop(self, key: str) -> None:
        with self._lock:
            if self._sessions.pop(key, None):
                self._persist()

    def rotate(self, key: str) -> Session | None:
        """Swap in a fresh UUID for an existing key (orphan recovery).
        Keeps metadata but resets the turn counter."""
        with self._lock:
            s = self._sessions.get(key)
            if s is None:
                return None
            s.claude_session_id = str(uuid.uuid4())
            s.last_activity_at = now_iso()
            s.turns = 0
            self._persist()
            log.info("rotated session %s → new UUID %s", key, s.claude_session_id[:8])
            return s
