---
name: status
description: Check passnote - whether this session has it on, which server it uses, whether the server answers, and who you are and whom you can send to there
---

Check passnote for this session. Run this (if `python3` is not found, use `python`, or `py` on Windows):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/client.py" status --session "${CLAUDE_SESSION_ID}"
```

Report the result in a few lines: whether passnote is on here, the server (`url`), and who the user is there and whom
they can send to (`you are ...; you can send to ...`). If something is missing, give the fix:

- `configured False`: run `/passnote:init <name> <server-url> [cert.pem]`.
- `enabled False`: run `/passnote:enable` (only if the user wants this session to use passnote).
- `server said 401`: the server does not know this computer's token yet. The user sends the line
  `"<name>": "<hash>"` that status printed to whoever runs the server, who adds it with
  `python3 server.py users add <name> <hash>`; no restart is needed. The line is not secret (it is the token's SHA-256).
- `the others are unknown`: the server runs passnote older than 0.2.0. Messages work; to list the others, whoever runs
  the server copies the new `server.py` over and restarts it once.
- `server unreachable` or a certificate error: check the URL, the server and its firewall, and that the certificate
  given to `init` is the server's current one. If the server moved, run `/passnote:init <name> <new-url> [new-cert.pem]`:
  the token stays the same.
