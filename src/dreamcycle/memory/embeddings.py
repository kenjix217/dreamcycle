"""Embedding providers that do not depend on a hosted API."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from dreamcycle.errors import ConfigurationError, EmbeddingError, OptionalDependencyError


class CallableEmbeddingProvider:
    """Wrap an application-owned embedding function in the public protocol."""

    def __init__(
        self,
        function: Callable[[Sequence[str]], Sequence[Sequence[float]]],
        *,
        dimension: int,
        model_name: str,
    ) -> None:
        if dimension < 1:
            raise ConfigurationError("embedding dimension must be positive")
        if not model_name.strip():
            raise ConfigurationError("embedding model_name is required")
        self._function = function
        self._dimension = dimension
        self._model_name = model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        vectors = self._function(texts)
        if len(vectors) != len(texts):
            raise EmbeddingError("embedding function returned the wrong vector count")
        return vectors


class SentenceTransformerEmbedding:
    """Local Sentence Transformers embeddings, loaded only when requested."""

    def __init__(
        self,
        model: str | Path,
        *,
        allow_remote_download: bool = False,
        normalize_embeddings: bool = True,
        device: str | None = None,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise OptionalDependencyError(
                "SentenceTransformerEmbedding requires 'pip install dreamcycle[embeddings]'"
            ) from exc

        model_value = str(model)
        if not allow_remote_download and not Path(model_value).expanduser().exists():
            raise ConfigurationError("model must be a local path unless allow_remote_download=True")
        self._model = SentenceTransformer(
            model_value,
            device=device,
            local_files_only=not allow_remote_download,
        )
        dimension = self._model.get_sentence_embedding_dimension()
        if dimension is None:
            raise EmbeddingError("embedding model did not report a vector dimension")
        self._dimension = int(dimension)
        self._model_name = model_value
        self._normalize = normalize_embeddings

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        values = self._model.encode(
            list(texts),
            normalize_embeddings=self._normalize,
            convert_to_numpy=True,
        )
        return [row.astype(float).tolist() for row in values]
