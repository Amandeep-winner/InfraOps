"""Managed demo web service running on port 8081 with /health and /work endpoints."""

import argparse
import http.server
import json
import os
import socketserver
import sys
import time
from pathlib import Path

from infraops.common.config import get_settings


class DemoRequestHandler(http.server.BaseHTTPRequestHandler):
    """Handles health probes and synthetic work requests."""

    def log_message(self, format, *args):
        # Redirect request logs to configured logger
        sys.stderr.write(f"[demo_service] {self.address_string()} - {format % args}\n")

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = json.dumps({"status": "ok", "service": "demo-service", "time": time.time()})
            self.wfile.write(resp.encode("utf-8"))
        elif self.path == "/work":
            # Synthetic CPU burst
            start = time.time()
            total = sum(i * i for i in range(50000))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = json.dumps(
                {
                    "status": "completed",
                    "result": total,
                    "duration_ms": round((time.time() - start) * 1000, 2),
                }
            )
            self.wfile.write(resp.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def run_demo_service(port: int = 8081):
    """Start HTTP server writing PID to sandbox/run and logs to sandbox/logs."""
    settings = get_settings()
    sandbox = Path(settings.sandbox_dir).resolve()
    run_dir = sandbox / "run"
    log_dir = sandbox / "logs"
    run_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    pidfile = run_dir / "demo-service.pid"
    pidfile.write_text(str(os.getpid()), encoding="utf-8")

    server_address = ("127.0.0.1", port)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(server_address, DemoRequestHandler) as httpd:
        sys.stderr.write(f"[demo_service] Running on 127.0.0.1:{port} (PID: {os.getpid()})\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            pidfile.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Demo Managed Service")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--infraops-sim", action="store_true", help="Marker flag")
    args = parser.parse_args()

    # Enforce simulation marker
    os.environ["INFRAOPS_SIM"] = "1"
    run_demo_service(port=args.port)


if __name__ == "__main__":
    main()
