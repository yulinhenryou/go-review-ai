"""Project metadata, read from config/project.json.

The product name is provisional, so it lives only in that file and is never
hard-coded in Python sources.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# python/src/weiqi/project.py -> repository root is three directories above `weiqi/`.
DEFAULT_PROJECT_FILE = Path(__file__).resolve().parents[3] / "config" / "project.json"


@dataclass(frozen=True)
class ProjectInfo:
    name: str
    slug: str
    provisional: bool
    tagline: str


def load_project_info(path: Path = DEFAULT_PROJECT_FILE) -> ProjectInfo:
    data = json.loads(path.read_text(encoding="utf-8"))
    name, slug, tagline = data["name"], data["slug"], data["tagline"]
    provisional = data["provisional"]
    if not all(isinstance(value, str) and value for value in (name, slug, tagline)):
        raise ValueError("project name, slug and tagline must be non-empty strings")
    if not isinstance(provisional, bool):
        raise ValueError("project 'provisional' must be a boolean")
    return ProjectInfo(name=name, slug=slug, provisional=provisional, tagline=tagline)
