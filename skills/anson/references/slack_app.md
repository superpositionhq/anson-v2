# Slack app — for the two-way bridge (Stage D Slack-bridge step, optional)

If you want the agent to be a real Slack bot you can DM ("hey, what's on my calendar?") and get replies in thread, you need to create a Slack app in your workspace.

This is **separate** from the `xoxc`/`xoxd` user tokens (`slack_tokens.md`). User tokens scan/read as you; the app posts as the bot.

## Steps

1. Go to https://api.slack.com/apps → **Create New App** → **From scratch**.
2. **App Name**: whatever you named your agent in Stage B (or pick now). **Workspace**: yours.
3. **Socket Mode** (left sidebar): **enable**. Generate an **App-Level Token** with scope `connections:write`. Copy as `SLACK_APP_TOKEN`.
4. **OAuth & Permissions** → **Bot Token Scopes**, add:
   - `app_mentions:read`
   - `chat:write`
   - `im:history`
   - `im:read`
   - `im:write`
   - `users:read`
5. **Event Subscriptions** → **Enable Events** → **Subscribe to bot events**:
   - `app_mention`
   - `message.im`
6. **Install App** (top of OAuth page) → **Install to Workspace** → authorize. Copy the **Bot User OAuth Token** (starts `xoxb-`) as `SLACK_BOT_TOKEN`.

## Store

Add to `.env`:

```
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

## DM the bot

Open a DM with your new bot in Slack. Send "ping". The bridge daemon (Stage D Slack-bridge install) replies in the same DM thread. If nothing happens, check `slack-bridge/logs/`.

## Allowlist

The bridge ships with an **allowlist** — only DMs from listed Slack user IDs trigger an agent invocation. Defaults to your own ID (set during Stage D Slack-bridge step).

To add others (e.g. teammates who can DM the bot):
```bash
# edit slack-bridge/config/allowlist.json
```

Don't open the allowlist to `*` — that means anyone in your workspace can run agent commands as you.
