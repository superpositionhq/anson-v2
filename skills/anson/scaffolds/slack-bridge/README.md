# slack-bridge

Self-contained Slack daemon. Listens on Socket Mode, dispatches every inbound DM/mention to `claude -p` running in your workspace, posts the response back as a thread reply.

Vendored into anson-v2 so the install is one repo. Anson Stage D wires this up if you opted in to the two-way Slack coworker; otherwise leave it alone.

## Configuration

Set `WORKSPACE_ROOT` to your anson workspace path:

```bash
export WORKSPACE_ROOT="$HOME/Assistant"   # or wherever your workspace lives
```

The bridge expects to live at `${WORKSPACE_ROOT}/slack-bridge/`. Tokens + policy + allowlist live in `${WORKSPACE_ROOT}/slack-bridge/.env` and `config/`.

## Install (manual — anson does this for you)

```bash
cd "${WORKSPACE_ROOT}/slack-bridge"
uv venv
uv pip install -e .
cp .env.example .env   # then fill in SLACK_BOT_TOKEN + SLACK_APP_TOKEN
```

For Slack app + token instructions, see `references/slack_app.md` in the anson-v2 repo.

## Run (foreground, for testing)

```bash
cd "${WORKSPACE_ROOT}/slack-bridge"
source .venv/bin/activate
WORKSPACE_ROOT="$WORKSPACE_ROOT" python -m slack_bridge
```

## Run (launchd, macOS persistent)

```bash
WORKSPACE_ROOT="$HOME/Assistant" ./launchd/install.sh
./launchd/uninstall.sh
```

`install.sh` substitutes `WORKSPACE_ROOT` into the plist template at install time.

## File layout

```
slack-bridge/
├── .env                                       (tokens — chmod 600)
├── config/
│   ├── policy.json                            (DM + channel policies)
│   └── allowlist.json                         (paired user IDs)
├── state/
│   ├── sessions.json                          (Slack-key → Claude session UUID)
│   └── outbox/                                (durable pending deliveries)
├── logs/
├── scripts/
│   ├── post_to_slack.py                       (send a one-shot message; used by scheduled tasks)
│   └── read_user_dm.py                        (read recent bot/user DM history)
├── launchd/
│   ├── ai.slack-bridge.gateway.plist.tmpl     (substituted at install time)
│   ├── install.sh
│   └── uninstall.sh
└── src/slack_bridge/                          (Python package)
```

## Architecture

```
Slack ─ Socket Mode ─► SocketModeClient ─► bridge.handle ─► claude -p
                                                                │
                                                       cwd = $WORKSPACE_ROOT
                                                                │
                                              loads CLAUDE.md → AGENTS.md → MEMORY.md
                                              all skills resolved from skills/
                                                                │
                                                       Response posted as thread reply
```

## Allowlist

`config/allowlist.json` lists Slack user IDs allowed to talk to the bridge. Anson defaults to your own user ID. Add others sparingly — anyone in the allowlist can run agent commands as you.
