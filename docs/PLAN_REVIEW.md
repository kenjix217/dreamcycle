# Extraction Plan Review

> Historical 0.1.0 review. Before the first commit or release, the project was
> relicensed to Apache-2.0 for the 0.2.0 vendor SDK baseline.

Date: 2026-07-16
Reviewer decision: Approved after revision

## Scope Review

The plan creates a new repository at `/home/ken/dreamcycle` and requires zero
changes in `/home/ken/nervous`. Runtime imports from JintellarCore are expressly
forbidden. This matches the requested product boundary.

## Findings Resolved Before Implementation

### 1. Namespace isolation was too easy to misuse

The draft allowed namespace-like filtering at the record API. That leaves room
for a caller to accidentally query a different tenant. The revised design binds
one `PostgresMemory` object to one required namespace and exposes no per-query
namespace override.

### 2. L2 lacked fields needed to reconstruct training episodes

Content and metadata alone are insufficient for deterministic user/assistant
pairing. The schema now requires first-class role, conversation ID, trace ID,
review state, training approval, and data classification fields.

### 3. L3 promotion could turn unverified text into claimed knowledge

The draft did not define who converts episodes into durable facts. The revised
plan requires a caller-controlled `KnowledgeExtractor` for automatic promotion.
Without one, explicit node content and type are required.

### 4. A trainer without a default evaluator is not a usable dream cycle

Third parties should not have to invent the first quality gate. The ML extra now
includes both a PEFT LoRA trainer and a held-out perplexity evaluator, while
keeping protocols open for task-specific replacements.

### 5. Database setup assumed extension privileges

Many managed PostgreSQL users cannot run `CREATE EXTENSION`. Setup now has an
explicit `create_vector_extension` option and a clear failure when pgvector is
not already installed.

### 6. Distance modes and indexing were conflated

The API can expose cosine, Euclidean/L2, and inner-product distance, but a single
HNSW index cannot optimize all three operator classes. Setup now indexes one
configured mode; other modes remain correct exact scans unless separately
indexed by the operator.

### 7. Dependency language overstated permissiveness

The package and pgvector are MIT, and the optional ML libraries are Apache-2.0.
Psycopg is LGPL-3.0-only. Depending on it as a separately installed database
driver is acceptable for this MIT project, but that fact must be visible in the
dependency review rather than described as purely permissive.

### 8. Package-name availability is time-sensitive

The `dreamcycle` PyPI project page returned 404 during review. That is useful
evidence, not a reservation. The plan now requires another availability check
at publication time.

## Residual Risks Accepted for 0.1.0

- PostgreSQL integration coverage requires an operator-provided test DSN.
- Model quality remains evaluator- and dataset-dependent; the package can
  enforce gates but cannot promise improvement.
- The first release uses synchronous psycopg calls behind `asyncio.to_thread`.
- HNSW performance tuning varies by dataset size and remains configurable.
- Cross-filesystem adapter promotion is rejected rather than pretending to be
  atomic.

## Go Decision

Proceed with implementation in `/home/ken/dreamcycle`. Do not add an adapter or
make any source, version, documentation, or configuration change in
`/home/ken/nervous`.
