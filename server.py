"""Jarvis HUD server: serves the UI and streams replies from the shared brain."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import brain

PORT = int(os.environ.get("JARVIS_PORT", "8765"))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        with open(os.path.join(ROOT, "index.html"), "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/chat":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        messages = json.loads(self.rfile.read(length))["messages"][-20:]
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            for kind, val in brain.stream_reply(messages):
                key = "t" if kind == "text" else "error"
                self.wfile.write((json.dumps({key: val}) + "\n").encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return


if __name__ == "__main__":
    print(f"Jarvis HUD on http://127.0.0.1:{PORT} (model {brain.MODEL})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
