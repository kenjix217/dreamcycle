# Changelog

All notable changes to DreamCycle are documented here.

## 0.3.2 - 2026-07-23

- Added sidecar and SDK support for reviewed L2 to L3 graph-memory promotion,
  L3 search, L3 neighbor lookup, and L3 stats.
- Added dashboard visibility for L3 graph memory and approved-L2 promotion.
- Guarded L3 promotion so raw captured L2 records must be reviewed, approved,
  and successful before they can become durable graph knowledge.

## 0.3.1 - 2026-07-23

- Added Linux and macOS GitHub Release install bundles for x86_64 and arm64.
- Added a one-line `curl | bash` installer plus a local `dreamcycle-update`
  command for reinstalling/updating from the latest release bundle.
- Added a packaged dashboard server wrapper so installed users can run
  `dreamcycle-dashboard` without Vite.
- Added CI packaging and GitHub Release asset upload for installer bundles.

## 0.3.0 - 2026-07-23

- Added a standalone local Vite dashboard adapted from the hidden Nervous Dream
  page design for memory, cycle, adapter, and rollback control.
- Added the `dreamcycle-hermes` command surface for Hermes-style adapter status
  and confirmation-gated rollback.
- Added importable Hermes helper hooks for chat tools that want to expose
  DreamCycle adapter control without depending on a specific Hermes runtime.
- Added Hermes install, smoke-check, and release helper scripts referenced by
  the DreamCycle Hermes memory skill.
- Included the public `skills/` folder in source distributions.

## 0.2.2 - 2026-07-16

- Removed the internal `docs/` folder from tracked public source.
- Excluded `docs/` from future source distributions.
- Removed public README links into the internal docs folder.

## 0.2.1 - 2026-07-16

- Removed an unrelated layout-reference citation from the thesis report.
- Regenerated the thesis PDF with only DreamCycle-relevant technical references.

## 0.2.0 - 2026-07-16

- Added the authenticated vendor SDK and standalone memory sidecar.
- Added observe and retrieve modes for an OpenAI-compatible Chat Completions proxy.
- Added asynchronous dream-cycle jobs and adapter status/rollback endpoints.
- Relicensed the unreleased project from MIT to Apache-2.0 and added `NOTICE`.
- Added a product-focused README and GitHub-rendered architecture guide.
- Added a Docker Compose five-minute memory quickstart.
- Added PyPI trusted publishing through GitHub Actions.
- Standardized public attribution to Kenny Jin.

## 0.1.0 - 2026-07-16

- Extracted the Dream Cycle orchestration into an independent Python package.
- Added direct PostgreSQL/pgvector L2 episodic memory.
- Added L3 knowledge nodes, relationships, and L2 provenance.
- Added deterministic reviewed-memory train/evaluation dataset generation.
- Added guarded adapter evaluation, promotion, and rollback.
- Added optional Transformers/PEFT LoRA training and perplexity evaluation.
- Added typed events, reports, examples, tests, and initial project metadata.
