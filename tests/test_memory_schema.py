import math

import pytest

from dreamcycle.errors import ConfigurationError, EmbeddingError
from dreamcycle.memory import CallableEmbeddingProvider, PostgresMemory, PostgresMemoryConfig
from dreamcycle.memory.schema import schema_statements, validate_identifier
from dreamcycle.types import DistanceMetric


def embed(texts):
    return [[float(len(text)), 1.0, 0.0] for text in texts]


def memory(metric=DistanceMetric.COSINE):
    provider = CallableEmbeddingProvider(embed, dimension=3, model_name="test-embedding")
    config = PostgresMemoryConfig(
        dsn="postgresql://user:secret@localhost/database",
        namespace="tenant-a",
        user_id="user-a",
        embedding_dimension=3,
        distance_metric=metric,
    )
    return PostgresMemory(config, provider)


def test_config_repr_does_not_expose_dsn():
    config = memory().config
    assert "secret" not in repr(config)


def test_schema_rejects_untrusted_identifier():
    with pytest.raises(ConfigurationError, match="invalid schema"):
        validate_identifier("public; DROP SCHEMA public", "schema name")


def test_schema_contains_scope_and_composite_foreign_keys():
    statements = "\n".join(
        schema_statements(
            schema="dreamcycle",
            embedding_dimension=3,
            distance_metric=DistanceMetric.COSINE,
            create_hnsw_index=True,
            hnsw_m=16,
            hnsw_ef_construction=64,
        )
    )

    assert "vector(3)" in statements
    assert "vector_cosine_ops" in statements
    assert "FOREIGN KEY (namespace, user_id, source_id)" in statements
    assert "FOREIGN KEY (namespace, user_id, memory_id)" in statements
    assert "approved_for_training" in statements


@pytest.mark.parametrize(
    ("metric", "operator"),
    [
        (DistanceMetric.COSINE, "<=>"),
        (DistanceMetric.L2, "<->"),
        (DistanceMetric.INNER_PRODUCT, "<#>"),
    ],
)
def test_all_distance_metrics_have_pgvector_operators(metric, operator):
    distance, similarity = PostgresMemory._distance_sql(metric, "value", "query")
    assert operator in distance
    assert operator in similarity


def test_embedding_dimension_must_match_config():
    provider = CallableEmbeddingProvider(embed, dimension=3, model_name="test")
    config = PostgresMemoryConfig(
        dsn="postgresql://localhost/test",
        namespace="tenant",
        embedding_dimension=4,
    )

    with pytest.raises(ConfigurationError, match="dimension"):
        PostgresMemory(config, provider)


def test_non_finite_embedding_is_rejected_before_database_io():
    provider = CallableEmbeddingProvider(
        lambda texts: [[math.nan, 0.0, 0.0] for _ in texts],
        dimension=3,
        model_name="bad",
    )
    store = PostgresMemory(
        PostgresMemoryConfig(
            dsn="postgresql://localhost/test",
            namespace="tenant",
            embedding_dimension=3,
        ),
        provider,
    )

    with pytest.raises(EmbeddingError, match="non-finite"):
        store._embed_one("content")


def test_turn_requires_both_messages_before_database_io():
    with pytest.raises(ConfigurationError, match="user and assistant"):
        memory().remember_turn("question", " ")
