from src.agents.odin import Odin
from src.agents.bao import Bao
from src.agents.brokkr import Brokkr
from src.agents.veritas import Veritas


class ContentProductionWorkflow:
    def __init__(self, max_revisions=1):
        self.odin = Odin()
        self.bao = Bao()
        self.brokkr = Brokkr()
        self.veritas = Veritas()
        self.max_revisions = max_revisions

    def run(self, request):
        print("[1/4] Starting Bao research...", flush=True)

        research = self.bao.research(request)

        print("[1/4] Bao complete.", flush=True)
        print("[2/4] Starting Brokkr production build...", flush=True)

        production_pack = self.brokkr.build(
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

            qa_result = self.veritas.review(
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

            production_pack = self.brokkr.revise(
                request=request,
                production_pack=production_pack,
                qa_result=qa_result,
            )

            print(
                f"[REVISION] Brokkr revision {revision_count} complete.",
                flush=True,
            )

        print("[4/4] Odin finalizing package...", flush=True)

        final_pack = self.odin.finalize(
            production_pack=production_pack,
            qa_result=qa_result,
        )

        print("[4/4] Odin complete.", flush=True)

        return final_pack