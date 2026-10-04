import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from src.ui.run_browser import (
    RunBrowser,
    create_server,
    format_duration,
    format_timestamp,
    render_markdown,
)


def run_entry(run_id, completed_at, **overrides):
    entry = {
        "run_id": run_id,
        "created_at": completed_at,
        "completed_at": completed_at,
        "topic": f"Topic {run_id}",
        "target_audience": "Developers",
        "platform": "YouTube",
        "production_type": "Tutorial",
        "final_qa_status": "PASS",
        "revision_count": 1,
        "automatic_revision_occurred": True,
        "total_duration_seconds": 65.25,
        "json_path": f"{run_id}/production-pack.json",
        "markdown_path": f"{run_id}/production-pack.md",
    }
    entry.update(overrides)
    return entry


def write_history(output_root, entries):
    output_root.mkdir(parents=True)
    (output_root / "index.json").write_text(
        json.dumps({"version": 1, "runs": entries}), encoding="utf-8"
    )


def write_artifacts(output_root, run_id, markdown, pack):
    run_directory = output_root / run_id
    run_directory.mkdir()
    (run_directory / "production-pack.md").write_text(markdown, encoding="utf-8")
    (run_directory / "production-pack.json").write_text(
        json.dumps(pack), encoding="utf-8"
    )


class RunBrowserListingTests(unittest.TestCase):
    def test_missing_index_has_clear_first_run_guidance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            browser = RunBrowser(Path(temp_dir) / "outputs")

            status, page = browser.response_for_path("/")

            self.assertEqual(status, 200)
            self.assertIn("No run history index was found", page)
            self.assertIn("outputs/index.json", page)

    def test_empty_index_explains_that_no_runs_are_available(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            write_history(output_root, [])

            status, page = RunBrowser(output_root).response_for_path("/")

            self.assertEqual(status, 200)
            self.assertIn("No completed runs yet", page)

    def test_malformed_index_returns_clear_error_without_changing_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            output_root.mkdir()
            index_path = output_root / "index.json"
            original = b"{not json"
            index_path.write_bytes(original)

            status, page = RunBrowser(output_root).response_for_path("/")

            self.assertEqual(status, 500)
            self.assertIn("Run history is malformed", page)
            self.assertIn("malformed run history index", page)
            self.assertEqual(index_path.read_bytes(), original)

    def test_home_lists_completed_runs_newest_first_with_summary_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            write_history(
                output_root,
                [
                    run_entry("older", "2026-01-01T00:00:00+00:00"),
                    run_entry("newer", "2026-01-02T00:00:00+00:00"),
                ],
            )

            page = RunBrowser(output_root).render_home()

            self.assertLess(page.index("newer"), page.index("older"))
            for value in (
                "Topic newer",
                "Jan 2, 2026, 12:00 AM UTC",
                "YouTube",
                "Tutorial",
                "PASS",
                "1",
                "1m 5.25s",
            ):
                self.assertIn(value, page)
            self.assertIn('/runs/newer', page)


class RunBrowserDetailTests(unittest.TestCase):
    def test_unknown_run_id_returns_clear_not_found_page(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            write_history(output_root, [])

            status, page = RunBrowser(output_root).response_for_path("/runs/unknown")

            self.assertEqual(status, 404)
            self.assertIn("Run not found", page)
            self.assertIn("unknown", page)

    def test_missing_referenced_artifact_returns_clear_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            write_history(
                output_root,
                [run_entry("missing-artifact", "2026-01-02T03:05:10+00:00")],
            )

            status, page = RunBrowser(output_root).response_for_path(
                "/runs/missing-artifact"
            )

            self.assertEqual(status, 500)
            self.assertIn("Artifact is missing", page)
            self.assertIn("missing-artifact/production-pack.json", page)

    def test_missing_markdown_artifact_returns_clear_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            entry = run_entry("missing-markdown", "2026-01-02T03:05:10+00:00")
            write_history(output_root, [entry])
            run_directory = output_root / "missing-markdown"
            run_directory.mkdir()
            (run_directory / "production-pack.json").write_text(
                json.dumps({"qa_status": "PASS"}), encoding="utf-8"
            )

            status, page = RunBrowser(output_root).response_for_path(
                "/runs/missing-markdown"
            )

            self.assertEqual(status, 500)
            self.assertIn("Artifact is missing", page)
            self.assertIn("missing-markdown/production-pack.md", page)

    def test_detail_renders_persisted_markdown_and_execution_information(self):
        markdown = "# Production Pack\n\n## Script\n\nUse **safe** tools.\n\n- First shot\n"
        pack = {
            "qa_status": "PASS",
            "qa_notes": ["Sources verified"],
            "execution_metadata": {
                "started_at": "2026-01-02T03:04:05+00:00",
                "ended_at": "2026-01-02T03:05:10+00:00",
                "total_duration_seconds": 65.25,
                "agents_used": ["Bao", "Brokkr", "Veritas"],
                "profiles_used": ["research", "production"],
                "revision_count": 1,
                "final_qa_status": "PASS",
                "automatic_revision_occurred": True,
                "stage_durations_seconds": {"research": 20.0},
                "cost_credits": None,
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            entry = run_entry("detail-run", "2026-01-02T03:05:10+00:00")
            write_history(output_root, [entry])
            write_artifacts(output_root, "detail-run", markdown, pack)
            original = (output_root / entry["markdown_path"]).read_bytes()

            page = RunBrowser(output_root).render_run("detail-run")

            self.assertIn("<h1>Production Pack</h1>", page)
            self.assertIn("<h2>Script</h2>", page)
            self.assertIn("Use <strong>safe</strong> tools.", page)
            self.assertIn("<li>First shot</li>", page)
            for value in (
                "detail-run/production-pack.json",
                "Available",
                "Bao, Brokkr, Veritas",
                "research, production",
                "Sources verified",
                "Automatic revision",
                "Yes",
            ):
                self.assertIn(value, page)
            self.assertEqual(
                (output_root / entry["markdown_path"]).read_bytes(), original
            )


class RenderingHelperTests(unittest.TestCase):
    def test_formatting_helpers_make_persisted_values_readable(self):
        self.assertEqual(
            format_timestamp("2026-01-02T03:04:05+00:00"),
            "Jan 2, 2026, 3:04 AM UTC",
        )
        self.assertEqual(format_duration(5), "5s")
        self.assertEqual(format_duration(65.25), "1m 5.25s")

    def test_format_timestamp_converts_offset_input_to_utc(self):
        self.assertEqual(
            format_timestamp("2026-01-02T03:04:05-05:00"),
            "Jan 2, 2026, 8:04 AM UTC",
        )

    def test_format_timestamp_assumes_naive_input_is_utc(self):
        self.assertEqual(
            format_timestamp("2026-01-02T03:04:05"),
            "Jan 2, 2026, 3:04 AM UTC",
        )

    def test_markdown_renderer_escapes_artifact_html(self):
        rendered = render_markdown("## Script\n\n<script>alert(1)</script> **bold**")

        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertIn("<strong>bold</strong>", rendered)


class RunBrowserHttpTests(unittest.TestCase):
    def test_server_serves_the_run_list_over_local_http(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            write_history(
                output_root,
                [run_entry("served-run", "2026-01-02T03:05:10+00:00")],
            )
            server = create_server("127.0.0.1", 0, output_root)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                with urlopen(
                    f"http://127.0.0.1:{server.server_port}/", timeout=5
                ) as response:
                    body = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get_content_type(), "text/html")
                self.assertIn("served-run", body)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
