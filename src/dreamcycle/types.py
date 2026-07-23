"""Public data types shared by the cycle, memory, and training modules."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DistanceMetric(str, Enum):
    COSINE = "cosine"
    L2 = "l2"
    INNER_PRODUCT = "inner_product"


class CycleStatus(str, Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    REJECTED = "rejected"
    ERROR = "error"


class PhaseStatus(str, Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    REJECTED = "rejected"
    ERROR = "error"


@dataclass(frozen=True)
class MemoryRecord:
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


@dataclass(frozen=True)
class TrainingCandidate:
    instruction: str
    output: str
    conversation_id: str
    trace_id: str
    source_ids: tuple[str, ...]
    data_classification: str = "public"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_example(self) -> dict[str, Any]:
        return {
            "instruction": self.instruction,
            "output": self.output,
            "metadata": {
                **dict(self.metadata),
                "conversation_id": self.conversation_id,
                "trace_id": self.trace_id,
                "source_ids": list(self.source_ids),
                "data_classification": self.data_classification,
            },
        }


@dataclass(frozen=True)
class KnowledgeNode:
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


@dataclass(frozen=True)
class KnowledgeEdge:
    id: str
    namespace: str
    user_id: str
    source_id: str
    target_id: str
    relation: str
    weight: float
    metadata: Mapping[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class KnowledgeStats:
    nodes: int
    edges: int
    provenance_links: int
    node_types: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeClaim:
    node_type: str
    key: str
    content: str
    source_memory_ids: tuple[str, ...]
    confidence: float = 1.0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DatasetArtifact:
    train_path: Path
    eval_path: Path
    manifest_path: Path
    train_samples: int
    eval_samples: int
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class TrainingResult:
    adapter_path: Path
    metrics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationResult:
    score: float
    baseline_score: float
    passed: bool
    perplexity: float | None = None
    baseline_perplexity: float | None = None
    reasoning_quality: float | None = None
    metrics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def relative_performance(self) -> float:
        if self.baseline_score == 0:
            return 0.0
        return self.score / self.baseline_score


@dataclass(frozen=True)
class ShadowResult:
    error_rate: float
    latency_ms: float
    throughput_tps: float
    acceptable: bool
    metrics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromotionResult:
    accepted: bool
    reason: str
    promoted_path: Path | None = None
    previous_path: Path | None = None
    metrics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PhaseResult:
    name: str
    status: PhaseStatus
    started_at: datetime
    completed_at: datetime
    detail: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()


@dataclass(frozen=True)
class DreamCycleReport:
    session_id: str
    status: CycleStatus
    started_at: datetime
    completed_at: datetime
    phases: tuple[PhaseResult, ...]
    dataset: DatasetArtifact | None = None
    training: TrainingResult | None = None
    evaluation: EvaluationResult | None = None
    shadow: ShadowResult | None = None
    promotion: PromotionResult | None = None
    reason: str = ""
    event_errors: tuple[str, ...] = ()

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(self)


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _json_ready(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value
