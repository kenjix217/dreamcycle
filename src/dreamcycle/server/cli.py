"""Command-line entry point for the standalone sidecar."""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DreamCycle vendor sidecar")
    parser.add_argument(
        "--host",
        default=os.getenv("DREAMCYCLE_HOST", "127.0.0.1"),
        help="interface to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("DREAMCYCLE_PORT", "8765")),
        help="TCP port (default: 8765)",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("DREAMCYCLE_LOG_LEVEL", "info"),
        choices=("critical", "error", "warning", "info", "debug", "trace"),
    )
    args = parser.parse_args()
    try:
        import uvicorn

        from dreamcycle.errors import DreamCycleError
        from dreamcycle.server.runtime import create_app_from_env
    except ImportError as exc:  # pragma: no cover - exercised by core-only installation
        parser.error("dreamcycle-server requires 'pip install dreamcycle[server,embeddings]'")
        raise AssertionError from exc
    try:
        app = create_app_from_env()
    except DreamCycleError as exc:
        parser.error(str(exc))
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
