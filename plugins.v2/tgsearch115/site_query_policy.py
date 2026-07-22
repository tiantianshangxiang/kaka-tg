# -*- coding: utf-8 -*-
"""Bounded year-query policy for the Guanying site source."""
from __future__ import annotations

from typing import Any, List, Optional

from .media_types import is_tv_media


def _to_year(value: Any) -> Optional[int]:
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if 1900 <= year <= 2100 else None


def site_query_years(subscribe: Any, mediainfo: Any, target_season: Optional[int]) -> List[Optional[int]]:
    """Return de-duplicated Guanying query years, including a TV no-year pass.

    Movie pages use the subscribed year only. TV pages can be indexed by series
    year, season premiere year, or neither, so the no-year pass is necessary
    before the later exact ID/type/season checks decide whether it is safe.
    """
    subscribed = _to_year(getattr(subscribe, "year", None))
    if not is_tv_media(getattr(subscribe, "type", None) or getattr(mediainfo, "type", None)):
        return [subscribed] if subscribed else [None]
    season_year = None
    seasons = getattr(mediainfo, "season_years", None) or {}
    if isinstance(seasons, dict) and target_season is not None:
        season_year = _to_year(seasons.get(target_season, seasons.get(str(target_season))))
    result: List[Optional[int]] = []
    for value in (subscribed, season_year, None):
        if value not in result:
            result.append(value)
    return result
