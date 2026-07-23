---
description: Install and wire DreamCycle as a Hermes memory and rollback command helper.
name: dreamcycle-hermes-memory
summary: Install a Hermes shim for DreamCycle status and confirmation-gated rollback.
category: software-development
---

# DreamCycle Hermes helper

## What this skill does

This skill gives Hermes users a one-command way to install the DreamCycle
helper shim, point Hermes at a running DreamCycle sidecar, and expose adapter
status plus confirmation-gated rollback.

## Prerequisites

- Git + shell access for the target user
- Running DreamCycle sidecar (`dreamcycle-server`) with key and namespace configured
- Optional but recommended: PostgreSQL + pgvector endpoint reachable by DreamCycle

## One-command install

```bash
# from a clone of this repo
bash scripts/install_dreamcycle_hermes_plugin.sh
```

The script installs:

- `~/.hermes/plugins/dreamcycle/__init__.py`

## Configure Hermes

Set these variables in your Hermes runtime config (equivalent to your profile env):

- `DREAMCYCLE_BASE_URL`
- `DREAMCYCLE_API_KEY`

Then Hermes, shell scripts, or another chat tool can call:

```bash
dreamcycle-hermes status
dreamcycle-hermes rollback --confirm
```

Rollback must be confirmation-gated in the caller. Ask the user first, then call
`rollback --confirm` only after approval.

## Smoke check

Run smoke script after env is set:

```bash
python scripts/hermes_sidecar_smoke.py --dry-run
```

Expected:

- `command ok`
- configured sidecar URL
- API-key status
- rollback gate reminder

## Verify install from this package

From this package:

- If running locally in this repo, place a copy under this profile's skill path (e.g. `~/.hermes/skills/software-development/dreamcycle-hermes-memory`) and run:

```bash
hermes skills install dreamcycle-hermes-memory
```

- If publishing to registry, users install via repo URL:

```bash
hermes skills install https://raw.githubusercontent.com/kenjix217/dreamcycle/main/skills/dreamcycle-hermes-memory/SKILL.md
```

## Release

### Release checklist

1. Freeze changes and bump version tags
2. Run packaging checks
3. Create GitHub tag and release artifacts:

```bash
bash scripts/release_dreamcycle_for_hermes.sh <VERSION>
```

4. Optionally mirror version in `CHANGELOG.md` and publish install notes.
