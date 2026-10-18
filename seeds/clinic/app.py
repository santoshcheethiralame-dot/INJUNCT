"""Bengaluru Dental - the front desk list. Standard library only."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import importlib

import store
import models.patient

HERE = Path(__file__).parent


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/patients"):
            try:
                m = importlib.reload(models.patient)   # the agent is editing this live
                con = store.build()
                body = json.dumps({"fields": m.FIELDS, "labels": m.LABELS,
                                   "rows": store.patients(con, m.FIELDS)}).encode()
                self._send(200, body, "application/json")
            except Exception as e:                                  # the trap surfaces here
                self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")
            return
        page = (HERE / "static" / "index.html").read_bytes()
        self._send(200, page, "text/html; charset=utf-8")


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8901
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
