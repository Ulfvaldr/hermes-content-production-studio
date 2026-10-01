from dataclasses import dataclass, field
from typing import List


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