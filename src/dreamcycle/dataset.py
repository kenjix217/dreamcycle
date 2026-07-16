"""Leak-resistant Dream Cycle dataset construction.

Adapted from the JintellarCore Dream Engine dataset and golden-path modules.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from dreamcycle.errors import ConfigurationError, InsufficientTrainingData
from dreamcycle.types import DatasetArtifact, TrainingCandidate


class TrainingCandidateSource(Protocol):
    def training_candidates(self, limit: int = 200) -> Sequence[TrainingCandidate]: ...


@dataclass(frozen=True)
class DatasetBuilderConfig:
    output_dir: Path
    candidate_limit: int = 200
    evaluation_ratio: float = 0.10
    minimum_train_samples: int = 1
    seed: int = 0

    def __post_init__(self) -> None:
        if self.candidate_limit < 2:
            raise ConfigurationError("candidate_limit must be at least 2")
        if not 0 < self.evaluation_ratio < 1:
            raise ConfigurationError("evaluation_ratio must be between 0 and 1")
        if self.minimum_train_samples < 1:
            raise ConfigurationError("minimum_train_samples must be positive")


class DatasetBuilder:
    def __init__(self, source: TrainingCandidateSource, config: DatasetBuilderConfig) -> None:
        self._source = source
        self._config = config

    def build(self, session_id: str) -> DatasetArtifact:
        candidates = list(self._source.training_candidates(self._config.candidate_limit))
        usable = [candidate for candidate in candidates if self._usable(candidate)]
        groups: dict[str, list[TrainingCandidate]] = defaultdict(list)
        for candidate in usable:
            groups[candidate.conversation_id].append(candidate)

        if len(groups) < 2:
            raise InsufficientTrainingData(
                "at least two conversations are required for a held-out evaluation split"
            )

        conversation_ids = sorted(groups)
        rng = random.Random(self._config.seed)
        rng.shuffle(conversation_ids)
        evaluation_groups = max(1, round(len(conversation_ids) * self._config.evaluation_ratio))
        evaluation_groups = min(evaluation_groups, len(conversation_ids) - 1)
        eval_ids = set(conversation_ids[:evaluation_groups])

        train = [item for key, items in groups.items() if key not in eval_ids for item in items]
        evaluation = [item for key, items in groups.items() if key in eval_ids for item in items]
        rng.shuffle(train)
        evaluation.sort(key=lambda item: (item.conversation_id, item.trace_id, item.source_ids))

        if len(train) < self._config.minimum_train_samples or not evaluation:
            raise InsufficientTrainingData(
                "approved memories cannot satisfy the configured train/evaluation split"
            )

        output_dir = self._config.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_session = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")
        if not safe_session:
            raise ConfigurationError("session_id must contain a safe path character")

        train_path = output_dir / f"{safe_session}_train.jsonl"
        eval_path = output_dir / f"{safe_session}_eval.jsonl"
        manifest_path = output_dir / f"{safe_session}_manifest.json"
        self._write_jsonl(train_path, train)
        self._write_jsonl(eval_path, evaluation)

        source_ids = tuple(
            sorted({source_id for candidate in usable for source_id in candidate.source_ids})
        )
        manifest = {
            "format_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "seed": self._config.seed,
            "train_samples": len(train),
            "eval_samples": len(evaluation),
            "train_conversation_ids": sorted(set(groups) - eval_ids),
            "eval_conversation_ids": sorted(eval_ids),
            "source_ids": list(source_ids),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        return DatasetArtifact(
            train_path=train_path,
            eval_path=eval_path,
            manifest_path=manifest_path,
            train_samples=len(train),
            eval_samples=len(evaluation),
            source_ids=source_ids,
        )

    @staticmethod
    def _usable(candidate: TrainingCandidate) -> bool:
        return bool(
            candidate.instruction.strip()
            and candidate.output.strip()
            and candidate.conversation_id.strip()
            and candidate.source_ids
        )

    @staticmethod
    def _write_jsonl(path: Path, candidates: Sequence[TrainingCandidate]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for candidate in candidates:
                handle.write(json.dumps(candidate.to_example(), sort_keys=True) + "\n")
