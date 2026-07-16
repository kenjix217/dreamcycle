"""Public DreamCycle exceptions."""


class DreamCycleError(Exception):
    """Base exception for package failures."""


class ConfigurationError(DreamCycleError):
    """Raised when configuration cannot produce a safe runtime."""


class InsufficientTrainingData(DreamCycleError):
    """Raised when a leak-free train/evaluation split cannot be built."""


class TrainingError(DreamCycleError):
    """Raised when local adapter training fails."""


class EvaluationError(DreamCycleError):
    """Raised when a model quality evaluation cannot be completed."""


class PromotionError(DreamCycleError):
    """Raised when an adapter cannot be atomically activated."""


class MemorySetupError(DreamCycleError):
    """Raised when the PostgreSQL memory schema is unavailable or incompatible."""


class EmbeddingError(DreamCycleError):
    """Raised when an embedding provider returns invalid vectors."""


class OptionalDependencyError(DreamCycleError, ImportError):
    """Raised when an explicitly requested optional feature is not installed."""
