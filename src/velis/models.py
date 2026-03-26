from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class FileRecord:
    original_path: Path
    category: str
    new_name: str
    target_path: Path
    resolved_target_path: Optional[Path] = None
    classification_reason: str = ""
    ai_summary: str = ""
    renamed_by_ai: bool = False


@dataclass
class CategoryBoxData:
    category: str
    directory: Path
    files: List[Path] = field(default_factory=list)
