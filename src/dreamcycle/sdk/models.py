"""Dependency-light result models returned by the vendor SDK."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MemoryItem:
    id: str
    namespace: str
    user_id: str
    content: str
    role: str
    source: str
    conversation_id: str
    trace_id: str
    importance: float
    success: bool
    reviewed: bool
    approved_for_training: bool
    data_classification: str
    metadata: Mapping[str, Any]
    created_at: datetime
    updated_at: datetime
    distance: float | None = None
    similarity: float | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> MemoryItem:
        data = dict(value)
        data["created_at"] = _parse_datetime(data["created_at"])
        data["updated_at"] = _parse_datetime(data["updated_at"])
        return cls(**data)


@dataclass(frozen=True)
class KnowledgeItem:
    id: str
    namespace: str
    user_id: str
    node_type: str
    key: str
    content: str
    confidence: float
    metadata: Mapping[str, Any]
    created_at: datetime
    updated_at: datetime
    distance: float | None = None
    similarity: float | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> KnowledgeItem:
        data = dict(value)
        data["created_at"] = _parse_datetime(data["created_at"])
        data["updated_at"] = _parse_datetime(data["updated_at"])
        return cls(**data)


@dataclass(frozen=True)
class KnowledgeEdgeItem:
    id: str
    namespace: str
    user_id: str
    source_id: str
    target_id: str
    relation: str
    weight: float
    metadata: Mapping[str, Any]
    created_at: datetime

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> KnowledgeEdgeItem:
        data = dict(value)
        data["created_at"] = _parse_datetime(data["created_at"])
        return cls(**data)


@dataclass(frozen=True)
class KnowledgeNeighbor:
    edge: KnowledgeEdgeItem
    node: KnowledgeItem

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> KnowledgeNeighbor:
        return cls(
            edge=KnowledgeEdgeItem.from_dict(value["edge"]),
            node=KnowledgeItem.from_dict(value["node"]),
        )


@dataclass(frozen=True)
class KnowledgeStats:
    nodes: int
    edges: int
    provenance_links: int
    node_types: Mapping[str, int]


@dataclass(frozen=True)
class CycleJob:
    id: str
    status: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    report: Mapping[str, Any] | None
    error: str | None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> CycleJob:
        data = dict(value)
        for field in ("created_at", "started_at", "completed_at"):
            if data.get(field):
                data[field] = _parse_datetime(data[field])
        return cls(**data)


@dataclass(frozen=True)
class AdapterState:
    available: bool
    active_path: str | None
    accepted: bool | None = None
    reason: str | None = None
    previous_path: str | None = None


def _parse_datetime(value: object) -> datetime:
    encoded = str(value)
    if encoded.endswith("Z"):
        encoded = encoded[:-1] + "+00:00"
    return datetime.fromisoformat(encoded)
