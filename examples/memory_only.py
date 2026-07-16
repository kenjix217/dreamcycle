"""Store and retrieve L2/L3 memory with a local embedding model."""

import os

from dreamcycle.memory import (
    PostgresMemory,
    PostgresMemoryConfig,
    SentenceTransformerEmbedding,
)


def main() -> None:
    embeddings = SentenceTransformerEmbedding(os.environ["DREAMCYCLE_EMBEDDING_MODEL"])
    memory = PostgresMemory(
        PostgresMemoryConfig(
            dsn=os.environ["DREAMCYCLE_POSTGRES_DSN"],
            namespace=os.getenv("DREAMCYCLE_NAMESPACE", "local-model"),
            user_id=os.getenv("DREAMCYCLE_USER_ID", "local-user"),
            embedding_dimension=embeddings.dimension,
        ),
        embeddings,
    )
    memory.setup()
    memory.remember(
        "DreamCycle stores this episode directly in PostgreSQL.",
        role="event",
        source="memory-only-example",
    )
    for record in memory.recall("Where is the episode stored?"):
        print(record.similarity, record.content)


if __name__ == "__main__":
    main()
