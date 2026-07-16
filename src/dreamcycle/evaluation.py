"""Quality and shadow gate calculations."""

from __future__ import annotations

from dataclasses import dataclass, replace

from dreamcycle.types import EvaluationResult, ShadowResult


@dataclass(frozen=True)
class QualityGate:
    minimum_score: float = 0.0
    minimum_relative_performance: float = 0.98

    def apply(self, result: EvaluationResult) -> EvaluationResult:
        passed = (
            result.passed
            and result.score >= self.minimum_score
            and result.relative_performance >= self.minimum_relative_performance
        )
        return replace(result, passed=passed)


@dataclass(frozen=True)
class ShadowGate:
    baseline_error_rate: float
    baseline_latency_ms: float
    maximum_error_increase: float = 0.05
    maximum_latency_multiplier: float = 1.20

    def apply(self, result: ShadowResult) -> ShadowResult:
        error_ok = result.error_rate <= self.baseline_error_rate * (1 + self.maximum_error_increase)
        latency_ok = result.latency_ms <= (
            self.baseline_latency_ms * self.maximum_latency_multiplier
        )
        return replace(result, acceptable=result.acceptable and error_ok and latency_ok)
