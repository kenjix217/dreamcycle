# DreamCycle Vendor SDK and Sidecar Plan

Status: Reviewed and approved for implementation
Target release: 0.2.0
Target license: Apache License 2.0

## 1. Objective

Make DreamCycle usable as an add-on for an existing local-model platform without
requiring that platform to adopt JintellarCore architecture or internal APIs.
Vendors can choose the least invasive integration that their platform supports:

1. OpenAI-compatible proxy: change the model endpoint URL and API key.
2. Python SDK: add explicit calls to record, retrieve, review, and run cycles.
3. Embedded library: construct DreamCycle objects directly in a Python process.

The 0.2.0 proxy supports the OpenAI Chat Completions request shape at
`POST /v1/chat/completions`. It does not claim compatibility with the complete
OpenAI API or the Responses API.

## 2. Product Boundaries

DreamCycle owns:

- L2 episodic memory in PostgreSQL with pgvector similarity search.
- L3 reviewed training memory and dataset assembly.
- Review and deletion controls.
- Dream-cycle orchestration, evaluation, adapter activation, and rollback.
- A small vendor SDK and an authenticated HTTP sidecar.
- Optional observe and retrieve proxy behavior for local model servers.

The vendor owns:

- The local model server and inference availability.
- The conversation UI and product-specific user identity.
- Consent, retention, deletion, and model-training policy.
- Selection and operation of embedding and training models.
- Network isolation and deployment of PostgreSQL and the sidecar.

DreamCycle will not depend on JintellarCore, Nervous, RuntimeCore, or any adapter
inside those repositories.

## 3. Integration Modes

### 3.1 OpenAI-Compatible Proxy

An application that already calls an OpenAI-compatible Chat Completions endpoint
can point its base URL at DreamCycle. DreamCycle forwards the original request to
the configured local model server and observes the completed turn.

- `observe`: forward the request unchanged and record successful user/assistant
  turns.
- `retrieve`: recall scoped memories and prepend clearly marked, untrusted
  reference context before forwarding; record successful turns afterward.
- Non-streaming and server-sent-event streaming responses are supported.
- A model response remains usable if memory recall or recording fails. Such a
  failure is logged and, where the response format permits, exposed as a warning.
- If the sidecar or upstream model server is unavailable, the request fails
  truthfully. DreamCycle cannot make an unavailable proxy fail open.

"Zero-code" applies only when the vendor already supports a configurable
OpenAI-compatible Chat Completions base URL and credentials. Other platforms use
the SDK or embedded library.

### 3.2 Python SDK

The synchronous `DreamCycleClient` exposes:

- health status;
- record one memory or an atomic user/assistant turn;
- scoped vector recall;
- review, approve, reject, and delete operations;
- start a cycle and poll its job status;
- inspect the active adapter and request rollback.

The SDK depends only on the sidecar HTTP contract. It does not import the
vendor's model runtime or require framework-specific plugins.

### 3.3 Embedded Library

Existing `PostgresMemory`, `DreamCycle`, trainer, evaluator, and adapter APIs
remain importable directly. HTTP dependencies stay optional so a core install
does not pull in a web framework.

## 4. Identity and Security

- Every non-health HTTP request requires a bearer API key.
- API keys map server-side to an immutable namespace and user ID.
- Request bodies cannot override namespace or user identity.
- The sidecar API key is never forwarded to the upstream model server.
- An optional, separate upstream API key is configured for that server.
- Secrets come from environment variables or the embedding application, never
  package defaults or committed configuration.
- Recalled memory is labeled as untrusted reference material, not instructions.
- Training candidates default to unreviewed and unapproved.
- L2 and L3 queries remain scoped by namespace and user ID.

Initial configuration supports one identity with `DREAMCYCLE_API_KEY`,
`DREAMCYCLE_NAMESPACE`, and `DREAMCYCLE_USER_ID`, or multiple identities using a
JSON API-key map. The simple form is the recommended local deployment.

## 5. HTTP Contract

| Route | Purpose |
|---|---|
| `GET /healthz` | Process readiness without authentication |
| `POST /v1/memory/records` | Record one L2 or L3 memory |
| `POST /v1/memory/turns` | Atomically record a user/assistant turn |
| `POST /v1/memory/search` | Search scoped memory by vector similarity |
| `POST /v1/memory/{id}/review` | Set review and approval state |
| `DELETE /v1/memory/{id}` | Delete one scoped memory |
| `POST /v1/cycles` | Queue a dream cycle |
| `GET /v1/cycles/{job_id}` | Read truthful job state and report/error |
| `GET /v1/adapters/active` | Read active adapter state |
| `POST /v1/adapters/rollback` | Roll back the active adapter |
| `POST /v1/chat/completions` | Chat Completions-compatible local proxy |

Cycle states are `queued`, `running`, `completed`, or `failed`. A queued response
never represents training success.

## 6. Module Layout

```text
src/dreamcycle/sdk/
  client.py       synchronous vendor SDK
  models.py       SDK result models

src/dreamcycle/server/
  app.py          FastAPI routes and application factory
  auth.py         API-key identity binding
  jobs.py         asynchronous cycle job state
  memory.py       identity-scoped Postgres memory resolver
  models.py       HTTP request/response schemas
  proxy.py        Chat Completions forwarding and capture
  runtime.py      environment-driven composition
  service.py      transport-independent application operations
  cli.py          dreamcycle-server entry point
```

FastAPI, Uvicorn, and HTTPX are optional dependencies. Importing `dreamcycle`
must continue to work without server, SDK, embedding, or training extras.

## 7. Proxy Data Flow

1. Authenticate the sidecar key and resolve its server-bound identity.
2. Determine a conversation ID from the DreamCycle header, DreamCycle metadata,
   request user field, or a generated UUID.
3. In retrieve mode, find the latest textual user message and recall scoped L2
   memory.
4. Add bounded untrusted reference context to a copied request.
5. Remove DreamCycle-only metadata and the incoming authorization header.
6. Add the separately configured upstream authorization, if any.
7. Forward all supported Chat Completions fields to the upstream model.
8. For a successful response, extract assistant text. For streaming, accumulate
   delta content until the stream completes.
9. Atomically record the user and assistant messages. Do not record failed or
   incomplete upstream responses as completed turns.

## 8. Local Cycle Activation

The sidecar can run memory-only until local training configuration is supplied.
When `DREAMCYCLE_BASE_MODEL` and `DREAMCYCLE_DATA_DIR` are configured, runtime
composition creates the existing Transformers/PEFT trainer, evaluator, and
adapter manager. Cycle execution runs outside the request path through the job
manager.

The first implementation uses an in-process job manager suitable for one local
sidecar instance. Job state is not durable across restarts; this limitation is
documented instead of hidden. Durable distributed workers are outside 0.2.0.

The sidecar accepts only one active cycle per server-bound identity. A second
request while a cycle is queued or running returns a conflict instead of
starting competing writes to the same adapter state.

## 9. License and Release

- Replace the unreleased MIT license with Apache License 2.0.
- Add a `NOTICE` file naming DreamCycle and its copyright holder.
- Change package metadata and classifiers to Apache-2.0.
- Record third-party dependency licenses without copying their terms into
  DreamCycle's own license.
- Bump the package version from 0.1.0 to 0.2.0.
- Preserve historical planning documents with a dated supersession note.

Because the repository has not been committed or released and has one current
copyright holder, the license change can be made before publication. Future
relicensing may require contributor permission or an appropriate contributor
agreement.

## 10. Verification

- Unit tests for API-key binding, scope isolation, SDK errors, proxy forwarding,
  retrieve injection, non-stream capture, stream capture, and memory fail-open.
- Job tests for queued/running/completed/failed state and unavailable cycles.
- PostgreSQL integration test for atomic turn storage and scoped recall.
- Import test proving core installation does not require optional HTTP/ML stacks.
- Ruff, pytest, package build, Twine metadata check, and clean-wheel import.
- License scan of direct dependencies and package artifacts.
- Coupling scan proving no JintellarCore or Nervous imports.

## 11. Explicit Non-Goals for 0.2.0

- Full OpenAI API or Responses API compatibility.
- A hosted multi-tenant control plane.
- Durable distributed cycle jobs.
- Automatic training without reviewed and approved L3 candidates.
- Framework-specific plugins for every local-model product.
- Remote cloud inference defaults.

## 12. Review Record

The implementation baseline was reviewed on 2026-07-15. Findings and required
dispositions are recorded in `VENDOR_SDK_PLAN_REVIEW.md`.
