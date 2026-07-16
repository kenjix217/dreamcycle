"""Environment-driven composition for the standalone sidecar process."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI

from dreamcycle.adapters import AdapterManager
from dreamcycle.cycle import DreamCycle, DreamCycleConfig
from dreamcycle.dataset import DatasetBuilder, DatasetBuilderConfig
from dreamcycle.errors import ConfigurationError
from dreamcycle.memory.embeddings import SentenceTransformerEmbedding
from dreamcycle.memory.postgres import PostgresMemoryConfig
from dreamcycle.server.app import create_app
from dreamcycle.server.auth import APIKeyAuthenticator, ClientIdentity
from dreamcycle.server.jobs import AdapterResolver, CycleJobManager, CycleResolver
from dreamcycle.server.memory import PostgresMemoryResolver
from dreamcycle.server.proxy import ChatCompletionsProxy, ProxyConfig, ProxyMode
from dreamcycle.server.service import DreamCycleService
from dreamcycle.training.transformers import (
    TransformersEvaluationConfig,
    TransformersLoRAConfig,
    TransformersLoRATrainer,
    TransformersPerplexityEvaluator,
)
from dreamcycle.types import DistanceMetric


@dataclass(frozen=True)
class SidecarSettings:
    dsn: str = field(repr=False)
    embedding_model: str
    api_keys: Mapping[str, ClientIdentity] = field(repr=False)
    schema: str = "dreamcycle"
    distance_metric: DistanceMetric = DistanceMetric.COSINE
    allow_remote_model_download: bool = False
    create_vector_extension: bool = False
    create_hnsw_index: bool = True
    upstream_base_url: str = ""
    upstream_api_key: str = field(default="", repr=False)
    proxy_mode: ProxyMode = ProxyMode.OBSERVE
    proxy_recall_limit: int = 5
    proxy_context_max_characters: int = 6000
    proxy_timeout_seconds: float = 120.0
    base_model: Path | None = None
    data_dir: Path | None = None
    candidate_limit: int = 200
    minimum_train_samples: int = 1

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> SidecarSettings:
        env = dict(os.environ if environ is None else environ)
        bindings = _api_key_bindings(env)
        try:
            metric = DistanceMetric(env.get("DREAMCYCLE_DISTANCE_METRIC", "cosine"))
        except ValueError as exc:
            raise ConfigurationError(
                "DREAMCYCLE_DISTANCE_METRIC must be cosine, l2, or inner_product"
            ) from exc
        try:
            mode = ProxyMode(env.get("DREAMCYCLE_PROXY_MODE", "observe"))
        except ValueError as exc:
            raise ConfigurationError("DREAMCYCLE_PROXY_MODE must be observe or retrieve") from exc

        base_model_value = env.get("DREAMCYCLE_BASE_MODEL", "").strip()
        data_dir_value = env.get("DREAMCYCLE_DATA_DIR", "").strip()
        if bool(base_model_value) != bool(data_dir_value):
            raise ConfigurationError(
                "DREAMCYCLE_BASE_MODEL and DREAMCYCLE_DATA_DIR must be configured together"
            )
        return cls(
            dsn=_required(env, "DREAMCYCLE_POSTGRES_DSN"),
            embedding_model=_required(env, "DREAMCYCLE_EMBEDDING_MODEL"),
            api_keys=bindings,
            schema=env.get("DREAMCYCLE_POSTGRES_SCHEMA", "dreamcycle").strip(),
            distance_metric=metric,
            allow_remote_model_download=_boolean(env, "DREAMCYCLE_ALLOW_REMOTE_MODEL_DOWNLOAD"),
            create_vector_extension=_boolean(env, "DREAMCYCLE_CREATE_VECTOR_EXTENSION"),
            create_hnsw_index=_boolean(env, "DREAMCYCLE_CREATE_HNSW_INDEX", default=True),
            upstream_base_url=env.get("DREAMCYCLE_UPSTREAM_BASE_URL", "").strip(),
            upstream_api_key=env.get("DREAMCYCLE_UPSTREAM_API_KEY", ""),
            proxy_mode=mode,
            proxy_recall_limit=_integer(env, "DREAMCYCLE_PROXY_RECALL_LIMIT", 5),
            proxy_context_max_characters=_integer(
                env, "DREAMCYCLE_PROXY_CONTEXT_MAX_CHARACTERS", 6000
            ),
            proxy_timeout_seconds=_floating(env, "DREAMCYCLE_PROXY_TIMEOUT_SECONDS", 120.0),
            base_model=Path(base_model_value).expanduser() if base_model_value else None,
            data_dir=Path(data_dir_value).expanduser() if data_dir_value else None,
            candidate_limit=_integer(env, "DREAMCYCLE_CANDIDATE_LIMIT", 200),
            minimum_train_samples=_integer(env, "DREAMCYCLE_MINIMUM_TRAIN_SAMPLES", 1),
        )


class LocalCycleResolver(CycleResolver, AdapterResolver):
    def __init__(
        self,
        memories: PostgresMemoryResolver,
        *,
        base_model: Path,
        data_dir: Path,
        candidate_limit: int,
        minimum_train_samples: int,
    ) -> None:
        self._memories = memories
        self._base_model = base_model.expanduser().resolve()
        self._data_dir = data_dir.expanduser().resolve()
        self._candidate_limit = candidate_limit
        self._minimum_train_samples = minimum_train_samples
        self._cycles: dict[ClientIdentity, DreamCycle] = {}
        self._adapters: dict[ClientIdentity, AdapterManager] = {}
        self._lock = threading.Lock()

    def resolve_cycle(self, identity: ClientIdentity) -> DreamCycle:
        with self._lock:
            if identity not in self._cycles:
                self._build(identity)
            return self._cycles[identity]

    def resolve_adapter(self, identity: ClientIdentity) -> AdapterManager:
        with self._lock:
            if identity not in self._adapters:
                self._build(identity)
            return self._adapters[identity]

    def _build(self, identity: ClientIdentity) -> None:
        root = self._data_dir / _identity_directory(identity)
        candidate_root = root / "candidates"
        adapter_manager = AdapterManager(
            candidate_root=candidate_root,
            active_root=root / "adapters",
        )
        memory = self._memories.resolve(identity)
        dataset_builder = DatasetBuilder(
            memory,
            DatasetBuilderConfig(
                output_dir=root / "datasets",
                candidate_limit=self._candidate_limit,
                minimum_train_samples=self._minimum_train_samples,
            ),
        )
        trainer = TransformersLoRATrainer(TransformersLoRAConfig(base_model_path=self._base_model))
        evaluator = TransformersPerplexityEvaluator(
            TransformersEvaluationConfig(base_model_path=self._base_model)
        )
        cycle = DreamCycle(
            config=DreamCycleConfig(candidate_adapter_dir=candidate_root),
            dataset_builder=dataset_builder,
            trainer=trainer,
            evaluator=evaluator,
            adapter_manager=adapter_manager,
            recorder=memory,
        )
        self._adapters[identity] = adapter_manager
        self._cycles[identity] = cycle


def create_app_from_env(environ: Mapping[str, str] | None = None) -> FastAPI:
    settings = SidecarSettings.from_env(environ)
    authenticator = APIKeyAuthenticator(settings.api_keys)
    embeddings = SentenceTransformerEmbedding(
        settings.embedding_model,
        allow_remote_download=settings.allow_remote_model_download,
    )
    base_identity = authenticator.identities[0]
    memories = PostgresMemoryResolver(
        PostgresMemoryConfig(
            dsn=settings.dsn,
            namespace=base_identity.namespace,
            user_id=base_identity.user_id,
            embedding_dimension=embeddings.dimension,
            schema=settings.schema,
            distance_metric=settings.distance_metric,
            create_vector_extension=settings.create_vector_extension,
            create_hnsw_index=settings.create_hnsw_index,
        ),
        embeddings,
    )
    for identity in authenticator.identities:
        memories.resolve(identity)
    service = DreamCycleService(memories)

    proxy = None
    if settings.upstream_base_url:
        proxy = ChatCompletionsProxy(
            ProxyConfig(
                upstream_base_url=settings.upstream_base_url,
                upstream_api_key=settings.upstream_api_key,
                mode=settings.proxy_mode,
                recall_limit=settings.proxy_recall_limit,
                context_max_characters=settings.proxy_context_max_characters,
                timeout_seconds=settings.proxy_timeout_seconds,
            ),
            service,
        )

    local_cycles = None
    if settings.base_model is not None and settings.data_dir is not None:
        local_cycles = LocalCycleResolver(
            memories,
            base_model=settings.base_model,
            data_dir=settings.data_dir,
            candidate_limit=settings.candidate_limit,
            minimum_train_samples=settings.minimum_train_samples,
        )
        for identity in authenticator.identities:
            local_cycles.resolve_cycle(identity)
    return create_app(
        authenticator=authenticator,
        service=service,
        jobs=CycleJobManager(local_cycles),
        adapters=local_cycles,
        proxy=proxy,
    )


def _api_key_bindings(env: Mapping[str, str]) -> Mapping[str, ClientIdentity]:
    encoded = env.get("DREAMCYCLE_API_KEYS_JSON", "").strip()
    simple_key = env.get("DREAMCYCLE_API_KEY", "")
    if encoded and simple_key:
        raise ConfigurationError(
            "configure DREAMCYCLE_API_KEYS_JSON or DREAMCYCLE_API_KEY, not both"
        )
    if encoded:
        try:
            value = json.loads(encoded)
        except json.JSONDecodeError as exc:
            raise ConfigurationError("DREAMCYCLE_API_KEYS_JSON must be valid JSON") from exc
        if not isinstance(value, dict) or not value:
            raise ConfigurationError("DREAMCYCLE_API_KEYS_JSON must be a non-empty object")
        bindings: dict[str, ClientIdentity] = {}
        for api_key, identity in value.items():
            if not isinstance(api_key, str) or not api_key:
                raise ConfigurationError("API key map keys must be non-empty strings")
            if not isinstance(identity, dict):
                raise ConfigurationError("each API key must map to an identity object")
            bindings[api_key] = ClientIdentity(
                namespace=str(identity.get("namespace") or ""),
                user_id=str(identity.get("user_id") or ""),
            )
        return bindings
    return {
        _required(env, "DREAMCYCLE_API_KEY"): ClientIdentity(
            namespace=_required(env, "DREAMCYCLE_NAMESPACE"),
            user_id=_required(env, "DREAMCYCLE_USER_ID"),
        )
    }


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} is required")
    return value


def _boolean(env: Mapping[str, str], name: str, *, default: bool = False) -> bool:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be true or false")


def _integer(env: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(env.get(name, str(default)))
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc


def _floating(env: Mapping[str, str], name: str, default: float) -> float:
    try:
        return float(env.get(name, str(default)))
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number") from exc


def _identity_directory(identity: ClientIdentity) -> str:
    digest = hashlib.sha256(f"{identity.namespace}\0{identity.user_id}".encode()).hexdigest()
    return digest[:24]
