from dataclasses import dataclass
from typing import Optional


@dataclass
class ContentRequest:
    topic: str
    target_audience: Optional[str] = None
    objective: Optional[str] = None
    duration: Optional[str] = None
    production_type: Optional[str] = None
    platform: Optional[str] = None
    tone: Optional[str] = None
    notes: Optional[str] = None