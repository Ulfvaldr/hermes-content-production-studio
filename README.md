# Hermes Content Production Studio

Hermes Content Production Studio is a multi-agent video pre-production system that turns a rough content idea into a production-ready package for AI-generated, live-action, or hybrid video.

## Current Stage

**Milestone 2 — Persisted Production Packs**

Every completed workflow run now attaches backward-compatible execution metadata
and persists the resulting `ProductionPack` in two forms: canonical JSON for
machine use and organized Markdown for people. Metadata includes UTC start/end
timestamps, total and per-stage duration, agents and Hermes profiles used,
revision state, and final QA status. Cost or credit data remains `null` because
Hermes does not expose it reliably; model/provider fields are omitted for the
same reason.

The POC validates the complete Hermes workflow:

`User Input → Odin → Bao → Brokkr → Veritas → Odin → Video Production Pack`

## Core Agents

- **Odin** — Orchestrator and final assembler
- **Bao** — Research and factual grounding
- **Brokkr** — Production-plan builder
- **Veritas** — Independent QA and validation

## Repository Structure

- `docs/` — specifications, architecture, roadmap, testing
- `src/agents/` — agent definitions and behavior
- `src/workflows/` — orchestration logic
- `src/schemas/` — structured input/output models
- `src/utils/` — shared helpers
- `tests/` — approved POC test scenarios
- `examples/production-packs/` — completed example outputs
- `config/` — project configuration

## Git Governance

Hermes may create and modify files, run tests, inspect diffs, and prepare commit messages.

Development follows these repository standards:

- Use one branch per task, and avoid direct feature work on `main`.
- When development runs in parallel, use one worktree per branch.
- Keep one active writer in each worktree to prevent conflicting edits.
- Have Veritas review changes before merge.
- Keep merge and push actions human-controlled.

The expected delivery sequence is:

`Build → Test → Review → Approve → Commit → Verify → Push`

## Automated Tests

The `tests/` directory is the automated test surface. Run `pytest` from the
repository root; root-level live scripts and generated example/output files are
not part of pytest collection.

## Persisted Outputs

A successful `ContentProductionWorkflow.run(...)` writes one directory per run:

```text
outputs/
├── index.json
└── 20260102T030405678901Z-a1b2c3d4/
    ├── production-pack.json
    └── production-pack.md
```

The UTC timestamp plus short UUID makes each run identifier sortable and unique.
`production-pack.json` is the deterministic, machine-readable representation of
all `ProductionPack` fields, including nested `execution_metadata`.
`production-pack.md` contains the same data in labeled sections suited to review
and handoff. The workflow returns the `ProductionPack` as before; paths for the
most recently completed run are available on `workflow.last_saved_output`.

`outputs/index.json` is a lightweight, versioned history catalog. It stores no
full `ProductionPack` content. Each entry contains the run ID, created and
completed timestamps, topic, optional target audience/platform/production type,
final QA status, revision count, whether an automatic revision occurred, total
duration, and relative paths to that run's JSON and Markdown artifacts. Entries
are returned newest-first by `list_runs()`; `get_run(run_id)` resolves the index
entry and loads the full JSON artifact from the canonical path for that run ID.
Both are available as methods on `ProductionPackStore` and as functions in
`src.outputs.production_pack`. Workflow saves always populate `topic`; direct
store callers that omit a `ContentRequest` record unavailable request metadata,
including `topic`, as `null`.

Run artifacts publish before the index is replaced atomically. Writers serialize
the publish-and-index transaction with an OS-backed local lock, so concurrent
threads and local processes accumulate entries instead of overwriting one
another. The lock is released automatically if a process exits. If artifact or
index persistence fails, the incomplete run is removed and no history entry is
published. Existing run directories are never overwritten. A missing index is
an empty history; malformed or unsupported index data raises a clear error
without replacing it. Index entries are type-checked, and artifact paths must
exactly match the canonical paths derived from their validated run IDs.

Generated `outputs/` content is local runtime data and is not tracked by Git.

## Current Objective

Complete the three approved POC scenarios and demonstrate that Hermes can reliably produce usable Video Production Packs with independent QA.
