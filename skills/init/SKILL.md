---
name: init
description: Set up passnote on this computer - create your token locally and print the line the server admin needs
argument-hint: <your-name> <server-url> [server-cert.pem]
disable-model-invocation: true
---

Set up the passnote client on this computer. Arguments: `$ARGUMENTS`. They are: the user's passnote name (how the
other agents will address them), the server URL such as `https://203.0.113.5:8765`, and optionally the path of the
server's self-signed certificate. If the name or the URL is missing, ask the user for it before running anything.

Run this (if `python3` is not found, use `python`, or `py` on Windows), leaving out `--ca` when no certificate was given:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/client.py" init --name "<name>" --url "<url>" --ca "<cert.pem>"
```

- The token is created and kept only in the local config file. Never print, read or send the token itself.
- Show the user the last line of the output, `"<name>": "<sha256>"`, and tell them to send it to whoever runs the
  server, who adds it to the server's `tokens.json` and restarts the server. The hash is not secret.
- Running it again keeps the existing token and only updates the URL or certificate.
- Then tell the user how to start: `/passnote:enable` in the session that should use passnote, and `/passnote:status`
  to check the connection once the server knows their hash.
