"""Standalone DreamCycle sidecar API with lazily loaded optional dependencies."""

from __future__ import annotations

from typing import Any

__all__ = [
    "APIKeyAuthenticator",
    "ChatCompletionsProxy",
    "ClientIdentity",
    "DreamCycleService",
    "ProxyConfig",
    "ProxyMode",
    "create_app",
]


def __getattr__(name: str) -> Any:
    if name == "create_app":
        from dreamcycle.server.app import create_app

        return create_app
    if name in {"APIKeyAuthenticator", "ClientIdentity"}:
        from dreamcycle.server.auth import APIKeyAuthenticator, ClientIdentity

        return {
            "APIKeyAuthenticator": APIKeyAuthenticator,
            "ClientIdentity": ClientIdentity,
        }[name]
    if name in {"ChatCompletionsProxy", "ProxyConfig", "ProxyMode"}:
        from dreamcycle.server.proxy import ChatCompletionsProxy, ProxyConfig, ProxyMode

        return {
            "ChatCompletionsProxy": ChatCompletionsProxy,
            "ProxyConfig": ProxyConfig,
            "ProxyMode": ProxyMode,
        }[name]
    if name == "DreamCycleService":
        from dreamcycle.server.service import DreamCycleService

        return DreamCycleService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
