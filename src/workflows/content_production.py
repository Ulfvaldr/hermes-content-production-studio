from datetime import datetime, timezone
from time import perf_counter

from src.agents.odin import Odin
from src.agents.bao import Bao
from src.agents.brokkr import Brokkr
from src.agents.veritas import Veritas
from src.outputs.production_pack import ProductionPackStore
from src.schemas.production_pack import ExecutionMetadata


class ContentProductionWorkflow:
    def __init__(
        self,
        max_revisions=1,
        clock=perf_counter,
        utc_now=None,
        production_pack_store=None,
    ):
        self.odin = Odin()
        self.bao = Bao()
        self.brokkr = Brokkr()
        self.veritas = Veritas()
        self.max_revisions = max_revisions
        self._clock = clock
        self._utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self.production_pack_store = (
            production_pack_store
            if production_pack_store is not None
            else ProductionPackStore()
        )
        self.last_saved_output = None

    def run(self, request):
        workflow_started = self._clock()
        started_at = self._utc_now().isoformat()
        stage_durations = {}

        print("[1/4] Starting Bao research...", flush=True)

        research = self._timed(
            "bao_research",
            stage_durations,
            self.bao.research,
            request,
        )

        print("[1/4] Bao complete.", flush=True)
        print("[2/4] Starting Brokkr production build...", flush=True)

        production_pack = self._timed(
            "brokkr_build",
            stage_durations,
            self.brokkr.build,
            request=request,
            research=research,
        )

        print("[2/4] Brokkr complete.", flush=True)

        revision_count = 0

        while True:
            print(
                f"[3/4] Starting Veritas QA "
                f"(revision {revision_count})...",
                flush=True,
            )

            qa_result = self._timed(
                "veritas_qa",
                stage_durations,
                self.veritas.review,
                request=request,
                production_pack=production_pack,
            )

            print(
                f"[3/4] Veritas result: {qa_result['status']}",
                flush=True,
            )

            if qa_result["status"] != "REVISION REQUIRED":
                break

            if revision_count >= self.max_revisions:
                print(
                    "[3/4] Maximum automatic revisions reached.",
                    flush=True,
                )
                break

            revision_count += 1

            print(
                f"[REVISION] Brokkr revision {revision_count} starting...",
                flush=True,
            )

            production_pack = self._timed(
                "brokkr_revision",
                stage_durations,
                self.brokkr.revise,
                request=request,
                production_pack=production_pack,
                qa_result=qa_result,
            )

            print(
                f"[REVISION] Brokkr revision {revision_count} complete.",
                flush=True,
            )

        print("[4/4] Odin finalizing package...", flush=True)

        final_pack = self._timed(
            "odin_finalize",
            stage_durations,
            self.odin.finalize,
            production_pack=production_pack,
            qa_result=qa_result,
        )

        print("[4/4] Odin complete.", flush=True)

        ended_at = self._utc_now().isoformat()
        total_duration = self._clock() - workflow_started
        final_pack.execution_metadata = ExecutionMetadata(
            started_at=started_at,
            ended_at=ended_at,
            total_duration_seconds=total_duration,
            agents_used=["Bao", "Brokkr", "Veritas", "Odin"],
            profiles_used=["bao", "brokkr", "veritas"],
            revision_count=revision_count,
            final_qa_status=qa_result["status"],
            automatic_revision_occurred=revision_count > 0,
            stage_durations_seconds=stage_durations,
        )

        self.last_saved_output = self.production_pack_store.save(
            final_pack,
            request=request,
        )

        return final_pack

    def _timed(self, stage, durations, operation, *args, **kwargs):
        started = self._clock()
        result = operation(*args, **kwargs)
        duration = self._clock() - started
        durations[stage] = durations.get(stage, 0.0) + duration
        return result
