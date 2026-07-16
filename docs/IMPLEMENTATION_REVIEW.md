# Implementation Review

Date: 2026-07-16
Release candidate: 0.1.0

> Historical release-candidate review. The unreleased project moved to the
> Apache-2.0 licensed 0.2.0 vendor SDK baseline on 2026-07-15.
Decision: Ready for an independent GitHub repository

## Scope Result

Implementation stayed inside `/home/ken/dreamcycle`. No JintellarCore adapter,
runtime import, route, configuration, migration, documentation, or version
change was added to `/home/ken/nervous`.

## Acceptance Evidence

- Unit suite: 23 passed; the opt-in PostgreSQL test skips without a DSN.
- Isolated live PostgreSQL/pgvector run: 1 passed.
- Live database coverage: schema setup, L2 writes, cosine/L2/inner-product
  retrieval, reviewed training selection, L3 provenance, graph links, and
  namespace isolation.
- Ruff lint: passed.
- Ruff format check: passed.
- Wheel and source distribution: built successfully.
- Twine metadata and README rendering checks: passed for both artifacts.
- Clean wheel installation and lightweight import smoke test: passed.
- Runtime coupling scan: no `core.brain`, `core.nervous`, or `NervousClient`
  imports in source, tests, or examples.
- Stub scan: no `TODO`, `FIXME`, `NotImplementedError`, or production `pass`.
- Credential scan: no embedded runtime credential; the one credential-shaped
  test DSN is synthetic and verifies that config `repr` redacts the DSN.

## Review Findings

### No fake model-improvement result

Training completion does not activate an adapter. The candidate must pass an
evaluator, optional shadow evaluation, path confinement, and atomic activation.
Failures return skipped, rejected, or error reports.

### Scope isolation is enforced twice

Every memory query includes namespace and user scope. L3 edges and provenance
also use composite PostgreSQL foreign keys, so application mistakes cannot
create a cross-scope relationship.

### Training export requires explicit human approval

Only successful assistant memories marked both reviewed and approved for
training are selected. Their previous user turn is paired by conversation, and
whole conversations remain entirely in train or evaluation data.

### Optional ML dependencies remain optional

The published wheel does not require Torch, Transformers, PEFT, Accelerate, or
Sentence Transformers for core use. ML imports occur only when those
implementations are instantiated or run, with an actionable missing-extra
error.

### Adapter activation is recoverable

Candidate directories are confined to a configured root. Promotion copies into
a version directory, atomically updates an `ACTIVE` pointer, preserves a
`PREVIOUS` pointer, and uses a bounded lock file to prevent overlap.

## Residual Risk

The optional Transformers/PEFT code was compiled, linted, import-tested, and
covered for missing dependencies, but it was not trained against a real local
Hugging Face model in this review. That acceptance requires a small licensed
model fixture or the operator's actual local base model and hardware. The
package does not claim that gate as completed.

The `dreamcycle` PyPI name appeared unclaimed during planning, but it is not
reserved. Recheck immediately before publication.

## Publication Boundary

The project may be initialized as a local Git repository. No remote, commit,
push, GitHub repository creation, PyPI upload, or release tag is part of this
implementation review.
