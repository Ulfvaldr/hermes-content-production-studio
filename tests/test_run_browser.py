import json
import socket
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from src.workflows.run_submission import SubmissionValidationError

from src.ui.run_browser import (
    RunBrowser,
    create_server,
    format_duration,
    format_timestamp,
    render_markdown,
)


def run_entry(run_id, completed_at, **overrides):
    entry = {
        "run_id": run_id,
        "created_at": completed_at,
        "completed_at": completed_at,
        "topic": f"Topic {run_id}",
        "target_audience": "Developers",
        "platform": "YouTube",
        "production_type": "Tutorial",
        "final_qa_status": "PASS",
        "revision_count": 1,
        "automatic_revision_occurred": True,
        "total_duration_seconds": 65.25,
        "json_path": f"{run_id}/production-pack.json",
        "markdown_path": f"{run_id}/production-pack.md",
    }
    entry.update(overrides)
    return entry


def write_history(output_root, entries):
    output_root.mkdir(parents=True)
    (output_root / "index.json").write_text(
        json.dumps({"version": 1, "runs": entries}), encoding="utf-8"
    )


def write_artifacts(output_root, run_id, markdown, pack):
    run_directory = output_root / run_id
    run_directory.mkdir()
    (run_directory / "production-pack.md").write_text(markdown, encoding="utf-8")
    (run_directory / "production-pack.json").write_text(
        json.dumps(pack), encoding="utf-8"
    )


class RecordingSubmitter:
    def __init__(self, result="submitted-run", error=None):
        self.values = []
        self.result = result
        self.error = error

    def submit(self, values):
        self.values.append(values)
        if self.error:
            raise self.error
        return self.result


class RunBrowserListingTests(unittest.TestCase):
    def test_missing_index_has_clear_first_run_guidance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            browser = RunBrowser(Path(temp_dir) / "outputs")

            status, page = browser.response_for_path("/")

            self.assertEqual(status, 200)
            self.assertIn("No run history index was found", page)
            self.assertIn("outputs/index.json", page)

    def test_empty_index_explains_that_no_runs_are_available(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            write_history(output_root, [])

            status, page = RunBrowser(output_root).response_for_path("/")

            self.assertEqual(status, 200)
            self.assertIn("No completed runs yet", page)

    def test_home_includes_minimal_run_submission_form(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            status, page = RunBrowser(Path(temp_dir) / "outputs").response_for_path("/")

        self.assertEqual(status, 200)
        self.assertIn('<form method="post" action="/runs">', page)
        self.assertIn('name="topic"', page)
        self.assertIn("required", page)
        self.assertIn('name="target_audience"', page)
        self.assertIn('name="objective"', page)
        self.assertIn('name="duration"', page)
        self.assertIn('name="production_type"', page)
        self.assertIn('name="platform"', page)
        self.assertIn('name="tone"', page)
        self.assertIn('name="notes"', page)

    def test_malformed_index_returns_clear_error_without_changing_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            output_root.mkdir()
            index_path = output_root / "index.json"
            original = b"{not json"
            index_path.write_bytes(original)

            status, page = RunBrowser(output_root).response_for_path("/")

            self.assertEqual(status, 500)
            self.assertIn("Run history is malformed", page)
            self.assertIn("malformed run history index", page)
            self.assertEqual(index_path.read_bytes(), original)

    def test_home_lists_completed_runs_newest_first_with_summary_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            write_history(
                output_root,
                [
                    run_entry("older", "2026-01-01T00:00:00+00:00"),
                    run_entry("newer", "2026-01-02T00:00:00+00:00"),
                ],
            )

            page = RunBrowser(output_root).render_home()

            self.assertLess(page.index("newer"), page.index("older"))
            for value in (
                "Topic newer",
                "Jan 2, 2026, 12:00 AM UTC",
                "YouTube",
                "Tutorial",
                "PASS",
                "1",
                "1m 5.25s",
            ):
                self.assertIn(value, page)
            self.assertIn('/runs/newer', page)


class RunBrowserDetailTests(unittest.TestCase):
    def test_unknown_run_id_returns_clear_not_found_page(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            write_history(output_root, [])

            status, page = RunBrowser(output_root).response_for_path("/runs/unknown")

            self.assertEqual(status, 404)
            self.assertIn("Run not found", page)
            self.assertIn("unknown", page)

    def test_missing_referenced_artifact_returns_clear_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            write_history(
                output_root,
                [run_entry("missing-artifact", "2026-01-02T03:05:10+00:00")],
            )

            status, page = RunBrowser(output_root).response_for_path(
                "/runs/missing-artifact"
            )

            self.assertEqual(status, 500)
            self.assertIn("Artifact is missing", page)
            self.assertIn("missing-artifact/production-pack.json", page)

    def test_missing_markdown_artifact_returns_clear_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            entry = run_entry("missing-markdown", "2026-01-02T03:05:10+00:00")
            write_history(output_root, [entry])
            run_directory = output_root / "missing-markdown"
            run_directory.mkdir()
            (run_directory / "production-pack.json").write_text(
                json.dumps({"qa_status": "PASS"}), encoding="utf-8"
            )

            status, page = RunBrowser(output_root).response_for_path(
                "/runs/missing-markdown"
            )

            self.assertEqual(status, 500)
            self.assertIn("Artifact is missing", page)
            self.assertIn("missing-markdown/production-pack.md", page)

    def test_detail_renders_persisted_markdown_and_execution_information(self):
        markdown = "# Production Pack\n\n## Script\n\nUse **safe** tools.\n\n- First shot\n"
        pack = {
            "qa_status": "PASS",
            "qa_notes": ["Sources verified"],
            "execution_metadata": {
                "started_at": "2026-01-02T03:04:05+00:00",
                "ended_at": "2026-01-02T03:05:10+00:00",
                "total_duration_seconds": 65.25,
                "agents_used": ["Bao", "Brokkr", "Veritas"],
                "profiles_used": ["research", "production"],
                "revision_count": 1,
                "final_qa_status": "PASS",
                "automatic_revision_occurred": True,
                "stage_durations_seconds": {"research": 20.0},
                "cost_credits": None,
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            entry = run_entry("detail-run", "2026-01-02T03:05:10+00:00")
            write_history(output_root, [entry])
            write_artifacts(output_root, "detail-run", markdown, pack)
            original = (output_root / entry["markdown_path"]).read_bytes()

            page = RunBrowser(output_root).render_run("detail-run")

            self.assertIn("<h1>Production Pack</h1>", page)
            self.assertIn("<h2>Script</h2>", page)
            self.assertIn("Use <strong>safe</strong> tools.", page)
            self.assertIn("<li>First shot</li>", page)
            for value in (
                "detail-run/production-pack.json",
                "Available",
                "Bao, Brokkr, Veritas",
                "research, production",
                "Sources verified",
                "Automatic revision",
                "Yes",
            ):
                self.assertIn(value, page)
            self.assertEqual(
                (output_root / entry["markdown_path"]).read_bytes(), original
            )


class RunBrowserSubmissionTests(unittest.TestCase):
    def test_valid_submission_delegates_and_redirects_to_persisted_run(self):
        submitter = RecordingSubmitter(result="new-run")
        browser = RunBrowser("outputs", submission_service=submitter)
        values = {"topic": "Local workflow", "platform": "YouTube"}

        status, page, location = browser.response_for_submission(values)

        self.assertEqual(status, 303)
        self.assertEqual(page, "")
        self.assertEqual(location, "/runs/new-run")
        self.assertEqual(submitter.values, [values])

    def test_invalid_submission_returns_form_error_and_preserves_input(self):
        submitter = RecordingSubmitter(
            error=SubmissionValidationError("Topic is required.")
        )
        browser = RunBrowser("outputs", submission_service=submitter)

        status, page, location = browser.response_for_submission(
            {"topic": "   ", "platform": '<unsafe & platform>'}
        )

        self.assertEqual(status, 400)
        self.assertIsNone(location)
        self.assertIn("Topic is required.", page)
        self.assertIn("&lt;unsafe &amp; platform&gt;", page)
        self.assertNotIn("<unsafe & platform>", page)

    def test_workflow_failure_returns_clear_error_without_redirect(self):
        browser = RunBrowser(
            "outputs",
            submission_service=RecordingSubmitter(error=RuntimeError("Hermes unavailable")),
        )

        status, page, location = browser.response_for_submission(
            {"topic": "Local workflow"}
        )

        self.assertEqual(status, 500)
        self.assertIsNone(location)
        self.assertIn("Run could not be completed", page)
        self.assertNotIn("Hermes unavailable", page)
        self.assertIn("Local workflow", page)


class RenderingHelperTests(unittest.TestCase):
    def test_formatting_helpers_make_persisted_values_readable(self):
        self.assertEqual(
            format_timestamp("2026-01-02T03:04:05+00:00"),
            "Jan 2, 2026, 3:04 AM UTC",
        )
        self.assertEqual(format_duration(5), "5s")
        self.assertEqual(format_duration(65.25), "1m 5.25s")

    def test_format_timestamp_converts_offset_input_to_utc(self):
        self.assertEqual(
            format_timestamp("2026-01-02T03:04:05-05:00"),
            "Jan 2, 2026, 8:04 AM UTC",
        )

    def test_format_timestamp_assumes_naive_input_is_utc(self):
        self.assertEqual(
            format_timestamp("2026-01-02T03:04:05"),
            "Jan 2, 2026, 3:04 AM UTC",
        )

    def test_markdown_renderer_escapes_artifact_html(self):
        rendered = render_markdown("## Script\n\n<script>alert(1)</script> **bold**")

        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertIn("<strong>bold</strong>", rendered)


class RunBrowserHttpTests(unittest.TestCase):
    def _start_server(self, submitter=None):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        server = create_server(
            "127.0.0.1",
            0,
            Path(self.temp_dir.name) / "outputs",
            submission_service=submitter,
        )
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    @staticmethod
    def _raw_request(server, request):
        with socket.create_connection(("127.0.0.1", server.server_port), timeout=5) as sock:
            sock.sendall(request)
            sock.shutdown(socket.SHUT_WR)
            response = bytearray()
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response.extend(chunk)
        status_line, _, body = bytes(response).partition(b"\r\n\r\n")
        return int(status_line.split(b" ", 2)[1]), body.decode("utf-8")

    def test_server_accepts_form_submission_and_redirects_to_new_run(self):
        submitter = RecordingSubmitter(result="http-run")
        with tempfile.TemporaryDirectory() as temp_dir:
            server = create_server(
                "127.0.0.1",
                0,
                Path(temp_dir) / "outputs",
                submission_service=submitter,
            )
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                body = urlencode({"topic": "HTTP workflow", "tone": "Direct"})
                connection.request(
                    "POST",
                    "/runs",
                    body=body,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Origin": f"http://127.0.0.1:{server.server_port}",
                    },
                )
                response = connection.getresponse()
                response.read()

                self.assertEqual(response.status, 303)
                self.assertEqual(response.getheader("Location"), "/runs/http-run")
                self.assertEqual(
                    submitter.values,
                    [{"topic": "HTTP workflow", "tone": "Direct"}],
                )
            finally:
                connection.close()
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_server_rejects_cross_origin_submission_before_workflow(self):
        submitter = RecordingSubmitter()
        server = self._start_server(submitter)
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        self.addCleanup(connection.close)

        connection.request(
            "POST",
            "/runs",
            body="topic=Do+not+run",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://attacker.example",
            },
        )
        response = connection.getresponse()
        body = response.read().decode("utf-8")

        self.assertEqual(response.status, 403)
        self.assertIn("Cross-origin submission rejected", body)
        self.assertEqual(submitter.values, [])

    def test_server_rejects_missing_malformed_and_negative_content_length(self):
        submitter = RecordingSubmitter()
        server = self._start_server(submitter)
        origin = f"http://127.0.0.1:{server.server_port}"
        base = (
            "POST /runs HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{server.server_port}\r\n"
            f"Origin: {origin}\r\n"
            "Content-Type: application/x-www-form-urlencoded\r\n"
        )

        for label, length, expected_status in (
            ("missing", None, 411),
            ("malformed", "nope", 400),
            ("negative", "-1", 400),
        ):
            with self.subTest(label=label):
                header = "" if length is None else f"Content-Length: {length}\r\n"
                status, body = self._raw_request(
                    server, (base + header + "Connection: close\r\n\r\n").encode("ascii")
                )
                self.assertEqual(status, expected_status)
                self.assertIn("Content-Length", body)
        self.assertEqual(submitter.values, [])

    def test_server_rejects_truncated_body_before_workflow(self):
        submitter = RecordingSubmitter()
        server = self._start_server(submitter)
        origin = f"http://127.0.0.1:{server.server_port}"
        request = (
            "POST /runs HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{server.server_port}\r\n"
            f"Origin: {origin}\r\n"
            "Content-Type: application/x-www-form-urlencoded\r\n"
            "Content-Length: 10\r\n"
            "Connection: close\r\n\r\n"
            "topic=abc"
        ).encode("ascii")

        status, body = self._raw_request(server, request)

        self.assertEqual(status, 400)
        self.assertIn("Incomplete request body", body)
        self.assertEqual(submitter.values, [])

    def test_server_times_out_stalled_body_before_workflow(self):
        submitter = RecordingSubmitter()
        server = self._start_server(submitter)
        origin = f"http://127.0.0.1:{server.server_port}"
        crlf = bytes((13, 10))
        request = crlf.join(
            (
                b"POST /runs HTTP/1.1",
                f"Host: 127.0.0.1:{server.server_port}".encode("ascii"),
                f"Origin: {origin}".encode("ascii"),
                b"Content-Type: application/x-www-form-urlencoded",
                b"Content-Length: 9",
                b"Connection: close",
            )
        ) + crlf + crlf

        with socket.create_connection(
            ("127.0.0.1", server.server_port), timeout=3
        ) as sock:
            sock.sendall(request)
            response = bytearray()
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response.extend(chunk)

        headers, _, body = bytes(response).partition(crlf + crlf)
        status = int(headers.split(b" ", 2)[1])
        self.assertEqual(status, 408)
        self.assertIn("Request body timed out", body.decode("utf-8"))
        self.assertEqual(submitter.values, [])

    def test_server_times_out_slow_drip_body_before_workflow(self):
        submitter = RecordingSubmitter()
        server = self._start_server(submitter)
        origin = f"http://127.0.0.1:{server.server_port}"
        crlf = bytes((13, 10))
        body = b"topic=abc"
        request = crlf.join(
            (
                b"POST /runs HTTP/1.1",
                f"Host: 127.0.0.1:{server.server_port}".encode("ascii"),
                f"Origin: {origin}".encode("ascii"),
                b"Content-Type: application/x-www-form-urlencoded",
                f"Content-Length: {len(body)}".encode("ascii"),
                b"Connection: close",
            )
        ) + crlf + crlf

        with socket.create_connection(
            ("127.0.0.1", server.server_port), timeout=3
        ) as sock:
            sock.sendall(request)
            response = bytearray()
            response_complete = threading.Event()

            def receive_response():
                try:
                    while True:
                        chunk = sock.recv(4096)
                        if not chunk:
                            break
                        response.extend(chunk)
                except OSError:
                    pass
                finally:
                    response_complete.set()

            receiver = threading.Thread(target=receive_response)
            receiver.start()
            for byte in body:
                if response_complete.is_set():
                    break
                try:
                    sock.sendall(bytes((byte,)))
                except OSError:
                    break
                if response_complete.wait(0.2):
                    break
            receiver.join(timeout=3)

        self.assertFalse(receiver.is_alive())
        headers, _, response_body = bytes(response).partition(crlf + crlf)
        status = int(headers.split(b" ", 2)[1])
        self.assertEqual(status, 408)
        self.assertIn("Request body timed out", response_body.decode("utf-8"))
        self.assertEqual(submitter.values, [])

    def test_server_rejects_unsupported_content_type_and_invalid_utf8(self):
        submitter = RecordingSubmitter()
        server = self._start_server(submitter)
        origin = f"http://127.0.0.1:{server.server_port}"

        for body, content_type, expected_status, message in (
            (b'{"topic":"no"}', "application/json", 415, "Unsupported content type"),
            (b"topic=bad\xff", "application/x-www-form-urlencoded", 400, "UTF-8"),
            (b"topic=%FF", "application/x-www-form-urlencoded", 400, "form data"),
        ):
            with self.subTest(message=message):
                connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                connection.request(
                    "POST",
                    "/runs",
                    body=body,
                    headers={"Content-Type": content_type, "Origin": origin},
                )
                response = connection.getresponse()
                page = response.read().decode("utf-8")
                connection.close()
                self.assertEqual(response.status, expected_status)
                self.assertIn(message, page)
        self.assertEqual(submitter.values, [])

    def test_server_enforces_request_and_field_size_limits_before_workflow(self):
        submitter = RecordingSubmitter()
        server = self._start_server(submitter)
        origin = f"http://127.0.0.1:{server.server_port}"

        for body, expected_status, message in (
            (b"x" * 65537, 413, "Request body is too large"),
            (urlencode({"topic": "x" * 10001}).encode(), 400, "Topic is too long"),
        ):
            with self.subTest(message=message):
                connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                connection.request(
                    "POST",
                    "/runs",
                    body=body,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Origin": origin,
                    },
                )
                response = connection.getresponse()
                page = response.read().decode("utf-8")
                connection.close()
                self.assertEqual(response.status, expected_status)
                self.assertIn(message, page)
        self.assertEqual(submitter.values, [])

    def test_server_serves_the_run_list_over_local_http(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            write_history(
                output_root,
                [run_entry("served-run", "2026-01-02T03:05:10+00:00")],
            )
            server = create_server("127.0.0.1", 0, output_root)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                with urlopen(
                    f"http://127.0.0.1:{server.server_port}/", timeout=5
                ) as response:
                    body = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get_content_type(), "text/html")
                self.assertIn("served-run", body)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
