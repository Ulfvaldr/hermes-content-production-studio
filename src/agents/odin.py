class Odin:
    def finalize(self, production_pack, qa_result):
        production_pack.qa_status = qa_result["status"]
        production_pack.qa_notes = qa_result["notes"]

        return production_pack