# Scheduled tasks

Anson installs recurring jobs (morning brief, nightly cleanup, weekly digests) using whichever scheduler your platform supports best.

## Claude Code (preferred)

Use the built-in **scheduled tasks** MCP. Each task lives at `~/.claude/scheduled-tasks/<name>/`:

```
<name>/
├── SKILL.md     # the prompt the scheduled run executes
├── scripts/     # any helpers
└── state/       # task state
```

Anson registers tasks via `mcp__scheduled-tasks__create_scheduled_task` during Stage D step 4. Cron schedule per task; execution body is just "follow the skill at `<workspace>/skills/<skill-name>/SKILL.md`".

Manage:
```
list scheduled tasks
update scheduled task <name>
delete scheduled task <name>
```

(Or via the MCP CLI directly.)

## macOS native (fallback)

If Claude Code isn't available, use launchd:

1. Drop a plist into `~/Library/LaunchAgents/`:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <plist version="1.0">
   <dict>
     <key>Label</key>          <string>com.example.morning-brief</string>
     <key>ProgramArguments</key><array>
       <string>/usr/bin/env</string>
       <string>bash</string>
       <string>-lc</string>
       <string>cd ~/Assistant && claude -p "Run morning-brief"</string>
     </array>
     <key>StartCalendarInterval</key><dict>
       <key>Hour</key><integer>10</integer>
       <key>Minute</key><integer>0</integer>
     </dict>
   </dict>
   </plist>
   ```
2. `launchctl load ~/Library/LaunchAgents/com.example.morning-brief.plist`

## Linux native (fallback)

systemd user units:

`~/.config/systemd/user/morning-brief.service`:
```
[Unit]
Description=Morning Brief

[Service]
Type=oneshot
WorkingDirectory=%h/Assistant
ExecStart=/usr/bin/env bash -lc 'claude -p "Run morning-brief"'
```

`~/.config/systemd/user/morning-brief.timer`:
```
[Unit]
Description=Morning Brief @ 10:00 daily

[Timer]
OnCalendar=*-*-* 10:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable: `systemctl --user enable --now morning-brief.timer`.

## Cron (last resort)

```
0 10 * * * cd ~/Assistant && claude -p "Run morning-brief" >> ~/Assistant/tmp/morning-brief.log 2>&1
```

## What anson schedules by default

Based on Stage C/D answers:

| Skill | Default schedule | Notes |
|---|---|---|
| `morning-brief` | once daily, time you picked | reads `state/directives.json` reminders |
| `note-management` | none — chat-triggered | runs `expire` as part of nightly cleanup |
| Nightly cleanup | once daily, ~23:00 local | `directives.py expire` + per-skill cleanup + `tmp/` prune |

You can edit anything later — the scheduler config is plain files.
