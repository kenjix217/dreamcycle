"""Five-minute DreamCycle demo: record, recall, review, and promote memory.

Run PostgreSQL first:
    docker compose run --rm quickstart

Or run this file directly against your own PostgreSQL/pgvector database by
setting DREAMCYCLE_POSTGRES_DSN.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections.abc import Sequence

from dreamcycle.memory import CallableEmbeddingProvider, PostgresMemory, PostgresMemoryConfig

DIMENSION = 16
DEFAULT_DSN = "postgresql://dreamcycle:dreamcycle@127.0.0.1:5432/dreamcycle"
TOKEN_RE = re.compile(r"[a-z0-9]+")


def embed(texts: Sequence[str]) -> list[list[float]]:
    """Tiny deterministic embedding for the quickstart.

    This is deliberately dependency-free so the first demo does not need a
    downloaded embedding model. Real applications should use their own embedder
    or `SentenceTransformerEmbedding`.
    """

    vectors: list[list[float]] = []
    for text in texts:
        vector = [0.0] * DIMENSION
        for token in TOKEN_RE.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
            index = digest[0] % DIMENSION
            vector[index] += 1.0 + (digest[1] % 3)
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        vectors.append([value / norm for value in vector])
    return vectors


def main() -> None:
    embeddings = CallableEmbeddingProvider(
        embed,
        dimension=DIMENSION,
        model_name="dreamcycle-demo-hash-embedding",
    )
    memory = PostgresMemory(
        PostgresMemoryConfig(
            dsn=os.getenv("DREAMCYCLE_POSTGRES_DSN", DEFAULT_DSN),
            namespace=os.getenv("DREAMCYCLE_NAMESPACE", "quickstart"),
            user_id=os.getenv("DREAMCYCLE_USER_ID", "hn-demo"),
            schema=os.getenv("DREAMCYCLE_SCHEMA", "dreamcycle_quickstart"),
            embedding_dimension=embeddings.dimension,
            create_vector_extension=True,
            create_hnsw_index=False,
        ),
        embeddings,
    )
    memory.setup()

    user, assistant = memory.remember_turn(
        "How should retry logic work for a flaky local model server?",
        "Use exponential backoff, cap the attempts, and keep the last failure reason.",
        conversation_id="five-minute-demo",
        source="quickstart",
    )
    reviewed = memory.mark_reviewed(assistant.id, approved_for_training=True)

    knowledge = memory.promote_to_l3(
        [user.id, assistant.id],
        node_type="engineering-practice",
        key="bounded-retries",
        content="Retry flaky local model calls with exponential backoff and a maximum attempt cap.",
        confidence=0.95,
    )

    print("Recorded L2 turn:")
    print(f"  user      {user.id}")
    print(f"  assistant {assistant.id} review_accepted={reviewed}")
    print()
    print("Recall for 'retry model server':")
    for record in memory.recall("retry model server", limit=3):
        print(f"  {record.role:<9} score={record.similarity:.3f} {record.content}")
    print()
    print("Promoted L3 knowledge:")
    print(f"  {knowledge.node_type}:{knowledge.key} confidence={knowledge.confidence:.2f}")
    print()
    print("Training candidates after review:")
    for candidate in memory.training_candidates(limit=3):
        print(f"  instruction={candidate.instruction!r}")
        print(f"  output={candidate.output!r}")


if __name__ == "__main__":
    main()
