import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from src.outputs.production_pack import (
    ProductionPackExporter,
    ProductionPackStore,
    get_run,
    list_runs,
)
from src.schemas.production_pack import ExecutionMetadata, ProductionPack
from src.schemas.request import ContentRequest


def valid_index_entry(run_id="indexed-run"):
    return {
        "run_id": run_id,
        "created_at": "2026-01-02T03:04:05+00:00",
        "completed_at": "2026-01-02T03:04:25+00:00",
        "topic": "Index validation",
        "target_audience": None,
        "platform": None,
        "production_type": None,
        "final_qa_status": "PASS",
        "revision_count": 0,
        "automatic_revision_occurred": False,
        "total_duration_seconds": 20.0,
        "json_path": f"{run_id}/production-pack.json",
        "markdown_path": f"{run_id}/production-pack.md",
    }


class RunHistoryTests(unittest.TestCase):
    def test_missing_index_behaves_as_empty_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProductionPackStore(Path(temp_dir) / "outputs")

            self.assertEqual(store.list_runs(), [])
            self.assertEqual(list_runs(output_root=store.output_root), [])

    def test_save_creates_lightweight_index_entry_after_artifacts(self):
        pack = ProductionPack(
            script="Full script content must stay out of the index",
            qa_status="PASS",
            execution_metadata=ExecutionMetadata(
                started_at="2026-01-02T03:04:05+00:00",
                ended_at="2026-01-02T03:04:25+00:00",
                total_duration_seconds=20.0,
                revision_count=1,
                final_qa_status="PASS",
                automatic_revision_occurred=True,
            ),
        )
        request = ContentRequest(
            topic="Atomic publishing",
            target_audience="Python developers",
            platform="YouTube",
            production_type="Tutorial",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            store = ProductionPackStore(output_root)

            store.save(pack, request=request, run_id="run-one")

            index = json.loads((output_root / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["version"], 1)
            self.assertEqual(
                index["runs"],
                [
                    {
                        "run_id": "run-one",
                        "created_at": "2026-01-02T03:04:05+00:00",
                        "completed_at": "2026-01-02T03:04:25+00:00",
                        "topic": "Atomic publishing",
                        "target_audience": "Python developers",
                        "platform": "YouTube",
                        "production_type": "Tutorial",
                        "final_qa_status": "PASS",
                        "revision_count": 1,
                        "automatic_revision_occurred": True,
                        "total_duration_seconds": 20.0,
                        "json_path": "run-one/production-pack.json",
                        "markdown_path": "run-one/production-pack.md",
                    }
                ],
            )
            self.assertNotIn("script", index["runs"][0])

    def test_list_runs_accumulates_entries_newest_first(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProductionPackStore(Path(temp_dir) / "outputs")
            older = ProductionPack(
                execution_metadata=ExecutionMetadata(
                    started_at="2026-01-01T00:00:00+00:00",
                    ended_at="2026-01-01T00:01:00+00:00",
                )
            )
            newer = ProductionPack(
                execution_metadata=ExecutionMetadata(
                    started_at="2026-01-02T00:00:00+00:00",
                    ended_at="2026-01-02T00:01:00+00:00",
                )
            )

            store.save(older, request=ContentRequest(topic="Older"), run_id="older")
            store.save(newer, request=ContentRequest(topic="Newer"), run_id="newer")

            self.assertEqual(
                [entry["run_id"] for entry in store.list_runs()],
                ["newer", "older"],
            )

    def test_concurrent_saves_accumulate_every_history_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            barrier = threading.Barrier(2)
            original_to_json = ProductionPackExporter.to_json

            def synchronize_artifact_writes(production_pack):
                rendered = original_to_json(production_pack)
                barrier.wait(timeout=5)
                return rendered

            stores = [ProductionPackStore(output_root), ProductionPackStore(output_root)]
            with patch.object(
                ProductionPackExporter,
                "to_json",
                side_effect=synchronize_artifact_writes,
            ):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [
                        executor.submit(
                            store.save,
                            ProductionPack(),
                            run_id=f"concurrent-{number}",
                            request=ContentRequest(topic=f"Topic {number}"),
                        )
                        for number, store in enumerate(stores)
                    ]
                    for future in futures:
                        future.result(timeout=10)

            self.assertEqual(
                {entry["run_id"] for entry in ProductionPackStore(output_root).list_runs()},
                {"concurrent-0", "concurrent-1"},
            )
            self.assertTrue((output_root / "concurrent-0").is_dir())
            self.assertTrue((output_root / "concurrent-1").is_dir())

    def test_get_run_loads_full_pack_from_artifact_not_index(self):
        pack = ProductionPack(script="Artifact-only script")
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProductionPackStore(Path(temp_dir) / "outputs")
            store.save(
                pack,
                request=ContentRequest(topic="Artifact lookup"),
                run_id="lookup-run",
            )

            loaded = store.get_run("lookup-run")

            self.assertEqual(loaded["script"], "Artifact-only script")
            self.assertNotIn("script", store.list_runs()[0])

    def test_module_functions_are_ready_for_future_ui_callers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            ProductionPackStore(output_root).save(
                ProductionPack(script="UI payload"),
                request=ContentRequest(topic="UI history"),
                run_id="ui-run",
            )

            self.assertEqual(list_runs(output_root=output_root)[0]["run_id"], "ui-run")
            self.assertEqual(
                get_run("ui-run", output_root=output_root)["script"],
                "UI payload",
            )

    def test_malformed_index_fails_clearly_without_publishing_run(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            output_root.mkdir()
            index_path = output_root / "index.json"
            original = "{not valid json"
            index_path.write_text(original, encoding="utf-8")
            store = ProductionPackStore(output_root)

            with self.assertRaisesRegex(ValueError, "malformed run history index"):
                store.save(
                    ProductionPack(),
                    request=ContentRequest(topic="Should fail"),
                    run_id="must-not-publish",
                )

            self.assertEqual(index_path.read_text(encoding="utf-8"), original)
            self.assertFalse((output_root / "must-not-publish").exists())

    def test_malformed_index_entry_fails_with_clear_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            output_root.mkdir()
            (output_root / "index.json").write_text(
                json.dumps({"version": 1, "runs": [{}]}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "malformed run history index"):
                ProductionPackStore(output_root).list_runs()

    def test_save_rejects_invalid_outgoing_metadata_before_publication(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            output_root.mkdir()
            index_path = output_root / "index.json"
            original = json.dumps({"version": 1, "runs": [valid_index_entry()]})
            index_path.write_text(original, encoding="utf-8")
            pack = ProductionPack(
                execution_metadata=ExecutionMetadata(revision_count=True)
            )

            with self.assertRaisesRegex(
                ValueError,
                "invalid outgoing run history entry.*field type",
            ):
                ProductionPackStore(output_root).save(
                    pack,
                    request=ContentRequest(topic="Invalid metadata"),
                    run_id="must-not-publish",
                )

            self.assertEqual(index_path.read_text(encoding="utf-8"), original)
            self.assertFalse((output_root / "must-not-publish").exists())
            self.assertEqual(
                sorted(path.name for path in output_root.iterdir()),
                ["index.json"],
            )

    def test_index_rejects_unknown_entry_fields_without_altering_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            output_root.mkdir()
            index_path = output_root / "index.json"
            entry = valid_index_entry()
            entry["script"] = "content must not be accepted in the lightweight index"
            original = json.dumps({"version": 1, "runs": [entry]})
            index_path.write_text(original, encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError,
                "malformed run history index.*unexpected run entry fields.*unknown: script",
            ):
                ProductionPackStore(output_root).list_runs()

            self.assertEqual(index_path.read_text(encoding="utf-8"), original)

    def test_index_rejects_invalid_field_types_without_altering_data(self):
        invalid_values = {
            "run_id": 7,
            "created_at": None,
            "completed_at": 7,
            "topic": 7,
            "target_audience": [],
            "platform": False,
            "production_type": {},
            "final_qa_status": None,
            "revision_count": True,
            "automatic_revision_occurred": 1,
            "total_duration_seconds": False,
            "json_path": 3,
            "markdown_path": None,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            output_root.mkdir()
            index_path = output_root / "index.json"

            for field, invalid_value in invalid_values.items():
                with self.subTest(field=field):
                    entry = valid_index_entry()
                    entry[field] = invalid_value
                    original = json.dumps({"version": 1, "runs": [entry]})
                    index_path.write_text(original, encoding="utf-8")

                    with self.assertRaisesRegex(ValueError, "malformed run history index"):
                        ProductionPackStore(output_root).list_runs()

                    self.assertEqual(index_path.read_text(encoding="utf-8"), original)

            original = json.dumps({"version": True, "runs": []})
            index_path.write_text(original, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "malformed run history index"):
                ProductionPackStore(output_root).list_runs()
            self.assertEqual(index_path.read_text(encoding="utf-8"), original)

    def test_index_rejects_unsafe_or_mismatched_artifact_paths(self):
        invalid_locations = (
            ("run_id", "../outside"),
            ("run_id", "C:\\outside"),
            ("json_path", "../outside.json"),
            ("json_path", "/absolute/production-pack.json"),
            ("json_path", "other-run/production-pack.json"),
            ("json_path", "indexed-run/../production-pack.json"),
            ("markdown_path", "../outside.md"),
            ("markdown_path", "other-run/production-pack.md"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            output_root.mkdir()
            index_path = output_root / "index.json"

            for field, invalid_value in invalid_locations:
                with self.subTest(field=field, value=invalid_value):
                    entry = valid_index_entry()
                    entry[field] = invalid_value
                    original = json.dumps({"version": 1, "runs": [entry]})
                    index_path.write_text(original, encoding="utf-8")

                    with self.assertRaisesRegex(ValueError, "malformed run history index"):
                        ProductionPackStore(output_root).list_runs()

                    self.assertEqual(index_path.read_text(encoding="utf-8"), original)

    def test_get_run_never_loads_an_artifact_outside_output_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            output_root.mkdir()
            outside_path = Path(temp_dir) / "outside.json"
            outside_path.write_text(json.dumps({"script": "must not load"}), encoding="utf-8")
            entry = valid_index_entry()
            entry["json_path"] = "../outside.json"
            index_path = output_root / "index.json"
            original = json.dumps({"version": 1, "runs": [entry]})
            index_path.write_text(original, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "malformed run history index"):
                ProductionPackStore(output_root).get_run("indexed-run")

            self.assertEqual(index_path.read_text(encoding="utf-8"), original)

    def test_index_persistence_failure_leaves_no_run_or_history_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            store = ProductionPackStore(output_root)
            original_write_text = Path.write_text

            def fail_index_write(path, data, *args, **kwargs):
                if path.name.startswith(".index-"):
                    raise OSError("simulated index write failure")
                return original_write_text(path, data, *args, **kwargs)

            with patch.object(
                Path,
                "write_text",
                autospec=True,
                side_effect=fail_index_write,
            ):
                with self.assertRaisesRegex(OSError, "index write failure"):
                    store.save(
                        ProductionPack(),
                        request=ContentRequest(topic="Failed indexing"),
                        run_id="failed-index",
                    )

            self.assertFalse((output_root / "failed-index").exists())
            self.assertEqual(store.list_runs(), [])

    def test_atomic_index_replace_failure_preserves_prior_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            store = ProductionPackStore(output_root)
            store.save(
                ProductionPack(),
                request=ContentRequest(topic="Existing"),
                run_id="existing",
            )
            original_index = (output_root / "index.json").read_text(encoding="utf-8")

            with patch.object(
                Path,
                "replace",
                autospec=True,
                side_effect=OSError("simulated atomic replace failure"),
            ):
                with self.assertRaisesRegex(OSError, "atomic replace failure"):
                    store.save(
                        ProductionPack(),
                        request=ContentRequest(topic="Not indexed"),
                        run_id="replace-failed",
                    )

            self.assertEqual(
                (output_root / "index.json").read_text(encoding="utf-8"),
                original_index,
            )
            self.assertFalse((output_root / "replace-failed").exists())
            self.assertEqual([entry["run_id"] for entry in store.list_runs()], ["existing"])
            self.assertEqual(list(output_root.glob(".index-*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
