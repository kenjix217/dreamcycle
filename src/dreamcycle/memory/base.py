"""Protocols and filters for standalone memory implementations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from dreamcycle.types import KnowledgeClaim, MemoryRecord


class EmbeddingProvider(Protocol):
    @property
    def dimension(self) -> int: ...

    @property
    def model_name(self) -> str: ...

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class KnowledgeExtractor(Protocol):
    def extract(self, memories: Sequence[MemoryRecord]) -> Sequence[KnowledgeClaim]: ...


@dataclass(frozen=True)
class MemoryFilters:
    role: str | None = None
    source: str | None = None
    successful_only: bool = False
    reviewed_only: bool = False
    minimum_importance: float = 0.0
    classifications: tuple[str, ...] = ()
