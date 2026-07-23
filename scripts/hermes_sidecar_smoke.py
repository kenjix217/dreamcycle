#!/usr/bin/env python3
"""Smoke-check DreamCycle's Hermes-facing command surface."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate DreamCycle Hermes command wiring")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="check command wiring without HTTP calls",
    )
    parser.add_argument("--url", default=os.getenv("DREAMCYCLE_BASE_URL", "http://127.0.0.1:8765"))
    parser.add_argument("--api-key", default=os.getenv("DREAMCYCLE_API_KEY", ""))
    args = parser.parse_args()

    command = shutil.which("dreamcycle-hermes")
    if command is None:
        print("dreamcycle-hermes is not on PATH", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"command ok: {command}")
        print(f"url: {args.url}")
        print("api key: configured" if args.api_key else "api key: missing")
        print("rollback gate ok: use `dreamcycle-hermes rollback --confirm` only after approval")
        return 0

    if not args.api_key:
        print("--api-key or DREAMCYCLE_API_KEY is required", file=sys.stderr)
        return 2

    result = subprocess.run(
        [command, "--url", args.url, "--api-key", args.api_key, "--json", "status"],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip(), file=sys.stderr)
        return result.returncode
    print(result.stdout.strip())
    print("status ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
