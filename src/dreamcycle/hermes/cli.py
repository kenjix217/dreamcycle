"""Command-line wrapper for Hermes-style DreamCycle operator controls."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager

from dreamcycle.hermes.commands import (
    DreamCycleCommandClient,
    HermesCommandResult,
    HermesDreamCycleCommands,
    RollbackConfirmationRequired,
)

ClientFactory = Callable[[str, str, float], AbstractContextManager[DreamCycleCommandClient]]


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: ClientFactory | None = None,
) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    base_url = args.url or os.getenv("DREAMCYCLE_BASE_URL", "http://127.0.0.1:8765")
    api_key = args.api_key or os.getenv("DREAMCYCLE_API_KEY", "")
    if not api_key:
        parser.error("--api-key or DREAMCYCLE_API_KEY is required")
    if client_factory is None:
        client_factory = _client_factory
    try:
        with client_factory(base_url, api_key, args.timeout) as client:
            commands = HermesDreamCycleCommands(client)
            if args.command == "status":
                result = commands.status()
            elif args.command == "rollback":
                result = commands.rollback(confirm=args.confirm)
            else:  # pragma: no cover - argparse prevents this path
                parser.error(f"unknown command: {args.command}")
    except RollbackConfirmationRequired as exc:
        result = HermesCommandResult(
            command="rollback",
            ok=False,
            available=False,
            confirmation_required=True,
            message=str(exc),
        )
        _emit(result, as_json=args.json, stream=sys.stderr)
        return 2
    except Exception as exc:
        if exc.__class__.__name__ == "DreamCycleSDKError":
            message = str(exc)
        else:
            message = f"DreamCycle Hermes command failed: {exc}"
        result = HermesCommandResult(
            command=args.command,
            ok=False,
            available=False,
            message=message,
        )
        _emit(result, as_json=args.json, stream=sys.stderr)
        return 1

    _emit(result, as_json=args.json, stream=sys.stdout)
    if result.command == "rollback" and not result.ok:
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dreamcycle-hermes",
        description="Hermes-compatible DreamCycle adapter controls",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="DreamCycle sidecar URL (default: DREAMCYCLE_BASE_URL or http://127.0.0.1:8765)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="DreamCycle sidecar API key (default: DREAMCYCLE_API_KEY)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("DREAMCYCLE_COMMAND_TIMEOUT", "30")),
        help="request timeout in seconds (default: 30)",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("status", help="show active adapter state")
    rollback = subcommands.add_parser("rollback", help="restore the previous promoted adapter")
    rollback.add_argument(
        "--confirm",
        action="store_true",
        help="required after an operator explicitly confirms rollback",
    )
    return parser


def _client_factory(
    base_url: str,
    api_key: str,
    timeout: float,
) -> AbstractContextManager[DreamCycleCommandClient]:
    from dreamcycle.sdk import DreamCycleClient

    return DreamCycleClient(base_url, api_key, timeout=timeout)


def _emit(
    result: HermesCommandResult,
    *,
    as_json: bool,
    stream: object,
) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), sort_keys=True), file=stream)
    else:
        print(result.message, file=stream)


if __name__ == "__main__":
    raise SystemExit(main())
