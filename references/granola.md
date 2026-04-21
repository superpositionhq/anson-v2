# Granola — meeting notes integration

[Granola](https://granola.ai) is a desktop meeting-notes app (macOS / Windows). It records, transcribes (in-app), and stores notes locally; an optional sync layer makes them available via REST.

The integration is **read-only** — anson-v2 reads recent meeting notes to feed the morning brief and the optional `granola-digest` skill. No writing back to Granola.

## Skip this entire section if

- You don't use Granola
- You're on Linux (Granola desktop is macOS / Windows only)

## Setup

1. Install Granola from https://granola.ai → sign in with your Google or Apple account.
2. Make sure the desktop app is running and logged in. The auth token lives in:
   ```
   ~/Library/Application Support/Granola/supabase.json    # macOS
   %APPDATA%\Granola\supabase.json                        # Windows
   ```
   anson reads `workos_tokens.access_token` from this file at runtime — no manual token paste.
3. Record at least one meeting in Granola so verify has data to read.

## Verify

```bash
python3 scripts/verify_granola.py
```

Lists last 3 meeting titles. Empty = no meetings yet (fine). 401/403 = token expired → open the Granola app and let it refresh, then retry.

## Token expiry

The cached token rolls every few weeks. When verify returns auth errors, the fix is just opening the Granola desktop app — it auto-refreshes the local token. No manual extraction.

## Content available

- `notes_plain` — text of in-app notes
- `title` — Granola's AI-generated title or the linked calendar event name
- `people` — attendee list
- `google_calendar_event` — calendar metadata if the meeting was linked

**Transcripts are NOT stored server-side.** Only post-call notes are accessible.

## What anson installs (if you opt in)

- `skills/granola-digest/` — generic skill that reads yesterday's (or any range's) meetings and produces a digest, optionally surfaced in `morning-brief` automatically.

## Privacy note

Meeting notes can include sensitive content. The integration reads from your local machine only — anson never uploads them anywhere. The morning brief, if you have one, includes meeting summaries in the local brief file and (optionally) posts them to Slack via the slack-bridge — same path as any other brief content.
