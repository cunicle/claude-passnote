---
name: enable
description: Turn passnote on for this session only
disable-model-invocation: true
---

Turn passnote on for this Claude Code session. Run this (if `python3` is not found, use `python`, or `py` on Windows):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/client.py" enable --session "${CLAUDE_SESSION_ID}"
```

Then tell the user, in a few lines:

- The hooks work right away: new messages are shown when the user sends a prompt, between tool calls (at most every
  20 seconds) and, if any are still unread, once before you stop.
- The MCP tools `send`, `read_inbox` and `ack` appear after this session restarts. In a terminal: `/exit`, then
  `claude --resume ${CLAUDE_SESSION_ID}` (with the same options as before, e.g. `--plugin-dir`). Warn that
  `--continue` resumes the most recent session of the current directory, which may be a different one. Until the
  restart, the `/passnote:mail` skill sends and reads messages from the command line.
- If this session is later continued as a new session (a new session id), run `/passnote:enable` there again.
- If the output says passnote is not configured, run `/passnote:init` first.
