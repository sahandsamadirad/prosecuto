#!/usr/bin/env python3
"""Minimal deploy webhook for laptop (Windows/Linux).

Listens for POST /deploy with Authorization: Bearer <DEPLOY_WEBHOOK_SECRET>,
then runs the platform deploy script.

Usage (laptop):
  export DEPLOY_WEBHOOK_SECRET=your-secret
  python3 deploy/webhook/server.py --port 9876

Usage (GX10 triggers laptop after backend deploy):
  DEPLOY_WEBHOOK_SECRET=your-secret ./deploy/gx10/deploy.sh
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import platform
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


SECRET = os.environ.get("DEPLOY_WEBHOOK_SECRET", "")
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))


def run_deploy() -> tuple[int, str]:
    system = platform.system()
    if system == "Windows":
        script = os.path.join(REPO_ROOT, "deploy", "laptop", "deploy.ps1")
        cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", script]
    else:
        script = os.path.join(REPO_ROOT, "deploy", "laptop", "deploy.sh")
        cmd = ["bash", script]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _auth_ok(self) -> bool:
        if not SECRET:
            return False
        auth = self.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        return hmac.compare_digest(token, SECRET)

    def do_POST(self) -> None:
        if self.path != "/deploy":
            self.send_error(404)
            return
        if not self._auth_ok():
            self.send_error(401)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        code, output = run_deploy()
        payload = json.dumps({"ok": code == 0, "exit_code": code, "output": output[-4000:]}).encode()
        self.send_response(200 if code == 0 else 500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/health":
            payload = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_error(404)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9876)
    args = parser.parse_args()
    if not SECRET:
        print("Set DEPLOY_WEBHOOK_SECRET before starting.", file=sys.stderr)
        sys.exit(1)
    server = HTTPServer((args.host, args.port), Handler)
    print(f"Deploy webhook listening on {args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
