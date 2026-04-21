# Slack user-session tokens (xoxc + xoxd)

User tokens let you read/scan Slack as **yourself** — no bot account, no "Slack Bot" sender. Required for read-only scans (`slack-triage`).

For a two-way bot ("DM the agent, get a reply in thread"), see `slack_app.md` (Stage D Slack-bridge step).

## Extract from DevTools

1. Open Slack in **Chrome / Edge / Firefox** (the desktop client uses the same tokens but harder to grab).
2. Open DevTools (`Cmd-Opt-I` / `Ctrl-Shift-I`).
3. Go to **Network** tab → filter for `api.slack.com`.
4. Click any visible request to slack.com.
5. **`xoxc-...` token** — under **Request Headers** → `Authorization: Bearer xoxc-...`. Copy everything starting at `xoxc-`.
6. **`xoxd-...` cookie** — under **Request Headers** → `Cookie:` line → find `d=xoxd-...`. Copy everything starting at `xoxd-`.

## Store

In your workspace `.env`:

```
SLACK_XOXC_TOKEN=xoxc-...
SLACK_XOXD_TOKEN=xoxd-...
```

Make sure `.env` has mode 600:
```bash
chmod 600 .env
```

## Verify

```bash
python3 scripts/verify_slack.py
```

Calls `auth.test`. Output should show your workspace + user ID.

## Token expiry

User-session tokens roll over every ~30 days. When `verify_slack.py` returns `invalid_auth`, repeat the DevTools extraction and update `.env`. The `slack-triage` skill will fail loudly when this happens — don't auto-retry.

## Hard rule baked into anson defaults

The skill **never posts as you** unless you give explicit per-conversation permission ("post this as me" / "send this as me"). Any send/dm command in the slack-triage skill requires that opt-in. This is enforced in `MEMORY.md § Hard Rules`.
