"""Local web server for the Energy Audit dashboard (standard library only).

Run:  python app.py            -> http://127.0.0.1:8000
      python app.py 0.0.0.0 8080   (to share on a company network)
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import energy_core as core

BASE = Path(__file__).parent
MAX_BODY = 1_000_000


class Handler(BaseHTTPRequestHandler):
    server_version = "EnergyAudit/1.0"

    def _send(self, code, body, ctype="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (BASE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/health":
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "Not found"})

    def do_POST(self):
        if self.path not in ("/api/calculate", "/api/export.csv"):
            return self._send(404, {"error": "Not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return self._send(400, {"error": "Bad Content-Length"})
        if length <= 0 or length > MAX_BODY:
            return self._send(400, {"error": "Request body missing or too large."})
        try:
            payload = json.loads(self.rfile.read(length))
            result = core.calculate_from_payload(payload)
        except json.JSONDecodeError:
            return self._send(400, {"error": "Request is not valid JSON."})
        except core.ValidationError as exc:
            return self._send(400, {"error": str(exc)})
        except Exception:  # never leak internals to the client
            return self._send(500, {"error": "Unexpected server error."})

        if self.path == "/api/calculate":
            self._send(200, result)
        else:
            org = str(payload.get("org", ""))[:100]
            self._send(200, core.to_csv(result, org), "text/csv; charset=utf-8",
                       {"Content-Disposition": 'attachment; filename="energy-report.csv"'})

    def log_message(self, fmt, *args):
        pass  # quiet; remove to log requests


def make_server(host="127.0.0.1", port=8000):
    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    print(f"Energy Audit running at http://{host}:{port}  (Ctrl+C to stop)")
    try:
        make_server(host, port).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
