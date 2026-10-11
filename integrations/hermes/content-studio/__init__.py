"""Hermes custom tool for the Content Production Studio."""
from __future__ import annotations

import json
import math
import os
import subprocess
import time
from pathlib import Path
from typing import Any

SCHEMA = {
    "name": "content_studio_generate",
    "description": "Run Content Production Studio for a complete eight-field request and return verified production-pack artifacts.",
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "string"},
            "topic": {"type": "string"},
            "target_audience": {"type": "string"},
            "objective": {"type": "string"},
            "duration": {"type": "string"},
            "production_type": {"type": "string"},
            "platform": {"type": "string"},
            "tone": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": [
            "schema_version", "topic", "target_audience", "objective", "duration",
            "production_type", "platform", "tone", "notes",
        ],
    },
}
REQUEST_SCHEMA = "content_studio.request.v1"
RESULT_SCHEMA = "content_studio.result.v1"
FIELDS = ("topic", "target_audience", "objective", "duration", "production_type", "platform", "tone", "notes")


def register(ctx):
    # Hermes v0.21 dispatches only task/session context kwargs to handlers.
    # Capture PluginContext at registration time so tool calls can read this
    # plugin's settings namespace through the supported API.
    def registered_handler(args: dict, **kwargs) -> str:
        kwargs.pop("plugin_context", None)
        kwargs.pop("ctx", None)
        return handle_generate(args, plugin_context=ctx, **kwargs)

    ctx.register_tool(
        name="content_studio_generate",
        toolset="content_studio",
        schema=SCHEMA,
        handler=registered_handler,
        description=SCHEMA["description"],
    )


def handle_generate(args: dict, plugin_context=None, **kwargs) -> str:
    started = time.monotonic()
    try:
        values = _validate_request(args)
        config = _load_config(plugin_context)
        result = _run_with_retry(values, config, started)
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    except _IntegrationError as exc:
        return json.dumps(_failure(exc.code, exc.message, exc.retryable, exc.stage, started), separators=(",", ":"))
    except Exception:
        return json.dumps(_failure("INTERNAL_ERROR", "Content Studio integration failed.", False, "plugin", started), separators=(",", ":"))


def _validate_request(args: Any) -> dict:
    if not isinstance(args, dict):
        raise _IntegrationError("INVALID_REQUEST", "Request must be an object.", False, "validation")
    if set(args) != {"schema_version", *FIELDS}:
        raise _IntegrationError("INVALID_REQUEST", "Request must contain exactly the version and eight content fields.", False, "validation")
    if args["schema_version"] != REQUEST_SCHEMA:
        raise _IntegrationError("UNSUPPORTED_SCHEMA_VERSION", "Unsupported request schema version.", False, "validation")
    if any(type(args[field]) is not str for field in FIELDS):
        raise _IntegrationError("INVALID_REQUEST", "All content fields must be strings.", False, "validation")
    if any(not args[field].strip() for field in FIELDS if field != "notes"):
        raise _IntegrationError("INVALID_REQUEST", "Required content fields must be non-empty.", False, "validation")
    return {"schema_version": REQUEST_SCHEMA, **{field: args[field] for field in FIELDS}}


def _load_config(ctx) -> dict:
    names = ("studio_path", "runner_path", "python_executable", "output_root", "pythonpath", "subprocess_timeout_seconds", "max_retries")
    config = {}
    for name in names:
        value = None
        if ctx is not None and hasattr(ctx, "get_config"):
            value = ctx.get_config(name, None)
        if value is None:
            value = os.environ.get("CONTENT_STUDIO_" + name.upper())
        if value is not None:
            config[name] = value
    config.setdefault("runner_path", str(Path(__file__).with_name("runner.py")))
    config.setdefault("subprocess_timeout_seconds", 1500)
    config.setdefault("max_retries", 1)
    missing = [name for name in ("studio_path", "python_executable", "output_root") if not config.get(name)]
    if missing:
        raise _IntegrationError("CONFIG_MISSING", "Missing configuration: " + ", ".join(missing), False, "configuration")
    try:
        config["subprocess_timeout_seconds"] = max(1, int(config["subprocess_timeout_seconds"]))
        config["max_retries"] = min(1, max(0, int(config["max_retries"])) )
    except (TypeError, ValueError):
        raise _IntegrationError("CONFIG_MISSING", "Timeout and retry settings are invalid.", False, "configuration")
    return config


def _run_with_retry(values, config, started):
    attempts = config["max_retries"] + 1
    last = None
    for attempt in range(attempts):
        try:
            return _run_once(values, config, started)
        except _IntegrationError as exc:
            last = exc
            if not exc.retryable or attempt + 1 >= attempts:
                raise
    raise last


def _run_once(values, config, started):
    env = _build_subprocess_env(config)
    try:
        completed = subprocess.run(
            [str(config["python_executable"]), str(config["runner_path"])],
            input=json.dumps(values), text=True, capture_output=True,
            cwd=str(Path(config["studio_path"]).resolve()), env=env,
            timeout=config["subprocess_timeout_seconds"], check=False,
        )
    except subprocess.TimeoutExpired:
        raise _IntegrationError("STUDIO_TIMEOUT", "The Studio subprocess exceeded its tool timeout; automatic retry is disabled because run creation is ambiguous.", False, "studio_subprocess")
    except (OSError, ValueError):
        raise _IntegrationError("RUNNER_NOT_FOUND", "The Studio runner could not be started.", True, "studio_subprocess")
    if completed.returncode != 0:
        # Submission may already have committed a durable run before failing.
        # Treat this as ambiguous and never resubmit automatically.
        raise _IntegrationError("STUDIO_EXIT_NONZERO", "The Studio subprocess failed; automatic retry is disabled because run creation is ambiguous.", False, "studio_subprocess")
    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise _IntegrationError("STUDIO_PROTOCOL_ERROR", "The Studio returned malformed output.", False, "protocol")
    return _validate_result(payload, config["output_root"], started, values)


# Only runtime variables needed to launch an already-selected interpreter are
# inherited. In particular, no provider, cloud, shell, or Hermes secret is
# forwarded. Explicit integration variables are added below, not inherited.
_SUBPROCESS_ENV_ALLOWLIST = frozenset({
    "HOME", "LANG", "LC_ALL", "PATH", "PYTHONHOME", "SYSTEMDRIVE",
    "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "USERPROFILE", "WINDIR",
})


def _build_subprocess_env(config) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key.upper() in _SUBPROCESS_ENV_ALLOWLIST}
    env.update({
        "CONTENT_STUDIO_STUDIO_PATH": str(Path(config["studio_path"]).resolve()),
        "CONTENT_STUDIO_OUTPUT_ROOT": str(Path(config["output_root"]).resolve()),
    })
    if config.get("pythonpath"):
        env["PYTHONPATH"] = str(config["pythonpath"])
    return env


_QA_STATUSES = frozenset({"PASS", "PASS WITH ISSUES", "REVISION REQUIRED"})


def _validate_result(payload, output_root, started, request_values=None):
    if not isinstance(payload, dict) or "error" in payload:
        raise _IntegrationError("STUDIO_PROTOCOL_ERROR", "The Studio returned an invalid result.", False, "protocol")
    required = ("run_id", "final_qa_status", "revision_count", "automatic_revision", "total_duration_seconds", "json_artifact_path", "markdown_artifact_path", "completion_summary")
    if any(key not in payload for key in required):
        raise _IntegrationError("STUDIO_PROTOCOL_ERROR", "The Studio result is missing required fields.", False, "protocol")
    status = payload["final_qa_status"]
    if not isinstance(status, str) or status not in _QA_STATUSES:
        raise _IntegrationError("STUDIO_PROTOCOL_ERROR", "The Studio returned an unknown or malformed final QA status.", False, "protocol")
    if not isinstance(payload["run_id"], str) or not payload["run_id"]:
        raise _IntegrationError("STUDIO_PROTOCOL_ERROR", "The Studio result has an invalid run ID.", False, "protocol")
    root = Path(output_root).resolve()
    run_dir = (root / payload["run_id"]).resolve()
    if run_dir.parent != root or not run_dir.is_dir():
        raise _IntegrationError("ARTIFACT_VALIDATION_FAILED", "The Studio run directory is invalid.", False, "validation")
    paths = [Path(payload["json_artifact_path"]), Path(payload["markdown_artifact_path"])]
    expected = [run_dir / "production-pack.json", run_dir / "production-pack.md"]
    if any(path.resolve() != target for path, target in zip(paths, expected)) or any(not path.is_file() or path.stat().st_size == 0 for path in expected):
        raise _IntegrationError("ARTIFACT_VALIDATION_FAILED", "The Studio artifacts are missing or unsafe.", False, "validation")
    try:
        artifact = json.loads(expected[0].read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise _IntegrationError("ARTIFACT_VALIDATION_FAILED", "The JSON artifact is unreadable.", False, "validation")
    metadata = artifact.get("execution_metadata", {}) if isinstance(artifact, dict) else {}
    if metadata.get("run_id") not in (None, payload["run_id"]):
        raise _IntegrationError("ARTIFACT_VALIDATION_FAILED", "Artifact run ID does not match the result.", False, "validation")
    if not isinstance(payload["revision_count"], int) or payload["revision_count"] < 0 or not isinstance(payload["automatic_revision"], bool) or not _finite_nonnegative(payload["total_duration_seconds"]):
        raise _IntegrationError("STUDIO_PROTOCOL_ERROR", "The Studio result contains invalid metrics.", False, "protocol")
    if request_values is not None:
        for field in FIELDS:
            if payload.get(field) != request_values[field]:
                raise _IntegrationError("STUDIO_PROTOCOL_ERROR", "The Studio result did not preserve the request fields.", False, "protocol")
    result = {"schema_version": RESULT_SCHEMA, "success": status != "REVISION REQUIRED", "run_id": payload["run_id"], "final_qa_status": status, "revision_count": payload["revision_count"], "automatic_revision": payload["automatic_revision"], "automatic_revision_occurred": payload["automatic_revision"], "total_duration_seconds": payload["total_duration_seconds"], "total_duration": payload["total_duration_seconds"], "json_artifact_path": str(expected[0]), "markdown_artifact_path": str(expected[1]), "completion_summary": str(payload["completion_summary"])[:500], "error": None}
    if request_values is not None:
        result.update({field: request_values[field] for field in FIELDS})
    if status == "PASS WITH ISSUES":
        result["qa_warning"] = "Content Studio completed with QA issues."
    elif status == "REVISION REQUIRED":
        result["error"] = {"code": "FINAL_QA_REVISION_REQUIRED", "message": "Content Studio completed, but final QA requires revision.", "retryable": False, "stage": "final_qa"}
    return result


def _finite_nonnegative(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _failure(code, message, retryable, stage, started):
    return {"schema_version": RESULT_SCHEMA, "success": False, "run_id": None, "final_qa_status": "unknown", "revision_count": 0, "automatic_revision": False, "total_duration_seconds": round(time.monotonic() - started, 3), "json_artifact_path": None, "markdown_artifact_path": None, "completion_summary": "Content Studio did not complete.", "error": {"code": code, "message": message[:2048], "retryable": retryable, "stage": stage}}


class _IntegrationError(Exception):
    def __init__(self, code, message, retryable, stage):
        self.code, self.message, self.retryable, self.stage = code, message, retryable, stage
        super().__init__(message)
