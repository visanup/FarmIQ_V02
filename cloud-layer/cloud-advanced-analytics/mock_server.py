"""Lightweight local development stand-in for Cloud Advanced Analytics."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json


class MockAnalyticsHandler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/api/health", "/health"):
            self._send_json(200, {"status": "ok", "service": "cloud-advanced-analytics", "mode": "mock"})
        else:
            self._send_json(200, {"service": "cloud-advanced-analytics", "mode": "mock", "message": "Analytics calculations are disabled for local development."})

    def do_POST(self):
        self._send_json(200, {"service": "cloud-advanced-analytics", "mode": "mock", "result": []})

    def log_message(self, *_args):
        pass


ThreadingHTTPServer(("0.0.0.0", 8000), MockAnalyticsHandler).serve_forever()
