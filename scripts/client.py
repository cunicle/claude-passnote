#!/usr/bin/env python3
"""Passnote client shared by mcp_server.py and hook.py, plus a small command line. Standard library only.

Configuration (environment variables win over the local config file):
  PASSNOTE_URL, PASSNOTE_TOKEN  server address (https://host:port) and your token
  PASSNOTE_CA                   certificate to trust for https (default: ca.pem in PASSNOTE_HOME if it exists, else the
                                system's trusted certificates)
  PASSNOTE_HOME                 local directory, default ~/.config/claude-passnote; holds config.json ({"url", "token",
                                "ca"}, written by `init`), ca.pem, the list of enabled sessions and the hooks'
                                per-session state. It is outside the plugin, so updating or uninstalling the plugin
                                keeps it.
Opt-in: passnote is active only in sessions that turned it on, so other conversations see no tools, get no hook output
and make no network calls:
  PASSNOTE_ENABLE=1             in the environment of that session (a shell or preset that sets it), or
  python3 client.py enable      adds the current session (--session, else CLAUDE_CODE_SESSION_ID) to
                                PASSNOTE_HOME/sessions; the /passnote:enable command does this
  PASSNOTE_ENABLE=0             forces it off.

usage: python3 client.py {init,enable,disable,status,inbox,send,ack} ...
  init --name NAME --url URL [--ca CERT]
                                create your token locally (saved in config.json, never printed) and print the line for
                                the server's tokens.json (only the token's SHA-256, which is not secret); --ca copies the
                                server's self-signed certificate to PASSNOTE_HOME/ca.pem
"""
import argparse
import json
import os
import shutil
import ssl
import sys
import urllib.error
import urllib.request

TYPES = ("info", "request", "interface_change", "claim", "done")


class PassnoteError(Exception):
    pass


def home():
    return os.environ.get("PASSNOTE_HOME") or os.path.join(os.path.expanduser("~"), ".config", "claude-passnote")


def config():
    """-> {"url", "token", "ca"} (url and token may be empty when not configured, ca when the system store is used)."""
    c = {}
    try:
        with open(os.path.join(home(), "config.json"), encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        pass
    url = (os.environ.get("PASSNOTE_URL") or c.get("url") or "").rstrip("/")
    token = os.environ.get("PASSNOTE_TOKEN") or c.get("token") or ""
    ca = os.environ.get("PASSNOTE_CA") or c.get("ca") or ""
    if not ca and os.path.exists(os.path.join(home(), "ca.pem")):
        ca = os.path.join(home(), "ca.pem")
    return {"url": url, "token": token, "ca": ca}


def session_id(given=None):
    # a command template whose ${...} was not substituted must not become a session id
    if given and "${" not in given:
        return given
    return os.environ.get("CLAUDE_CODE_SESSION_ID", "")


def enabled_sessions():
    try:
        with open(os.path.join(home(), "sessions"), encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    except OSError:
        return set()


def enabled(sid=None):
    flag = os.environ.get("PASSNOTE_ENABLE", "")
    if flag in ("0", "1"):
        return flag == "1"
    sid = session_id(sid)
    return bool(sid) and sid in enabled_sessions()


def configured():
    c = config()
    return bool(c["url"] and c["token"])


def call(method, path, payload=None, timeout=5.0):
    """One request to the server -> the decoded JSON. Raises PassnoteError (not configured, unreachable, rejected)."""
    c = config()
    if not (c["url"] and c["token"]):
        raise PassnoteError("passnote is not configured: run /passnote:init (or set PASSNOTE_URL and PASSNOTE_TOKEN)")
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(c["url"] + path, data=data, method=method,
                                 headers={"Authorization": "Bearer " + c["token"], "Content-Type": "application/json"})
    ctx = None
    if c["url"].startswith("https://"):
        if c["ca"] and not os.path.exists(c["ca"]):
            raise PassnoteError(f"certificate file not found: {c['ca']}")
        try:
            ctx = ssl.create_default_context(cafile=c["ca"] or None)
        except ssl.SSLError as e:
            raise PassnoteError(f"cannot load the certificate {c['ca']}: {e}") from None
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("error", "")
        except (ValueError, OSError):
            msg = ""
        raise PassnoteError(f"server said {e.code}: {msg}") from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise PassnoteError(f"server unreachable: {e}") from None


def send(to, type, body, refs=(), needs_reply=False, reply_to=None, timeout=5.0):
    p = {"to": to, "type": type, "body": body, "refs": list(refs), "needs_reply": bool(needs_reply)}
    if reply_to is not None:
        p["reply_to"] = int(reply_to)
    return call("POST", "/send", p, timeout)


def inbox(include_acked=False, limit=50, timeout=5.0):
    return call("GET", f"/inbox?include_acked={int(bool(include_acked))}&limit={int(limit)}", timeout=timeout)["messages"]


def ack(ids, timeout=5.0):
    return call("POST", "/ack", {"ids": [int(i) for i in ids]}, timeout)["acked"]


def _set_session(sid, on):
    os.makedirs(home(), exist_ok=True)
    s = enabled_sessions()
    s = (s | {sid}) if on else (s - {sid})
    tmp = os.path.join(home(), "sessions.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("".join(x + "\n" for x in sorted(s)))
    os.replace(tmp, os.path.join(home(), "sessions"))


def init(name, url, ca=""):
    """Create your token locally: saved in PASSNOTE_HOME/config.json (never printed); returns the tokens.json line with
    its SHA-256, which is all the server needs (the hash is not secret). ca: the server's certificate, copied to
    PASSNOTE_HOME/ca.pem."""
    import hashlib
    import secrets
    os.makedirs(home(), exist_ok=True)
    path = os.path.join(home(), "config.json")
    try:
        with open(path, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    if url:
        c["url"] = url.rstrip("/")
    if ca:
        shutil.copyfile(ca, os.path.join(home(), "ca.pem"))
        c.pop("ca", None)                       # ca.pem in PASSNOTE_HOME is the default
    if not c.get("token"):
        c["token"] = secrets.token_urlsafe(32)
    fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(c, f)
    os.replace(path + ".tmp", path)
    return path, f'"{name}": "{hashlib.sha256(c["token"].encode()).hexdigest()}"'


def main():
    p = argparse.ArgumentParser(description="passnote client (see README.md)")
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("init", help="create your token locally and print the line for the server's tokens.json")
    q.add_argument("--name", required=True, help="your mailbox name, as the others will address you")
    q.add_argument("--url", default="", help="server address, e.g. https://203.0.113.5:8765")
    q.add_argument("--ca", default="", help="the server's self-signed certificate (not needed for a CA-signed one)")
    for name in ("enable", "disable", "status"):
        q = sub.add_parser(name)
        q.add_argument("--session", default="", help="session id (default: $CLAUDE_CODE_SESSION_ID)")
    q = sub.add_parser("inbox")
    q.add_argument("--all", action="store_true", help="include acked messages")
    q = sub.add_parser("send")
    q.add_argument("--to", required=True)
    q.add_argument("--type", required=True, choices=TYPES)
    q.add_argument("--body", required=True)
    q.add_argument("--refs", nargs="*", default=[])
    q.add_argument("--needs_reply", action="store_true")
    q.add_argument("--reply_to", type=int)
    q = sub.add_parser("ack")
    q.add_argument("ids", type=int, nargs="+")
    a = p.parse_args()
    out = sys.stdout.buffer
    try:
        if a.cmd == "init":
            path, line = init(a.name, a.url, a.ca)
            print(f"token saved in {path} (keep it there; PASSNOTE_TOKEN, if set, overrides it)\n"
                  f"line for the server's tokens.json (not secret, send it to whoever runs the server):\n{line}")
        elif a.cmd in ("enable", "disable"):
            sid = session_id(a.session)
            if not sid:
                sys.exit("no session id: run this inside a Claude Code session or pass --session")
            _set_session(sid, a.cmd == "enable")
            print(f"passnote {a.cmd}d for session {sid} ({os.path.join(home(), 'sessions')}); the hooks take effect at "
                  f"once, the MCP tools {'appear' if a.cmd == 'enable' else 'go away'} after the session restarts (in a "
                  f"terminal: /exit, then `claude --resume {sid}`; --continue resumes the latest session of the current "
                  "directory, which may be another one)")
        elif a.cmd == "status":
            c, sid = config(), session_id(a.session)
            print(f"session {sid or '-'}: enabled {enabled(sid)}, configured {configured()}\n"
                  f"url {c['url'] or '-'}, certificate {c['ca'] or 'system store'}, home {home()}")
            if configured():
                print("server:", call("GET", "/health"))
        elif a.cmd == "inbox":
            out.write((json.dumps(inbox(a.all), ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
        elif a.cmd == "send":
            print(json.dumps(send(a.to, a.type, a.body, a.refs, a.needs_reply, a.reply_to)))
        else:
            print(json.dumps({"acked": ack(a.ids)}))
    except PassnoteError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
