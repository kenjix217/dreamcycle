# Contributing

Contributions should keep DreamCycle independent, local-first, and truthful
about model quality.

## Development Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
```

The development extra includes the SDK and sidecar test stack. Install
`.[training]` only when changing the Transformers/PEFT implementation. Use a
small local Hugging Face model for manual checks; tests must not download models
or require a GPU.

## Change Requirements

- Keep one module responsible for one coherent behavior.
- Preserve namespace and user-scope filters in every database query.
- Never accept namespace or user scope from an authenticated sidecar request.
- Never forward the inbound DreamCycle API key to a model server.
- Add tests for success, rejection, and real failure paths.
- Do not add cloud egress, model uploads, or credential persistence by default.
- Do not add AGPL dependencies.
- Do not report training completion as model improvement without evaluator
  evidence.
- Update public docs and the changelog when behavior changes.

PostgreSQL integration tests require `DREAMCYCLE_TEST_DSN`. They create and
remove a unique test schema.
