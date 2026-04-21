# Gmail OAuth setup

Two paths. Pick one.

## Path A — `gog` CLI (recommended)

`gog` is a small Google Workspace CLI used by skills for `gmail` + `calendar` + `drive`.

```bash
brew install gog   # or download from https://github.com/.../gog
gog auth add <email-address>   # opens browser, you sign in
```

Repeat `gog auth add` for each Gmail account (work + personal).

Verify:
```bash
gog -a <email-address> gmail list --unread --limit 3
```

## Path B — Native Google OAuth app

Use this if `gog` doesn't fit, or for a custom integration.

1. Go to https://console.cloud.google.com → create a project (or pick existing).
2. **APIs & Services → Library** → enable **Gmail API**.
3. **Credentials → Create Credentials → OAuth client ID** → **Desktop app**.
4. Download the JSON; save as `~/.config/anson/google_oauth.json`.
5. First run: a browser opens for consent. Token cached locally.

Scopes needed (minimum):
- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/gmail.modify` (for archive/label)

## Verify

```bash
python3 scripts/verify_gmail.py <email1> <email2>
```

Lists last 3 unread per account. Empty = fine. Auth error = stop, retry path A or B.

## Common issues

- **`invalid_grant`** — token expired or refresh token revoked. Re-run `gog auth add <email>`.
- **Multiple accounts** — `gog` keeps separate token caches per `-a <email>`.
- **2FA prompt loop** — clear browser cookies for `accounts.google.com`, retry.
