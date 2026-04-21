# Anson v2

**Battle-tested coworker setup for Claude Code · Slack · Notion · Gmail · Granola.**

Bootstrap a working AI coworker end-to-end, by interview.

Anson v1 wrote your identity docs. **v2 installs the whole coworker**: identity + integrations + scheduled automations + custom workflows. You talk to it once, and at the end you have a workspace you can talk to immediately.

## What you get

- **Identity** — `AGENTS.md`, `IDENTITY.md`, `USER.md`, `SOUL.md`, `MEMORY.md` written from your answers, not templates
- **Integrations** — Gmail, Google Calendar, Slack, Notion, Granola (macOS), iMessage (macOS) — authenticated, verified, and wired into your agent's tool surface
- **Rhythm** — morning brief, standup notes, evening wrap-up, weekly digests — whichever you ask for, scheduled and running
- **Two-way Slack coworker (optional)** — DM the agent from your phone, get replies in thread
- **Your own workflows** — describe any automation in plain English; Anson generates a skill, dry-runs it on your real data, and installs it if you approve

This stack is what runs day-to-day for the founder it was built around — every skill, every directive pattern, every cleanup hook has hit production. Strangers get the same battle-tested core, customized to *their* identity and workflow.

## Install

```bash
git clone https://github.com/superpositionhq/anson-v2 ~/.claude/skills/anson
```

Then in your agent:

> Run anson

That's it. Anson handles the rest — step by step, one question at a time, resumable if you get interrupted.

## Requirements

- **Claude Code** (primary) — Agent SDK works with reduced features
- **Strong reasoning model** (Claude Sonnet 4.6+ / Opus)
- **`anthropic-skills:skill-creator`** plugin
- **`uv`** for the Slack bridge (optional stage)
- **macOS or Linux** — iMessage + Granola are macOS-only; everything else works on both

## What the interview covers

The flow is conversational, not a checklist — but at a high level:

| Stage | What happens | What gets written |
|---|---|---|
| **A** | Anson introduces itself, picks workspace root | `<workspace>/ANSON_META.md` |
| **B** | Who are you? (identity interview before any tools) | `USER.md`, `IDENTITY.md`, `SOUL.md`, `KEY_PEOPLE.md`, `MEMORY.md` skeleton |
| **C** | How do you work? (open-ended workflow discovery) | workflow summary in `ANSON_META.md` |
| **D** | Anson proposes the install plan based on Stage C, then executes only what your workflow needs | `.env`, verified integrations, installed skills, scheduled tasks, optional Slack bridge |
| **E** | Any custom workflows? Describe in plain English; anson generates a skill, dry-runs it, installs it | custom skills (≤5 per session) |
| **F** | Hand-off | install inventory + next steps |

Total time: ~30–45 minutes, mostly waiting on OAuth.

Identity (Stage B) comes before integrations (Stage D) so installs are tailored to your stated voice and preferences. Integrations are consequences of Stage C — if you don't use Slack, anson never asks for a Slack token.

## Resumable

If you close the terminal mid-install, Anson picks up from the last checkpoint when you say "Run anson" again. Progress is tracked in `ANSON_META.md`.

## Adding workflows later

Re-run `anson` any time. It detects the existing install, skips everything done, and jumps you straight to Stage E so you can add more automations.

## License

MIT.

## Credits

Successor to [anson v1](https://github.com/superpositionhq/anson) by Superposition. The v1 identity-interview approach is preserved as Stage B; v2 absorbs everything around it.
