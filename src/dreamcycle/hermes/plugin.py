"""Importable hooks for Hermes-style chat tools.

These helpers intentionally wrap the same command facade as the CLI. A Hermes
plugin can ask the user for confirmation in chat, then call rollback(confirm=True).
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from dreamcycle.hermes.commands import HermesDreamCycleCommands
from dreamcycle.sdk import DreamCycleClient


def status(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float = 30.0,
) -> Mapping[str, object]:
    with _client(base_url=base_url, api_key=api_key, timeout=timeout) as client:
        return HermesDreamCycleCommands(client).status().to_dict()


def rollback(
    *,
    confirm: bool = False,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float = 30.0,
) -> Mapping[str, object]:
    with _client(base_url=base_url, api_key=api_key, timeout=timeout) as client:
        return HermesDreamCycleCommands(client).rollback(confirm=confirm).to_dict()


def _client(
    *,
    base_url: str | None,
    api_key: str | None,
    timeout: float,
) -> DreamCycleClient:
    return DreamCycleClient(
        base_url or os.getenv("DREAMCYCLE_BASE_URL", "http://127.0.0.1:8765"),
        api_key or os.getenv("DREAMCYCLE_API_KEY", ""),
        timeout=timeout,
    )
