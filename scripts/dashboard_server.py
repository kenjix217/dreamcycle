#!/usr/bin/env python3
"""Serve the packaged DreamCycle dashboard and proxy sidecar API calls."""

from __future__ import annotations

import argparse
import http.server
import json
import mimetypes
import urllib.error
import urllib.request
from pathlib import Path
from socketserver import ThreadingTCPServer


class DashboardRequestHandler(http.server.BaseHTTPRequestHandler):
    dashboard_dir: Path
    api_url: str

    def do_GET(self) -> None:
        if self.path.startswith("/dreamcycle-api/") or self.path == "/dreamcycle-api":
            self._proxy()
            return
        self._serve_static()

    def do_POST(self) -> None:
        self._proxy()

    def do_DELETE(self) -> None:
        self._proxy()

    def log_message(self, format: str, *args: object) -> None:
        print(f"[dreamcycle-dashboard] {self.address_string()} - {format % args}")

    def _serve_static(self) -> None:
        relative = self.path.split("?", 1)[0].lstrip("/")
        path = (
            (self.dashboard_dir / relative).resolve()
            if relative
            else self.dashboard_dir / "index.html"
        )
        root = self.dashboard_dir.resolve()
        if not str(path).startswith(str(root)) or not path.is_file():
            path = root / "index.html"
        content = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _proxy(self) -> None:
        if not self.path.startswith("/dreamcycle-api"):
            self._json_error(404, "unknown dashboard route")
            return
        upstream_path = self.path.replace("/dreamcycle-api", "", 1) or "/"
        url = f"{self.api_url.rstrip('/')}{upstream_path}"
        body = self.rfile.read(int(self.headers.get("Content-Length") or "0"))
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "content-length", "connection"}
        }
        request = urllib.request.Request(
            url,
            data=body or None,
            method=self.command,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                response_body = response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() not in {"transfer-encoding", "connection"}:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)
        except urllib.error.HTTPError as exc:
            response_body = exc.read()
            self.send_response(exc.code)
            content_type = exc.headers.get("Content-Type") or "application/json"
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)
        except OSError as exc:
            self._json_error(502, f"DreamCycle sidecar is unavailable: {exc}")

    def _json_error(self, status: int, detail: str) -> None:
        body = json.dumps({"detail": detail}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the packaged DreamCycle dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--api-url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--dashboard-dir",
        default=str(Path(__file__).resolve().parent / "dist"),
        help="built dashboard directory",
    )
    args = parser.parse_args()

    dashboard_dir = Path(args.dashboard_dir).expanduser().resolve()
    if not (dashboard_dir / "index.html").is_file():
        raise SystemExit(f"dashboard build is missing: {dashboard_dir}")

    class Handler(DashboardRequestHandler):
        pass

    Handler.dashboard_dir = dashboard_dir
    Handler.api_url = args.api_url
    with ThreadingTCPServer((args.host, args.port), Handler) as server:
        print(f"DreamCycle dashboard: http://{args.host}:{args.port}")
        print(f"Proxying /dreamcycle-api to {args.api_url}")
        server.serve_forever()


if __name__ == "__main__":
    main()
