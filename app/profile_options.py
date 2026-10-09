"""Read learner-profile choices from the data-only onboarding options pack."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

OPTIONS_PATH = Path(__file__).resolve().parents[1] / "content" / "learner-profile" / "options.json"


def load_profile_options() -> dict[str, Any]:
    with OPTIONS_PATH.open(encoding="utf-8") as source:
        return cast(dict[str, Any], json.load(source))


def initial_level(education_level: str) -> tuple[float, str]:
    levels = load_profile_options()["education_levels"]
    for level in levels:
        if level["id"] == education_level:
            return float(level["initial_level"]), str(level["id"])
    raise ValueError(f"Unknown education level: {education_level}")


def level_label(level_value: float) -> str:
    levels = load_profile_options()["education_levels"]
    for level in levels:
        if level_value <= float(level["max_level"]):
            return str(level["id"])
    return str(levels[-1]["id"])
