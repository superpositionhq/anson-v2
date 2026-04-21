"""Make `claude -p`-born sessions visible in Claude Code's /resume picker.

Claude Code hides sessions whose JSONL attachment records are tagged
`entrypoint: sdk-cli` (headless). After each dispatch we flip those to
`claude-desktop` so the Slack-born conversation is navigable from
interactive Claude Code like any other session.

Safe to call on every turn — our per-session concurrency lock guarantees
the file isn't being written by Claude at the same time.
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"

TARGET = '"entrypoint":"sdk-cli"'
REPLACEMENT = '"entrypoint":"claude-desktop"'


def _project_dir_for(workspace: Path) -> Path:
    """Claude Code's project-dir naming: leading '-', then '/' → '-'."""
    encoded = "-" + str(workspace).replace("/", "-").lstrip("-")
    return CLAUDE_PROJECTS / encoded


def unhide_session(workspace: Path, session_id: str) -> bool:
    """Rewrite `"entrypoint":"sdk-cli"` → `"entrypoint":"claude-desktop"` in
    the session's JSONL. Streams line-by-line so memory stays bounded even
    on long sessions. Returns True if the file was rewritten."""
    sess_path = _project_dir_for(workspace) / f"{session_id}.jsonl"
    tmp_path = sess_path.with_suffix(".jsonl.tmp")
    changed = False
    try:
        with sess_path.open("r") as src, tmp_path.open("w") as dst:
            for line in src:
                if TARGET in line:
                    dst.write(line.replace(TARGET, REPLACEMENT))
                    changed = True
                else:
                    dst.write(line)
    except FileNotFoundError:
        log.debug("session jsonl not found: %s", sess_path)
        tmp_path.unlink(missing_ok=True)
        return False

    if not changed:
        tmp_path.unlink(missing_ok=True)
        return False

    tmp_path.replace(sess_path)
    log.info("session %s unhidden in Claude Code picker", session_id[:8])
    return True
