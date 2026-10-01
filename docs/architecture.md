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
```

## Design Principles

- Keep the team lean.
- Give each agent a distinct responsibility.
- Keep Veritas independent from generation work.
- Prefer structured handoffs between agents.
- Preserve human control of Git commit and push operations.
- Optimize model usage and context size as the product matures.
