# Hermes Content Production Studio

Hermes Content Production Studio is a multi-agent video pre-production system that turns a rough content idea into a production-ready package for AI-generated, live-action, or hybrid video.

## Current Stage

**Milestone 2 — Lightweight Execution Metadata**

The workflow now attaches backward-compatible execution metadata to each
`ProductionPack`: UTC start/end timestamps, total and per-stage duration,
agents and Hermes profiles used, revision state, and final QA status. Cost or
credit data is reserved as `None` because Hermes does not expose it reliably;
model/provider fields are omitted for the same reason.

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

## Current Objective

Complete the three approved POC scenarios and demonstrate that Hermes can reliably produce usable Video Production Packs with independent QA.
