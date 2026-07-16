"""Validated PostgreSQL DDL for DreamCycle-owned memory tables."""

from __future__ import annotations

import re

from dreamcycle.errors import ConfigurationError
from dreamcycle.types import DistanceMetric

SCHEMA_VERSION = "1"
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(value: str, label: str = "SQL identifier") -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ConfigurationError(f"invalid {label}: {value!r}")
    return value


def qualified(schema: str, table: str) -> str:
    validate_identifier(schema, "schema name")
    validate_identifier(table, "table name")
    return f'"{schema}"."{table}"'


def schema_statements(
    *,
    schema: str,
    embedding_dimension: int,
    distance_metric: DistanceMetric,
    create_hnsw_index: bool,
    hnsw_m: int,
    hnsw_ef_construction: int,
) -> list[str]:
    validate_identifier(schema, "schema name")

    def q(table: str) -> str:
        return qualified(schema, table)

    statements = [
        f'CREATE SCHEMA IF NOT EXISTS "{schema}"',
        f"""
        CREATE TABLE IF NOT EXISTS {q("schema_meta")} (
            key text PRIMARY KEY,
            value text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {q("l2_memories")} (
            id uuid PRIMARY KEY,
            namespace text NOT NULL,
            user_id text NOT NULL DEFAULT '',
            conversation_id text NOT NULL DEFAULT '',
            trace_id text NOT NULL DEFAULT '',
            role text NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool', 'event')),
            content text NOT NULL CHECK (length(content) > 0),
            source text NOT NULL DEFAULT 'application',
            importance double precision NOT NULL DEFAULT 0.5 CHECK (importance BETWEEN 0 AND 1),
            success boolean NOT NULL DEFAULT true,
            reviewed boolean NOT NULL DEFAULT false,
            approved_for_training boolean NOT NULL DEFAULT false,
            data_classification text NOT NULL DEFAULT 'public',
            metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            embedding_model text NOT NULL,
            embedding vector({embedding_dimension}) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (namespace, user_id, id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {q("l3_nodes")} (
            id uuid PRIMARY KEY,
            namespace text NOT NULL,
            user_id text NOT NULL DEFAULT '',
            node_type text NOT NULL,
            node_key text NOT NULL,
            content text NOT NULL CHECK (length(content) > 0),
            confidence double precision NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
            metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            embedding_model text NOT NULL,
            embedding vector({embedding_dimension}) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (namespace, user_id, node_type, node_key),
            UNIQUE (namespace, user_id, id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {q("l3_edges")} (
            id uuid PRIMARY KEY,
            namespace text NOT NULL,
            user_id text NOT NULL DEFAULT '',
            source_id uuid NOT NULL,
            target_id uuid NOT NULL,
            relation text NOT NULL,
            weight double precision NOT NULL DEFAULT 1.0 CHECK (weight BETWEEN 0 AND 1),
            metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (namespace, user_id, source_id, target_id, relation),
            FOREIGN KEY (namespace, user_id, source_id)
                REFERENCES {q("l3_nodes")} (namespace, user_id, id) ON DELETE CASCADE,
            FOREIGN KEY (namespace, user_id, target_id)
                REFERENCES {q("l3_nodes")} (namespace, user_id, id) ON DELETE CASCADE,
            CHECK (source_id <> target_id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {q("l3_provenance")} (
            namespace text NOT NULL,
            user_id text NOT NULL DEFAULT '',
            node_id uuid NOT NULL,
            memory_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (namespace, user_id, node_id, memory_id),
            FOREIGN KEY (namespace, user_id, node_id)
                REFERENCES {q("l3_nodes")} (namespace, user_id, id) ON DELETE CASCADE,
            FOREIGN KEY (namespace, user_id, memory_id)
                REFERENCES {q("l2_memories")} (namespace, user_id, id) ON DELETE RESTRICT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {q("cycle_runs")} (
            id uuid PRIMARY KEY,
            namespace text NOT NULL,
            user_id text NOT NULL DEFAULT '',
            session_id text NOT NULL,
            status text NOT NULL,
            report jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (namespace, user_id, session_id)
        )
        """,
        f"CREATE INDEX IF NOT EXISTS l2_scope_created_idx ON {q('l2_memories')} "
        "(namespace, user_id, created_at DESC)",
        f"CREATE INDEX IF NOT EXISTS l2_conversation_idx ON {q('l2_memories')} "
        "(namespace, user_id, conversation_id, created_at)",
        f"CREATE INDEX IF NOT EXISTS l2_training_idx ON {q('l2_memories')} "
        "(namespace, user_id, created_at DESC) "
        "WHERE reviewed AND approved_for_training AND success",
        f"CREATE INDEX IF NOT EXISTS l3_scope_type_idx ON {q('l3_nodes')} "
        "(namespace, user_id, node_type, updated_at DESC)",
        f"CREATE INDEX IF NOT EXISTS l3_edge_source_idx ON {q('l3_edges')} "
        "(namespace, user_id, source_id)",
        f"CREATE INDEX IF NOT EXISTS l3_edge_target_idx ON {q('l3_edges')} "
        "(namespace, user_id, target_id)",
    ]
    if create_hnsw_index:
        operator_class = {
            DistanceMetric.COSINE: "vector_cosine_ops",
            DistanceMetric.L2: "vector_l2_ops",
            DistanceMetric.INNER_PRODUCT: "vector_ip_ops",
        }[distance_metric]
        statements.extend(
            [
                f"CREATE INDEX IF NOT EXISTS l2_embedding_hnsw_idx ON {q('l2_memories')} "
                f"USING hnsw (embedding {operator_class}) "
                f"WITH (m = {hnsw_m}, ef_construction = {hnsw_ef_construction})",
                f"CREATE INDEX IF NOT EXISTS l3_embedding_hnsw_idx ON {q('l3_nodes')} "
                f"USING hnsw (embedding {operator_class}) "
                f"WITH (m = {hnsw_m}, ef_construction = {hnsw_ef_construction})",
            ]
        )
    return statements
