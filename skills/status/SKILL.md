---
name: status
description: Check passnote - whether this session has it on, whether it is configured, and whether the server answers
---

Check passnote for this session. Run this (if `python3` is not found, use `python`, or `py` on Windows):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/client.py" status --session "${CLAUDE_SESSION_ID}"
```

Report the result in a few lines and, if something is missing, the fix:

- `configured False`: run `/passnote:init <name> <server-url> [cert.pem]`.
- `enabled False`: run `/passnote:enable` (only if the user wants this session to use passnote).
- `server said 401`: the server does not know this computer's token yet; send the hash line printed by `init` to
  whoever runs the server.
- `server unreachable` or a certificate error: check the URL, the server and its firewall, and that the certificate
  given to `init` is the server's current one.
