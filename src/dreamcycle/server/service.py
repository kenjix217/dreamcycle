"""Transport-independent operations shared by the sidecar and proxy."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dreamcycle.memory.base import MemoryFilters
from dreamcycle.server.auth import ClientIdentity
from dreamcycle.server.memory import MemoryResolver
from dreamcycle.types import DistanceMetric, MemoryRecord


class DreamCycleService:
    def __init__(self, memories: MemoryResolver) -> None:
        self.memories = memories

    def record(
        self,
        identity: ClientIdentity,
        content: str,
        *,
        role: str = "event",
        source: str = "vendor-sdk",
        conversation_id: str = "",
        trace_id: str = "",
        importance: float = 0.5,
        success: bool = True,
        data_classification: str = "public",
        metadata: Mapping[str, Any] | None = None,
    ) -> MemoryRecord:
        return self.memories.resolve(identity).remember(
            content,
            role=role,
            source=source,
            conversation_id=conversation_id,
            trace_id=trace_id,
            importance=importance,
            success=success,
            reviewed=False,
            approved_for_training=False,
            data_classification=data_classification,
            metadata=metadata,
        )

    def record_turn(
        self,
        identity: ClientIdentity,
        user_content: str,
        assistant_content: str,
        *,
        source: str = "vendor-sdk",
        conversation_id: str = "",
        trace_id: str = "",
        importance: float = 0.5,
        success: bool = True,
        data_classification: str = "public",
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[MemoryRecord, MemoryRecord]:
        return self.memories.resolve(identity).remember_turn(
            user_content,
            assistant_content,
            source=source,
            conversation_id=conversation_id,
            trace_id=trace_id,
            importance=importance,
            success=success,
            data_classification=data_classification,
            user_metadata=metadata,
            assistant_metadata=metadata,
        )

    def search(
        self,
        identity: ClientIdentity,
        query: str,
        *,
        limit: int = 10,
        filters: MemoryFilters | None = None,
        metric: DistanceMetric | None = None,
    ) -> list[MemoryRecord]:
        return self.memories.resolve(identity).recall(
            query,
            limit=limit,
            filters=filters,
            metric=metric,
        )

    def review(
        self,
        identity: ClientIdentity,
        memory_id: str,
        *,
        approved_for_training: bool,
    ) -> bool:
        return self.memories.resolve(identity).mark_reviewed(
            memory_id,
            approved_for_training=approved_for_training,
        )

    def delete(self, identity: ClientIdentity, memory_id: str) -> bool:
        return self.memories.resolve(identity).delete(memory_id)
