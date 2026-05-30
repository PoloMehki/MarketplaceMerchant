"""Simple HTTP server: serves web/index.html + /api/spec + /api/run (SSE)."""
from __future__ import annotations
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).parent


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence access log

    def do_GET(self):
        if self.path == "/":
            self._serve_file(ROOT / "web" / "index.html", "text/html")
        elif self.path == "/api/spec":
            data = json.loads((ROOT / "demo.json").read_text())
            self._json(data)
        elif self.path == "/api/run":
            self._sse_run()
        else:
            self.send_error(404)

    def _serve_file(self, path: Path, ctype: str):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _sse_run(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        proc = subprocess.Popen(
            [sys.executable, "-m", "negagent.cli", "--spec", "demo.json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(ROOT),
        )
        try:
            for line in proc.stdout:
                payload = json.dumps({"line": line.rstrip()})
                self.wfile.write(f"data: {payload}\n\n".encode())
                self.wfile.flush()
            proc.wait()
            done = json.dumps({"done": True, "code": proc.returncode})
            self.wfile.write(f"data: {done}\n\n".encode())
            self.wfile.flush()
        except BrokenPipeError:
            proc.terminate()


if __name__ == "__main__":
    port = 8000
    print(f"Serving on http://localhost:{port}")
    HTTPServer(("", port), Handler).serve_forever()
