"""Invoke `claude -p` with per-conversation session continuity.

First turn: `claude -p <prompt> --session-id <uuid> --name <label>` so the
UUID becomes Claude's session ID and `/resume` shows a useful label.
Subsequent turns: `claude -p <prompt> --resume <uuid>`.

Sessions land in `~/.claude/projects/<workspace-slug>/<uuid>.jsonl`,
so `cd $WORKSPACE_ROOT && claude /resume` surfaces every live Slack
conversation with its full transcript.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Substrings in stderr that indicate `--resume <uuid>` is no longer valid.
# Brittle across CLI versions — re-verify against `claude` after upgrades.
ORPHAN_MARKERS = (
    "could not find session",
    "no such session",
    "session not found",
    "unknown session",
    "resume target not found",
)


@dataclass
class DispatchResult:
    ok: bool
    text: str
    returncode: int
    session_orphaned: bool = False


def _looks_orphaned(returncode: int, stderr: str) -> bool:
    if returncode == 0:
        return False
    low = (stderr or "").lower()
    return any(marker in low for marker in ORPHAN_MARKERS)


def run_claude(
    *,
    prompt: str,
    workspace: Path,
    claude_bin: str,
    timeout: int,
    session_id: str,
    is_new_session: bool,
    session_label: str | None = None,
) -> DispatchResult:
    """Run one turn. On `--resume` failure against a missing session,
    returns `session_orphaned=True`; caller rotates + retries as new."""
    cmd = [claude_bin, "-p", prompt, "--output-format", "text"]
    if is_new_session:
        cmd += ["--session-id", session_id]
        if session_label:
            cmd += ["--name", session_label]
    else:
        cmd += ["--resume", session_id]

    log.info(
        "dispatch: %d chars → claude (%s %s%s)",
        len(prompt),
        "new" if is_new_session else "resume",
        session_id[:8],
        f" '{session_label}'" if is_new_session and session_label else "",
    )
    try:
        res = subprocess.run(
            cmd,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log.error("claude timed out after %ds", timeout)
        return DispatchResult(
            ok=False,
            text=f"(agent timeout after {timeout}s — try again)",
            returncode=-1,
        )

    if res.returncode != 0:
        orphaned = (not is_new_session) and _looks_orphaned(res.returncode, res.stderr)
        log.error(
            "claude exit %d%s stderr=%s",
            res.returncode,
            " [orphan session]" if orphaned else "",
            res.stderr[:500],
        )
        return DispatchResult(
            ok=False,
            text=f"(agent error: exit {res.returncode})",
            returncode=res.returncode,
            session_orphaned=orphaned,
        )

    return DispatchResult(ok=True, text=res.stdout.strip(), returncode=0)
