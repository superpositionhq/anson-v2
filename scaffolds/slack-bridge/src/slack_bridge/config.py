"""Load config from slack-bridge's own `.env`.

Self-contained: this module owns its own tokens, policies, and allowlist file.
The parent workspace is identified by the WORKSPACE_ROOT env var (or
SLACK_BRIDGE_WORKSPACE for back-compat).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _default_workspace() -> Path:
    """Workspace root resolution order:
    1. WORKSPACE_ROOT env var (anson-v2 default)
    2. SLACK_BRIDGE_WORKSPACE env var (legacy)
    3. parent of slack-bridge dir (assumes vendored install)
    """
    env_root = os.environ.get("WORKSPACE_ROOT") or os.environ.get("SLACK_BRIDGE_WORKSPACE")
    if env_root:
        return Path(env_root).expanduser()
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Config:
    slack_bot_token: str
    slack_app_token: str
    workspace: Path
    claude_bin: str
    claude_timeout: int
    log_level: str
    dm_policy: str
    group_policy: str
    channels: dict
    allowlist_path: Path
    state_dir: Path
    log_dir: Path


def load() -> Config:
    """Read `.env` + `config/policy.json`. Missing required values raise.

    Also loads the parent workspace's `.env` (if present) so skills invoked
    via `claude -p` inherit any other tokens (NOTION_API_KEY, etc).
    slack-bridge's own `.env` takes precedence.
    """
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")

    workspace = _default_workspace()
    if workspace.is_dir():
        load_dotenv(workspace / ".env", override=False)

    bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
    app_token = os.environ.get("SLACK_APP_TOKEN", "")
    if not bot_token.startswith("xoxb-"):
        raise RuntimeError(
            "SLACK_BOT_TOKEN missing or malformed (want xoxb-...). "
            "Set it in slack-bridge/.env (see anson Stage D Slack-bridge)."
        )
    if not app_token.startswith("xapp-"):
        raise RuntimeError(
            "SLACK_APP_TOKEN missing or malformed (want xapp-...). "
            "Set it in slack-bridge/.env (see anson Stage D Slack-bridge)."
        )

    if not workspace.is_dir():
        raise RuntimeError(
            f"WORKSPACE_ROOT not a directory: {workspace}. "
            "Set WORKSPACE_ROOT env var to your anson workspace path."
        )

    state_dir = project_root / "state"
    log_dir = project_root / "logs"
    config_dir = project_root / "config"
    state_dir.mkdir(exist_ok=True)
    log_dir.mkdir(exist_ok=True)
    config_dir.mkdir(exist_ok=True)

    policy = _load_policy(config_dir / "policy.json")

    return Config(
        slack_bot_token=bot_token,
        slack_app_token=app_token,
        workspace=workspace,
        claude_bin=os.environ.get("CLAUDE_BIN", "claude"),
        claude_timeout=int(os.environ.get("SLACK_BRIDGE_CLAUDE_TIMEOUT", "300")),
        log_level=os.environ.get("SLACK_BRIDGE_LOG_LEVEL", "INFO"),
        dm_policy=policy.get("dm_policy", "open"),
        group_policy=policy.get("group_policy", "open"),
        channels=policy.get("channels", {}) or {},
        allowlist_path=config_dir / "allowlist.json",
        state_dir=state_dir,
        log_dir=log_dir,
    )


def _load_policy(path: Path) -> dict:
    """Policy JSON shape:
    {
      "dm_policy": "pairing" | "open",
      "group_policy": "allowlist" | "open",
      "channels": {"C0ABC...": {"requireMention": true}, ...}
    }
    Missing file → empty defaults (dm_policy=open, group_policy=open).
    """
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as e:
        logging.warning("policy file %s unreadable: %s — using defaults", path, e)
        return {}
