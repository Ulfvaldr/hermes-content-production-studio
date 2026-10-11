import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("__init__.py")
spec = importlib.util.spec_from_file_location("content_studio_plugin", MODULE_PATH)
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


class Context:
    def __init__(self, values):
        self.values = values
        self.handler = None

    def get_config(self, name, default=None):
        return self.values.get(name, default)

    def register_tool(self, **kwargs):
        self.handler = kwargs["handler"]


class ContentStudioPluginTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "studio_path": str(Path.cwd()),
            "python_executable": "python",
            "output_root": str(Path.cwd()),
            "runner_path": str(Path.cwd() / "runner.py"),
            "subprocess_timeout_seconds": 5,
            "max_retries": 1,
        }

    def test_registered_handler_uses_plugin_context_with_dispatch_kwargs(self):
        context = Context(self.config)
        plugin.register(context)
        with patch.object(plugin, "_run_with_retry", return_value={"success": True}):
            result = json.loads(context.handler(plugin._validate_request({
                "schema_version": plugin.REQUEST_SCHEMA,
                "topic": "topic", "target_audience": "audience", "objective": "objective",
                "duration": "1m", "production_type": "video", "platform": "web",
                "tone": "direct", "notes": "",
            }), task_id="task", session_id="session", user_task="request"))
        self.assertTrue(result["success"])

    def test_environment_is_minimal_and_excludes_secrets(self):
        with patch.dict(os.environ, {
            "PATH": "runtime-path",
            "SYSTEMROOT": "windows-root",
            "OPENAI_API_KEY": "secret",
            "HERMES_TOKEN": "secret",
            "RANDOM_APP_STATE": "secret",
        }, clear=True):
            env = plugin._build_subprocess_env(self.config)
        self.assertEqual(env["PATH"], "runtime-path")
        self.assertEqual(env["SYSTEMROOT"], "windows-root")
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("HERMES_TOKEN", env)
        self.assertNotIn("RANDOM_APP_STATE", env)
        self.assertEqual(env["CONTENT_STUDIO_STUDIO_PATH"], str(Path(self.config["studio_path"]).resolve()))

    def test_nonzero_submission_failure_is_not_retried(self):
        completed = subprocess.CompletedProcess([], 17, "", "failure")
        with patch.object(plugin.subprocess, "run", return_value=completed) as run:
            with self.assertRaises(plugin._IntegrationError) as raised:
                plugin._run_with_retry({"topic": "x"}, self.config, 0)
        self.assertEqual(raised.exception.code, "STUDIO_EXIT_NONZERO")
        self.assertFalse(raised.exception.retryable)
        run.assert_called_once()

    def test_timeout_submission_failure_is_not_retried(self):
        with patch.object(plugin.subprocess, "run", side_effect=subprocess.TimeoutExpired("python", 5)) as run:
            with self.assertRaises(plugin._IntegrationError) as raised:
                plugin._run_with_retry({"topic": "x"}, self.config, 0)
        self.assertEqual(raised.exception.code, "STUDIO_TIMEOUT")
        self.assertFalse(raised.exception.retryable)
        run.assert_called_once()

    def test_runner_start_failure_can_retry_once(self):
        completed = subprocess.CompletedProcess([], 0, '{"bad": true}', "")
        with patch.object(plugin.subprocess, "run", side_effect=[OSError("not started"), completed]) as run:
            with self.assertRaises(plugin._IntegrationError):
                plugin._run_with_retry({"topic": "x"}, self.config, 0)
        self.assertEqual(run.call_count, 2)

    def _valid_payload(self, status="PASS"):
        root = Path(self.tmp.name)
        run_dir = root / "run-1"
        run_dir.mkdir(exist_ok=True)
        (run_dir / "production-pack.json").write_text(json.dumps({"execution_metadata": {"run_id": "run-1"}}), encoding="utf-8")
        (run_dir / "production-pack.md").write_text("# Production pack\n", encoding="utf-8")
        values = {field: field + " value" for field in plugin.FIELDS}
        payload = {
            **values,
            "run_id": "run-1", "final_qa_status": status, "revision_count": 2,
            "automatic_revision": True, "total_duration_seconds": 12.5,
            "json_artifact_path": str(run_dir / "production-pack.json"),
            "markdown_artifact_path": str(run_dir / "production-pack.md"),
            "completion_summary": "done",
        }
        return payload, values

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = {
            "studio_path": str(Path.cwd()),
            "python_executable": "python",
            "output_root": self.tmp.name,
            "runner_path": str(Path.cwd() / "runner.py"),
            "subprocess_timeout_seconds": 5,
            "max_retries": 1,
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_pass_is_success_and_preserves_contract(self):
        payload, values = self._valid_payload("PASS")
        result = plugin._validate_result(payload, self.tmp.name, 0, values)
        self.assertTrue(result["success"])
        self.assertEqual(result["final_qa_status"], "PASS")
        self.assertEqual({field: result[field] for field in plugin.FIELDS}, values)
        self.assertEqual(result["automatic_revision_occurred"], True)

    def test_pass_with_issues_is_success_with_warning(self):
        payload, values = self._valid_payload("PASS WITH ISSUES")
        result = plugin._validate_result(payload, self.tmp.name, 0, values)
        self.assertTrue(result["success"])
        self.assertEqual(result["final_qa_status"], "PASS WITH ISSUES")
        self.assertIn("qa_warning", result)

    def test_revision_required_is_distinct_non_success(self):
        payload, values = self._valid_payload("REVISION REQUIRED")
        result = plugin._validate_result(payload, self.tmp.name, 0, values)
        self.assertFalse(result["success"])
        self.assertEqual(result["final_qa_status"], "REVISION REQUIRED")
        self.assertEqual(result["error"]["code"], "FINAL_QA_REVISION_REQUIRED")

    def test_unknown_or_malformed_qa_status_is_contract_error(self):
        for status in ("UNKNOWN", None, 42):
            with self.subTest(status=status):
                payload, values = self._valid_payload(status)
                with self.assertRaises(plugin._IntegrationError) as raised:
                    plugin._validate_result(payload, self.tmp.name, 0, values)
                self.assertEqual(raised.exception.code, "STUDIO_PROTOCOL_ERROR")

    def test_invalid_persisted_artifact_is_artifact_validation_failure(self):
        payload, values = self._valid_payload("PASS")
        (Path(self.tmp.name) / "run-1" / "production-pack.json").write_text("not json", encoding="utf-8")
        with self.assertRaises(plugin._IntegrationError) as raised:
            plugin._validate_result(payload, self.tmp.name, 0, values)
        self.assertEqual(raised.exception.code, "ARTIFACT_VALIDATION_FAILED")


if __name__ == "__main__":
    unittest.main()
