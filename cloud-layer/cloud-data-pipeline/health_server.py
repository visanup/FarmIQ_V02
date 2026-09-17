import json
import os
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class HealthRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/api/health", "/health"):
            payload = {
                "status": "ok",
                "service": "cloud-data-pipeline",
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        super().do_GET()

    def log_message(self, format, *args):
        # Keep container logs compact while still serving files/health checks.
        print("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), format % args))


def main():
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthRequestHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
