"""Run LoRA training against reviewed PostgreSQL memories."""

import asyncio
import os
from pathlib import Path

from dreamcycle import (
    AdapterManager,
    DatasetBuilder,
    DatasetBuilderConfig,
    DreamCycle,
    DreamCycleConfig,
)
from dreamcycle.memory import (
    PostgresMemory,
    PostgresMemoryConfig,
    SentenceTransformerEmbedding,
)
from dreamcycle.training import (
    TransformersEvaluationConfig,
    TransformersLoRAConfig,
    TransformersLoRATrainer,
    TransformersPerplexityEvaluator,
)


async def run() -> None:
    root = Path(os.getenv("DREAMCYCLE_DATA_DIR", "./dreamcycle-data")).resolve()
    base_model = Path(os.environ["DREAMCYCLE_BASE_MODEL"]).resolve()
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

    cycle = DreamCycle(
        config=DreamCycleConfig(candidate_adapter_dir=root / "candidates"),
        dataset_builder=DatasetBuilder(memory, DatasetBuilderConfig(output_dir=root / "datasets")),
        trainer=TransformersLoRATrainer(TransformersLoRAConfig(base_model_path=base_model)),
        evaluator=TransformersPerplexityEvaluator(
            TransformersEvaluationConfig(base_model_path=base_model)
        ),
        adapter_manager=AdapterManager(
            candidate_root=root / "candidates", active_root=root / "active"
        ),
        recorder=memory,
    )
    report = await cycle.run()
    print(report.to_dict())


if __name__ == "__main__":
    asyncio.run(run())
