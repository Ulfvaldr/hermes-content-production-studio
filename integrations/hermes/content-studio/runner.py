"""JSON subprocess boundary for Content Production Studio."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def main() -> int:
    try:
        values = json.load(sys.stdin)
        output_root = Path(os.environ["CONTENT_STUDIO_OUTPUT_ROOT"])
        studio_path = Path(os.environ["CONTENT_STUDIO_STUDIO_PATH"])
        sys.path.insert(0, str(studio_path))
        from src.workflows.run_submission import RunSubmissionService

        started = time.monotonic()
        run_id = RunSubmissionService(output_root=output_root).submit(values)
        elapsed = time.monotonic() - started
        entry = next(
            e for e in _read_index(output_root)["runs"] if e["run_id"] == run_id
        )
        result = {
            "run_id": run_id,
            "final_qa_status": entry["final_qa_status"],
            "revision_count": entry["revision_count"],
            "automatic_revision": entry["automatic_revision_occurred"],
            "automatic_revision_occurred": entry["automatic_revision_occurred"],
            "total_duration_seconds": entry["total_duration_seconds"],
            "total_duration": entry["total_duration_seconds"],
            "json_artifact_path": str(output_root / run_id / "production-pack.json"),
            "markdown_artifact_path": str(output_root / run_id / "production-pack.md"),
            "completion_summary": "Content Production Studio completed.",
            "runner_duration_seconds": elapsed,
        }
        result.update({field: values[field] for field in (
            "topic", "target_audience", "objective", "duration",
            "production_type", "platform", "tone", "notes",
        )})
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        # Do not expose exception text: Studio exceptions can contain credentials.
        print(json.dumps({"error": "Studio submission failed."}), flush=True)
        return 1


def _read_index(output_root: Path) -> dict:
    return json.loads((output_root / "index.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
