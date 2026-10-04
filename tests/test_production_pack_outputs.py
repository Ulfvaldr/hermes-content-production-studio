import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from src.outputs.production_pack import (
    ProductionPackExporter,
    ProductionPackStore,
    generate_run_id,
)
from src.schemas.production_pack import ExecutionMetadata, ProductionPack


class ProductionPackExporterTests(unittest.TestCase):
    def test_json_export_preserves_every_field_and_nested_metadata(self):
        pack = ProductionPack(
            creative_brief="Brief",
            research_summary="Research",
            recommended_angle="Angle",
            hook="Hook",
            script="Script",
            scene_plan=["Scene 1"],
            shot_list=["Shot 1"],
            b_roll=["B-roll 1"],
            ai_prompts=["Prompt 1"],
            continuity_guide=["Keep wardrobe consistent"],
            voiceover="Voiceover",
            on_screen_text=["Caption"],
            title_options=["Title"],
            thumbnail_concept="Thumbnail",
            production_checklist=["Check audio"],
            qa_status="PASS",
            qa_notes=["Verified"],
            execution_metadata=ExecutionMetadata(
                started_at="2026-01-02T03:04:05+00:00",
                ended_at="2026-01-02T03:04:25+00:00",
                total_duration_seconds=20.0,
                agents_used=["Bao", "Brokkr", "Veritas", "Odin"],
                profiles_used=["bao", "brokkr", "veritas"],
                revision_count=1,
                final_qa_status="PASS",
                automatic_revision_occurred=True,
                stage_durations_seconds={"bao_research": 2.0},
                cost_credits=None,
            ),
        )

        exported = json.loads(ProductionPackExporter.to_json(pack))

        self.assertEqual(exported["creative_brief"], "Brief")
        self.assertEqual(exported["qa_notes"], ["Verified"])
        self.assertEqual(
            exported["execution_metadata"],
            {
                "agents_used": ["Bao", "Brokkr", "Veritas", "Odin"],
                "automatic_revision_occurred": True,
                "cost_credits": None,
                "ended_at": "2026-01-02T03:04:25+00:00",
                "final_qa_status": "PASS",
                "profiles_used": ["bao", "brokkr", "veritas"],
                "revision_count": 1,
                "stage_durations_seconds": {"bao_research": 2.0},
                "started_at": "2026-01-02T03:04:05+00:00",
                "total_duration_seconds": 20.0,
            },
        )
        self.assertEqual(set(exported), set(ProductionPack.__dataclass_fields__))

    def test_markdown_export_has_readable_section_for_every_field(self):
        pack = ProductionPack(
            creative_brief="Brief body",
            research_summary="Research body",
            recommended_angle="Angle body",
            hook="Hook body",
            script="Script body",
            scene_plan=["Scene one"],
            shot_list=["Shot one"],
            b_roll=["B-roll one"],
            ai_prompts=["Prompt one"],
            continuity_guide=["Continuity one"],
            voiceover="Voiceover body",
            on_screen_text=["Caption one"],
            title_options=["Title one"],
            thumbnail_concept="Thumbnail body",
            production_checklist=["Checklist one"],
            qa_status="PASS",
            qa_notes=["QA note one"],
            execution_metadata=ExecutionMetadata(
                started_at="2026-01-02T03:04:05+00:00",
                stage_durations_seconds={"bao_research": 2.0},
            ),
        )

        markdown = ProductionPackExporter.to_markdown(pack)

        expected_sections = [
            "Creative Brief",
            "Research Summary",
            "Recommended Angle",
            "Hook",
            "Script",
            "Scene Plan",
            "Shot List",
            "B-Roll",
            "AI Prompts",
            "Continuity Guide",
            "Voiceover",
            "On-Screen Text",
            "Title Options",
            "Thumbnail Concept",
            "Production Checklist",
            "QA Status",
            "QA Notes",
            "Execution Metadata",
        ]
        for section in expected_sections:
            self.assertIn(f"## {section}\n", markdown)
        self.assertIn("- Scene one", markdown)
        self.assertIn("- **Started At:** 2026-01-02T03:04:05+00:00", markdown)
        self.assertIn("  - **Bao Research:** 2.0", markdown)


class ProductionPackStoreTests(unittest.TestCase):
    def test_run_id_combines_utc_timestamp_and_short_uuid(self):
        run_id = generate_run_id(
            now=datetime(2026, 1, 2, 3, 4, 5, 678901, tzinfo=timezone.utc),
            unique_id=UUID("a1b2c3d4-1111-2222-3333-444455556666"),
        )

        self.assertEqual(run_id, "20260102T030405678901Z-a1b2c3d4")

    def test_save_generates_one_run_id_for_both_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProductionPackStore(
                Path(temp_dir), run_id_factory=lambda: "generated-run-id"
            )

            saved = store.save(ProductionPack())

            self.assertEqual(saved.run_id, "generated-run-id")
            self.assertEqual(saved.json_path.parent, saved.markdown_path.parent)
            self.assertEqual(saved.directory.name, "generated-run-id")

    def test_save_rejects_run_id_that_can_escape_output_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProductionPackStore(Path(temp_dir) / "outputs")

            with self.assertRaisesRegex(ValueError, "run_id"):
                store.save(ProductionPack(), run_id="../escape")

    def test_save_fails_when_output_root_is_a_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            output_root.write_text("not a directory", encoding="utf-8")
            store = ProductionPackStore(output_root)

            with self.assertRaises(FileExistsError):
                store.save(ProductionPack(), run_id="blocked-run")

    def test_save_removes_partial_publication_when_second_write_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            store = ProductionPackStore(output_root)
            original_write_text = Path.write_text

            def fail_markdown_write(path, data, *args, **kwargs):
                if path.name == "production-pack.md":
                    raise OSError("simulated markdown write failure")
                return original_write_text(path, data, *args, **kwargs)

            with patch.object(Path, "write_text", autospec=True, side_effect=fail_markdown_write):
                with self.assertRaisesRegex(OSError, "markdown write failure"):
                    store.save(ProductionPack(), run_id="failed-run")

            self.assertFalse((output_root / "failed-run").exists())
            self.assertEqual(list(output_root.iterdir()), [])

    def test_save_rejects_an_existing_run_directory_without_modifying_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            run_directory = output_root / "existing-run"
            run_directory.mkdir(parents=True)
            sentinel = run_directory / "keep.txt"
            sentinel.write_text("original", encoding="utf-8")
            store = ProductionPackStore(output_root)

            with self.assertRaises(FileExistsError):
                store.save(ProductionPack(), run_id="existing-run")

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "original")
            self.assertEqual(list(run_directory.iterdir()), [sentinel])

    def test_save_writes_json_and_markdown_to_predictable_run_directory(self):
        pack = ProductionPack(script="A deterministic script")
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            store = ProductionPackStore(output_root)

            saved = store.save(pack, run_id="20260102T030405000000Z-a1b2c3d4")

            expected_directory = output_root / "20260102T030405000000Z-a1b2c3d4"
            self.assertEqual(saved.run_id, "20260102T030405000000Z-a1b2c3d4")
            self.assertEqual(saved.directory, expected_directory)
            self.assertEqual(saved.json_path, expected_directory / "production-pack.json")
            self.assertEqual(saved.markdown_path, expected_directory / "production-pack.md")
            self.assertEqual(
                saved.json_path.read_text(encoding="utf-8"),
                ProductionPackExporter.to_json(pack),
            )
            self.assertEqual(
                saved.markdown_path.read_text(encoding="utf-8"),
                ProductionPackExporter.to_markdown(pack),
            )


if __name__ == "__main__":
    unittest.main()
