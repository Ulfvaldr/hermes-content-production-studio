from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ExecutionMetadata:
    started_at: str = ""
    ended_at: str = ""
    total_duration_seconds: float = 0.0
    agents_used: List[str] = field(default_factory=list)
    profiles_used: List[str] = field(default_factory=list)
    revision_count: int = 0
    final_qa_status: str = ""
    automatic_revision_occurred: bool = False
    stage_durations_seconds: Dict[str, float] = field(default_factory=dict)
    cost_credits: Optional[float] = None


@dataclass
class ProductionPack:
    creative_brief: str = ""
    research_summary: str = ""
    recommended_angle: str = ""
    hook: str = ""
    script: str = ""
    scene_plan: List[str] = field(default_factory=list)
    shot_list: List[str] = field(default_factory=list)
    b_roll: List[str] = field(default_factory=list)
    ai_prompts: List[str] = field(default_factory=list)
    continuity_guide: List[str] = field(default_factory=list)
    voiceover: str = ""
    on_screen_text: List[str] = field(default_factory=list)
    title_options: List[str] = field(default_factory=list)
    thumbnail_concept: str = ""
    production_checklist: List[str] = field(default_factory=list)
    qa_status: str = ""
    qa_notes: List[str] = field(default_factory=list)
    execution_metadata: ExecutionMetadata = field(default_factory=ExecutionMetadata)
