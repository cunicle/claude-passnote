---
name: disable
description: Turn passnote off for this session
disable-model-invocation: true
---

Turn passnote off for this Claude Code session. Run this (if `python3` is not found, use `python`, or `py` on Windows):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/client.py" disable --session "${CLAUDE_SESSION_ID}"
```

Tell the user that the hooks stop at once and the MCP tools go away when the session restarts. A session started with
`PASSNOTE_ENABLE=1` in its environment stays on until it is restarted without it.
