"""Jarvis HUD server: serves the UI, streams replies from the shared brain, and runs the scheduler.

Security: the server holds access to your mail, messages and files, so it refuses requests that did not come from
your own browser session. It checks (1) the Host header (stops DNS-rebinding), (2) the Origin header (stops other
websites posting to it) and (3) a secret access key stored in a cookie. Get the one-time login URL with:
    .venv/bin/python server.py --print-url
"""
import hmac
import json
import os
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import brain
import config
import notify
import scheduler

PORT = int(os.environ.get("JARVIS_PORT", "8765"))
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "static")
KEY_PATH = os.path.join(HERE, ".access_key")
COOKIE = "jarvis_key"


def access_key() -> str:
    try:
        with open(KEY_PATH) as f:
            key = f.read().strip()
        if key:
            return key
    except FileNotFoundError:
        pass
    key = secrets.token_urlsafe(32)
    fd = os.open(KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key)
    return key


KEY = access_key()


def allowed_hosts() -> set[str]:
    extra = config.load().get("allowed_hosts", [])  # e.g. your Tailscale name: "mac.tail1234.ts.net"
    return {f"127.0.0.1:{PORT}", f"localhost:{PORT}", f"[::1]:{PORT}", *extra, *(f"{h}:{PORT}" for h in extra)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    # ---- request checks -----------------------------------------------------------------
    def _host_ok(self) -> bool:
        return (self.headers.get("Host") or "") in allowed_hosts()

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = urlparse(origin).netloc
        return host in allowed_hosts()

    def _cookie_key(self) -> str:
        for part in (self.headers.get("Cookie") or "").split(";"):
            name, _, val = part.strip().partition("=")
            if name == COOKIE:
                return val
        return ""

    def _authed(self) -> bool:
        return hmac.compare_digest(self._cookie_key(), KEY)

    def _reply(self, code: int, body: bytes, ctype: str = "text/plain; charset=utf-8", headers: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _guard(self) -> bool:
        """True if the request may proceed; otherwise sends the refusal."""
        if not self._host_ok() or not self._origin_ok():
            self._reply(403, b"Forbidden")
            return False
        return True

    # ---- routes -------------------------------------------------------------------------
    def do_GET(self):
        if not self._guard():
            return
        url = urlparse(self.path)
        if url.path == "/" and "key" in parse_qs(url.query):
            given = parse_qs(url.query)["key"][0]
            if hmac.compare_digest(given, KEY):
                secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
                self._reply(303, b"", headers={
                    "Location": "/", "Set-Cookie": f"{COOKIE}={KEY}; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000{secure}"})
                return
        if not self._authed():
            self._reply(401, b"Jarvis: not signed in. Run 'python server.py --print-url' on the Mac and open that link once.")
            return
        if url.path in ("/", "/index.html"):
            with open(os.path.join(ROOT, "index.html"), "rb") as f:
                self._reply(200, f.read(), "text/html; charset=utf-8")
        elif url.path == "/events":
            since = int(parse_qs(url.query).get("since", ["0"])[0] or 0)
            self._reply(200, json.dumps(notify.events_since(since)).encode(), "application/json")
        else:
            self._reply(404, b"Not found")

    def do_POST(self):
        if not self._guard():
            return
        if not self._authed():
            self._reply(401, b"Not signed in")
            return
        if self.path != "/chat" or "application/json" not in (self.headers.get("Content-Type") or ""):
            self._reply(404, b"Not found")
            return
        try:
            length = min(int(self.headers.get("Content-Length", 0)), 200_000)
            payload = json.loads(self.rfile.read(length))
            messages = [m for m in payload["messages"][-20:] if m.get("role") in ("user", "assistant")]
            lang = str(payload.get("lang", "en"))[:5]
        except (ValueError, KeyError, TypeError):
            self._reply(400, b"Bad request")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            for kind, val in brain.stream_reply(messages, lang):
                key = "t" if kind == "text" else "error"
                self.wfile.write((json.dumps({key: val}) + "\n").encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return


if __name__ == "__main__":
    if "--print-url" in sys.argv:
        print(f"http://127.0.0.1:{PORT}/?key={KEY}")
        sys.exit(0)
    scheduler.start()
    print(f"Jarvis HUD on http://127.0.0.1:{PORT} (model {brain.MODEL})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
