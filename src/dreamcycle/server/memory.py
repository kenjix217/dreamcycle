"""Identity-scoped memory resolution for the standalone sidecar."""

from __future__ import annotations

import threading
from dataclasses import replace
from typing import Protocol

from dreamcycle.memory.base import EmbeddingProvider, MemoryFilters
from dreamcycle.memory.postgres import PostgresMemory, PostgresMemoryConfig
from dreamcycle.server.auth import ClientIdentity
from dreamcycle.types import (
    DistanceMetric,
    KnowledgeEdge,
    KnowledgeNode,
    KnowledgeStats,
    MemoryRecord,
)


class MemoryClient(Protocol):
    def remember(self, content: str, **kwargs: object) -> MemoryRecord: ...

    def remember_turn(
        self, user_content: str, assistant_content: str, **kwargs: object
    ) -> tuple[MemoryRecord, MemoryRecord]: ...

    def recall(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: MemoryFilters | None = None,
        metric: DistanceMetric | None = None,
    ) -> list[MemoryRecord]: ...

    def mark_reviewed(self, memory_id: str, *, approved_for_training: bool = False) -> bool: ...

    def delete(self, memory_id: str) -> bool: ...

    def promote_to_l3(
        self,
        memory_ids: list[str] | tuple[str, ...],
        *,
        node_type: str,
        key: str,
        content: str,
        confidence: float = 1.0,
        metadata: dict[str, object] | None = None,
    ) -> KnowledgeNode: ...

    def recall_knowledge(
        self,
        query: str,
        *,
        limit: int = 10,
        node_type: str | None = None,
        metric: DistanceMetric | None = None,
    ) -> list[KnowledgeNode]: ...

    def neighbors(
        self, node_id: str, *, relation: str | None = None, limit: int = 50
    ) -> list[tuple[KnowledgeEdge, KnowledgeNode]]: ...

    def knowledge_stats(self) -> KnowledgeStats: ...


class MemoryResolver(Protocol):
    def resolve(self, identity: ClientIdentity) -> MemoryClient: ...


class PostgresMemoryResolver:
    """Create cached Postgres clients from an immutable authenticated identity."""

    def __init__(
        self,
        base_config: PostgresMemoryConfig,
        embeddings: EmbeddingProvider,
        *,
        setup_schema: bool = True,
    ) -> None:
        self._base_config = base_config
        self._embeddings = embeddings
        self._setup_schema = setup_schema
        self._schema_ready = False
        self._clients: dict[ClientIdentity, PostgresMemory] = {}
        self._lock = threading.Lock()

    def resolve(self, identity: ClientIdentity) -> PostgresMemory:
        with self._lock:
            existing = self._clients.get(identity)
            if existing is not None:
                return existing
            memory = PostgresMemory(
                replace(
                    self._base_config,
                    namespace=identity.namespace,
                    user_id=identity.user_id,
                ),
                self._embeddings,
            )
            if self._setup_schema and not self._schema_ready:
                memory.setup()
                self._schema_ready = True
            self._clients[identity] = memory
            return memory
