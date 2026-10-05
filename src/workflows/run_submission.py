"""Application service for submitting local production runs."""

from src.outputs.production_pack import ProductionPackStore
from src.schemas.request import ContentRequest
from src.workflows.content_production import ContentProductionWorkflow


_REQUEST_FIELDS = (
    "topic",
    "target_audience",
    "objective",
    "duration",
    "production_type",
    "platform",
    "tone",
    "notes",
)


class SubmissionValidationError(ValueError):
    """The submitted request cannot start a production run."""


class SubmissionExecutionError(RuntimeError):
    """The workflow completed without a usable persisted-run identity."""


class RunSubmissionService:
    """Translate local form values into a persisted workflow run."""

    def __init__(self, output_root="outputs", workflow_factory=None):
        self.store = ProductionPackStore(output_root)
        self.workflow_factory = workflow_factory or self._create_workflow

    @staticmethod
    def _create_workflow(store):
        return ContentProductionWorkflow(production_pack_store=store)

    def submit(self, values):
        normalized = {
            field: (values.get(field) or "").strip() or None
            for field in _REQUEST_FIELDS
        }
        if normalized["topic"] is None:
            raise SubmissionValidationError("Topic is required.")
        request = ContentRequest(**normalized)
        workflow = self.workflow_factory(self.store)
        workflow.run(request)
        saved_output = getattr(workflow, "last_saved_output", None)
        run_id = getattr(saved_output, "run_id", None)
        if not isinstance(run_id, str) or not run_id:
            raise SubmissionExecutionError(
                "Workflow did not report a persisted output run ID."
            )
        return run_id
