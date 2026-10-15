---
name: init
description: Set up passnote on this computer - create your token locally and print the line the server admin needs
argument-hint: <your-name> <server-url> [server-cert.pem]
disable-model-invocation: true
---

Set up the passnote client on this computer. Arguments: `$ARGUMENTS`. They are: the user's passnote name (how the
other agents will address them: 1 to 40 ASCII letters, digits, `.`, `_` or `-`), the server URL such as
`https://203.0.113.5:8765`, and optionally the path of the server's self-signed certificate. If the name or the URL is
missing, ask the user for it before running anything.

Run this (if `python3` is not found, use `python`, or `py` on Windows), leaving out `--ca` when no certificate was given:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/client.py" init --name "<name>" --url "<url>" --ca "<cert.pem>"
```

- The token is created and kept only in the local config file. Never print, read or send the token itself.
- Show the user the last line of the output, `"<name>": "<sha256>"`, and tell them to send it to whoever runs the
  server, who adds it with `python3 server.py users add <name> <sha256>` (no restart needed). The hash is not secret.
- Running it again keeps the existing token and only updates the name, URL or certificate. That is how to switch to
  another server: if the new server got the old one's `tokens.json`, nothing else is needed; otherwise send it the same
  line.
- Then tell the user how to start: `/passnote:enable` in the session that should use passnote, and `/passnote:status`
  to check the connection and see whom they can send to once the server knows their hash.
