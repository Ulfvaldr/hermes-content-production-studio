import json
import os
import subprocess


class Bao:
    EXPECTED_KEYS = {
        "audience_observations",
        "important_facts",
        "creative_angles",
        "claims_to_verify",
        "hooks",
        "source_notes",
    }

    def research(self, request):
        prompt = f"""
You are Bao, the research specialist for Hermes Content Production Studio.

Research the following video/content project.

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

Your job is research, not script writing.

Return ONLY one valid JSON object with exactly these keys:

{{
  "audience_observations": [],
  "important_facts": [],
  "creative_angles": [],
  "claims_to_verify": [],
  "hooks": [],
  "source_notes": []
}}

Requirements:
- Use current research where useful.
- Do not invent product specifications.
- Clearly flag claims that require verification.
- Keep findings concise and useful to the production builder.
- source_notes should identify the source or source type behind factual findings.
- Do not use markdown code fences.
- Do not add commentary before or after the JSON.
"""

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["NO_COLOR"] = "1"

        result = subprocess.run(
            [
                "hermes",
                "-p",
                "bao",
                "chat",
                "--oneshot",
                "--quiet",
                "--query-file",
                "-",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=True,
        )

        output = (result.stdout or "").strip()

        if not output:
            raise ValueError(
                "Hermes Bao returned no output.\n\n"
                f"stderr:\n{result.stderr}"
            )

        research = self._extract_final_research_json(output)

        if research is None:
            raise ValueError(
                "Bao ran successfully, but no completed research JSON "
                "matching the expected schema was found.\n\n"
                f"Raw Hermes output:\n{output}"
            )

        return research

    def _extract_final_research_json(self, text):
        """
        Hermes may echo the prompt, show reasoning/tool output, and print
        session metadata. We locate the LAST occurrence of Bao's expected
        JSON schema and extract the balanced JSON object around it.
        """

        anchor = '"audience_observations"'
        anchor_index = text.rfind(anchor)

        if anchor_index == -1:
            return None

        # Walk backward from the final schema occurrence to its opening brace.
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
                    and any(obj.get(key) for key in self.EXPECTED_KEYS)
                ):
                    return obj

            # Try the previous opening brace if this one wasn't the object.
            start = text.rfind("{", 0, start)

        return None

    @staticmethod
    def _extract_balanced_object(text, start):
        """
        Extract one JSON-style {...} object while respecting quoted strings
        and escaped characters.
        """

        depth = 0
        in_string = False
        escaped = False

        for index in range(start, len(text)):
            char = text[index]

            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False

                continue

            if char == '"':
                in_string = True

            elif char == "{":
                depth += 1

            elif char == "}":
                depth -= 1

                if depth == 0:
                    return text[start:index + 1]

        return None