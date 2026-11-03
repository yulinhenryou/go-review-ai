import json
import tomllib
from pathlib import Path

import pytest

from weiqi.project import DEFAULT_PROJECT_FILE, load_project_info

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_distribution_name_matches_project_slug() -> None:
    # Guards the rename checklist: pyproject must follow config/project.json.
    info = load_project_info()
    assert tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["name"] == info.slug


def test_name_and_tagline_are_present() -> None:
    info = load_project_info()
    assert info.name in info.tagline
    assert DEFAULT_PROJECT_FILE.name == "project.json"


def test_rejects_empty_fields(tmp_path: Path) -> None:
    path = tmp_path / "project.json"
    path.write_text(json.dumps({"name": "", "slug": "x", "provisional": True, "tagline": "x"}))
    with pytest.raises(ValueError):
        load_project_info(path)
