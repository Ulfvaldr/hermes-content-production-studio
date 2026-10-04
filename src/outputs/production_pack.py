import errno
import json
import os
import re
import shutil
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from src.schemas.production_pack import ProductionPack


_INDEX_LOCKS = {}
_INDEX_LOCKS_GUARD = threading.Lock()

_RUN_ENTRY_FIELDS = {
    "run_id",
    "created_at",
    "completed_at",
    "topic",
    "target_audience",
    "platform",
    "production_type",
    "final_qa_status",
    "revision_count",
    "automatic_revision_occurred",
    "total_duration_seconds",
    "json_path",
    "markdown_path",
}


def _validate_run_entry(entry):
    if not isinstance(entry, dict):
        raise ValueError("unexpected run entry structure")
    entry_fields = set(entry)
    if entry_fields != _RUN_ENTRY_FIELDS:
        missing = ", ".join(sorted(_RUN_ENTRY_FIELDS - entry_fields)) or "none"
        unknown = ", ".join(sorted(entry_fields - _RUN_ENTRY_FIELDS)) or "none"
        raise ValueError(
            f"unexpected run entry fields (missing: {missing}; unknown: {unknown})"
        )

    string_fields = (
        "run_id",
        "created_at",
        "completed_at",
        "final_qa_status",
        "json_path",
        "markdown_path",
    )
    nullable_string_fields = (
        "topic",
        "target_audience",
        "platform",
        "production_type",
    )
    if any(not isinstance(entry[field], str) for field in string_fields):
        raise ValueError("unexpected run entry field type")
    if any(
        entry[field] is not None and not isinstance(entry[field], str)
        for field in nullable_string_fields
    ):
        raise ValueError("unexpected run entry field type")
    if type(entry["revision_count"]) is not int:
        raise ValueError("unexpected run entry field type")
    if type(entry["automatic_revision_occurred"]) is not bool:
        raise ValueError("unexpected run entry field type")
    if type(entry["total_duration_seconds"]) not in (int, float):
        raise ValueError("unexpected run entry field type")

    run_id = entry["run_id"]
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", run_id) is None:
        raise ValueError("unsafe run ID")
    if entry["json_path"] != f"{run_id}/production-pack.json":
        raise ValueError("unexpected JSON artifact path")
    if entry["markdown_path"] != f"{run_id}/production-pack.md":
        raise ValueError("unexpected Markdown artifact path")


@contextmanager
def _locked_index(output_root):
    lock_path = output_root / ".index.lock"
    lock_key = str(lock_path.resolve())
    with _INDEX_LOCKS_GUARD:
        process_lock = _INDEX_LOCKS.setdefault(lock_key, threading.Lock())

    with process_lock, lock_path.open("a+b") as lock_file:
        if lock_file.seek(0, os.SEEK_END) == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)

        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if error.errno not in (errno.EACCES, errno.EDEADLK):
                        raise
                    time.sleep(0.05)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def generate_run_id(now: datetime = None, unique_id: UUID = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    identifier = unique_id or uuid4()
    return f"{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}-{identifier.hex[:8]}"


@dataclass(frozen=True)
class PersistedProductionPack:
    run_id: str
    directory: Path
    json_path: Path
    markdown_path: Path


class ProductionPackStore:
    def __init__(self, output_root="outputs", run_id_factory=generate_run_id):
        self.output_root = Path(output_root)
        self.run_id_factory = run_id_factory

    def list_runs(self):
        index_path = self.output_root / "index.json"
        if not index_path.exists():
            return []
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            if (
                not isinstance(index, dict)
                or type(index.get("version")) is not int
                or index["version"] != 1
                or not isinstance(index.get("runs"), list)
            ):
                raise ValueError("unexpected index structure")
            runs = index["runs"]
            for entry in runs:
                _validate_run_entry(entry)
            return sorted(
                runs,
                key=lambda entry: (entry["completed_at"], entry["created_at"]),
                reverse=True,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"malformed run history index: {index_path}: {error}"
            ) from error

    def get_run(self, run_id):
        entry = next(
            (entry for entry in self.list_runs() if entry["run_id"] == run_id),
            None,
        )
        if entry is None:
            raise KeyError(f"run not found: {run_id}")
        artifact_path = self.output_root / entry["run_id"] / "production-pack.json"
        return json.loads(artifact_path.read_text(encoding="utf-8"))

    def _write_index(self, runs):
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=".index-",
            suffix=".tmp",
            dir=self.output_root,
        )
        os.close(file_descriptor)
        temporary_path = Path(temporary_name)
        try:
            temporary_path.write_text(
                json.dumps({"version": 1, "runs": runs}, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(self.output_root / "index.json")
        finally:
            temporary_path.unlink(missing_ok=True)

    def save(
        self, production_pack: ProductionPack, run_id: str = None, request=None
    ) -> PersistedProductionPack:
        run_id = run_id or self.run_id_factory()
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", run_id) is None:
            raise ValueError("run_id must contain only letters, numbers, hyphens, or underscores")
        directory = self.output_root / run_id
        self.output_root.mkdir(parents=True, exist_ok=True)
        if directory.exists():
            raise FileExistsError(f"run directory already exists: {directory}")

        staging_directory = Path(
            tempfile.mkdtemp(prefix=f".{run_id}-", suffix=".tmp", dir=self.output_root)
        )
        published_directory = False
        try:
            (staging_directory / "production-pack.json").write_text(
                ProductionPackExporter.to_json(production_pack), encoding="utf-8"
            )
            (staging_directory / "production-pack.md").write_text(
                ProductionPackExporter.to_markdown(production_pack), encoding="utf-8"
            )
            metadata = production_pack.execution_metadata
            entry = {
                "run_id": run_id,
                "created_at": metadata.started_at,
                "completed_at": metadata.ended_at,
                "topic": getattr(request, "topic", None),
                "target_audience": getattr(request, "target_audience", None),
                "platform": getattr(request, "platform", None),
                "production_type": getattr(request, "production_type", None),
                "final_qa_status": metadata.final_qa_status,
                "revision_count": metadata.revision_count,
                "automatic_revision_occurred": metadata.automatic_revision_occurred,
                "total_duration_seconds": metadata.total_duration_seconds,
                "json_path": f"{run_id}/production-pack.json",
                "markdown_path": f"{run_id}/production-pack.md",
            }
            try:
                _validate_run_entry(entry)
            except ValueError as error:
                raise ValueError(
                    f"invalid outgoing run history entry: {error}"
                ) from error
            with _locked_index(self.output_root):
                runs = self.list_runs()
                staging_directory.rename(directory)
                published_directory = True
                runs.append(entry)
                runs.sort(
                    key=lambda item: (item["completed_at"], item["created_at"]),
                    reverse=True,
                )
                self._write_index(runs)
        except Exception:
            shutil.rmtree(staging_directory, ignore_errors=True)
            if published_directory:
                shutil.rmtree(directory, ignore_errors=True)
            raise

        json_path = directory / "production-pack.json"
        markdown_path = directory / "production-pack.md"
        return PersistedProductionPack(
            run_id=run_id,
            directory=directory,
            json_path=json_path,
            markdown_path=markdown_path,
        )


def list_runs(output_root="outputs"):
    return ProductionPackStore(output_root).list_runs()


def get_run(run_id, output_root="outputs"):
    return ProductionPackStore(output_root).get_run(run_id)


class ProductionPackExporter:
    _SECTIONS = (
        ("creative_brief", "Creative Brief"),
        ("research_summary", "Research Summary"),
        ("recommended_angle", "Recommended Angle"),
        ("hook", "Hook"),
        ("script", "Script"),
        ("scene_plan", "Scene Plan"),
        ("shot_list", "Shot List"),
        ("b_roll", "B-Roll"),
        ("ai_prompts", "AI Prompts"),
        ("continuity_guide", "Continuity Guide"),
        ("voiceover", "Voiceover"),
        ("on_screen_text", "On-Screen Text"),
        ("title_options", "Title Options"),
        ("thumbnail_concept", "Thumbnail Concept"),
        ("production_checklist", "Production Checklist"),
        ("qa_status", "QA Status"),
        ("qa_notes", "QA Notes"),
    )

    @staticmethod
    def to_json(production_pack: ProductionPack) -> str:
        return json.dumps(
            asdict(production_pack),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"

    @classmethod
    def to_markdown(cls, production_pack: ProductionPack) -> str:
        pack_data = asdict(production_pack)
        lines = ["# Production Pack", ""]
        for field_name, heading in cls._SECTIONS:
            lines.extend([f"## {heading}", ""])
            value = pack_data[field_name]
            if isinstance(value, list):
                lines.extend(f"- {item}" for item in value)
                if not value:
                    lines.append("_None_")
            else:
                lines.append(str(value) if value != "" else "_Not provided_")
            lines.append("")

        lines.extend(["## Execution Metadata", ""])
        for name, value in pack_data["execution_metadata"].items():
            label = cls._humanize(name)
            if isinstance(value, dict):
                lines.append(f"- **{label}:**")
                if value:
                    for item_name, item_value in value.items():
                        lines.append(
                            f"  - **{cls._humanize(item_name)}:** {item_value}"
                        )
                else:
                    lines.append("  - _None_")
            elif isinstance(value, list):
                rendered = ", ".join(str(item) for item in value) or "None"
                lines.append(f"- **{label}:** {rendered}")
            elif isinstance(value, bool):
                lines.append(f"- **{label}:** {'Yes' if value else 'No'}")
            else:
                lines.append(f"- **{label}:** {value if value is not None else 'None'}")

        return "\n".join(lines) + "\n"

    @staticmethod
    def _humanize(name: str) -> str:
        return " ".join(word.capitalize() for word in name.split("_"))
