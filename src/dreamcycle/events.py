"""Local event hooks for observing a Dream Cycle run."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from dreamcycle.types import utc_now


class EventType(str, Enum):
    CYCLE_STARTED = "dreamcycle.cycle.started"
    PHASE_STARTED = "dreamcycle.phase.started"
    PHASE_COMPLETED = "dreamcycle.phase.completed"
    QUALITY_GATE = "dreamcycle.quality_gate.completed"
    SHADOW_GATE = "dreamcycle.shadow_gate.completed"
    ADAPTER_PROMOTED = "dreamcycle.adapter.promoted"
    CYCLE_COMPLETED = "dreamcycle.cycle.completed"


@dataclass(frozen=True)
class DreamEvent:
    event_type: EventType
    session_id: str
    occurred_at: datetime = field(default_factory=utc_now)
    payload: Mapping[str, Any] = field(default_factory=dict)


EventSink = Callable[[DreamEvent], None | Awaitable[None]]


class EventDispatcher:
    def __init__(self, sinks: tuple[EventSink, ...] = ()) -> None:
        self._sinks = sinks

    async def emit(
        self,
        event_type: EventType,
        session_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> list[str]:
        event = DreamEvent(event_type=event_type, session_id=session_id, payload=payload or {})
        errors: list[str] = []
        for sink in self._sinks:
            try:
                result = sink(event)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # Event observers cannot alter gate truth.
                errors.append(f"{type(exc).__name__}: {exc}")
        return errors
