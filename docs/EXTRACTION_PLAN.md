# DreamCycle Standalone Extraction Plan

Status: Implemented and verified
Date: 2026-07-16
Project root: `/home/ken/dreamcycle`
Python import: `dreamcycle`
License: MIT

> Superseded for the unreleased 0.2.0 baseline on 2026-07-15: the standalone
> project is now Apache-2.0 licensed. See `VENDOR_SDK_PLAN.md`.
Copyright holder: Kenny Jin

## 1. Objective

Create an independent Python project that extracts the reusable Dream Cycle
ideas and code from JintellarCore without changing JintellarCore or requiring
JintellarCore, Nervous RuntimeCore, Brain, Muscle, or Integration Hub at
runtime.

The package must let another developer:

1. connect directly to PostgreSQL with the pgvector extension;
2. store and retrieve L2 semantic/episodic memory;
3. maintain L3 durable knowledge nodes and relationships;
4. build reviewed local training datasets from memory;
5. run a guarded dream cycle around a local model trainer;
6. benchmark, reject, promote, and roll back adapters through Python APIs; and
7. replace the built-in components with their own implementations through
   small Python protocols.

## 2. Hard Boundaries

- Do not edit `/home/ken/nervous`.
- Do not add a JintellarCore adapter or compatibility layer.
- Do not import from `core.brain`, `core.nervous`, or any other JintellarCore
  package.
- Do not copy credentials, local data, model files, runtime configuration, or
  tenant records.
- Do not claim that a model is improved merely because training completed.
  Promotion requires explicit benchmark and shadow gates.
- Keep model training optional so memory-only users do not install GPU stacks.

## 3. Source Extraction Map

| JintellarCore source | Standalone destination | Treatment |
|---|---|---|
| `core/brain/dream/cycle_runner.py` | `src/dreamcycle/cycle.py` | Copy orchestration behavior; replace operation constants and emitter coupling with public events and hooks. |
| `core/brain/dream/cycle_payload.py` | `src/dreamcycle/results.py` | Copy serialization behavior; expose typed cycle reports. |
| `core/brain/dream/types.py` | `src/dreamcycle/types.py` | Copy and expand public result/config types. |
| `core/brain/dream/lora_dataset_builder.py` | `src/dreamcycle/dataset.py` | Preserve deterministic train/eval split and manifest; replace Nervous candidate query with repository protocols. |
| `core/brain/dream/golden_path_extractor.py` | `src/dreamcycle/dataset.py` | Preserve user/assistant pair extraction; use standalone memory records. |
| `core/brain/dream/evaluation.py` | `src/dreamcycle/evaluation.py` | Keep gate calculations; make evaluators callable protocols. |
| `core/brain/dream/adapter_promotion.py` | `src/dreamcycle/adapters.py` | Keep filesystem promotion and rollback state; remove RuntimeCore requests. |
| `core/brain/dream/training_pipeline.py` | `src/dreamcycle/training/` | Keep orchestration; add a real optional Transformers/PEFT LoRA trainer. |
| `core/brain/memory/l2_postgres_adapter.py` | `src/dreamcycle/memory/postgres.py` | Rewrite completely for direct psycopg/pgvector access. |
| Nervous/Brain request emitters and config | none | Exclude. Public hooks and environment-neutral config replace them. |

Copied and adapted files will carry a short provenance comment. Git history for
the new repository begins independently; the README will state that the first
release was extracted from the author's JintellarCore Dream Engine work.

## 4. Public Package Shape

```text
dreamcycle/
  LICENSE
  README.md
  CHANGELOG.md
  CONTRIBUTING.md
  SECURITY.md
  pyproject.toml
  src/dreamcycle/
    __init__.py
    cycle.py
    dataset.py
    events.py
    evaluation.py
    adapters.py
    types.py
    memory/
      __init__.py
      base.py
      postgres.py
      schema.py
      embeddings.py
    training/
      __init__.py
      base.py
      transformers.py
  examples/
    basic_cycle.py
    memory_only.py
  tests/
```

The top-level import should support this shape:

```python
from dreamcycle import DreamCycle, DreamCycleConfig
from dreamcycle.memory import PostgresMemory, PostgresMemoryConfig
from dreamcycle.training import TransformersLoRATrainer
```

## 5. Direct PostgreSQL and pgvector Design

### Connection and setup

- Use `psycopg` 3 and `pgvector` as the only required database dependencies.
- Accept a DSN through constructor/config; never log it or persist it.
- Validate SQL schema/table identifiers before interpolation.
- Use bound parameters for all record values.
- `PostgresMemory.setup()` creates owned tables and indexes. Extension creation
  is controlled by `create_vector_extension`; operators without extension
  privileges can install pgvector separately and disable that step. Importing
  the package never mutates a database.
- Embedding dimension is configured at setup and verified on later startups.
- Each `PostgresMemory` instance is permanently bound to a required
  `namespace`; record methods do not accept a namespace override. Optional
  `user_id` provides finer isolation inside that namespace.
- One configured HNSW operator class is indexed. All three distance modes remain
  available, with non-indexed modes using exact scans unless the operator adds
  another index.

### L2 semantic/episodic memory

The L2 table stores content, role, source, conversation ID, trace ID,
importance, success/review/training-approval flags, data classification,
metadata, embedding model, vector, timestamps, and stable IDs. APIs:

- `remember(...)`
- `recall(query, limit, filters)` using cosine, L2, or inner-product distance
- `list_episodes(...)`
- `mark_reviewed(...)`
- `training_candidates(...)`
- `delete(...)`

The caller supplies an embedding provider. A Sentence Transformers provider is
available through an optional dependency; a deterministic fake embedder exists
only in tests.

### L3 durable knowledge graph

L3 uses PostgreSQL tables rather than requiring Apache AGE:

- nodes: namespace, type, key, content, metadata, confidence, vector;
- edges: namespace, source node, target node, relation, weight, metadata;
- source links: L2 memory IDs used to derive each L3 node.

APIs:

- `upsert_knowledge(...)`
- `link_knowledge(...)`
- `recall_knowledge(...)`
- `neighbors(...)`
- `promote_to_l3(memory_ids, ...)`

Foreign keys and namespace checks prevent cross-namespace graph links.
Automatic consolidation requires a caller-supplied `KnowledgeExtractor`
protocol that returns typed claims and relationships. Without an extractor,
`promote_to_l3` requires explicit node content and type from the caller; the
package does not silently relabel raw episodes as facts.

## 6. Dream Cycle Contract

`DreamCycle.run()` executes these phases:

1. select reviewed/successful L2 memories and optional L3 knowledge;
2. build deterministic train and held-out evaluation JSONL files;
3. train a candidate adapter through the trainer protocol;
4. benchmark candidate and baseline through the evaluator protocol;
5. reject regressions using configured score, error, and latency limits;
6. optionally run a caller-supplied shadow evaluator;
7. atomically promote the accepted adapter while preserving the previous one;
8. write the cycle result and selected durable findings back to memory; and
9. return a typed `DreamCycleReport` with every phase outcome.

The cycle is async, but database methods are synchronous first. The cycle calls
them through `asyncio.to_thread` so database I/O does not block the event loop;
a native async database API is deferred until a real consumer requires it.

## 7. Local Training

The core package defines `Trainer`, `Evaluator`, `EmbeddingProvider`,
`KnowledgeExtractor`, and `EventSink` protocols. The optional `training` extra
provides a working Transformers/PEFT LoRA trainer and perplexity evaluator that:

- loads a local Hugging Face causal-language-model directory;
- refuses remote model downloads by default;
- tokenizes instruction/output JSONL records;
- masks prompt tokens from the loss;
- trains a PEFT LoRA adapter with explicit hyperparameters;
- saves adapter, tokenizer metadata, and a training manifest; and
- returns structured metrics or raises a typed error.

The evaluator scores both the unchanged base model and candidate adapter on the
held-out split. Its result drives the default quality gate; callers can replace
it with task-specific evaluators.

CUDA availability is detected by PyTorch. CPU training remains possible for
small test models but is not represented as production-friendly.

## 8. Events, Errors, and Safety

- Events are local typed records delivered to zero or more caller callbacks.
- Event callback failure is recorded but does not silently change gate results.
- Database errors, invalid embeddings, empty datasets, failed training, and
  failed evaluation produce explicit typed exceptions or failed phase results.
- Adapter promotion is atomic within one filesystem and uses a standard-library
  lock file with bounded stale-lock recovery to prevent overlapping promotions
  without adding a runtime dependency.
- Paths are resolved and constrained to configured dataset/adapter roots.
- Training data exports include source IDs and classifications in metadata;
  callers can filter classifications before export.
- Examples use environment variables for DSNs and contain no secrets.

## 9. Packaging and Licensing

- Distribution and import name: `dreamcycle`. The PyPI project URL returned 404
  during the 2026-07-16 review; availability must be checked again immediately
  before publishing because names are not reserved by this plan.
- Initial version: `0.1.0`.
- Python: 3.10 through 3.13.
- Build backend: Hatchling or setuptools, chosen for minimal build complexity.
- Dependency review: pgvector is MIT; Transformers and PEFT are Apache-2.0;
  Psycopg is LGPL-3.0-only and remains a separately installed database-driver
  dependency. No dependency is copied into this repository and no AGPL
  dependency is allowed.
- Heavy ML dependencies are optional extras.
- Include MIT `LICENSE`, project classifiers, typed package marker, changelog,
  contribution guide, security policy, and source distribution exclusions.
- Initialize a new Git repository, but do not configure a remote, commit, push,
  publish to PyPI, or create GitHub resources without a later explicit request.

## 10. Tests and Acceptance Gates

Unit tests must cover:

- cycle success, no-data skip, training failure, benchmark rejection, shadow
  rejection, promotion failure, and noncritical event failure;
- deterministic dataset split and no train/eval source overlap;
- embedding dimension validation and SQL identifier validation;
- namespace isolation in every L2 and L3 query;
- L2 distance selection for cosine, Euclidean/L2, and inner product;
- L3 node upsert, relationship constraints, neighbors, and L2 provenance;
- atomic adapter promotion and rollback;
- package import without ML extras; and
- optional trainer dependency errors that identify the missing extra; and
- local wheel and source-distribution builds.

PostgreSQL integration tests run when `DREAMCYCLE_TEST_DSN` is set and otherwise
skip explicitly. Unit tests use repository fakes, never a fake production
database implementation.

Acceptance commands:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
```

Final audit checks:

```bash
rg -n 'core\.brain|core\.nervous|jintellarcore|NervousClient' src tests examples
git status --short
```

The coupling scan may find `JintellarCore` only in provenance documentation,
never in runtime imports.

## 11. Delivery Sequence

1. Review this plan and revise any ambiguous or unsafe boundary.
2. Scaffold metadata and package modules.
3. Implement typed protocols, events, results, and cycle orchestration.
4. Implement direct PostgreSQL L2/L3 memory.
5. Implement datasets and adapter lifecycle.
6. Implement optional Transformers/PEFT trainer.
7. Add examples and public documentation.
8. Add unit and optional PostgreSQL integration tests.
9. Build distributions, run all tests, and perform a hostile coupling/release
   audit.

## 12. Explicit Non-Goals for 0.1.0

- No JintellarCore integration or adapter.
- No hosted service, REST API, dashboard, scheduler, or background daemon.
- No automatic upload to model hubs.
- No automatic cloud model or embedding calls.
- No distributed training.
- No promise that training improves a model without evaluator evidence.
- No schema migration framework beyond idempotent versioned setup metadata.
