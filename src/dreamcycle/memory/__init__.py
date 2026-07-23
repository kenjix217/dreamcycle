"""Direct L2/L3 memory APIs."""

from dreamcycle.memory.base import EmbeddingProvider, KnowledgeExtractor, MemoryFilters
from dreamcycle.memory.embeddings import CallableEmbeddingProvider, SentenceTransformerEmbedding
from dreamcycle.memory.postgres import PostgresMemory, PostgresMemoryConfig
from dreamcycle.types import (
    DistanceMetric,
    KnowledgeClaim,
    KnowledgeEdge,
    KnowledgeNode,
    KnowledgeStats,
    MemoryRecord,
)

__all__ = [
    "CallableEmbeddingProvider",
    "DistanceMetric",
    "EmbeddingProvider",
    "KnowledgeClaim",
    "KnowledgeEdge",
    "KnowledgeExtractor",
    "KnowledgeNode",
    "KnowledgeStats",
    "MemoryFilters",
    "MemoryRecord",
    "PostgresMemory",
    "PostgresMemoryConfig",
    "SentenceTransformerEmbedding",
]
