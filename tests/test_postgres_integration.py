import os
from uuid import uuid4

import psycopg
import pytest

from dreamcycle.memory import CallableEmbeddingProvider, PostgresMemory, PostgresMemoryConfig
from dreamcycle.types import DistanceMetric

TEST_DSN = os.getenv("DREAMCYCLE_TEST_DSN")
pytestmark = pytest.mark.skipif(not TEST_DSN, reason="DREAMCYCLE_TEST_DSN is not set")


def embedding(texts):
    return [[float(len(text) % 7), float(sum(map(ord, text)) % 11), 1.0] for text in texts]


@pytest.fixture
def stores():
    schema = f"dreamcycle_test_{uuid4().hex[:12]}"
    provider = CallableEmbeddingProvider(embedding, dimension=3, model_name="integration-test")
    first = PostgresMemory(
        PostgresMemoryConfig(
            dsn=TEST_DSN,
            namespace="first",
            embedding_dimension=3,
            schema=schema,
            create_vector_extension=False,
        ),
        provider,
    )
    second = PostgresMemory(
        PostgresMemoryConfig(
            dsn=TEST_DSN,
            namespace="second",
            embedding_dimension=3,
            schema=schema,
            create_vector_extension=False,
        ),
        provider,
    )
    first.setup()
    second.setup()
    try:
        yield first, second
    finally:
        with psycopg.connect(TEST_DSN, autocommit=True) as connection:
            connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_l2_l3_and_namespace_isolation(stores):
    first, second = stores
    user = first.remember("How do I test this?", role="user", conversation_id="one")
    assistant = first.remember(
        "Use a focused test.",
        role="assistant",
        conversation_id="one",
        reviewed=True,
        approved_for_training=True,
    )
    second.remember("private second namespace", role="assistant")

    for metric in DistanceMetric:
        recalled = first.recall("focused test", metric=metric)
        assert recalled
        assert {record.namespace for record in recalled} == {"first"}

    candidates = first.training_candidates()
    assert len(candidates) == 1
    assert candidates[0].source_ids == (user.id, assistant.id)

    node = first.promote_to_l3(
        [user.id, assistant.id],
        node_type="practice",
        key="focused-tests",
        content="Use focused tests for behavior changes.",
    )
    related = first.upsert_knowledge(
        node_type="tool", key="pytest", content="pytest runs Python tests"
    )
    second_node = second.upsert_knowledge(
        node_type="private", key="second-only", content="second namespace knowledge"
    )
    edge = first.link_knowledge(node.id, related.id, "uses")
    assert edge.namespace == "first"
    assert first.neighbors(node.id)[0][1].id == related.id
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        first.link_knowledge(node.id, second_node.id, "must-not-cross-scope")
    assert {item.id for item in second.recall_knowledge("focused tests")} == {second_node.id}


def test_atomic_turn_order_and_training_review_boundary(stores):
    first, _ = stores
    user, assistant = first.remember_turn(
        "What did we decide?",
        "Keep captured turns unapproved.",
        conversation_id="atomic-turn",
        trace_id="trace-1",
    )

    assert user.role == "user"
    assert assistant.role == "assistant"
    assert user.created_at < assistant.created_at
    assert not assistant.reviewed
    assert not assistant.approved_for_training
    assert first.training_candidates() == []

    assert first.mark_reviewed(assistant.id, approved_for_training=True)
    candidates = first.training_candidates()
    assert len(candidates) == 1
    assert candidates[0].source_ids == (user.id, assistant.id)
