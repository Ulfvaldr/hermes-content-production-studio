# Testing

## Testing Goal

Testing for Hermes Content Production Studio focuses on validating the behavior of the complete multi-agent workflow rather than only individual functions.

The primary system under test is:

Bao → Brokkr → Veritas → optional Brokkr revision → Veritas recheck → Odin

Testing is intended to answer:

- Does each agent complete its assigned responsibility?
- Does the workflow preserve structured data between stages?
- Does Veritas independently identify meaningful problems?
- Does the revision loop trigger only when required?
- Does the revision loop stop at the configured maximum?
- Can the workflow support different content types?
- Are unresolved issues clearly preserved for human review?

## Current Test Environment

The POC runs locally on Windows using the existing Hermes profiles.

Current profile usage:

- Odin: Hermes Odin profile
- Bao: Hermes Bao profile
- Brokkr: Hermes Brokkr profile
- Veritas: Hermes Veritas profile

The application invokes Hermes through the CLI using one-shot, quiet execution.

The current POC does not depend on direct application-level OpenAI API calls for the agent workflow.

## Test Case 1 — Product / Influencer Video

### Objective

Validate short-form promotional production, factual claim handling, safety-related QA, and automatic revision behavior.

### Input

Topic:

Portable power station for camping and emergency home preparedness.

Audience:

Campers and homeowners.

Objective:

Create a useful 60-second promotional video.

Duration:

60 seconds.

Production type:

Hybrid.

Platform:

Instagram Reels.

### Expected Behavior

Bao should identify:

- audience needs
- useful product categories
- common buying criteria
- claims requiring verification

Brokkr should produce:

- 60-second script
- timed scene plan
- shot list
- B-roll
- voiceover
- captions
- title ideas
- thumbnail concept
- practical production checklist

Veritas should detect unsupported or unsafe claims if present.

If Veritas returns `REVISION REQUIRED`, Brokkr should revise once and Veritas should review again.

### Actual Result

Initial Veritas result:

`REVISION REQUIRED`

The workflow triggered:

`Brokkr revision 1`

The second Veritas result was:

`REVISION REQUIRED`

The workflow then correctly stopped because the configured maximum automatic revision count had been reached.

Odin finalized the revised production package with the remaining QA notes.

### Remaining QA Findings

The second QA review identified:

- narration and visuals were not fully synchronized
- simultaneous headlines and captions were too dense in some sections
- existing 60-second timing should be preserved while correcting synchronization
- the exact product model and reference assets must be locked before final asset generation

### Test Result

Workflow behavior:

`PASS`

Content QA:

`REVISION REQUIRED`

### What This Test Proved

- automatic revision routing works
- Brokkr can revise an existing package instead of rebuilding blindly
- Veritas performs independent second-pass QA
- the loop stops at the configured maximum
- unresolved issues remain visible
- Odin finalizes the latest state without hiding QA failures

---

## Test Case 2 — Educational YouTube Video

### Objective

Validate longer-form educational planning, technical explanation, pacing, audience fit, and factual QA.

### Input

Topic:

How AI agents work and how they can help small businesses.

Audience:

General audience and small business owners with little AI experience.

Objective:

Explain AI agents clearly, provide practical examples, and avoid unnecessary jargon.

Duration:

5–8 minutes.

Production type:

Hybrid.

Platform:

YouTube.

### Expected Behavior

Bao should provide research and framing useful for a beginner audience.

Brokkr should produce:

- complete long-form script
- clear structure
- realistic examples
- presenter guidance
- scene plan
- B-roll
- graphics guidance
- on-screen text
- titles
- thumbnail concept
- production checklist

Veritas should evaluate both factual accuracy and clarity.

### Actual Result

Veritas returned:

`PASS WITH ISSUES`

No automatic revision was triggered because the workflow only revises on `REVISION REQUIRED`.

### QA Findings

Veritas identified:

- inconsistent runtime references
- chatbot-versus-agent wording that was slightly too categorical
- "brain, hands, checklist" should be framed as a teaching model
- central animations and staged workflow UI require clearer production specifications

### Test Result

`PASS WITH ISSUES`

### What This Test Proved

- Hermes can support longer-form educational production
- the system can maintain a structured narrative beyond short-form content
- Veritas can identify subtle conceptual problems rather than only obvious errors
- the workflow correctly distinguishes blocking issues from non-blocking issues
- `PASS WITH ISSUES` does not trigger unnecessary revision cost

---

## Test Case 3 — AI Cinematic Short

### Objective

Validate AI-video planning, character continuity, environment continuity, generation order, reusable prompts, and cinematic structure.

### Input

Topic:

A lone traveler discovers an abandoned research station in a frozen landscape.

Audience:

Viewers interested in cinematic science-fiction and mystery.

Objective:

Create a 60–90 second AI-generated cinematic short with strong visual continuity.

Duration:

60–90 seconds.

Production type:

AI-generated.

Platform:

YouTube Shorts / Instagram Reels.

### Expected Behavior

Brokkr should produce:

- recurring character definition
- recurring environment definition
- scene progression
- shot-level prompts
- reference-image strategy
- generation order
- continuity rules
- camera guidance
- lighting guidance
- cinematic story arc

Veritas should inspect continuity and prompt contradictions.

### Actual Result

Veritas returned:

`PASS WITH ISSUES`

No automatic revision was triggered.

### QA Findings

Veritas identified:

- the reveal should match across voiceover, screen text, and visuals
- the stated 12-second beacon pulse should be applied consistently
- the final light source needs clearer continuity
- uncited audience-response statements should be treated as assumptions
- platform-safe text placement needs more actionable guidance

### Test Result

`PASS WITH ISSUES`

### What This Test Proved

- Hermes can plan AI-generated cinematic content
- Brokkr can create reusable character and location anchors
- the workflow can produce shot-specific generation prompts
- reference generation can be sequenced before video generation
- continuity rules can be carried across multiple scenes
- Veritas can identify contradictions across prompts, narration, and visual logic

---

## Overall POC Test Summary

| Test | Scenario | Workflow Result | Final QA |
|---|---|---|---|
| Test 1 | Product / Influencer | Completed with revision cycle | REVISION REQUIRED |
| Test 2 | Educational YouTube | Completed | PASS WITH ISSUES |
| Test 3 | AI Cinematic | Completed | PASS WITH ISSUES |

## POC Acceptance

Milestone 1 is accepted as a backend proof of concept.

Acceptance is based on system behavior rather than requiring every generated content package to receive a clean QA pass.

The workflow demonstrated:

- successful agent routing
- successful Hermes profile invocation
- structured request handling
- structured production output
- independent QA
- bounded automatic revision
- support for multiple production types
- preservation of unresolved issues
- predictable stop conditions

## Known Testing Gaps

Future testing should add:

- unit tests for schema validation
- unit tests for Hermes CLI parsing
- malformed JSON recovery tests
- Hermes timeout and subprocess failure tests
- retry behavior
- empty-output handling
- missing-field handling
- cost tracking
- latency tracking
- multiple revision limits
- persistence tests
- platform-specific validation
- export tests
- human approval checkpoints

## Recommended Next Testing Stage

For Milestone 2, testing should move beyond manually inspected POC runs.

The next test layer should include:

1. deterministic local tests for schemas and parsers
2. mocked Hermes CLI responses
3. integration tests for workflow routing
4. live agent smoke tests
5. saved production-pack regression examples
6. explicit pass/fail acceptance criteria
7. cost and latency logging

The existing three POC scenarios should remain as regression tests as the product evolves.