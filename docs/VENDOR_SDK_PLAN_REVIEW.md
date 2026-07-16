# DreamCycle Vendor SDK Plan Review

Date: 2026-07-15
Reviewed plan: `VENDOR_SDK_PLAN.md`
Decision: Approved for implementation after revision

## Findings

### 1. "Zero-code" was too broad

Risk: A platform without a configurable OpenAI-compatible Chat Completions
endpoint still needs an integration change.

Disposition: The plan now limits zero-code deployment to platforms that can
change their endpoint URL and credentials. All others use the SDK or embedded
library.

### 2. Sidecar credentials could leak upstream

Risk: Forwarding the inbound `Authorization` header would disclose the
DreamCycle key to the model server.

Disposition: The proxy strips inbound authorization and uses a separate,
optional upstream credential.

### 3. Client-selected identity would break isolation

Risk: Accepting namespace or user ID in request bodies allows one key to search
or mutate another identity's memory.

Disposition: Each key resolves server-side to an immutable namespace and user
ID. HTTP bodies contain no scope override fields.

### 4. Streaming capture could store partial answers

Risk: Recording content before a stream completes creates incomplete or falsely
successful memories.

Disposition: The proxy accumulates assistant deltas and records the turn only
after a successful completed stream. Disconnects and malformed upstream streams
are not recorded as completed turns.

### 5. "Fail open" needed a precise boundary

Risk: Claiming fail-open behavior could hide sidecar or upstream outages.

Disposition: Recall and post-response memory-write failures do not discard an
otherwise successful model response. Sidecar and upstream availability failures
remain truthful request failures.

### 6. Observed turns must not become automatic training approval

Risk: Directly promoted conversation data could train a model without review or
consent.

Disposition: Captured turns are unreviewed and unapproved. L3 dataset assembly
continues to require explicit reviewed and approved records.

### 7. Training cannot run in an HTTP request

Risk: Long training requests would time out and a `200` response could be
mistaken for successful training.

Disposition: Cycle start returns a job identifier. Polling exposes queued,
running, completed, and failed states with the real report or error. Concurrent
cycles for one identity are rejected.

### 8. Compatibility claim needed to be narrower

Risk: One route could be advertised as full OpenAI API compatibility.

Disposition: Release 0.2.0 explicitly implements only
`POST /v1/chat/completions`, including its common streaming shape. Responses,
embeddings, audio, image, batch, and administrative APIs are non-goals.

### 9. License migration needs attribution and provenance

Risk: Replacing a license without copyright or dependency records weakens the
public release and can misstate third-party terms.

Disposition: Use the unmodified Apache License 2.0 text, add `NOTICE`, update
package classifiers, preserve dependency licenses in `THIRD_PARTY.md`, and note
that the project was relicensed before its first commit or release.

### 10. The feature set requires a release boundary

Risk: Shipping new HTTP APIs and changed licensing under 0.1.0 makes package
consumers unable to distinguish the contract.

Disposition: Bump the package and public documentation to 0.2.0. Historical
0.1.0 reviews receive supersession notes rather than silent rewriting.

## Acceptance Gate

Implementation is complete only when:

- tests prove API-key identity isolation and rejected body scope overrides;
- proxy tests cover non-streaming, streaming, retrieve mode, and memory failure;
- the SDK exercises every public sidecar operation;
- cycle tests prove truthful states and same-identity concurrency rejection;
- PostgreSQL integration proves atomic turn storage and scoped recall;
- a core-only import succeeds without HTTP or ML extras;
- built artifacts contain Apache-2.0 metadata, `LICENSE`, and `NOTICE`;
- source and built artifacts contain no JintellarCore or Nervous dependency.

## Residual Risks

- In-process cycle state disappears when the sidecar restarts.
- OpenAI-compatible local servers vary in undocumented edge behavior.
- A proxy adds an availability hop even when memory failures are isolated.
- Operators remain responsible for consent, retention, deletion, and training
  policy appropriate to their jurisdiction and users.
