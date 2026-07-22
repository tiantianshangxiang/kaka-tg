# -*- coding: utf-8 -*-
"""Small compatibility helpers for MoviePilot TMDB result shapes."""
from __future__ import annotations

from typing import Any, Dict, Iterable


def _value(item: Any, name: str) -> Any:
    return item.get(name) if isinstance(item, dict) else getattr(item, name, None)


def season_year_map(seasons: Iterable[Any]) -> Dict[int, int]:
    """Build a conservative ``season_number -> premiere year`` mapping.

    MoviePilot versions expose TMDB season rows as either Pydantic models or
    dictionaries. Invalid and special-season rows are intentionally ignored.
    """
    result: Dict[int, int] = {}
    for item in seasons or []:
        try:
            season = int(_value(item, "season_number"))
        except (TypeError, ValueError):
            continue
        if season < 0:
            continue
        air_date = str(_value(item, "air_date") or "")
        if len(air_date) < 4 or not air_date[:4].isdigit():
            continue
        result[season] = int(air_date[:4])
    return result
