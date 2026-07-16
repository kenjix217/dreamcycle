"""Validated HTTP request and response models."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from dreamcycle.server.jobs import CycleJobState
from dreamcycle.types import DistanceMetric, MemoryRecord


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemoryRecordRequest(StrictRequest):
    content: str = Field(min_length=1)
    role: Literal["user", "assistant", "system", "tool", "event"] = "event"
    source: str = Field(default="vendor-sdk", min_length=1, max_length=200)
    conversation_id: str = Field(default="", max_length=500)
    trace_id: str = Field(default="", max_length=500)
    importance: float = Field(default=0.5, ge=0, le=1)
    success: bool = True
    data_classification: str = Field(default="public", min_length=1, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryTurnRequest(StrictRequest):
    user_content: str = Field(min_length=1)
    assistant_content: str = Field(min_length=1)
    source: str = Field(default="vendor-sdk", min_length=1, max_length=200)
    conversation_id: str = Field(default="", max_length=500)
    trace_id: str = Field(default="", max_length=500)
    importance: float = Field(default=0.5, ge=0, le=1)
    success: bool = True
    data_classification: str = Field(default="public", min_length=1, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemorySearchRequest(StrictRequest):
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=200)
    role: str | None = None
    source: str | None = None
    successful_only: bool = False
    reviewed_only: bool = False
    minimum_importance: float = Field(default=0, ge=0, le=1)
    classifications: tuple[str, ...] = ()
    metric: DistanceMetric | None = None


class MemoryReviewRequest(StrictRequest):
    approved_for_training: bool = False


class MemoryItem(BaseModel):
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
    def from_record(cls, record: MemoryRecord) -> MemoryItem:
        return cls(**record.__dict__)


class MemoryTurnResponse(BaseModel):
    user: MemoryItem
    assistant: MemoryItem


class MemorySearchResponse(BaseModel):
    memories: list[MemoryItem]


class MutationResponse(BaseModel):
    success: bool


class CycleJobResponse(BaseModel):
    id: str
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    report: Mapping[str, Any] | None = None
    error: str | None = None

    @classmethod
    def from_state(cls, state: CycleJobState) -> CycleJobResponse:
        return cls(
            id=state.id,
            status=state.status.value,
            created_at=state.created_at,
            started_at=state.started_at,
            completed_at=state.completed_at,
            report=state.report,
            error=state.error,
        )


class AdapterStateResponse(BaseModel):
    available: bool
    active_path: str | None = None
    accepted: bool | None = None
    reason: str | None = None
    previous_path: str | None = None
