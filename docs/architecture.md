# Architecture

## Workflow

```text
User Request
    |
    v
  Odin
    |
    +--> Bao ------+
    |              |
    +--> Brokkr <--+
    |              |
    +--> Veritas --+
    |
    v
Final Video Production Pack
    |
    v
outputs/index.json + per-run JSON/Markdown
    |
    v
Local read-only run browser (`src/ui/`)
```

## Local Interface Boundary

The browser is a standard-library HTTP presentation layer. It reads run summaries
through `ProductionPackStore` and reads only the canonical artifact paths validated
by the persistence layer. UI code remains separate from agent adapters, workflow
orchestration, schemas, and persistence/index implementation. It introduces no
storage model and cannot submit or modify runs.

## Design Principles

- Keep the team lean.
- Give each agent a distinct responsibility.
- Keep Veritas independent from generation work.
- Prefer structured handoffs between agents.
- Preserve human control of Git commit and push operations.
- Optimize model usage and context size as the product matures.
