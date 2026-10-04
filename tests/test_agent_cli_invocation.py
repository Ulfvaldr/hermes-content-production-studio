import json
import subprocess
import unittest
from unittest.mock import patch

from src.agents.bao import Bao
from src.agents.brokkr import Brokkr
from src.agents.veritas import Veritas
from src.schemas.production_pack import ProductionPack
from src.schemas.request import ContentRequest


class AgentCliInvocationTests(unittest.TestCase):
    def setUp(self):
        self.request = ContentRequest(topic="A long prompt test")

    def assert_prompt_is_sent_over_stdin(self, run_mock, profile):
        run_mock.assert_called_once()
        args, kwargs = run_mock.call_args

        self.assertEqual(args[0], profile)
        self.assertIsInstance(args[1], str)
        self.assertIn("A long prompt test", args[1])
        self.assertEqual(kwargs, {})

    @patch("src.agents.bao.run_hermes_profile")
    def test_bao_sends_prompt_over_stdin(self, run_mock):
        payload = {
            "audience_observations": ["audience"],
            "important_facts": [],
            "creative_angles": [],
            "claims_to_verify": [],
            "hooks": [],
            "source_notes": [],
        }
        run_mock.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(payload), stderr=""
        )

        Bao().research(self.request)

        self.assert_prompt_is_sent_over_stdin(run_mock, "bao")

    @patch("src.agents.brokkr.run_hermes_profile")
    def test_brokkr_sends_prompt_over_stdin(self, run_mock):
        payload = {
            "creative_brief": "brief",
            "research_summary": "summary",
            "recommended_angle": "angle",
            "hook": "hook",
            "script": "script",
            "scene_plan": ["scene"],
            "shot_list": ["shot"],
            "b_roll": [],
            "ai_prompts": [],
            "continuity_guide": [],
            "voiceover": "voiceover",
            "on_screen_text": [],
            "title_options": [],
            "thumbnail_concept": "thumbnail",
            "production_checklist": ["check"],
        }
        run_mock.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(payload), stderr=""
        )

        Brokkr().build(self.request, research={})

        self.assert_prompt_is_sent_over_stdin(run_mock, "brokkr")

    @patch("src.agents.veritas.run_hermes_profile")
    def test_veritas_sends_prompt_over_stdin(self, run_mock):
        payload = {"status": "PASS", "notes": []}
        run_mock.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(payload), stderr=""
        )

        Veritas().review(self.request, ProductionPack())

        self.assert_prompt_is_sent_over_stdin(run_mock, "veritas")


if __name__ == "__main__":
    unittest.main()
