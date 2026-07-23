"""DreamCycle public API."""

from dreamcycle.adapters import AdapterManager
from dreamcycle.cycle import DreamCycle, DreamCycleConfig, Evaluator, ShadowEvaluator, Trainer
from dreamcycle.dataset import DatasetBuilder, DatasetBuilderConfig, TrainingCandidateSource
from dreamcycle.evaluation import QualityGate, ShadowGate
from dreamcycle.events import DreamEvent, EventSink, EventType
from dreamcycle.types import (
    CycleStatus,
    DatasetArtifact,
    DreamCycleReport,
    EvaluationResult,
    PhaseResult,
    PhaseStatus,
    PromotionResult,
    ShadowResult,
    TrainingCandidate,
    TrainingResult,
)

__version__ = "0.3.1"

__all__ = [
    "AdapterManager",
    "CycleStatus",
    "DatasetArtifact",
    "DatasetBuilder",
    "DatasetBuilderConfig",
    "DreamCycle",
    "DreamCycleConfig",
    "DreamCycleReport",
    "DreamEvent",
    "EvaluationResult",
    "Evaluator",
    "EventSink",
    "EventType",
    "PhaseResult",
    "PhaseStatus",
    "PromotionResult",
    "QualityGate",
    "ShadowEvaluator",
    "ShadowGate",
    "ShadowResult",
    "Trainer",
    "TrainingCandidate",
    "TrainingCandidateSource",
    "TrainingResult",
]
