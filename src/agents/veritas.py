import json

from src.utils.hermes_cli import extract_balanced_json_object, run_hermes_profile


class Veritas:
    EXPECTED_KEYS = {
        "status",
        "notes",
    }

    VALID_STATUSES = {
        "PASS",
        "PASS WITH ISSUES",
        "REVISION REQUIRED",
    }

    def review(self, request, production_pack):
        pack_json = json.dumps(
            {
                "creative_brief": production_pack.creative_brief,
                "research_summary": production_pack.research_summary,
                "recommended_angle": production_pack.recommended_angle,
                "hook": production_pack.hook,
                "script": production_pack.script,
                "scene_plan": production_pack.scene_plan,
                "shot_list": production_pack.shot_list,
                "b_roll": production_pack.b_roll,
                "ai_prompts": production_pack.ai_prompts,
                "continuity_guide": production_pack.continuity_guide,
                "voiceover": production_pack.voiceover,
                "on_screen_text": production_pack.on_screen_text,
                "title_options": production_pack.title_options,
                "thumbnail_concept": production_pack.thumbnail_concept,
                "production_checklist": production_pack.production_checklist,
            },
            indent=2,
            ensure_ascii=False,
        )

        prompt = f"""
You are Veritas, the independent QA agent for Hermes Content Production Studio.

Review the production package against the original user request.

ORIGINAL REQUEST

TOPIC:
{request.topic}

TARGET AUDIENCE:
{request.target_audience or "Not specified"}

OBJECTIVE:
{request.objective or "Not specified"}

DURATION:
{request.duration or "Not specified"}

PRODUCTION TYPE:
{request.production_type or "Not specified"}

PLATFORM:
{request.platform or "Not specified"}

TONE:
{request.tone or "Not specified"}

NOTES:
{request.notes or "None"}

PRODUCTION PACKAGE

{pack_json}

Review for:

- factual accuracy
- unsupported or overly strong claims
- script completeness
- scene continuity
- visual continuity
- audience alignment
- platform suitability
- requested duration
- production feasibility
- missing shots or assets
- quality of AI prompts where applicable
- whether the package satisfies the original objective

Do not rewrite the production package.

Return ONLY one valid JSON object:

{{
  "status": "PASS | PASS WITH ISSUES | REVISION REQUIRED",
  "notes": []
}}

Use:
- PASS when no meaningful issue remains.
- PASS WITH ISSUES when the package is usable but has minor issues.
- REVISION REQUIRED when important problems should be corrected before production.

Each note must be specific and actionable.

Do not use markdown code fences.
Do not add commentary before or after the JSON.
"""

        result = run_hermes_profile("veritas", prompt)
        output = result.stdout

        if not output:
            raise ValueError(
                "Hermes Veritas returned no output.\n\n"
                f"stderr:\n{result.stderr}"
            )

        qa_result = self._extract_final_json(output)

        if qa_result is None:
            raise ValueError(
                "Veritas ran successfully, but no valid QA JSON "
                "matching the expected schema was found.\n\n"
                f"Raw Hermes output:\n{output}"
            )

        return qa_result

    def _extract_final_json(self, text):
        anchor = '"status"'
        anchor_index = text.rfind(anchor)

        if anchor_index == -1:
            return None

        start = text.rfind("{", 0, anchor_index)

        while start != -1:
            candidate = self._extract_balanced_object(text, start)

            if candidate:
                try:
                    obj = json.loads(candidate)
                except json.JSONDecodeError:
                    obj = None

                if isinstance(obj, dict):
                    status = str(
                        obj.get("status", "")
                    ).strip().upper()

                    notes = obj.get("notes")

                    if (
                        self.EXPECTED_KEYS.issubset(obj.keys())
                        and status in self.VALID_STATUSES
                        and isinstance(notes, list)
                    ):
                        return {
                            "status": status,
                            "notes": [str(note) for note in notes],
                        }

            start = text.rfind("{", 0, start)

        return None

    _extract_balanced_object = staticmethod(extract_balanced_json_object)