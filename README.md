# DreamCycle

[![CI](https://github.com/kenjix217/dreamcycle/actions/workflows/ci.yml/badge.svg)](https://github.com/kenjix217/dreamcycle/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![PostgreSQL](https://img.shields.io/badge/memory-PostgreSQL%20%2B%20pgvector-336791.svg)](https://github.com/pgvector/pgvector)

## Turn local-model conversations into compounding intelligence

DreamCycle is the **memory and guarded self-improvement layer for local AI**.
It helps a model remember useful interactions, retrieve them when they matter,
turn reviewed experience into training data, challenge new adapters against a
baseline, and promote only the candidates that earn their place.

In plain English: your local model gets a memory, a learning loop, and a quality
control system without giving its data to a hosted AI platform.

```text
Record -> Recall -> Review -> Train -> Evaluate -> Promote -> Roll back
```

DreamCycle was created by **Kenny Jin** for builders who want local AI to become
more useful over time without turning production into an uncontrolled training
experiment.

> **DreamCycle is an early `0.3.0` alpha.** If memory-native, locally
> controlled AI is useful to you, try the five-minute demo and open an issue
> with the first rough edge you hit. That feedback will shape the next release.

## Why DreamCycle Exists

Local models are private and flexible, but most of them wake up with amnesia.
Conversation logs pile up, useful corrections disappear, and "fine-tune it"
often means gambling on a dataset without a promotion gate.

DreamCycle turns that loose history into a **Local Intelligence Flywheel**:

- **Memory Fabric:** PostgreSQL and pgvector store scoped L2 episodes and
  vector-searchable L3 knowledge.
- **Context Recall:** relevant experience can return to the prompt without
  replacing the vendor's model runtime.
- **Human Review Gate:** captured turns start unapproved. Training requires an
  explicit review decision.
- **Dream Dataset Forge:** approved conversations become deterministic training
  and held-out evaluation sets without splitting one conversation across both.
- **Candidate Arena:** a new adapter is measured against the baseline before it
  can become active.
- **Adapter Vault:** accepted adapters are activated atomically, with a previous
  version retained for rollback.

Training completion is not treated as model improvement. A candidate has to
pass the configured evidence gates first.

## Three Ways DreamCycle Improves Model Behavior

DreamCycle is not only a fine-tuning script. It is a behavior-improvement layer
that can help at three different depths:

- **Prompt Lift:** retrieve mode injects the right memories into the next
  request, so a local or OpenAI-compatible model gets sharper context
  immediately.
- **Local Weight Lift:** reviewed conversations become train/eval datasets for
  local LoRA adapters, with evaluation and rollback before anything becomes
  active.
- **Cloud Dataset Lift:** reviewed, scoped, provenance-backed examples can be
  exported into provider-ready training datasets when a vendor wants to
  fine-tune a cloud model through that provider's official workflow.

That means DreamCycle can improve how a cloud model is used through better
prompt context today, while keeping cloud weight updates explicit,
provider-owned, and opt-in.

## The Architecture, Without the Enterprise Jargon

DreamCycle sits beside an existing local-model application. It is not a new AI
platform that forces everything to be rebuilt around it.

```mermaid
flowchart LR
    App["Your app or agent"]
    SDK["DreamCycle Python SDK"]
    Proxy["Chat Completions proxy"]
    Memory["L2 and L3 memory fabric"]
    PG[("PostgreSQL + pgvector")]
    Model["Your local model server"]
    Cycle["Guarded dream cycle"]
    Adapter["Promoted adapter"]

    App -->|"a few SDK calls"| SDK
    App -->|"change the base URL"| Proxy
    SDK --> Memory
    Proxy --> Memory
    Memory <--> PG
    Proxy --> Model
    Memory -->|"reviewed experience"| Cycle
    Cycle -->|"evaluate, then promote"| Adapter
    Adapter -.->|"loaded by your runtime"| Model
```

There are three ways in:

1. **Drop-in proxy:** point a configurable OpenAI-compatible Chat Completions
   client at DreamCycle and keep the existing conversation code.
2. **Vendor SDK:** add explicit Python calls for record, recall, review,
   deletion, cycle jobs, and adapter control.
3. **Embedded engine:** import the memory and cycle classes directly and keep
   everything inside one Python process.

The deeper component map, request flow, memory model, cycle state machine, and
failure boundaries are in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## What Ships Today

- Direct PostgreSQL/pgvector L2 episodic memory.
- Cosine, Euclidean/L2, and inner-product retrieval.
- L3 knowledge nodes, relationships, and L2 provenance.
- Immutable API-key bindings for namespace and user isolation.
- Atomic user/assistant turn capture.
- Explicit review, approval, rejection, and deletion controls.
- A synchronous Python vendor SDK.
- An authenticated FastAPI sidecar.
- Observe and retrieve modes for `POST /v1/chat/completions`.
- Non-streaming and SSE streaming response capture.
- Asynchronous dream-cycle jobs with truthful status reporting.
- Hermes-compatible adapter status and confirmation-gated rollback commands.
- Optional local Transformers/PEFT LoRA training.
- Baseline-versus-candidate perplexity evaluation.
- Atomic adapter promotion and one-step rollback.
- Reviewed train/eval JSONL artifacts that can be adapted to cloud
  fine-tuning workflows.
- Protocols for custom trainers, evaluators, embedders, shadow tests, event
  sinks, and knowledge extractors.

DreamCycle has no JintellarCore runtime dependency, no hosted API requirement,
and no cloud-model requirement. It improves cloud-model usage through memory
and datasets, but it does not automatically call hosted fine-tuning APIs or
mutate closed-provider weights.

## What DreamCycle Is and Is Not

DreamCycle is:

- a PostgreSQL/pgvector memory layer for local AI systems;
- a review-gated dataset builder for model improvement;
- a Python SDK, sidecar API, and OpenAI-compatible proxy add-on;
- a local adapter training and promotion loop for teams that want one.

DreamCycle is not:

- a replacement for Ollama, LM Studio, llama.cpp, or a model server;
- a hosted AI service;
- a LangChain-style agent framework;
- an automatic cloud fine-tuning client;
- a promise that every remembered conversation should become training data.

## Quick Start

### Five-minute memory demo

This path does not need a downloaded embedding model or a local LLM. It starts
PostgreSQL with pgvector, records one turn, recalls it, reviews it for
training, promotes an L3 knowledge node, and prints the resulting training
candidate.

```bash
git clone https://github.com/kenjix217/dreamcycle.git
cd dreamcycle

docker compose run --rm quickstart
```

The demo compose file keeps PostgreSQL inside Docker's private network, so it
does not collide with an existing local Postgres server on `5432`.

### Install the mode you need

Core memory and orchestration:

```bash
pip install dreamcycle
```

Python vendor SDK and Hermes/agent-shell commands:

```bash
pip install 'dreamcycle[sdk]'
```

Sidecar with local embeddings:

```bash
pip install 'dreamcycle[server,embeddings]'
```

Sidecar with local LoRA training:

```bash
pip install 'dreamcycle[server,embeddings,training]'
```

### Start the sidecar

DreamCycle needs PostgreSQL with the pgvector extension enabled.

```bash
export DREAMCYCLE_POSTGRES_DSN='postgresql://dreamcycle:password@127.0.0.1/dreamcycle'
export DREAMCYCLE_EMBEDDING_MODEL='/models/all-MiniLM-L6-v2'
export DREAMCYCLE_API_KEY='replace-with-a-random-sidecar-key'
export DREAMCYCLE_NAMESPACE='my-local-model'
export DREAMCYCLE_USER_ID='local-user'

dreamcycle-server
```

The default bind is `127.0.0.1:8765`. Interactive API documentation appears at
`http://127.0.0.1:8765/docs`.

### Add memory with the SDK

```python
from dreamcycle.sdk import DreamCycleClient

with DreamCycleClient("http://127.0.0.1:8765", "sidecar-key") as client:
    user, assistant = client.record_turn(
        "How should retries be bounded?",
        "Use exponential backoff with a maximum attempt count.",
        conversation_id="conversation-42",
    )

    related = client.recall("retry strategy", limit=5)

    # Captured data cannot train anything until someone makes this decision.
    client.review(assistant.id, approved_for_training=True)
```

API keys are bound server-side to an immutable namespace and user ID. Request
bodies cannot jump to a different memory scope.

## Add Memory Without Rewriting the Vendor Platform

If the application already supports an OpenAI-compatible Chat Completions base
URL, point it at:

```text
Base URL: http://127.0.0.1:8765/v1
API key:  your DREAMCYCLE_API_KEY value
```

Then tell DreamCycle where the existing local model server lives:

```bash
export DREAMCYCLE_UPSTREAM_BASE_URL='http://127.0.0.1:11434/v1'
export DREAMCYCLE_PROXY_MODE='observe'
dreamcycle-server
```

- **Observe mode** forwards the request and records completed turns.
- **Retrieve mode** recalls scoped memory, labels it as untrusted historical
  reference data, and adds it before local inference.

```bash
export DREAMCYCLE_PROXY_MODE='retrieve'
```

The sidecar credential is never forwarded upstream. A different
`DREAMCYCLE_UPSTREAM_API_KEY` can be configured when the local model server
requires one.

This drop-in path applies to configurable Chat Completions clients. DreamCycle
does not claim compatibility with the full OpenAI API or the Responses API.

## Use DreamCycle Directly in Python

```python
import os

from dreamcycle.memory import PostgresMemory, PostgresMemoryConfig
from dreamcycle.memory import SentenceTransformerEmbedding

embeddings = SentenceTransformerEmbedding("/models/all-MiniLM-L6-v2")
memory = PostgresMemory(
    PostgresMemoryConfig(
        dsn=os.environ["DREAMCYCLE_POSTGRES_DSN"],
        namespace="my-local-model",
        user_id="developer-1",
        embedding_dimension=embeddings.dimension,
    ),
    embeddings,
)
memory.setup()

user_memory, assistant_memory = memory.remember_turn(
    "How should retries be bounded?",
    "Use exponential backoff with a maximum attempt count.",
    conversation_id="conversation-42",
)

similar = memory.recall("retry strategy", limit=5)
memory.mark_reviewed(assistant_memory.id, approved_for_training=True)
```

Set `create_vector_extension=True` only when the database role is allowed to
run `CREATE EXTENSION`. Otherwise, enable pgvector as an operator before
starting DreamCycle.

## Build Durable L3 Knowledge

L3 is a vector-searchable PostgreSQL knowledge graph with provenance back to
the original L2 memories.

```python
practice = memory.promote_to_l3(
    [user_memory.id, assistant_memory.id],
    node_type="engineering-practice",
    key="bounded-retries",
    content="Retries use exponential backoff and a maximum attempt count.",
    confidence=0.95,
)

python = memory.upsert_knowledge(
    node_type="language",
    key="python",
    content="Python application development",
)

memory.link_knowledge(practice.id, python.id, "applies-to")
knowledge = memory.recall_knowledge("resilient Python calls")
```

Automatic knowledge extractors must retain valid L2 source IDs. DreamCycle
rejects claims that cite memories outside the authenticated scope.

## Run the Guarded Dream Cycle

Enable the built-in local training path:

```bash
export DREAMCYCLE_BASE_MODEL='/models/hf/my-local-model'
export DREAMCYCLE_DATA_DIR='/var/lib/dreamcycle'
```

Then start a cycle through the SDK:

```python
job = client.start_cycle()
current = client.cycle_status(job.id)
print(current.status)
```

The HTTP job states are `queued`, `running`, `completed`, and `failed`. A
`202 Accepted` response means the cycle was queued; it does not mean training
succeeded or the candidate was promoted.

The built-in evaluator compares candidate and baseline perplexity on held-out
data. Coding, classification, tool-use, and domain products should plug in an
evaluator that measures their real target behavior.

### Control rollback from Hermes or another agent shell

Rollback already lives in the backend API. DreamCycle `0.3.0` adds a small
operator command surface that Hermes, OpenClaw, or another local agent shell can
wrap without changing the host platform:

```bash
dreamcycle-hermes status \
  --url http://127.0.0.1:8765 \
  --api-key "$DREAMCYCLE_API_KEY"
```

For machine-readable chat tools:

```bash
dreamcycle-hermes --json status
```

Rollback is deliberately confirmation-gated. The command refuses to mutate the
active adapter unless the operator has already approved it:

```bash
dreamcycle-hermes rollback
# refuses and explains that confirmation is required

dreamcycle-hermes rollback --confirm
# restores the previous promoted adapter
```

Hermes can map this cleanly to natural-language controls:

```text
"Show me the active DreamCycle adapter." -> dreamcycle-hermes status
"Roll back to the previous adapter."    -> ask for confirmation, then rollback --confirm
```

Python wrappers can import the same surface:

```python
from dreamcycle.hermes.plugin import rollback, status

print(status())
print(rollback(confirm=True))
```

The intended flow is:

```text
Hermes conversation
-> DreamCycle stores the turn
-> relevant memories are recalled later
-> selected records are reviewed
-> approved records become a dataset
-> optional LoRA candidate is trained
-> candidate is evaluated
-> candidate is promoted or rejected
-> previous adapter remains available for confirmed rollback
```

## Bring Your Own Model Stack

DreamCycle is built around ordinary Python protocols, not one training vendor.

```python
class MyTrainer:
    async def train(self, dataset_path, eval_path, output_path): ...


class MyEvaluator:
    async def evaluate(self, adapter_path, eval_path): ...
```

Return `TrainingResult` and `EvaluationResult` from `dreamcycle`. This leaves
room for MLX, Unsloth, llama.cpp adapter pipelines, custom PyTorch code, and
other local training stacks without pulling those frameworks into the core.

## Cloud Models Without Cloud Lock-In

DreamCycle can sit in front of any OpenAI-compatible endpoint. In retrieve mode,
the model receives a bounded memory packet as context, which can make hosted or
local responses more consistent without changing the underlying model.

For actual cloud fine-tuning, DreamCycle should be treated as the dataset and
governance layer. It records turns, keeps review decisions, preserves source
provenance, and can feed approved examples into whatever fine-tuning workflow a
provider officially supports. The hosted provider still owns upload, training,
deployment, billing, and model-version policy.

## Safety Is Part of the Product

- Captured turns start unreviewed and unapproved.
- Every memory query includes namespace and user scope.
- SQL values use bound parameters and schema identifiers are validated.
- L3 edges and provenance enforce scope with composite foreign keys.
- Local model paths are the default; remote model download is opt-in.
- Failed data preparation, training, evaluation, or promotion cannot become a
  fake success report.
- A failed memory lookup does not discard an otherwise successful proxied model
  response.
- Interrupted streams are not stored as completed assistant turns.
- Adapter promotion uses an atomic pointer and preserves a rollback target.

Applications still own consent, retention, deletion, database security, model
licensing, and the right to train on collected data.

## Project Status and Roadmap

DreamCycle is ready for local evaluation as an alpha project. The most useful
next community contributions are:

- adapters and examples for popular local model servers;
- task-specific quality evaluators;
- an asynchronous vendor SDK;
- durable distributed cycle jobs;
- more embedding and training backends;
- real-world compatibility reports.

## Development

```bash
git clone https://github.com/kenjix217/dreamcycle.git
cd dreamcycle
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'

.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
```

Set `DREAMCYCLE_TEST_DSN` to run the PostgreSQL integration tests. They create
and remove uniquely named schemas.

## Origin

DreamCycle was extracted and rewritten from Dream Engine work originally
developed by **Kenny Jin**. The standalone project removes all JintellarCore
runtime dependencies and connects directly to PostgreSQL.

## License

Copyright 2026 **Kenny Jin**.

Licensed under the Apache License 2.0. See [`LICENSE`](LICENSE) and
[`NOTICE`](NOTICE). Direct dependency licenses are summarized in
[`THIRD_PARTY.md`](THIRD_PARTY.md).
