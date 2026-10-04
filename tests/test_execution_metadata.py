import unittest
from datetime import datetime, timezone

from src.schemas.production_pack import ExecutionMetadata, ProductionPack
from src.workflows.content_production import ContentProductionWorkflow


class ExecutionMetadataSchemaTests(unittest.TestCase):
    def test_production_pack_has_backward_compatible_metadata_defaults(self):
        pack = ProductionPack()

        self.assertIsInstance(pack.execution_metadata, ExecutionMetadata)
        self.assertEqual(pack.execution_metadata.started_at, "")
        self.assertEqual(pack.execution_metadata.ended_at, "")
        self.assertEqual(pack.execution_metadata.total_duration_seconds, 0.0)
        self.assertEqual(pack.execution_metadata.agents_used, [])
        self.assertEqual(pack.execution_metadata.profiles_used, [])
        self.assertEqual(pack.execution_metadata.revision_count, 0)
        self.assertEqual(pack.execution_metadata.final_qa_status, "")
        self.assertFalse(pack.execution_metadata.automatic_revision_occurred)
        self.assertEqual(pack.execution_metadata.stage_durations_seconds, {})
        self.assertIsNone(pack.execution_metadata.cost_credits)


class FakeBao:
    def research(self, request):
        return {"research": "complete"}


class FakeBrokkr:
    def build(self, request, research):
        return ProductionPack(script="draft")

    def revise(self, request, production_pack, qa_result):
        production_pack.script = "revised"
        return production_pack


class FakeVeritas:
    def __init__(self, results):
        self.results = iter(results)

    def review(self, request, production_pack):
        return next(self.results)


class FakeOdin:
    def finalize(self, production_pack, qa_result):
        production_pack.qa_status = qa_result["status"]
        production_pack.qa_notes = qa_result["notes"]
        return production_pack


class SequenceClock:
    def __init__(self, values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


class ExecutionMetadataWorkflowTests(unittest.TestCase):
    def test_pass_records_workflow_and_stage_timing(self):
        timestamps = iter(
            [
                datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
                datetime(2026, 1, 2, 3, 4, 25, tzinfo=timezone.utc),
            ]
        )
        workflow = ContentProductionWorkflow(
            clock=SequenceClock([0, 1, 3, 4, 7, 8, 13, 14, 16, 20]),
            utc_now=lambda: next(timestamps),
        )
        workflow.bao = FakeBao()
        workflow.brokkr = FakeBrokkr()
        workflow.veritas = FakeVeritas([{"status": "PASS", "notes": []}])
        workflow.odin = FakeOdin()

        pack = workflow.run(object())

        metadata = pack.execution_metadata
        self.assertEqual(metadata.started_at, "2026-01-02T03:04:05+00:00")
        self.assertEqual(metadata.ended_at, "2026-01-02T03:04:25+00:00")
        self.assertEqual(metadata.total_duration_seconds, 20.0)
        self.assertEqual(
            metadata.stage_durations_seconds,
            {
                "bao_research": 2.0,
                "brokkr_build": 3.0,
                "veritas_qa": 5.0,
                "odin_finalize": 2.0,
            },
        )
        self.assertEqual(metadata.agents_used, ["Bao", "Brokkr", "Veritas", "Odin"])
        self.assertEqual(metadata.profiles_used, ["bao", "brokkr", "veritas"])
        self.assertEqual(metadata.final_qa_status, "PASS")
        self.assertEqual(metadata.revision_count, 0)
        self.assertFalse(metadata.automatic_revision_occurred)

    def test_automatic_revision_records_count_and_cumulative_stage_timing(self):
        timestamps = iter(
            [
                datetime(2026, 2, 1, tzinfo=timezone.utc),
                datetime(2026, 2, 1, 0, 0, 30, tzinfo=timezone.utc),
            ]
        )
        workflow = ContentProductionWorkflow(
            clock=SequenceClock([0, 1, 2, 3, 5, 6, 9, 10, 14, 15, 20, 21, 23, 30]),
            utc_now=lambda: next(timestamps),
        )
        workflow.bao = FakeBao()
        workflow.brokkr = FakeBrokkr()
        workflow.veritas = FakeVeritas(
            [
                {"status": "REVISION REQUIRED", "notes": ["Fix it"]},
                {"status": "PASS WITH ISSUES", "notes": ["Minor issue"]},
            ]
        )
        workflow.odin = FakeOdin()

        pack = workflow.run(object())

        metadata = pack.execution_metadata
        self.assertEqual(metadata.revision_count, 1)
        self.assertTrue(metadata.automatic_revision_occurred)
        self.assertEqual(metadata.final_qa_status, "PASS WITH ISSUES")
        self.assertEqual(
            metadata.stage_durations_seconds,
            {
                "bao_research": 1.0,
                "brokkr_build": 2.0,
                "veritas_qa": 8.0,
                "brokkr_revision": 4.0,
                "odin_finalize": 2.0,
            },
        )
        self.assertEqual(metadata.total_duration_seconds, 30.0)

    def test_revision_required_at_limit_is_preserved_in_metadata(self):
        timestamps = iter(
            [
                datetime(2026, 3, 1, tzinfo=timezone.utc),
                datetime(2026, 3, 1, 0, 0, 10, tzinfo=timezone.utc),
            ]
        )
        workflow = ContentProductionWorkflow(
            max_revisions=0,
            clock=SequenceClock([0, 1, 2, 3, 4, 5, 6, 7, 8, 10]),
            utc_now=lambda: next(timestamps),
        )
        workflow.bao = FakeBao()
        workflow.brokkr = FakeBrokkr()
        workflow.veritas = FakeVeritas(
            [{"status": "REVISION REQUIRED", "notes": ["Unresolved"]}]
        )
        workflow.odin = FakeOdin()

        pack = workflow.run(object())

        metadata = pack.execution_metadata
        self.assertEqual(metadata.final_qa_status, "REVISION REQUIRED")
        self.assertEqual(metadata.revision_count, 0)
        self.assertFalse(metadata.automatic_revision_occurred)
        self.assertNotIn("brokkr_revision", metadata.stage_durations_seconds)


if __name__ == "__main__":
    unittest.main()
