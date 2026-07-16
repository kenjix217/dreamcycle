"""Direct PostgreSQL/pgvector L2 and L3 memory implementation."""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from dreamcycle.errors import ConfigurationError, EmbeddingError, MemorySetupError
from dreamcycle.memory.base import EmbeddingProvider, KnowledgeExtractor, MemoryFilters
from dreamcycle.memory.schema import (
    SCHEMA_VERSION,
    qualified,
    schema_statements,
    validate_identifier,
)
from dreamcycle.types import (
    DistanceMetric,
    DreamCycleReport,
    KnowledgeEdge,
    KnowledgeNode,
    MemoryRecord,
    TrainingCandidate,
    utc_now,
)


@dataclass(frozen=True)
class PostgresMemoryConfig:
    dsn: str = field(repr=False)
    namespace: str
    embedding_dimension: int
    user_id: str = ""
    schema: str = "dreamcycle"
    distance_metric: DistanceMetric = DistanceMetric.COSINE
    create_vector_extension: bool = False
    create_hnsw_index: bool = True
    hnsw_m: int = 16
    hnsw_ef_construction: int = 64
    training_classifications: tuple[str, ...] = ("public", "internal")

    def __post_init__(self) -> None:
        if not self.dsn.strip():
            raise ConfigurationError("PostgreSQL DSN is required")
        if not self.namespace.strip():
            raise ConfigurationError("memory namespace is required")
        if self.embedding_dimension < 1 or self.embedding_dimension > 16000:
            raise ConfigurationError("embedding_dimension must be between 1 and 16000")
        if self.create_hnsw_index and self.embedding_dimension > 2000:
            raise ConfigurationError("HNSW indexes for vector require at most 2000 dimensions")
        validate_identifier(self.schema, "schema name")
        if not 2 <= self.hnsw_m <= 100:
            raise ConfigurationError("hnsw_m must be between 2 and 100")
        if not 4 <= self.hnsw_ef_construction <= 1000:
            raise ConfigurationError("hnsw_ef_construction must be between 4 and 1000")
        if not self.training_classifications:
            raise ConfigurationError("training_classifications cannot be empty")


class PostgresMemory:
    """A namespace-bound direct memory client.

    Every query includes the configured namespace and user scope. There is no
    method-level namespace override.
    """

    def __init__(self, config: PostgresMemoryConfig, embeddings: EmbeddingProvider) -> None:
        if embeddings.dimension != config.embedding_dimension:
            raise ConfigurationError(
                "embedding provider dimension does not match PostgresMemoryConfig"
            )
        self.config = config
        self.embeddings = embeddings
        self._l2 = qualified(config.schema, "l2_memories")
        self._nodes = qualified(config.schema, "l3_nodes")
        self._edges = qualified(config.schema, "l3_edges")
        self._provenance = qualified(config.schema, "l3_provenance")
        self._runs = qualified(config.schema, "cycle_runs")
        self._meta = qualified(config.schema, "schema_meta")

    def setup(self) -> None:
        try:
            with self._connect(register=False) as connection:
                if self.config.create_vector_extension:
                    connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
                extension = connection.execute(
                    "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
                ).fetchone()
                if extension is None:
                    raise MemorySetupError(
                        "pgvector is not installed; install it or enable create_vector_extension"
                    )
                register_vector(connection)
                for statement in schema_statements(
                    schema=self.config.schema,
                    embedding_dimension=self.config.embedding_dimension,
                    distance_metric=self.config.distance_metric,
                    create_hnsw_index=self.config.create_hnsw_index,
                    hnsw_m=self.config.hnsw_m,
                    hnsw_ef_construction=self.config.hnsw_ef_construction,
                ):
                    connection.execute(statement)
                self._verify_meta(connection, "schema_version", SCHEMA_VERSION)
                self._verify_meta(
                    connection, "embedding_dimension", str(self.config.embedding_dimension)
                )
                self._verify_meta(connection, "distance_metric", self.config.distance_metric.value)
                if self.config.create_hnsw_index:
                    self._verify_meta(connection, "hnsw_m", str(self.config.hnsw_m))
                    self._verify_meta(
                        connection,
                        "hnsw_ef_construction",
                        str(self.config.hnsw_ef_construction),
                    )
        except MemorySetupError:
            raise
        except psycopg.Error as exc:
            raise MemorySetupError(f"failed to set up DreamCycle memory: {exc}") from exc

    def remember(
        self,
        content: str,
        *,
        role: str = "event",
        source: str = "application",
        conversation_id: str = "",
        trace_id: str = "",
        importance: float = 0.5,
        success: bool = True,
        reviewed: bool = False,
        approved_for_training: bool = False,
        data_classification: str = "public",
        metadata: Mapping[str, Any] | None = None,
    ) -> MemoryRecord:
        clean_content = content.strip()
        if not clean_content:
            raise ConfigurationError("memory content cannot be empty")
        if role not in {"user", "assistant", "system", "tool", "event"}:
            raise ConfigurationError(f"unsupported memory role: {role}")
        if not 0 <= importance <= 1:
            raise ConfigurationError("importance must be between 0 and 1")
        if approved_for_training and not reviewed:
            raise ConfigurationError("training approval requires reviewed=True")
        vector = self._embed_one(clean_content)
        memory_id = uuid4()
        query = f"""
            INSERT INTO {self._l2} (
                id, namespace, user_id, conversation_id, trace_id, role, content,
                source, importance, success, reviewed, approved_for_training,
                data_classification, metadata, embedding_model, embedding
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) RETURNING *
        """
        with self._connect() as connection:
            row = connection.execute(
                query,
                (
                    memory_id,
                    self.config.namespace,
                    self.config.user_id,
                    conversation_id,
                    trace_id,
                    role,
                    clean_content,
                    source,
                    importance,
                    success,
                    reviewed,
                    approved_for_training,
                    data_classification,
                    Jsonb(dict(metadata or {})),
                    self.embeddings.model_name,
                    vector,
                ),
            ).fetchone()
        return self._memory_record(row)

    def remember_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        source: str = "application",
        conversation_id: str = "",
        trace_id: str = "",
        importance: float = 0.5,
        success: bool = True,
        data_classification: str = "public",
        user_metadata: Mapping[str, Any] | None = None,
        assistant_metadata: Mapping[str, Any] | None = None,
    ) -> tuple[MemoryRecord, MemoryRecord]:
        """Atomically store one completed user/assistant turn.

        Observed turns intentionally start unreviewed and unapproved. Review is
        a separate action so capture cannot silently authorize training.
        """

        user_text = user_content.strip()
        assistant_text = assistant_content.strip()
        if not user_text or not assistant_text:
            raise ConfigurationError("user and assistant turn content are required")
        if not 0 <= importance <= 1:
            raise ConfigurationError("importance must be between 0 and 1")
        vectors = self._embed_many((user_text, assistant_text))
        created_at = utc_now()
        values = (
            (
                uuid4(),
                "user",
                user_text,
                Jsonb(dict(user_metadata or {})),
                vectors[0],
                created_at,
            ),
            (
                uuid4(),
                "assistant",
                assistant_text,
                Jsonb(dict(assistant_metadata or {})),
                vectors[1],
                created_at + timedelta(microseconds=1),
            ),
        )
        statement = f"""
            INSERT INTO {self._l2} (
                id, namespace, user_id, conversation_id, trace_id, role, content,
                source, importance, success, reviewed, approved_for_training,
                data_classification, metadata, embedding_model, embedding,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false, false,
                %s, %s, %s, %s, %s, %s
            ) RETURNING *
        """
        rows: list[Mapping[str, Any]] = []
        with self._connect() as connection:
            for memory_id, role, content, metadata, vector, timestamp in values:
                rows.append(
                    connection.execute(
                        statement,
                        (
                            memory_id,
                            self.config.namespace,
                            self.config.user_id,
                            conversation_id,
                            trace_id,
                            role,
                            content,
                            source,
                            importance,
                            success,
                            data_classification,
                            metadata,
                            self.embeddings.model_name,
                            vector,
                            timestamp,
                            timestamp,
                        ),
                    ).fetchone()
                )
        return self._memory_record(rows[0]), self._memory_record(rows[1])

    def recall(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: MemoryFilters | None = None,
        metric: DistanceMetric | None = None,
    ) -> list[MemoryRecord]:
        self._validate_limit(limit)
        vector = self._embed_one(query)
        selected_metric = metric or self.config.distance_metric
        operator, similarity = self._distance_sql(selected_metric, "m.embedding", "q.embedding")
        clauses, parameters = self._scope_clauses("m")
        active_filters = filters or MemoryFilters()
        if active_filters.role:
            clauses.append("m.role = %s")
            parameters.append(active_filters.role)
        if active_filters.source:
            clauses.append("m.source = %s")
            parameters.append(active_filters.source)
        if active_filters.successful_only:
            clauses.append("m.success")
        if active_filters.reviewed_only:
            clauses.append("m.reviewed")
        if active_filters.minimum_importance:
            clauses.append("m.importance >= %s")
            parameters.append(active_filters.minimum_importance)
        if active_filters.classifications:
            clauses.append("m.data_classification = ANY(%s)")
            parameters.append(list(active_filters.classifications))
        statement = f"""
            SELECT m.*, {operator} AS distance, {similarity} AS similarity
            FROM {self._l2} AS m
            CROSS JOIN (SELECT %s::vector AS embedding) AS q
            WHERE {" AND ".join(clauses)}
            ORDER BY {operator}
            LIMIT %s
        """
        with self._connect() as connection:
            rows = connection.execute(statement, [vector, *parameters, limit]).fetchall()
        return [self._memory_record(row) for row in rows]

    def list_episodes(
        self,
        *,
        conversation_id: str = "",
        trace_id: str = "",
        limit: int = 100,
    ) -> list[MemoryRecord]:
        self._validate_limit(limit, maximum=1000)
        clauses, parameters = self._scope_clauses("m")
        if conversation_id:
            clauses.append("m.conversation_id = %s")
            parameters.append(conversation_id)
        if trace_id:
            clauses.append("m.trace_id = %s")
            parameters.append(trace_id)
        statement = f"""
            SELECT m.* FROM {self._l2} AS m
            WHERE {" AND ".join(clauses)}
            ORDER BY m.created_at ASC, m.id ASC
            LIMIT %s
        """
        with self._connect() as connection:
            rows = connection.execute(statement, [*parameters, limit]).fetchall()
        return [self._memory_record(row) for row in rows]

    def mark_reviewed(self, memory_id: str, *, approved_for_training: bool = False) -> bool:
        clauses, parameters = self._scope_clauses()
        statement = f"""
            UPDATE {self._l2}
            SET reviewed = true, approved_for_training = %s, updated_at = now()
            WHERE id = %s AND {" AND ".join(clauses)}
            RETURNING id
        """
        with self._connect() as connection:
            row = connection.execute(
                statement,
                [approved_for_training, self._uuid(memory_id), *parameters],
            ).fetchone()
        return row is not None

    def delete(self, memory_id: str) -> bool:
        clauses, parameters = self._scope_clauses()
        statement = f"""
            DELETE FROM {self._l2}
            WHERE id = %s AND {" AND ".join(clauses)}
            RETURNING id
        """
        with self._connect() as connection:
            row = connection.execute(statement, [self._uuid(memory_id), *parameters]).fetchone()
        return row is not None

    def training_candidates(self, limit: int = 200) -> list[TrainingCandidate]:
        self._validate_limit(limit, maximum=5000)
        clauses, parameters = self._scope_clauses("assistant_memory")
        clauses.extend(
            [
                "assistant_memory.role = 'assistant'",
                "assistant_memory.success",
                "assistant_memory.reviewed",
                "assistant_memory.approved_for_training",
                "assistant_memory.conversation_id <> ''",
                "assistant_memory.data_classification = ANY(%s)",
            ]
        )
        parameters.append(list(self.config.training_classifications))
        statement = f"""
            SELECT
                user_memory.id AS user_memory_id,
                assistant_memory.id AS assistant_memory_id,
                user_memory.content AS instruction,
                assistant_memory.content AS output,
                assistant_memory.conversation_id,
                assistant_memory.trace_id,
                assistant_memory.data_classification,
                assistant_memory.metadata
            FROM {self._l2} AS assistant_memory
            JOIN LATERAL (
                SELECT candidate.id, candidate.content
                FROM {self._l2} AS candidate
                WHERE candidate.namespace = assistant_memory.namespace
                  AND candidate.user_id = assistant_memory.user_id
                  AND candidate.conversation_id = assistant_memory.conversation_id
                  AND candidate.role = 'user'
                  AND (candidate.created_at, candidate.id) <
                      (assistant_memory.created_at, assistant_memory.id)
                ORDER BY candidate.created_at DESC, candidate.id DESC
                LIMIT 1
            ) AS user_memory ON true
            WHERE {" AND ".join(clauses)}
            ORDER BY assistant_memory.created_at DESC, assistant_memory.id DESC
            LIMIT %s
        """
        with self._connect() as connection:
            rows = connection.execute(statement, [*parameters, limit]).fetchall()
        return [
            TrainingCandidate(
                instruction=row["instruction"],
                output=row["output"],
                conversation_id=row["conversation_id"],
                trace_id=row["trace_id"],
                source_ids=(str(row["user_memory_id"]), str(row["assistant_memory_id"])),
                data_classification=row["data_classification"],
                metadata=row["metadata"] or {},
            )
            for row in rows
        ]

    def upsert_knowledge(
        self,
        *,
        node_type: str,
        key: str,
        content: str,
        confidence: float = 1.0,
        metadata: Mapping[str, Any] | None = None,
    ) -> KnowledgeNode:
        self._validate_knowledge(node_type, key, content, confidence)
        vector = self._embed_one(content)
        with self._connect() as connection:
            row = self._upsert_knowledge(
                connection,
                node_type=node_type,
                key=key,
                content=content,
                confidence=confidence,
                metadata=metadata,
                vector=vector,
            )
        return self._knowledge_node(row)

    def link_knowledge(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        *,
        weight: float = 1.0,
        metadata: Mapping[str, Any] | None = None,
    ) -> KnowledgeEdge:
        if not relation.strip():
            raise ConfigurationError("knowledge relation cannot be empty")
        if not 0 <= weight <= 1:
            raise ConfigurationError("knowledge edge weight must be between 0 and 1")
        edge_id = uuid4()
        statement = f"""
            INSERT INTO {self._edges} (
                id, namespace, user_id, source_id, target_id, relation, weight, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (namespace, user_id, source_id, target_id, relation)
            DO UPDATE SET weight = EXCLUDED.weight, metadata = EXCLUDED.metadata
            RETURNING *
        """
        with self._connect() as connection:
            row = connection.execute(
                statement,
                (
                    edge_id,
                    self.config.namespace,
                    self.config.user_id,
                    self._uuid(source_id),
                    self._uuid(target_id),
                    relation.strip(),
                    weight,
                    Jsonb(dict(metadata or {})),
                ),
            ).fetchone()
        return self._knowledge_edge(row)

    def recall_knowledge(
        self,
        query: str,
        *,
        limit: int = 10,
        node_type: str | None = None,
        metric: DistanceMetric | None = None,
    ) -> list[KnowledgeNode]:
        self._validate_limit(limit)
        vector = self._embed_one(query)
        selected_metric = metric or self.config.distance_metric
        operator, similarity = self._distance_sql(selected_metric, "n.embedding", "q.embedding")
        clauses, parameters = self._scope_clauses("n")
        if node_type:
            clauses.append("n.node_type = %s")
            parameters.append(node_type)
        statement = f"""
            SELECT n.*, {operator} AS distance, {similarity} AS similarity
            FROM {self._nodes} AS n
            CROSS JOIN (SELECT %s::vector AS embedding) AS q
            WHERE {" AND ".join(clauses)}
            ORDER BY {operator}
            LIMIT %s
        """
        with self._connect() as connection:
            rows = connection.execute(statement, [vector, *parameters, limit]).fetchall()
        return [self._knowledge_node(row) for row in rows]

    def neighbors(
        self,
        node_id: str,
        *,
        relation: str | None = None,
        limit: int = 50,
    ) -> list[tuple[KnowledgeEdge, KnowledgeNode]]:
        self._validate_limit(limit, maximum=1000)
        clauses, parameters = self._scope_clauses("edge")
        clauses.append("edge.source_id = %s")
        parameters.append(self._uuid(node_id))
        if relation:
            clauses.append("edge.relation = %s")
            parameters.append(relation)
        statement = f"""
            SELECT
                edge.id AS edge_id, edge.namespace AS edge_namespace,
                edge.user_id AS edge_user_id, edge.source_id, edge.target_id,
                edge.relation, edge.weight, edge.metadata AS edge_metadata,
                edge.created_at AS edge_created_at,
                node.*
            FROM {self._edges} AS edge
            JOIN {self._nodes} AS node
              ON node.namespace = edge.namespace
             AND node.user_id = edge.user_id
             AND node.id = edge.target_id
            WHERE {" AND ".join(clauses)}
            ORDER BY edge.weight DESC, edge.created_at DESC
            LIMIT %s
        """
        with self._connect() as connection:
            rows = connection.execute(statement, [*parameters, limit]).fetchall()
        return [
            (
                KnowledgeEdge(
                    id=str(row["edge_id"]),
                    namespace=row["edge_namespace"],
                    user_id=row["edge_user_id"],
                    source_id=str(row["source_id"]),
                    target_id=str(row["target_id"]),
                    relation=row["relation"],
                    weight=float(row["weight"]),
                    metadata=row["edge_metadata"] or {},
                    created_at=row["edge_created_at"],
                ),
                self._knowledge_node(row),
            )
            for row in rows
        ]

    def promote_to_l3(
        self,
        memory_ids: Sequence[str],
        *,
        node_type: str,
        key: str,
        content: str,
        confidence: float = 1.0,
        metadata: Mapping[str, Any] | None = None,
    ) -> KnowledgeNode:
        if not memory_ids:
            raise ConfigurationError("L3 promotion requires at least one source memory")
        self._validate_knowledge(node_type, key, content, confidence)
        source_ids = [self._uuid(value) for value in memory_ids]
        vector = self._embed_one(content)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id FROM {self._l2}
                WHERE namespace = %s AND user_id = %s AND id = ANY(%s)
                """,
                (self.config.namespace, self.config.user_id, source_ids),
            ).fetchall()
            found = {row["id"] for row in rows}
            missing = [str(value) for value in source_ids if value not in found]
            if missing:
                raise ConfigurationError(
                    "source memories are missing from this namespace: " + ", ".join(missing)
                )
            row = self._upsert_knowledge(
                connection,
                node_type=node_type,
                key=key,
                content=content,
                confidence=confidence,
                metadata=metadata,
                vector=vector,
            )
            for memory_id in source_ids:
                connection.execute(
                    f"""
                    INSERT INTO {self._provenance} (namespace, user_id, node_id, memory_id)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (self.config.namespace, self.config.user_id, row["id"], memory_id),
                )
        return self._knowledge_node(row)

    def promote_with_extractor(
        self, memory_ids: Sequence[str], extractor: KnowledgeExtractor
    ) -> list[KnowledgeNode]:
        memories = self._memories_by_id(memory_ids)
        claims = extractor.extract(memories)
        allowed_source_ids = {memory.id for memory in memories}
        for claim in claims:
            if not claim.source_memory_ids:
                raise ConfigurationError("extracted knowledge must retain L2 provenance")
            if not set(claim.source_memory_ids) <= allowed_source_ids:
                raise ConfigurationError(
                    "knowledge extractor returned source IDs outside the requested memory set"
                )
        return [
            self.promote_to_l3(
                claim.source_memory_ids,
                node_type=claim.node_type,
                key=claim.key,
                content=claim.content,
                confidence=claim.confidence,
                metadata=claim.metadata,
            )
            for claim in claims
        ]

    def record_cycle(self, report: DreamCycleReport) -> None:
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO {self._runs} (id, namespace, user_id, session_id, status, report)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (namespace, user_id, session_id)
                DO UPDATE SET status = EXCLUDED.status, report = EXCLUDED.report
                """,
                (
                    uuid4(),
                    self.config.namespace,
                    self.config.user_id,
                    report.session_id,
                    report.status.value,
                    Jsonb(report.to_dict()),
                ),
            )

    def _memories_by_id(self, memory_ids: Sequence[str]) -> list[MemoryRecord]:
        if not memory_ids:
            return []
        values = [self._uuid(value) for value in memory_ids]
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM {self._l2}
                WHERE namespace = %s AND user_id = %s AND id = ANY(%s)
                ORDER BY created_at ASC, id ASC
                """,
                (self.config.namespace, self.config.user_id, values),
            ).fetchall()
        if len(rows) != len(set(values)):
            raise ConfigurationError("one or more source memories are outside this memory scope")
        return [self._memory_record(row) for row in rows]

    def _upsert_knowledge(
        self,
        connection: psycopg.Connection[Any],
        *,
        node_type: str,
        key: str,
        content: str,
        confidence: float,
        metadata: Mapping[str, Any] | None,
        vector: list[float],
    ) -> Mapping[str, Any]:
        statement = f"""
            INSERT INTO {self._nodes} (
                id, namespace, user_id, node_type, node_key, content, confidence,
                metadata, embedding_model, embedding
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (namespace, user_id, node_type, node_key)
            DO UPDATE SET
                content = EXCLUDED.content,
                confidence = EXCLUDED.confidence,
                metadata = EXCLUDED.metadata,
                embedding_model = EXCLUDED.embedding_model,
                embedding = EXCLUDED.embedding,
                updated_at = now()
            RETURNING *
        """
        return connection.execute(
            statement,
            (
                uuid4(),
                self.config.namespace,
                self.config.user_id,
                node_type.strip(),
                key.strip(),
                content.strip(),
                confidence,
                Jsonb(dict(metadata or {})),
                self.embeddings.model_name,
                vector,
            ),
        ).fetchone()

    def _verify_meta(self, connection: psycopg.Connection[Any], key: str, value: str) -> None:
        connection.execute(
            f"INSERT INTO {self._meta} (key, value) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (key, value),
        )
        row = connection.execute(
            f"SELECT value FROM {self._meta} WHERE key = %s", (key,)
        ).fetchone()
        if row is None or row["value"] != value:
            actual = None if row is None else row["value"]
            raise MemorySetupError(f"{key} mismatch: database={actual!r}, configured={value!r}")

    def _embed_one(self, text: str) -> list[float]:
        if not text.strip():
            raise EmbeddingError("cannot embed empty text")
        vectors = self.embeddings.embed([text])
        if len(vectors) != 1:
            raise EmbeddingError("embedding provider must return exactly one vector")
        vector = [float(value) for value in vectors[0]]
        if len(vector) != self.config.embedding_dimension:
            raise EmbeddingError(
                f"expected {self.config.embedding_dimension} embedding values, got {len(vector)}"
            )
        if not all(math.isfinite(value) for value in vector):
            raise EmbeddingError("embedding contains a non-finite value")
        return vector

    def _embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingError("cannot embed empty text")
        vectors = self.embeddings.embed(texts)
        if len(vectors) != len(texts):
            raise EmbeddingError("embedding provider returned the wrong vector count")
        normalized = [[float(value) for value in vector] for vector in vectors]
        for vector in normalized:
            if len(vector) != self.config.embedding_dimension:
                raise EmbeddingError(
                    f"expected {self.config.embedding_dimension} embedding values, "
                    f"got {len(vector)}"
                )
            if not all(math.isfinite(value) for value in vector):
                raise EmbeddingError("embedding contains a non-finite value")
        return normalized

    def _scope_clauses(self, alias: str = "") -> tuple[list[str], list[Any]]:
        prefix = f"{alias}." if alias else ""
        return (
            [f"{prefix}namespace = %s", f"{prefix}user_id = %s"],
            [self.config.namespace, self.config.user_id],
        )

    @staticmethod
    def _distance_sql(metric: DistanceMetric, value: str, query: str) -> tuple[str, str]:
        if metric is DistanceMetric.COSINE:
            distance = f"({value} <=> {query})"
            return distance, f"(1 - {distance})"
        if metric is DistanceMetric.L2:
            distance = f"({value} <-> {query})"
            return distance, f"(1 / (1 + {distance}))"
        if metric is DistanceMetric.INNER_PRODUCT:
            distance = f"({value} <#> {query})"
            return distance, f"(-1 * {distance})"
        raise ConfigurationError(f"unsupported distance metric: {metric}")

    @staticmethod
    def _validate_limit(limit: int, *, maximum: int = 200) -> None:
        if not 1 <= limit <= maximum:
            raise ConfigurationError(f"limit must be between 1 and {maximum}")

    @staticmethod
    def _validate_knowledge(node_type: str, key: str, content: str, confidence: float) -> None:
        if not node_type.strip() or not key.strip() or not content.strip():
            raise ConfigurationError("knowledge type, key, and content are required")
        if not 0 <= confidence <= 1:
            raise ConfigurationError("knowledge confidence must be between 0 and 1")

    @staticmethod
    def _uuid(value: str) -> UUID:
        try:
            return UUID(str(value))
        except ValueError as exc:
            raise ConfigurationError(f"invalid UUID: {value!r}") from exc

    @contextmanager
    def _connect(self, *, register: bool = True) -> Iterator[psycopg.Connection[Any]]:
        with psycopg.connect(self.config.dsn, row_factory=dict_row) as connection:
            if register:
                register_vector(connection)
            yield connection

    @staticmethod
    def _memory_record(row: Mapping[str, Any]) -> MemoryRecord:
        return MemoryRecord(
            id=str(row["id"]),
            namespace=row["namespace"],
            user_id=row["user_id"],
            content=row["content"],
            role=row["role"],
            source=row["source"],
            conversation_id=row["conversation_id"],
            trace_id=row["trace_id"],
            importance=float(row["importance"]),
            success=bool(row["success"]),
            reviewed=bool(row["reviewed"]),
            approved_for_training=bool(row["approved_for_training"]),
            data_classification=row["data_classification"],
            metadata=row["metadata"] or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            distance=float(row["distance"]) if row.get("distance") is not None else None,
            similarity=(float(row["similarity"]) if row.get("similarity") is not None else None),
        )

    @staticmethod
    def _knowledge_node(row: Mapping[str, Any]) -> KnowledgeNode:
        return KnowledgeNode(
            id=str(row["id"]),
            namespace=row["namespace"],
            user_id=row["user_id"],
            node_type=row["node_type"],
            key=row["node_key"],
            content=row["content"],
            confidence=float(row["confidence"]),
            metadata=row["metadata"] or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            distance=float(row["distance"]) if row.get("distance") is not None else None,
            similarity=(float(row["similarity"]) if row.get("similarity") is not None else None),
        )

    @staticmethod
    def _knowledge_edge(row: Mapping[str, Any]) -> KnowledgeEdge:
        return KnowledgeEdge(
            id=str(row["id"]),
            namespace=row["namespace"],
            user_id=row["user_id"],
            source_id=str(row["source_id"]),
            target_id=str(row["target_id"]),
            relation=row["relation"],
            weight=float(row["weight"]),
            metadata=row["metadata"] or {},
            created_at=row["created_at"],
        )
