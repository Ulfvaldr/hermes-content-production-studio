import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.schemas.production_pack import ProductionPack
from src.ui.run_browser import RunBrowser
from src.workflows.content_production import ContentProductionWorkflow
from src.workflows.run_submission import (
    RunSubmissionService,
    SubmissionExecutionError,
    SubmissionValidationError,
)


class RecordingWorkflow:
    def __init__(self, run_id="submitted-run"):
        self.requests = []
        self.last_saved_output = SimpleNamespace(run_id=run_id)

    def run(self, request):
        self.requests.append(request)


class FailingWorkflow(RecordingWorkflow):
    def run(self, request):
        super().run(request)
        raise RuntimeError("agent failed")


class FakeBao:
    def research(self, request):
        return {"summary": f"Research for {request.topic}"}


class FakeBrokkr:
    def build(self, request, research):
        return ProductionPack(script=f"Script for {request.topic}")


class FakeVeritas:
    def review(self, request, production_pack):
        return {"status": "PASS", "notes": []}


class FakeOdin:
    def finalize(self, production_pack, qa_result):
        production_pack.qa_status = qa_result["status"]
        return production_pack


class RunSubmissionServiceTests(unittest.TestCase):
    def test_submit_through_existing_workflow_creates_browsable_artifacts_and_history(self):
        def workflow_factory(store):
            workflow = ContentProductionWorkflow(production_pack_store=store)
            workflow.bao = FakeBao()
            workflow.brokkr = FakeBrokkr()
            workflow.veritas = FakeVeritas()
            workflow.odin = FakeOdin()
            return workflow

        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            service = RunSubmissionService(output_root, workflow_factory=workflow_factory)

            run_id = service.submit(
                {"topic": "Browsable submission", "platform": "YouTube"}
            )

            runs = service.store.list_runs()
            status, page = RunBrowser(output_root).response_for_path(f"/runs/{run_id}")
            self.assertEqual([entry["run_id"] for entry in runs], [run_id])
            self.assertEqual(runs[0]["topic"], "Browsable submission")
            self.assertTrue((output_root / run_id / "production-pack.json").is_file())
            self.assertTrue((output_root / run_id / "production-pack.md").is_file())
            self.assertEqual(status, 200)
            self.assertIn("Script for Browsable submission", page)

    def test_output_root_store_and_workflow_are_wired_to_the_same_store(self):
        workflow = RecordingWorkflow()
        received_stores = []
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "custom-outputs"
            service = RunSubmissionService(
                output_root=output_root,
                workflow_factory=lambda store: received_stores.append(store) or workflow,
            )

            service.submit({"topic": "Wiring check"})

            self.assertEqual(service.store.output_root, output_root)
            self.assertEqual(received_stores, [service.store])

    def test_submit_builds_request_runs_workflow_and_returns_persisted_run_id(self):
        workflow = RecordingWorkflow()
        with tempfile.TemporaryDirectory() as temp_dir:
            service = RunSubmissionService(
                output_root=Path(temp_dir) / "outputs",
                workflow_factory=lambda store: workflow,
            )

            run_id = service.submit(
                {
                    "topic": "  A practical local agent  ",
                    "target_audience": " Developers ",
                    "objective": " ",
                    "duration": "5 minutes",
                    "production_type": "Tutorial",
                    "platform": "YouTube",
                    "tone": "Direct",
                    "notes": "Use local examples",
                }
            )

        self.assertEqual(run_id, "submitted-run")
        self.assertEqual(len(workflow.requests), 1)
        request = workflow.requests[0]
        self.assertEqual(request.topic, "A practical local agent")
        self.assertEqual(request.target_audience, "Developers")
        self.assertIsNone(request.objective)
        self.assertEqual(request.duration, "5 minutes")
        self.assertEqual(request.production_type, "Tutorial")
        self.assertEqual(request.platform, "YouTube")
        self.assertEqual(request.tone, "Direct")
        self.assertEqual(request.notes, "Use local examples")

    def test_submit_rejects_blank_topic_before_starting_workflow(self):
        workflow = RecordingWorkflow()
        service = RunSubmissionService(workflow_factory=lambda store: workflow)

        with self.assertRaisesRegex(SubmissionValidationError, "Topic is required"):
            service.submit({"topic": "   ", "platform": "YouTube"})

        self.assertEqual(workflow.requests, [])

    def test_submit_rejects_workflow_that_does_not_report_a_persisted_output(self):
        workflow = RecordingWorkflow()
        workflow.last_saved_output = None
        service = RunSubmissionService(workflow_factory=lambda store: workflow)

        with self.assertRaisesRegex(
            SubmissionExecutionError, "did not report a persisted output"
        ):
            service.submit({"topic": "Malformed workflow result"})

    def test_workflow_failure_does_not_create_output_history_or_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            workflow = FailingWorkflow()
            service = RunSubmissionService(
                output_root, workflow_factory=lambda store: workflow
            )

            with self.assertRaisesRegex(RuntimeError, "agent failed"):
                service.submit({"topic": "Failed run"})

            self.assertFalse(output_root.exists())


if __name__ == "__main__":
    unittest.main()
