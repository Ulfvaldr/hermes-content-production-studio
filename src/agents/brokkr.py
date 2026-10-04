import json

from src.schemas.production_pack import ProductionPack
from src.utils.hermes_cli import extract_balanced_json_object, run_hermes_profile


class Brokkr:
    EXPECTED_KEYS = {
        "creative_brief",
        "research_summary",
        "recommended_angle",
        "hook",
        "script",
        "scene_plan",
        "shot_list",
        "b_roll",
        "ai_prompts",
        "continuity_guide",
        "voiceover",
        "on_screen_text",
        "title_options",
        "thumbnail_concept",
        "production_checklist",
    }

    def build(self, request, research):
        research_json = json.dumps(
            research,
            indent=2,
            ensure_ascii=False,
        )

        prompt = f"""
You are Brokkr, the production builder for Hermes Content Production Studio.

Create a complete production-ready video plan from the user's request and
Bao's research.

USER REQUEST

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

BAO RESEARCH

{research_json}

{self._output_instructions()}
"""

        return self._run_brokkr(prompt)

    def revise(self, request, production_pack, qa_result):
        pack_json = self._pack_to_json(production_pack)

        qa_json = json.dumps(
            qa_result,
            indent=2,
            ensure_ascii=False,
        )

        prompt = f"""
You are Brokkr, the production builder for Hermes Content Production Studio.

Veritas reviewed your production package and found issues that must be fixed.

Revise the current package.

Do not start over unnecessarily.
Preserve strong material that was not criticized.
Correct every actionable Veritas finding.

ORIGINAL USER REQUEST

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

CURRENT PRODUCTION PACKAGE

{pack_json}

VERITAS QA

{qa_json}

Requirements:
- Address every Veritas note.
- Remove unsafe, misleading, unsupported, or overly broad claims.
- Correct timing and continuity issues.
- Preserve the requested audience, platform, tone, duration, and production type.
- Return the complete revised package, not only changed sections.
- Do not mention the revision process in the package.

{self._output_instructions()}
"""

        return self._run_brokkr(prompt)

    def _run_brokkr(self, prompt):
        result = run_hermes_profile("brokkr", prompt)
        output = result.stdout

        if not output:
            raise ValueError(
                "Hermes Brokkr returned no output.\n\n"
                f"stderr:\n{result.stderr}"
            )

        obj = self._extract_final_json(output)

        if obj is None:
            raise ValueError(
                "Brokkr ran successfully, but no completed production JSON "
                "matching the expected schema was found.\n\n"
                f"Raw Hermes output:\n{output}"
            )

        return self._dict_to_pack(obj)

    def _output_instructions(self):
        return """
Return ONLY one valid JSON object using exactly these keys:

{
  "creative_brief": "",
  "research_summary": "",
  "recommended_angle": "",
  "hook": "",
  "script": "",
  "scene_plan": [],
  "shot_list": [],
  "b_roll": [],
  "ai_prompts": [],
  "continuity_guide": [],
  "voiceover": "",
  "on_screen_text": [],
  "title_options": [],
  "thumbnail_concept": "",
  "production_checklist": []
}

Requirements:
- Script must be production-ready.
- Scene timing must match the requested duration.
- Shot instructions must be practical.
- Do not invent unsupported specifications.
- Qualify or remove claims requiring product-specific verification.
- AI prompts must not misrepresent the product.
- Maintain visual and narrative continuity.
- Voiceover must be ready to read aloud.
- Keep platform requirements in mind.
- Production checklist must be actionable.
- Do not use markdown fences.
- Do not add commentary before or after the JSON.
"""

    @staticmethod
    def _pack_to_json(pack):
        return json.dumps(
            {
                "creative_brief": pack.creative_brief,
                "research_summary": pack.research_summary,
                "recommended_angle": pack.recommended_angle,
                "hook": pack.hook,
                "script": pack.script,
                "scene_plan": pack.scene_plan,
                "shot_list": pack.shot_list,
                "b_roll": pack.b_roll,
                "ai_prompts": pack.ai_prompts,
                "continuity_guide": pack.continuity_guide,
                "voiceover": pack.voiceover,
                "on_screen_text": pack.on_screen_text,
                "title_options": pack.title_options,
                "thumbnail_concept": pack.thumbnail_concept,
                "production_checklist": pack.production_checklist,
            },
            indent=2,
            ensure_ascii=False,
        )

    @staticmethod
    def _dict_to_pack(obj):
        return ProductionPack(
            creative_brief=obj["creative_brief"],
            research_summary=obj["research_summary"],
            recommended_angle=obj["recommended_angle"],
            hook=obj["hook"],
            script=obj["script"],
            scene_plan=obj["scene_plan"],
            shot_list=obj["shot_list"],
            b_roll=obj["b_roll"],
            ai_prompts=obj["ai_prompts"],
            continuity_guide=obj["continuity_guide"],
            voiceover=obj["voiceover"],
            on_screen_text=obj["on_screen_text"],
            title_options=obj["title_options"],
            thumbnail_concept=obj["thumbnail_concept"],
            production_checklist=obj["production_checklist"],
        )

    def _extract_final_json(self, text):
        anchor = '"creative_brief"'
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

                if (
                    isinstance(obj, dict)
                    and self.EXPECTED_KEYS.issubset(obj.keys())
                    and self._looks_complete(obj)
                ):
                    return obj

            start = text.rfind("{", 0, start)

        return None

    @staticmethod
    def _looks_complete(obj):
        required_text = [
            "creative_brief",
            "recommended_angle",
            "hook",
            "script",
            "voiceover",
            "thumbnail_concept",
        ]

        required_lists = [
            "scene_plan",
            "shot_list",
            "production_checklist",
        ]

        for key in required_text:
            value = obj.get(key)

            if not isinstance(value, str) or not value.strip():
                return False

        for key in required_lists:
            value = obj.get(key)

            if not isinstance(value, list) or not value:
                return False

        return True

    _extract_balanced_object = staticmethod(extract_balanced_json_object)