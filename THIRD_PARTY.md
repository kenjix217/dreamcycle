# Third-Party Dependencies

DreamCycle source is Apache-2.0 licensed. Its declared direct dependencies remain
separate packages under their own licenses:

| Package | Use | License |
|---|---|---|
| pgvector | Python vector type integration | MIT |
| Psycopg | PostgreSQL driver | LGPL-3.0-only |
| Sentence Transformers | Optional local embeddings | Apache-2.0 |
| Transformers | Optional local model training | Apache-2.0 |
| PEFT | Optional LoRA adapters | Apache-2.0 |
| PyTorch | Optional tensor and training runtime | BSD-3-Clause |
| Accelerate | Optional training runtime support | Apache-2.0 |
| FastAPI | Optional sidecar API framework | MIT |
| HTTPX | Optional SDK and proxy HTTP client | BSD-3-Clause |
| Uvicorn | Optional sidecar ASGI server | BSD-3-Clause |

Development dependencies are not distributed as part of DreamCycle. Before a
release, dependency license metadata should be rechecked against the exact
resolved versions.
