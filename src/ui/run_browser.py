"""Dependency-free, read-only browser for persisted production runs."""

import argparse
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from src.outputs.production_pack import ProductionPackStore


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
@media (max-width:800px) { .detail-grid { grid-template-columns:1fr; } }
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


class RunBrowser:
    """Read persisted history through the existing ProductionPackStore API."""

    def __init__(self, output_root="outputs"):
        self.output_root = Path(output_root)
        self.store = ProductionPackStore(self.output_root)

    def response_for_path(self, path):
        """Return an HTTP status and page without mutating local history."""
        if path == "/":
            index_path = self.output_root / "index.json"
            if not index_path.exists():
                return 200, self._message_page(
                    "No run history index was found",
                    f"Complete a production run first. Expected index: {index_path.as_posix()}",
                )
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
            '<p class="subtitle">Read-only view of persisted production packs.</p>' + table
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


def create_server(host="127.0.0.1", port=8000, output_root="outputs"):
    """Create a local HTTP server; callers control its lifecycle."""
    browser = RunBrowser(output_root)

    class RunBrowserHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, page = browser.response_for_path(urlsplit(self.path).path)
            payload = page.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(payload)

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
        f"Read-only run browser: http://{arguments.host}:{server.server_port} "
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
