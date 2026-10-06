# Architecture

## Workflow

```text
Local browser form
    |
    v
Run submission service
    |
    v
ContentProductionWorkflow
    |
    +--> Bao ------+
    |              |
    +--> Brokkr <--+
    |              |
    +--> Veritas --+
    |
    +--> Odin finalization
    |
    v
outputs/index.json + per-run JSON/Markdown
    |
    v
Read-only history and detail views
```

## Local Interface Boundary

The browser is a standard-library HTTP presentation layer. Its existing run
history views read summaries through `ProductionPackStore` and read only the
canonical artifact paths validated by the persistence layer. A small application
service translates form values into `ContentRequest`, validates the required
topic, and invokes `ContentProductionWorkflow` with a store rooted at the same
output directory. The UI owns HTTP and form rendering; persistence owns artifact
publication; the workflow owns orchestration; agent adapters remain unchanged.
No alternate storage model or direct UI-to-agent path is introduced.

## Design Principles

- Keep the team lean.
- Give each agent a distinct responsibility.
- Keep Veritas independent from generation work.
- Prefer structured handoffs between agents.
- Preserve human control of Git commit and push operations.
- Optimize model usage and context size as the product matures.
