"""Demo upstream TCP listener dependency running on port 8082."""

import argparse
import os
import socket
import sys
import threading
from pathlib import Path

from infraops.common.config import get_settings


def handle_client(conn, addr):
    try:
        data = conn.recv(1024)
        if data:
            conn.sendall(b"PONG: " + data)
    except Exception:
        pass
    finally:
        conn.close()


def run_upstream(port: int = 8082):
    settings = get_settings()
    sandbox = Path(settings.sandbox_dir).resolve()
    run_dir = sandbox / "run"
    run_dir.mkdir(parents=True, exist_ok=True)

    pidfile = run_dir / "demo-upstream.pid"
    pidfile.write_text(str(os.getpid()), encoding="utf-8")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(5)
    sys.stderr.write(f"[demo_upstream] Listening on 127.0.0.1:{port} (PID: {os.getpid()})\n")

    try:
        while True:
            conn, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        pidfile.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Demo Upstream TCP Service")
    parser.add_argument("--port", type=int, default=8082)
    parser.add_argument("--infraops-sim", action="store_true", help="Marker flag")
    args = parser.parse_args()

    os.environ["INFRAOPS_SIM"] = "1"
    run_upstream(port=args.port)


if __name__ == "__main__":
    main()
