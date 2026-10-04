import subprocess
import unittest
from unittest.mock import patch

from src.utils.hermes_cli import extract_balanced_json_object, run_hermes_profile


class HermesCliTests(unittest.TestCase):
    @patch("src.utils.hermes_cli.subprocess.run")
    def test_run_hermes_profile_invokes_cli_over_stdin(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=" result \n", stderr="warning"
        )

        result = run_hermes_profile("bao", "prompt", timeout=17)

        self.assertEqual(result.stdout, "result")
        self.assertEqual(result.stderr, "warning")
        run_mock.assert_called_once()
        args, kwargs = run_mock.call_args
        self.assertEqual(
            args[0],
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
        )
        self.assertEqual(kwargs["input"], "prompt")
        self.assertTrue(kwargs["capture_output"])
        self.assertTrue(kwargs["text"])
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(kwargs["errors"], "replace")
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["timeout"], 17)
        self.assertEqual(kwargs["env"]["PYTHONUTF8"], "1")
        self.assertEqual(kwargs["env"]["NO_COLOR"], "1")

    @patch("src.utils.hermes_cli.subprocess.run")
    def test_run_hermes_profile_reports_timeout_with_profile_context(self, run_mock):
        run_mock.side_effect = subprocess.TimeoutExpired(
            cmd=["hermes"], timeout=23
        )

        with self.assertRaisesRegex(
            TimeoutError, "Hermes profile 'veritas' timed out after 23 seconds"
        ):
            run_hermes_profile("veritas", "prompt", timeout=23)

    def test_extract_balanced_json_object_respects_braces_in_strings(self):
        text = 'prefix {"message": "brace } and \\"quoted\\"", "nested": {}} suffix'

        self.assertEqual(
            extract_balanced_json_object(text, text.index("{")),
            '{"message": "brace } and \\"quoted\\"", "nested": {}}',
        )


if __name__ == "__main__":
    unittest.main()
