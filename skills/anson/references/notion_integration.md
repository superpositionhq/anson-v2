# Notion integration

You need an **integration** + a list of databases shared with it.

## 1. Create the integration

1. Go to https://www.notion.so/my-integrations → **+ New integration**.
2. **Name**: pick anything (e.g. "Coworker", or whatever you named your agent in Stage B). **Workspace**: yours.
3. **Capabilities**: tick **Read content**, **Update content**, **Insert content**. Comments + user info as needed.
4. Click **Submit**. Copy the **Internal Integration Token** (starts `secret_` or `ntn_`).

Add to `.env`:
```
NOTION_API_KEY=secret_...
```

## 2. Share each database with the integration

Notion's integration model is **explicit per-page**. The integration sees nothing until you share specific pages/databases with it.

For each database the agent should access:

1. Open the database in Notion.
2. Top-right **`...`** menu → **Connections** → search your integration name → **Confirm**.
3. The integration now has access to that database **and all child pages**.

Repeat for every DB you care about. Common candidates:
- Tasks DB
- Projects / Specs DB
- Bug Tracker DB
- Meetings DB
- CRM / Contacts DB
- Notes / Wiki DB

## 3. Capture each DB ID

The DB ID is the 32-char hex in the URL:
```
https://www.notion.so/<workspace>/<NAME>-<32CHARID>?v=...
                                          ^^^^^^^^^^
```

Anson asks for these one at a time during Stage D (Notion step). Each gets recorded in `MEMORY.md § Notion Databases` with its role (Tasks / Bugs / etc.).

## Verify

```bash
python3 scripts/verify_notion.py --db <DB_ID> --db <DB_ID>
```

For each DB: probes one row. If you forgot to share a DB with the integration, this fails with 404 — go back to Step 2.

## Common issues

- **404 on a DB you can see in Notion** — you didn't share it with the integration. Share it.
- **Token has no `secret_` prefix** — older format. Still works.
- **Workspace owner restrictions** — some workspaces require admins to approve integrations. Ask your admin.
