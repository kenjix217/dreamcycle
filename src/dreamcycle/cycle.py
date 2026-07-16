"""Standalone Dream Cycle orchestration.

Adapted from the dependency-injected JintellarCore Dream Engine cycle runner.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from dreamcycle.adapters import AdapterManager
from dreamcycle.dataset import DatasetBuilder
from dreamcycle.errors import InsufficientTrainingData
from dreamcycle.evaluation import QualityGate, ShadowGate
from dreamcycle.events import EventDispatcher, EventSink, EventType
from dreamcycle.types import (
    CycleStatus,
    DreamCycleReport,
    EvaluationResult,
    PhaseResult,
    PhaseStatus,
    ShadowResult,
    TrainingResult,
    utc_now,
)


class Trainer(Protocol):
    async def train(
        self, dataset_path: Path, eval_path: Path, output_path: Path
    ) -> TrainingResult: ...


class Evaluator(Protocol):
    async def evaluate(self, adapter_path: Path, eval_path: Path) -> EvaluationResult: ...


class ShadowEvaluator(Protocol):
    async def evaluate(self, adapter_path: Path) -> ShadowResult: ...


class CycleRecorder(Protocol):
    def record_cycle(self, report: DreamCycleReport) -> Any: ...


@dataclass(frozen=True)
class DreamCycleConfig:
    candidate_adapter_dir: Path
    quality_gate: QualityGate = QualityGate()
    shadow_gate: ShadowGate | None = None
    require_shadow: bool = False


class DreamCycle:
    def __init__(
        self,
        *,
        config: DreamCycleConfig,
        dataset_builder: DatasetBuilder,
        trainer: Trainer,
        evaluator: Evaluator,
        adapter_manager: AdapterManager,
        shadow_evaluator: ShadowEvaluator | None = None,
        recorder: CycleRecorder | None = None,
        event_sinks: tuple[EventSink, ...] = (),
    ) -> None:
        if (config.require_shadow or config.shadow_gate is not None) and shadow_evaluator is None:
            raise ValueError("require_shadow=True requires a shadow_evaluator")
        self._config = config
        self._dataset_builder = dataset_builder
        self._trainer = trainer
        self._evaluator = evaluator
        self._adapter_manager = adapter_manager
        self._shadow_evaluator = shadow_evaluator
        self._recorder = recorder
        self._events = EventDispatcher(event_sinks)

    async def run(self) -> DreamCycleReport:
        session_id = f"dc-{utc_now().strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}"
        started_at = utc_now()
        phases: list[PhaseResult] = []
        event_errors = await self._events.emit(EventType.CYCLE_STARTED, session_id)
        dataset = None
        training = None
        evaluation = None
        shadow = None
        promotion = None

        try:
            dataset = await self._phase(
                phases,
                session_id,
                "dataset_build",
                lambda: asyncio.to_thread(self._dataset_builder.build, session_id),
                event_errors,
            )
            candidate_path = self._config.candidate_adapter_dir.resolve() / session_id
            candidate_path.mkdir(parents=True, exist_ok=False)
            training = await self._phase(
                phases,
                session_id,
                "adapter_training",
                lambda: self._trainer.train(dataset.train_path, dataset.eval_path, candidate_path),
                event_errors,
            )
            evaluation = await self._phase(
                phases,
                session_id,
                "benchmark",
                lambda: self._evaluator.evaluate(training.adapter_path, dataset.eval_path),
                event_errors,
            )
            evaluation = self._config.quality_gate.apply(evaluation)
            event_errors.extend(
                await self._events.emit(
                    EventType.QUALITY_GATE,
                    session_id,
                    {
                        "passed": evaluation.passed,
                        "score": evaluation.score,
                        "baseline_score": evaluation.baseline_score,
                        "relative_performance": evaluation.relative_performance,
                    },
                )
            )
            if not evaluation.passed:
                phases.append(self._rejected_phase("quality_gate", "benchmark gate failed"))
                report = self._report(
                    session_id=session_id,
                    status=CycleStatus.REJECTED,
                    started_at=started_at,
                    phases=phases,
                    dataset=dataset,
                    training=training,
                    evaluation=evaluation,
                    reason="benchmark gate failed",
                    event_errors=event_errors,
                )
                return await self._finish(report)

            if self._shadow_evaluator is not None:
                shadow = await self._phase(
                    phases,
                    session_id,
                    "shadow_mode",
                    lambda: self._shadow_evaluator.evaluate(training.adapter_path),
                    event_errors,
                )
                if self._config.shadow_gate is not None:
                    shadow = self._config.shadow_gate.apply(shadow)
                event_errors.extend(
                    await self._events.emit(
                        EventType.SHADOW_GATE,
                        session_id,
                        {"acceptable": shadow.acceptable, "error_rate": shadow.error_rate},
                    )
                )
                if not shadow.acceptable:
                    phases.append(self._rejected_phase("shadow_gate", "shadow gate failed"))
                    report = self._report(
                        session_id=session_id,
                        status=CycleStatus.REJECTED,
                        started_at=started_at,
                        phases=phases,
                        dataset=dataset,
                        training=training,
                        evaluation=evaluation,
                        shadow=shadow,
                        reason="shadow gate failed",
                        event_errors=event_errors,
                    )
                    return await self._finish(report)

            promotion = await self._phase(
                phases,
                session_id,
                "promotion",
                lambda: asyncio.to_thread(
                    self._adapter_manager.promote,
                    training.adapter_path,
                    session_id=session_id,
                    metrics={
                        "score": evaluation.score,
                        "baseline_score": evaluation.baseline_score,
                        "relative_performance": evaluation.relative_performance,
                    },
                ),
                event_errors,
            )
            event_errors.extend(
                await self._events.emit(
                    EventType.ADAPTER_PROMOTED,
                    session_id,
                    {"adapter_path": str(promotion.promoted_path)},
                )
            )
            report = self._report(
                session_id=session_id,
                status=CycleStatus.SUCCESS,
                started_at=started_at,
                phases=phases,
                dataset=dataset,
                training=training,
                evaluation=evaluation,
                shadow=shadow,
                promotion=promotion,
                event_errors=event_errors,
            )
            return await self._finish(report)
        except InsufficientTrainingData as exc:
            if phases and phases[-1].name == "dataset_build":
                phases[-1] = replace(phases[-1], status=PhaseStatus.SKIPPED)
            else:
                phases.append(self._error_phase("dataset_build", PhaseStatus.SKIPPED, exc))
            return await self._finish(
                self._report(
                    session_id=session_id,
                    status=CycleStatus.SKIPPED,
                    started_at=started_at,
                    phases=phases,
                    reason=str(exc),
                    event_errors=event_errors,
                )
            )
        except Exception as exc:
            if not phases or phases[-1].status is not PhaseStatus.ERROR:
                phases.append(self._error_phase("cycle", PhaseStatus.ERROR, exc))
            return await self._finish(
                self._report(
                    session_id=session_id,
                    status=CycleStatus.ERROR,
                    started_at=started_at,
                    phases=phases,
                    dataset=dataset,
                    training=training,
                    evaluation=evaluation,
                    shadow=shadow,
                    promotion=promotion,
                    reason=f"{type(exc).__name__}: {exc}",
                    event_errors=event_errors,
                )
            )

    async def _phase(
        self,
        phases: list[PhaseResult],
        session_id: str,
        name: str,
        operation: Callable[[], Awaitable[Any]],
        event_errors: list[str],
    ) -> Any:
        started = utc_now()
        event_errors.extend(
            await self._events.emit(EventType.PHASE_STARTED, session_id, {"phase": name})
        )
        try:
            result = await operation()
        except Exception as exc:
            phases.append(
                PhaseResult(
                    name=name,
                    status=PhaseStatus.ERROR,
                    started_at=started,
                    completed_at=utc_now(),
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            raise
        phases.append(
            PhaseResult(
                name=name,
                status=PhaseStatus.SUCCESS,
                started_at=started,
                completed_at=utc_now(),
            )
        )
        event_errors.extend(
            await self._events.emit(EventType.PHASE_COMPLETED, session_id, {"phase": name})
        )
        return result

    async def _finish(self, report: DreamCycleReport) -> DreamCycleReport:
        event_errors = list(report.event_errors)
        event_errors.extend(
            await self._events.emit(
                EventType.CYCLE_COMPLETED,
                report.session_id,
                {"status": report.status.value, "reason": report.reason},
            )
        )
        report = self._replace_event_errors(report, tuple(event_errors))
        if self._recorder is not None:
            try:
                result = self._recorder.record_cycle(report)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                event_errors.append(f"cycle recorder: {type(exc).__name__}: {exc}")
                report = self._replace_event_errors(report, tuple(event_errors))
        return report

    @staticmethod
    def _report(
        *,
        session_id: str,
        status: CycleStatus,
        started_at: datetime,
        phases: list[PhaseResult],
        dataset: Any = None,
        training: Any = None,
        evaluation: Any = None,
        shadow: Any = None,
        promotion: Any = None,
        reason: str = "",
        event_errors: list[str],
    ) -> DreamCycleReport:
        return DreamCycleReport(
            session_id=session_id,
            status=status,
            started_at=started_at,
            completed_at=utc_now(),
            phases=tuple(phases),
            dataset=dataset,
            training=training,
            evaluation=evaluation,
            shadow=shadow,
            promotion=promotion,
            reason=reason,
            event_errors=tuple(event_errors),
        )

    @staticmethod
    def _replace_event_errors(
        report: DreamCycleReport, event_errors: tuple[str, ...]
    ) -> DreamCycleReport:
        return DreamCycleReport(
            session_id=report.session_id,
            status=report.status,
            started_at=report.started_at,
            completed_at=report.completed_at,
            phases=report.phases,
            dataset=report.dataset,
            training=report.training,
            evaluation=report.evaluation,
            shadow=report.shadow,
            promotion=report.promotion,
            reason=report.reason,
            event_errors=event_errors,
        )

    @staticmethod
    def _rejected_phase(name: str, reason: str) -> PhaseResult:
        now = utc_now()
        return PhaseResult(
            name=name,
            status=PhaseStatus.REJECTED,
            started_at=now,
            completed_at=now,
            error=reason,
        )

    @staticmethod
    def _error_phase(name: str, status: PhaseStatus, exc: Exception) -> PhaseResult:
        now = utc_now()
        return PhaseResult(
            name=name,
            status=status,
            started_at=now,
            completed_at=now,
            error=f"{type(exc).__name__}: {exc}",
        )
