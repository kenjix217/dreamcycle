"""Hermes-compatible adapter control commands.

The backend owns adapter state. This module keeps the agent-facing command
surface small, explicit, and safe to wrap from chat tools.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from dreamcycle.sdk.models import AdapterState
else:
    AdapterState = Any


class RollbackConfirmationRequired(Exception):
    """Raised when rollback is requested without explicit operator confirmation."""


class DreamCycleCommandClient(Protocol):
    def active_adapter(self) -> AdapterState: ...

    def rollback_adapter(self) -> AdapterState: ...


@dataclass(frozen=True)
class HermesCommandResult:
    command: Literal["status", "rollback"]
    ok: bool
    available: bool
    message: str
    active_path: str | None = None
    previous_path: str | None = None
    accepted: bool | None = None
    reason: str | None = None
    confirmation_required: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class HermesDreamCycleCommands:
    """Small command facade that Hermes or another agent shell can wrap."""

    def __init__(self, client: DreamCycleCommandClient) -> None:
        self._client = client

    def status(self) -> HermesCommandResult:
        state = self._client.active_adapter()
        if not state.available:
            return HermesCommandResult(
                command="status",
                ok=True,
                available=False,
                active_path=None,
                message="DreamCycle adapter management is not configured.",
            )
        if state.active_path:
            message = f"Active DreamCycle adapter: {state.active_path}"
        else:
            message = "DreamCycle adapter management is configured, but no adapter is active."
        return HermesCommandResult(
            command="status",
            ok=True,
            available=True,
            active_path=state.active_path,
            message=message,
        )

    def rollback(self, *, confirm: bool = False) -> HermesCommandResult:
        if not confirm:
            raise RollbackConfirmationRequired(
                "DreamCycle rollback requires explicit confirmation. "
                "Ask the operator first, then retry with confirm=True or --confirm."
            )
        state = self._client.rollback_adapter()
        accepted = bool(state.accepted)
        if accepted:
            message = f"DreamCycle rolled back to: {state.active_path or '(no active adapter)'}"
        else:
            message = state.reason or "DreamCycle rollback was rejected."
        return HermesCommandResult(
            command="rollback",
            ok=accepted,
            available=state.available,
            active_path=state.active_path,
            previous_path=state.previous_path,
            accepted=state.accepted,
            reason=state.reason,
            message=message,
        )
