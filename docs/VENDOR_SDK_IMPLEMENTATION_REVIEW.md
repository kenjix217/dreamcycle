# DreamCycle Vendor SDK Implementation Review

Date: 2026-07-15
Release candidate: 0.2.0
Decision: Ready for an independent Apache-2.0 GitHub alpha release

## Scope Result

The implementation is contained in `/home/ken/dreamcycle`. It adds no route,
adapter, migration, configuration, import, or architecture change to Nervous or
JintellarCore.

The release now contains:

- direct PostgreSQL/pgvector L2 and L3 memory;
- atomic unreviewed user/assistant turn capture;
- a synchronous Python vendor SDK;
- an authenticated sidecar with server-bound identity scopes;
- an observe/retrieve Chat Completions proxy with SSE support;
- asynchronous cycle jobs and adapter status/rollback routes;
- optional local Transformers/PEFT runtime composition;
- Apache-2.0 package metadata, `LICENSE`, and `NOTICE`;
- vendor documentation, examples, tests, and CI gates.

## Review Findings Fixed

### 1. Completed streams could miss capture on immediate disconnect

The first implementation recorded after the upstream iterator ended. A client
that closed as soon as it read `[DONE]` could cancel the generator first.
Capture now occurs before yielding the chunk containing `[DONE]`, with a
regression test that closes immediately after that chunk.

### 2. Python 3.10 could reject UTC `Z` timestamps

SDK parsing used `datetime.fromisoformat` directly. The parser now normalizes a
trailing `Z` to `+00:00`, and SDK fixtures use `Z` timestamps.

### 3. The core-only console command imported FastAPI too early

Python loads a package initializer before a submodule. The server initializer
was eager, so `dreamcycle-server` could raise a raw missing-FastAPI error before
the CLI provided install guidance. Server exports are now lazy and verified in
a clean wheel environment.

### 4. Invalid training paths were discovered on the first request

Per-identity cycle objects are now composed during sidecar startup when local
training is configured. Invalid base-model or dataset settings prevent startup
instead of becoming a misleading request-time client error.

### 5. Fresh pgvector images do not automatically enable the extension

CI now explicitly creates the vector extension in its dedicated test database.
Runtime behavior remains operator-controlled through
`DREAMCYCLE_CREATE_VECTOR_EXTENSION`.

### 6. Upstream connection failures returned a generic server error

Failures before an upstream response now map to a bounded `502` response.
Upstream HTTP status, body, and safe response headers remain preserved once a
response exists.

### 7. Cancelled cycle tasks could remain marked running

Cancellation now records a failed terminal state before task cleanup. Job state
is still intentionally in process and non-durable in 0.2.0.

### 8. Legal files needed artifact-level verification

The build declares both `LICENSE` and `NOTICE` as license files. CI opens the
wheel and sdist, verifies both files are present, and checks the
`License-Expression: Apache-2.0` metadata.

## Acceptance Evidence

- Full pytest gate passes with a disposable PostgreSQL 16 + pgvector database.
- Ruff lint and formatting checks pass.
- Two live Uvicorn listeners verify sidecar auth, retrieve injection, separate
  upstream credentials, non-stream capture, and SSE capture over TCP.
- Twine accepts both wheel and sdist.
- A clean wheel install proves core imports do not load HTTP or ML extras.
- The core-only console command reports the correct server/embedding extra.
- AST inspection proves there are no JintellarCore, Nervous, or `core.*`
  runtime imports.
- Built artifacts include Apache-2.0 metadata, `LICENSE`, and `NOTICE`.

## Residual Risks and Limits

- Compatibility is limited to `POST /v1/chat/completions`; local servers can
  still vary in undocumented ways.
- The sidecar is an additional availability hop. Memory failures are isolated,
  but a stopped sidecar cannot proxy inference.
- Cycle jobs and same-identity locks are process-local and do not coordinate
  multiple sidecar replicas.
- The sidecar has no built-in TLS termination, rate limiting, or dynamic key
  reload. Operators must add those controls when exposing it beyond loopback.
- The full Transformers/PEFT training path was not run with real model weights,
  GPU hardware, and production data in this environment. Its dependency and
  boundary tests pass, but model-specific validation remains an operator task.
- The live database test uses a deterministic test embedder; loading a specific
  Sentence Transformers model remains deployment-specific.
- SDK 0.2.0 is synchronous. Async SDK support is a future compatibility slice.
- Consent, retention, deletion, model licensing, and permission to train remain
  the adopting vendor's responsibilities.
- Apache-2.0 is an engineering and product recommendation, not legal advice.

## Release Decision

The repository is suitable for an independent GitHub alpha release after the
owner reviews public naming, contact details, and repository visibility. It has
not been committed, pushed, or published by this implementation run.
