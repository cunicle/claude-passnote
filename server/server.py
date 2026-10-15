#!/usr/bin/env python3
"""Passnote server: a small HTTP(S) + SQLite message service for Claude Code agents on different computers.
Standard library only. Deployment and client setup: README.md.

usage:
  python3 server.py serve --db passnote.db --tokens tokens.json --bind 0.0.0.0:8765 [--cert cert.pem --key key.pem]
  python3 server.py gen-token NAME     new token for NAME (give it to that person) and the line for tokens.json;
                                       usually each person runs /passnote:init instead and sends only that line

tokens.json maps each name to the SHA-256 of that person's token ({"alice": "<hex>", "bob": "<hex>"}); the server never
stores tokens. The sender of a message is the owner of the token, so nobody can send in someone else's name. Restart the
server after changing tokens.json.

API (JSON; every call except /health needs "Authorization: Bearer <token>"):
  GET  /health                                         -> {"ok": true}
  POST /send   {to, type, body, refs?, needs_reply?, reply_to?}
                                                       -> {"id", "created_at"}
  GET  /inbox?include_acked=0&limit=50                 -> {"messages": [...]}  addressed to the caller, oldest first
  POST /ack    {"ids": [...]}                          -> {"acked": n}         only messages addressed to the caller
A message: {id, from, to, type, body, refs, needs_reply, reply_to, created_at, acked, acked_at}; type is one of
info / request / interface_change / claim / done; body at most MAX_BODY characters (details go into a file the
message refers to).
"""
import argparse
import hashlib
import hmac
import json
import secrets
import sqlite3
import ssl
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TYPES = ("info", "request", "interface_change", "claim", "done")
MAX_BODY = 1000             # characters
MAX_REFS, MAX_REF = 10, 200
MAX_REQUEST = 16 * 1024     # bytes
SEND_PER_HOUR = 120         # per sender

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sender TEXT NOT NULL,
  recipient TEXT NOT NULL,
  type TEXT NOT NULL,
  body TEXT NOT NULL,
  refs TEXT NOT NULL DEFAULT '[]',
  needs_reply INTEGER NOT NULL DEFAULT 0,
  reply_to INTEGER,
  created_at TEXT NOT NULL,
  acked_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_inbox ON messages (recipient, acked_at, id);
"""


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Store:
    """One SQLite connection behind a lock (traffic is a few requests a minute)."""

    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    @staticmethod
    def public(r):
        return {"id": r["id"], "from": r["sender"], "to": r["recipient"], "type": r["type"], "body": r["body"],
                "refs": json.loads(r["refs"]), "needs_reply": bool(r["needs_reply"]), "reply_to": r["reply_to"],
                "created_at": r["created_at"], "acked": r["acked_at"] is not None, "acked_at": r["acked_at"]}

    def send(self, sender, to, typ, body, refs, needs_reply, reply_to):
        with self.lock, self.db:
            if reply_to is not None:
                r = self.db.execute("SELECT sender, recipient FROM messages WHERE id = ?", (reply_to,)).fetchone()
                if r is None or sender not in (r["sender"], r["recipient"]):
                    raise ValueError("reply_to: no such message in your conversations")
            ts = now()
            cur = self.db.execute(
                "INSERT INTO messages (sender, recipient, type, body, refs, needs_reply, reply_to, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (sender, to, typ, body, json.dumps(refs), int(needs_reply), reply_to, ts))
            return {"id": cur.lastrowid, "created_at": ts}

    def inbox(self, user, include_acked, limit):
        q = "SELECT * FROM messages WHERE recipient = ?" + ("" if include_acked else " AND acked_at IS NULL")
        with self.lock:
            rows = self.db.execute(q + " ORDER BY id DESC LIMIT ?", (user, limit)).fetchall()
        return [self.public(r) for r in reversed(rows)]

    def ack(self, user, ids):
        with self.lock, self.db:
            cur = self.db.execute(
                f"UPDATE messages SET acked_at = ? WHERE recipient = ? AND acked_at IS NULL AND id IN "
                f"({','.join('?' * len(ids))})", (now(), user, *ids))
            return cur.rowcount


class Handler(BaseHTTPRequestHandler):
    server_version = "passnote/1"
    timeout = 10                # per connection (also bounds the TLS handshake, which runs in the handler's thread)
    store = users = None        # set in serve()
    sent = {}                   # sender -> send timestamps of the last hour

    def log_message(self, fmt, *args):     # method, path and status only: never tokens or bodies
        sys.stderr.write(f"{now()} {self.address_string()} {fmt % args}\n")

    def reply(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def user(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        h = token_hash(auth[7:].strip())
        for name, want in self.users.items():
            if hmac.compare_digest(h, want):
                return name
        return None

    def payload(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_REQUEST:
            raise ValueError("request too large")
        obj = json.loads(self.rfile.read(n) or b"{}")
        if not isinstance(obj, dict):
            raise ValueError("expected a JSON object")
        return obj

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/health":
            return self.reply(200, {"ok": True})
        user = self.user()
        if user is None:
            return self.reply(401, {"error": "unauthorized"})
        if u.path != "/inbox":
            return self.reply(404, {"error": "not found"})
        q = parse_qs(u.query)
        try:
            limit = max(1, min(200, int(q.get("limit", ["50"])[0])))
        except ValueError:
            return self.reply(400, {"error": "limit must be an integer"})
        include_acked = q.get("include_acked", ["0"])[0] in ("1", "true")
        self.reply(200, {"user": user, "messages": self.store.inbox(user, include_acked, limit)})

    def do_POST(self):
        user = self.user()
        if user is None:
            return self.reply(401, {"error": "unauthorized"})
        try:
            p = self.payload()
            if self.path == "/send":
                return self.reply(200, self.send_message(user, p))
            if self.path == "/ack":
                ids = p.get("ids")
                if not isinstance(ids, list) or not ids or len(ids) > 200 or \
                        not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
                    raise ValueError("ids: a non-empty list of message ids")
                return self.reply(200, {"acked": self.store.ack(user, ids)})
            return self.reply(404, {"error": "not found"})
        except (ValueError, json.JSONDecodeError) as e:
            return self.reply(400, {"error": str(e)})

    def send_message(self, user, p):
        to, typ, body = p.get("to"), p.get("type"), p.get("body")
        refs, needs_reply, reply_to = p.get("refs", []), p.get("needs_reply", False), p.get("reply_to")
        if to not in self.users:
            raise ValueError(f"to: one of {sorted(self.users)}")
        if typ not in TYPES:
            raise ValueError(f"type: one of {list(TYPES)}")
        if not isinstance(body, str) or not body.strip() or len(body) > MAX_BODY:
            raise ValueError(f"body: non-empty text of at most {MAX_BODY} characters (put details into a file and "
                             "reference it in refs)")
        if not isinstance(refs, list) or len(refs) > MAX_REFS or \
                not all(isinstance(r, str) and 0 < len(r) <= MAX_REF for r in refs):
            raise ValueError(f"refs: a list of at most {MAX_REFS} strings (commit SHAs, file paths)")
        if not isinstance(needs_reply, bool):
            raise ValueError("needs_reply: true or false")
        if reply_to is not None and (not isinstance(reply_to, int) or isinstance(reply_to, bool)):
            raise ValueError("reply_to: a message id")
        t = time.time()
        recent = [s for s in self.sent.get(user, []) if t - s < 3600]
        if len(recent) >= SEND_PER_HOUR:
            raise ValueError("rate limit: too many messages in the last hour")
        self.sent[user] = recent + [t]
        return self.store.send(user, to, typ, body.strip(), refs, needs_reply, reply_to)


def serve(a):
    users = json.load(open(a.tokens, encoding="utf-8"))
    assert isinstance(users, dict) and users and all(len(v) == 64 for v in users.values()), \
        "tokens.json: {name: sha256 hex of the token}"
    Handler.store, Handler.users = Store(a.db), users
    host, port = a.bind.rsplit(":", 1)
    httpd = ThreadingHTTPServer((host, int(port)), Handler)
    scheme = "http"
    if a.cert:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(a.cert, a.key)
        # handshake on first read, in the connection's own thread: a client that connects and stays silent must not
        # block accept() for everybody else
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True, do_handshake_on_connect=False)
        scheme = "https"
    sys.stderr.write(f"{now()} passnote on {scheme}://{a.bind} for {sorted(users)}\n")
    httpd.serve_forever()


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--db", required=True)
    s.add_argument("--tokens", required=True)
    s.add_argument("--bind", default="127.0.0.1:8765")
    s.add_argument("--cert", default="")
    s.add_argument("--key", default="")
    g = sub.add_parser("gen-token")
    g.add_argument("name")
    a = p.parse_args()
    if a.cmd == "gen-token":
        tok = secrets.token_urlsafe(32)
        print(f"token for {a.name} (give it to them; it is not stored anywhere): {tok}")
        print(f'tokens.json entry: "{a.name}": "{token_hash(tok)}"')
    else:
        serve(a)


if __name__ == "__main__":
    main()
