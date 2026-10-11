---
name: content-production-studio
description: "Run and report Content Production Studio requests through the Hermes tool contract."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Content Studio, content production, kanban, Hermes]
    related_skills: []
---

# Content Production Studio

## When to use

Use this skill when a Kanban task asks Hermes to generate content with the Content Production Studio, or when the task explicitly names `content_studio_generate`. Hermes remains the orchestration and result surface; this skill is instructional and does not reimplement Studio workflow logic.

## Request envelope

Before invoking the tool, identify the versioned JSON request envelope. It must use `schema_version: "content_studio.request.v1"` and preserve these eight string fields exactly: `topic`, `target_audience`, `objective`, `duration`, `production_type`, `platform`, `tone`, and `notes`. All nine top-level properties, including `schema_version` and `notes`, are required; reject unknown fields, missing values, nulls, non-strings, blank required values, or another schema version. Do not add Kanban, profile, or diagnostic data to the content request.

## Invocation

After validating the envelope and confirming the configured Studio runtime is available, call the Hermes tool `content_studio_generate` in the `content_studio` toolset with that request. Do not import Studio modules into the Hermes process, bypass the tool, or call it before the request is complete and validated. The tool returns a JSON string; parse it as one `content_studio.result.v1` result envelope.

## Interpret and validate results

A successful result has `success: true`, a non-empty `run_id`, `final_qa_status` exactly `PASS` or `PASS WITH ISSUES`, non-negative `revision_count`, boolean `automatic_revision_occurred`, finite non-negative duration, and readable absolute JSON and Markdown artifact paths. `PASS WITH ISSUES` is successful but must surface its QA warning. `REVISION REQUIRED` is a completed workflow with `success: false` and error code `FINAL_QA_REVISION_REQUIRED`; unknown or malformed QA status is a protocol error. Verify both files exist, are regular non-empty files, remain inside the approved output root (unless explicitly configured otherwise), and have the expected formats. Check the JSON artifact's run identity when available. Artifact validation is independent of QA-status interpretation: `ARTIFACT_VALIDATION_FAILED` is reserved for invalid persisted outputs.

A failure result has `success: false` and structured `error.code`, `error.message`, `error.retryable`, and `error.stage`. Follow the contract's narrow retry policy: at most one eligible transient retry, never retry invalid input, missing configuration, authentication failure, protocol errors, completed partial runs, or a run that may have durable side effects. Report failure through the task's normal blocked/failed handling rather than claiming completion.

## Completion and safety

Only after mechanical validation succeeds, call `kanban_complete` with a concise summary, bounded metadata containing the run ID, QA status, revision count, duration, and validation outcome, and the two verified artifact paths in `artifacts`. Never put secrets, credentials, environment dumps, raw command lines, unbounded stderr, or raw exceptions in summaries, metadata, comments, or artifacts. Redact token, secret, password, API-key, authorization, cookie, and provider-credential material from diagnostics. On configuration failure, expose setting names only; fail closed instead of guessing paths, interpreters, providers, or credentials.

The request and result schemas are versioned independently. Additive fields may be ignored, but changes to field names, meanings, requiredness, path semantics, timeout guarantees, or error-code meanings require a new schema version.
