"""Dependency-free local browser and production run submission UI."""

import argparse
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, unquote, urlsplit

from src.outputs.production_pack import ProductionPackStore
from src.workflows.run_submission import RunSubmissionService, SubmissionValidationError


_MAX_REQUEST_BODY_BYTES = 64 * 1024
_MAX_FIELD_CHARACTERS = 10_000
_REQUEST_BODY_TIMEOUT_SECONDS = 1.0
_LOGGER = logging.getLogger(__name__)

_STYLES = """
:root { color-scheme: dark; --bg:#0b1020; --panel:#151c30; --line:#2b3655;
  --text:#eef2ff; --muted:#aeb9d6; --accent:#78a9ff; --good:#62d69f; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:15px/1.55 system-ui,sans-serif; }
main { width:min(1180px,94vw); margin:0 auto; padding:3rem 0 5rem; }
a { color:var(--accent); } h1 { margin:.2rem 0; font-size:clamp(2rem,5vw,3.2rem); }
.eyebrow { color:var(--accent); font-weight:700; letter-spacing:.12em; text-transform:uppercase; }
.subtitle,.muted { color:var(--muted); }.panel { background:var(--panel); border:1px solid var(--line);
  border-radius:14px; margin-top:2rem; overflow:hidden; }.notice { padding:2rem; }
.table-wrap { overflow-x:auto; } table { width:100%; border-collapse:collapse; }
th,td { padding:.9rem 1rem; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }
th { color:var(--muted); font-size:.78rem; text-transform:uppercase; letter-spacing:.06em; }
tbody tr:last-child td { border-bottom:0; }.status { color:var(--good); font-weight:700; }
.back { display:inline-block; margin-bottom:1.5rem; }.detail-grid { display:grid;
  grid-template-columns:minmax(0,2fr) minmax(260px,1fr); gap:1.5rem; align-items:start; }
.document,.sidebar section { padding:1.3rem 1.6rem; }.document h1 { font-size:2rem; }
.document h2 { margin-top:2rem; border-bottom:1px solid var(--line); padding-bottom:.35rem; }
.document li { margin:.35rem 0; }.sidebar section { border-bottom:1px solid var(--line); }
.sidebar section:last-child { border-bottom:0; }.facts { display:grid; gap:.8rem; margin:0; }
.facts div { display:grid; gap:.1rem; }.facts dt { color:var(--muted); font-size:.78rem;
  text-transform:uppercase; letter-spacing:.05em; }.facts dd { margin:0; overflow-wrap:anywhere; }
.run-form { padding:1.4rem 1.6rem; }.form-grid { display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr)); gap:1rem; }.field { display:grid; gap:.35rem; }
.field-wide { grid-column:1/-1; }.field label { color:var(--muted); font-weight:700; }
input,textarea { width:100%; border:1px solid var(--line); border-radius:8px; padding:.7rem;
  background:var(--bg); color:var(--text); font:inherit; } textarea { min-height:6rem; resize:vertical; }
button { margin-top:1rem; border:0; border-radius:8px; padding:.75rem 1rem;
  background:var(--accent); color:#08101f; font:inherit; font-weight:800; cursor:pointer; }
.error { color:#ff9c9c; font-weight:700; }
@media (max-width:800px) { .detail-grid,.form-grid { grid-template-columns:1fr; } }
"""


def format_timestamp(value):
    """Format an ISO timestamp in UTC, treating naïve persisted values as UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    month = parsed.strftime("%b")
    return f"{month} {parsed.day}, {parsed.year}, {parsed.strftime('%I:%M %p').lstrip('0')} UTC"


def format_duration(seconds):
    seconds = float(seconds)
    minutes, remainder = divmod(seconds, 60)
    rendered_seconds = f"{remainder:.2f}".rstrip("0").rstrip(".")
    return f"{int(minutes)}m {rendered_seconds}s" if minutes else f"{rendered_seconds}s"


def _layout(title, content):
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title><style>{_STYLES}</style></head>"
        f"<body><main>{content}</main></body></html>"
    )


def _inline_markdown(text):
    safe = escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)


def render_markdown(markdown):
    """Render the limited Markdown emitted by ProductionPackExporter safely."""
    rendered = []
    list_open = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("- "):
            if not list_open:
                rendered.append("<ul>")
                list_open = True
            rendered.append(f"<li>{_inline_markdown(line[2:])}</li>")
            continue
        if list_open:
            rendered.append("</ul>")
            list_open = False
        if not line:
            continue
        if line.startswith("## "):
            rendered.append(f"<h2>{_inline_markdown(line[3:])}</h2>")
        elif line.startswith("# "):
            rendered.append(f"<h1>{_inline_markdown(line[2:])}</h1>")
        else:
            rendered.append(f"<p>{_inline_markdown(line)}</p>")
    if list_open:
        rendered.append("</ul>")
    return "".join(rendered)


def _display(value):
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "None"
    if isinstance(value, dict):
        return ", ".join(f"{key}: {item}" for key, item in value.items()) or "None"
    return "None" if value is None or value == "" else str(value)


def _facts(items):
    return '<dl class="facts">' + "".join(
        f"<div><dt>{escape(label)}</dt><dd>{escape(_display(value))}</dd></div>"
        for label, value in items
    ) + "</dl>"


def _submission_form(values=None, error=None):
    values = values or {}

    def field(name, label, *, wide=False, textarea=False, required=False):
        value = escape(str(values.get(name, "")), quote=True)
        classes = "field field-wide" if wide else "field"
        required_attribute = " required" if required else ""
        if textarea:
            control = f'<textarea name="{name}"{required_attribute}>{value}</textarea>'
        else:
            control = f'<input name="{name}" value="{value}"{required_attribute}>'
        return f'<div class="{classes}"><label>{escape(label)}</label>{control}</div>'

    error_message = f'<p class="error">{escape(error)}</p>' if error else ""
    fields = "".join(
        (
            field("topic", "Topic", wide=True, textarea=True, required=True),
            field("target_audience", "Target audience"),
            field("objective", "Objective"),
            field("duration", "Duration"),
            field("production_type", "Production type"),
            field("platform", "Platform"),
            field("tone", "Tone"),
            field("notes", "Notes", wide=True, textarea=True),
        )
    )
    return (
        '<section class="panel run-form"><h2>Start a production run</h2>'
        '<p class="muted">Runs execute locally and appear in completed runs when finished.</p>'
        f'{error_message}<form method="post" action="/runs"><div class="form-grid">'
        f"{fields}</div><button type=\"submit\">Start run</button></form></section>"
    )


class RunBrowser:
    """Render persisted history and delegate submissions to the workflow service."""

    def __init__(self, output_root="outputs", submission_service=None):
        self.output_root = Path(output_root)
        self.store = ProductionPackStore(self.output_root)
        self.submission_service = submission_service or RunSubmissionService(
            self.output_root
        )

    def response_for_submission(self, values):
        """Start one local workflow and redirect to its persisted result."""
        try:
            run_id = self.submission_service.submit(values)
        except SubmissionValidationError as error:
            content = (
                '<p class="eyebrow">Local production</p><h1>Check the request</h1>'
                f"{_submission_form(values, str(error))}"
            )
            return 400, _layout("Check the request", content), None
        except Exception:
            _LOGGER.exception("Production run submission failed")
            message = (
                "The workflow or artifact persistence failed. "
                "Check the terminal output, then try again."
            )
            content = (
                '<p class="eyebrow">Local production</p>'
                '<h1>Run could not be completed</h1>'
                f"{_submission_form(values, message)}"
            )
            return 500, _layout("Run could not be completed", content), None
        return 303, "", f"/runs/{run_id}"

    def response_for_path(self, path):
        """Return an HTTP status and page without mutating local history."""
        if path == "/":
            index_path = self.output_root / "index.json"
            if not index_path.exists():
                content = (
                    '<p class="eyebrow">Run browser</p>'
                    '<h1>No run history index was found</h1>'
                    '<section class="panel notice"><p>Complete a production run first. '
                    f'Expected index: {escape(index_path.as_posix())}</p></section>'
                    f"{_submission_form()}"
                )
                return 200, _layout("No run history index was found", content)
            try:
                return 200, self.render_home()
            except ValueError as error:
                return 500, self._message_page("Run history is malformed", str(error))
        if path.startswith("/runs/"):
            run_id = unquote(path[len("/runs/") :])
            if not run_id or "/" in run_id or "\\" in run_id:
                return 404, self._message_page("Run not found", run_id or "Missing run ID")
            try:
                return 200, self.render_run(run_id)
            except KeyError:
                return 404, self._message_page(
                    "Run not found", f"No indexed run has ID {run_id}."
                )
            except FileNotFoundError as error:
                missing_path = Path(error.filename)
                try:
                    missing_path = missing_path.relative_to(self.output_root)
                except ValueError:
                    pass
                return 500, self._message_page(
                    "Artifact is missing",
                    f"The index references an artifact that is not available: {missing_path.as_posix()}",
                )
            except (ValueError, TypeError) as error:
                return 500, self._message_page("Run data is malformed", str(error))
        return 404, self._message_page("Page not found", "Return to completed runs.")

    @staticmethod
    def _message_page(title, message):
        content = (
            f'<p class="eyebrow">Run browser</p><h1>{escape(title)}</h1>'
            f'<section class="panel notice"><p>{escape(message)}</p>'
            '<p><a href="/">View completed runs</a></p></section>'
        )
        return _layout(title, content)

    def render_home(self):
        runs = self.store.list_runs()
        if not runs:
            content = (
                '<p class="eyebrow">Local production history</p>'
                '<h1>No completed runs yet</h1>'
                '<section class="panel notice"><p>Completed production runs will appear here.</p></section>'
                f"{_submission_form()}"
            )
            return _layout("No completed runs", content)
        rows = []
        for run in runs:
            cells = (
                f'<a href="/runs/{escape(run["run_id"], quote=True)}">'
                f'{escape(run["run_id"])}</a>',
                escape(run["topic"] or "Unavailable"),
                escape(format_timestamp(run["completed_at"])),
                escape(run["platform"] or "Unavailable"),
                escape(run["production_type"] or "Unavailable"),
                f'<span class="status">{escape(run["final_qa_status"] or "Unavailable")}</span>',
                str(run["revision_count"]),
                escape(format_duration(run["total_duration_seconds"])),
            )
            rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
        table = (
            '<section class="panel table-wrap"><table><thead><tr>'
            "<th>Run ID</th><th>Topic</th><th>Completed</th><th>Platform</th>"
            "<th>Production type</th><th>Final QA</th><th>Revisions</th><th>Duration</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></section>"
        )
        content = (
            '<p class="eyebrow">Local production history</p><h1>Completed runs</h1>'
            '<p class="subtitle">Persisted production packs and local run submission.</p>'
            f"{_submission_form()}" + table
        )
        return _layout("Completed runs", content)

    def render_run(self, run_id):
        entry = next(
            (item for item in self.store.list_runs() if item["run_id"] == run_id),
            None,
        )
        if entry is None:
            raise KeyError(f"run not found: {run_id}")
        pack = self.store.get_run(run_id)
        markdown_path = self.output_root / entry["markdown_path"]
        markdown = markdown_path.read_text(encoding="utf-8")
        metadata = pack.get("execution_metadata", {})
        qa_items = (
            ("Pack QA status", pack.get("qa_status")),
            ("Final QA status", entry["final_qa_status"]),
            ("QA notes", pack.get("qa_notes", [])),
            ("Revision count", entry["revision_count"]),
            ("Automatic revision", entry["automatic_revision_occurred"]),
        )
        metadata_items = (
            ("Started", metadata.get("started_at")),
            ("Completed", metadata.get("ended_at")),
            ("Total duration", format_duration(entry["total_duration_seconds"])),
            ("Agents", metadata.get("agents_used", [])),
            ("Profiles", metadata.get("profiles_used", [])),
            ("Stage durations", metadata.get("stage_durations_seconds", {})),
            ("Cost credits", metadata.get("cost_credits")),
        )
        artifact_items = (
            ("Markdown", f"Available — {entry['markdown_path']}"),
            ("JSON", f"Available — {entry['json_path']}"),
        )
        content = (
            '<a class="back" href="/">← All completed runs</a>'
            f'<p class="eyebrow">Run {escape(run_id)}</p>'
            f'<p class="subtitle">{escape(entry["topic"] or "Topic unavailable")}</p>'
            '<div class="detail-grid"><article class="panel document">'
            f'{render_markdown(markdown)}</article><aside class="panel sidebar">'
            f'<section><h2>Artifacts</h2>{_facts(artifact_items)}</section>'
            f'<section><h2>Execution</h2>{_facts(metadata_items)}</section>'
            f'<section><h2>Quality assurance</h2>{_facts(qa_items)}</section>'
            '</aside></div>'
        )
        return _layout(f"Run {run_id}", content)


def create_server(
    host="127.0.0.1", port=8000, output_root="outputs", submission_service=None
):
    """Create a local HTTP server; callers control its lifecycle."""
    browser = RunBrowser(output_root, submission_service=submission_service)

    class RunBrowserHandler(BaseHTTPRequestHandler):
        def _send_page(self, status, page):
            payload = page.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
            )
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            status, page = browser.response_for_path(urlsplit(self.path).path)
            self._send_page(status, page)

        def do_POST(self):
            if urlsplit(self.path).path != "/runs":
                status, page = browser.response_for_path("/not-found")
                self._send_page(status, page)
                return
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                self._send_page(
                    411,
                    browser._message_page(
                        "Invalid request", "Content-Length is required."
                    ),
                )
                return
            try:
                content_length = int(raw_length)
            except ValueError:
                content_length = -1
            if content_length < 0:
                self._send_page(
                    400,
                    browser._message_page(
                        "Invalid request", "Content-Length must be a non-negative integer."
                    ),
                )
                return
            if content_length > _MAX_REQUEST_BODY_BYTES:
                # Consume a bounded prefix so a just-over-limit request that is
                # already in flight receives the HTTP error instead of a reset.
                self.connection.settimeout(0.1)
                try:
                    self.rfile.read(_MAX_REQUEST_BODY_BYTES + 1)
                except TimeoutError:
                    pass
                self.close_connection = True
                self._send_page(
                    413,
                    browser._message_page(
                        "Invalid request", "Request body is too large."
                    ),
                )
                return
            previous_timeout = self.connection.gettimeout()
            deadline = time.monotonic() + _REQUEST_BODY_TIMEOUT_SECONDS
            body_chunks = []
            body_bytes_read = 0
            body_timed_out = False
            try:
                while body_bytes_read < content_length:
                    remaining_time = deadline - time.monotonic()
                    if remaining_time <= 0:
                        body_timed_out = True
                        break
                    self.connection.settimeout(remaining_time)
                    try:
                        chunk = self.rfile.read1(
                            min(8192, content_length - body_bytes_read)
                        )
                    except TimeoutError:
                        body_timed_out = True
                        break
                    if time.monotonic() >= deadline:
                        body_timed_out = True
                        break
                    if not chunk:
                        break
                    body_chunks.append(chunk)
                    body_bytes_read += len(chunk)
            finally:
                self.connection.settimeout(previous_timeout)
            if body_timed_out:
                self.close_connection = True
                self._send_page(
                    408,
                    browser._message_page(
                        "Invalid request", "Request body timed out."
                    ),
                )
                return
            raw_body = b"".join(body_chunks)
            if len(raw_body) != content_length:
                self.close_connection = True
                self._send_page(
                    400,
                    browser._message_page(
                        "Invalid request", "Incomplete request body."
                    ),
                )
                return
            origin = self.headers.get("Origin")
            if origin:
                parsed_origin = urlsplit(origin)
                if parsed_origin.scheme not in ("http", "https") or (
                    parsed_origin.netloc != self.headers.get("Host")
                ):
                    self._send_page(
                        403,
                        browser._message_page(
                            "Submission rejected", "Cross-origin submission rejected."
                        ),
                    )
                    return
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/x-www-form-urlencoded":
                self._send_page(
                    415,
                    browser._message_page(
                        "Invalid request", "Unsupported content type."
                    ),
                )
                return
            try:
                body = raw_body.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                self._send_page(
                    400,
                    browser._message_page(
                        "Invalid request", "Request body must be valid UTF-8."
                    ),
                )
                return
            try:
                parsed_values = parse_qs(
                    body,
                    keep_blank_values=True,
                    encoding="utf-8",
                    errors="strict",
                    max_num_fields=32,
                )
            except (UnicodeDecodeError, ValueError):
                self._send_page(
                    400,
                    browser._message_page("Invalid request", "Invalid form data."),
                )
                return
            if any(len(items) != 1 for items in parsed_values.values()):
                self._send_page(
                    400,
                    browser._message_page("Invalid request", "Invalid form data."),
                )
                return
            values = {name: items[0] for name, items in parsed_values.items()}
            oversized_field = next(
                (
                    name
                    for name, value in values.items()
                    if len(value) > _MAX_FIELD_CHARACTERS
                ),
                None,
            )
            if oversized_field is not None:
                label = oversized_field.replace("_", " ").capitalize()
                self._send_page(
                    400,
                    browser._message_page(
                        "Invalid request", f"{label} is too long."
                    ),
                )
                return
            status, page, location = browser.response_for_submission(values)
            if location is not None:
                self.send_response(status)
                self.send_header("Location", location)
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self._send_page(status, page)

        def log_message(self, template, *args):
            print(f"Run browser: {template % args}")

    return ThreadingHTTPServer((host, port), RunBrowserHandler)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Browse persisted production runs")
    parser.add_argument("--output-root", default="outputs", help="persisted output directory")
    parser.add_argument("--host", default="127.0.0.1", help="local bind address")
    parser.add_argument("--port", default=8000, type=int, help="local TCP port")
    arguments = parser.parse_args(argv)
    server = create_server(arguments.host, arguments.port, arguments.output_root)
    print(
        f"Local run browser: http://{arguments.host}:{server.server_port} "
        f"(outputs: {Path(arguments.output_root).resolve()})"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nRun browser stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
