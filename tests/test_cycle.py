from pathlib import Path

import pytest

from dreamcycle import (
    AdapterManager,
    CycleStatus,
    DatasetBuilder,
    DatasetBuilderConfig,
    DreamCycle,
    DreamCycleConfig,
    EvaluationResult,
    PhaseStatus,
    ShadowResult,
    TrainingCandidate,
    TrainingResult,
)
from dreamcycle.errors import TrainingError


class Source:
    def __init__(self, count=2):
        self.count = count

    def training_candidates(self, limit=200):
        return [
            TrainingCandidate(
                instruction=f"question {index}",
                output=f"answer {index}",
                conversation_id=f"conversation-{index}",
                trace_id=f"trace-{index}",
                source_ids=(f"user-{index}", f"assistant-{index}"),
            )
            for index in range(self.count)
        ]


class Trainer:
    def __init__(self, error=None, outside_path=None):
        self.error = error
        self.outside_path = outside_path

    async def train(self, dataset_path, eval_path, output_path):
        if self.error:
            raise self.error
        target = self.outside_path or output_path
        target.mkdir(parents=True, exist_ok=True)
        (target / "adapter_config.json").write_text("{}")
        return TrainingResult(adapter_path=target, metrics={"loss": 0.1})


class Evaluator:
    def __init__(self, passed=True):
        self.passed = passed

    async def evaluate(self, adapter_path, eval_path):
        return EvaluationResult(
            score=1.1 if self.passed else 0.5,
            baseline_score=1.0,
            passed=self.passed,
            perplexity=4.0,
            baseline_perplexity=4.4,
        )


class ShadowEvaluator:
    def __init__(self, acceptable):
        self.acceptable = acceptable

    async def evaluate(self, adapter_path):
        return ShadowResult(
            error_rate=0.01,
            latency_ms=100.0,
            throughput_tps=20.0,
            acceptable=self.acceptable,
        )


class Recorder:
    def __init__(self):
        self.reports = []

    def record_cycle(self, report):
        self.reports.append(report)


def build_cycle(
    tmp_path: Path,
    *,
    source_count=2,
    trainer=None,
    evaluator=None,
    shadow=None,
    event_sinks=(),
    recorder=None,
):
    candidates = tmp_path / "candidates"
    return DreamCycle(
        config=DreamCycleConfig(
            candidate_adapter_dir=candidates,
            require_shadow=shadow is not None,
        ),
        dataset_builder=DatasetBuilder(
            Source(source_count), DatasetBuilderConfig(output_dir=tmp_path / "datasets")
        ),
        trainer=trainer or Trainer(),
        evaluator=evaluator or Evaluator(),
        adapter_manager=AdapterManager(candidate_root=candidates, active_root=tmp_path / "active"),
        shadow_evaluator=shadow,
        event_sinks=event_sinks,
        recorder=recorder,
    )


@pytest.mark.asyncio
async def test_successful_cycle_promotes_and_records_adapter(tmp_path):
    recorder = Recorder()
    report = await build_cycle(tmp_path, recorder=recorder).run()

    assert report.status is CycleStatus.SUCCESS
    assert report.promotion and report.promotion.promoted_path.is_dir()
    assert [phase.name for phase in report.phases] == [
        "dataset_build",
        "adapter_training",
        "benchmark",
        "promotion",
    ]
    assert recorder.reports == [report]


@pytest.mark.asyncio
async def test_cycle_skips_once_when_eval_split_is_impossible(tmp_path):
    report = await build_cycle(tmp_path, source_count=1).run()

    assert report.status is CycleStatus.SKIPPED
    assert len(report.phases) == 1
    assert report.phases[0].name == "dataset_build"
    assert report.phases[0].status is PhaseStatus.SKIPPED


@pytest.mark.asyncio
async def test_benchmark_rejection_does_not_promote(tmp_path):
    report = await build_cycle(tmp_path, evaluator=Evaluator(passed=False)).run()

    assert report.status is CycleStatus.REJECTED
    assert report.promotion is None
    assert report.phases[-1].name == "quality_gate"


@pytest.mark.asyncio
async def test_shadow_rejection_does_not_promote(tmp_path):
    report = await build_cycle(tmp_path, shadow=ShadowEvaluator(False)).run()

    assert report.status is CycleStatus.REJECTED
    assert report.shadow and not report.shadow.acceptable
    assert report.phases[-1].name == "shadow_gate"


@pytest.mark.asyncio
async def test_training_failure_is_an_error_report(tmp_path):
    report = await build_cycle(
        tmp_path, trainer=Trainer(error=TrainingError("hardware unavailable"))
    ).run()

    assert report.status is CycleStatus.ERROR
    assert report.phases[-1].name == "adapter_training"
    assert "hardware unavailable" in report.reason


@pytest.mark.asyncio
async def test_promotion_outside_candidate_root_fails_closed(tmp_path):
    report = await build_cycle(tmp_path, trainer=Trainer(outside_path=tmp_path / "outside")).run()

    assert report.status is CycleStatus.ERROR
    assert report.phases[-1].name == "promotion"
    assert report.promotion is None


@pytest.mark.asyncio
async def test_event_failure_is_visible_but_noncritical(tmp_path):
    def broken_sink(event):
        raise RuntimeError(f"cannot observe {event.event_type.value}")

    report = await build_cycle(tmp_path, event_sinks=(broken_sink,)).run()

    assert report.status is CycleStatus.SUCCESS
    assert report.event_errors
    assert any("cannot observe" in error for error in report.event_errors)
