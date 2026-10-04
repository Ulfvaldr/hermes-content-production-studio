import json
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from src.schemas.production_pack import ProductionPack


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

    def save(
        self, production_pack: ProductionPack, run_id: str = None
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
        try:
            (staging_directory / "production-pack.json").write_text(
                ProductionPackExporter.to_json(production_pack), encoding="utf-8"
            )
            (staging_directory / "production-pack.md").write_text(
                ProductionPackExporter.to_markdown(production_pack), encoding="utf-8"
            )
            staging_directory.rename(directory)
        except Exception:
            shutil.rmtree(staging_directory, ignore_errors=True)
            raise

        json_path = directory / "production-pack.json"
        markdown_path = directory / "production-pack.md"
        return PersistedProductionPack(
            run_id=run_id,
            directory=directory,
            json_path=json_path,
            markdown_path=markdown_path,
        )


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
