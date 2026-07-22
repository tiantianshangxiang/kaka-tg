# -*- coding: utf-8 -*-
"""Season parsing and bounded season-aware search helpers."""
from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional, Set


_CN_DIGITS = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
_SEASON_TOKEN = re.compile(r"(?i)(?:season\s*|s)0*(\d{1,3})(?=\D|$)")
_SEASON_RANGE = re.compile(
    r"(?i)(?:season\s*|s)0*(\d{1,3})\s*[-~至到]\s*(?:season\s*|s)?0*(\d{1,3})"
)
_CN_SEASON = re.compile(r"第\s*([零〇一二两三四五六七八九十百\d]+)\s*季")
_CN_RANGE = re.compile(
    r"第\s*([零〇一二两三四五六七八九十百\d]+)\s*[-~至到]\s*"
    r"([零〇一二两三四五六七八九十百\d]+)\s*季"
)
_ALL_SEASONS = re.compile(r"全\s*([零〇一二两三四五六七八九十百\d]+)\s*季")
_SPECIALS = re.compile(r"(?i)(?:特别篇|特別篇|特别季|特別季|specials?|ova|oad)")


def _cn_number(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text in _CN_DIGITS:
        return _CN_DIGITS[text]
    if "百" in text:
        left, right = text.split("百", 1)
        hundreds = _CN_DIGITS.get(left, 1) if left else 1
        tail = _cn_number(right) if right else 0
        return hundreds * 100 + (tail or 0)
    if "十" in text:
        left, right = text.split("十", 1)
        tens = _CN_DIGITS.get(left, 1) if left else 1
        ones = _CN_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    digits = [_CN_DIGITS.get(char) for char in text]
    if all(item is not None for item in digits):
        return int("".join(str(item) for item in digits))
    return None


def _expand(start: int, end: int) -> Set[int]:
    if start < 0 or end < 0 or abs(end - start) > 100:
        return set()
    low, high = sorted((start, end))
    return set(range(low, high + 1))


def parse_seasons(value: Any) -> Set[int]:
    """Parse scalar, collection, JSON-like and textual season representations."""
    result: Set[int] = set()
    if value is None or value == "":
        return result
    if isinstance(value, bool):
        return result
    if isinstance(value, int):
        return {value} if value >= 0 else set()
    if isinstance(value, (list, tuple, set)):
        for item in value:
            result.update(parse_seasons(item))
        return result
    if isinstance(value, dict):
        for key in ("season", "seasons", "target_seasons", "season_list"):
            if key in value:
                result.update(parse_seasons(value.get(key)))
        return result

    text = str(value).strip()
    if not text:
        return result
    for match in _SEASON_RANGE.finditer(text):
        result.update(_expand(int(match.group(1)), int(match.group(2))))
    for match in _CN_RANGE.finditer(text):
        start, end = _cn_number(match.group(1)), _cn_number(match.group(2))
        if start is not None and end is not None:
            result.update(_expand(start, end))
    for match in _SEASON_TOKEN.finditer(text):
        result.add(int(match.group(1)))
    for match in _CN_SEASON.finditer(text):
        number = _cn_number(match.group(1))
        if number is not None:
            result.add(number)
    for match in _ALL_SEASONS.finditer(text):
        number = _cn_number(match.group(1))
        if number is not None and 0 < number <= 100:
            result.update(range(1, number + 1))
    if _SPECIALS.search(text):
        result.add(0)
    if not result and re.fullmatch(r"\s*\d{1,3}\s*", text):
        result.add(int(text))
    return {season for season in result if 0 <= season <= 999}


def target_seasons(subscribe: Any) -> List[int]:
    """Return explicit target seasons; MoviePilot currently stores one season per row."""
    result: Set[int] = set()
    for attr in ("season", "seasons", "target_seasons"):
        if hasattr(subscribe, attr):
            result.update(parse_seasons(getattr(subscribe, attr, None)))
    note = getattr(subscribe, "note", None)
    if isinstance(note, dict):
        result.update(parse_seasons(note))
    return sorted(result)


def candidate_seasons(candidate: Any) -> Set[int]:
    parts = []
    for attr in (
        "resource_title", "source_title", "text", "title", "description",
        "display_name", "name",
    ):
        value = getattr(candidate, attr, None)
        if value:
            parts.append(str(value))
    if isinstance(candidate, dict):
        parts.extend(str(candidate.get(key) or "") for key in (
            "resource_title", "source_title", "text", "title", "description",
        ))
    return parse_seasons("\n".join(parts))


def supports_target_season(candidate: Any, season: Optional[int]) -> bool:
    if season is None:
        return True
    seasons = candidate_seasons(candidate)
    return bool(seasons and int(season) in seasons)


def supports_target_season_or_unknown_share(
        candidate: Any, season: Optional[int], is_115_share: bool) -> bool:
    """Allow a seasonless 115 share to reach the bounded metadata probe.

    A share that explicitly names another season is still rejected immediately.
    A seasonless share is not considered matched here; callers must probe its
    file names and run ``supports_target_season`` again before rule matching.
    """
    if supports_target_season(candidate, season):
        return True
    return bool(season is not None and is_115_share and not candidate_seasons(candidate))


def season_distribution(candidates: Iterable[Any]) -> List[int]:
    found: Set[int] = set()
    for candidate in candidates or []:
        found.update(candidate_seasons(candidate))
    return sorted(found)


def cache_covers_season(candidates: Iterable[Any], season: Optional[int]) -> bool:
    return season is None or int(season) in season_distribution(candidates)


def deduplicate_search_hits(candidates: Iterable[Any]) -> List[Any]:
    """Keep source order while removing repeats produced by alias queries."""
    seen = set()
    result = []
    for candidate in candidates or []:
        if isinstance(candidate, dict):
            url = str(candidate.get("share_url") or "").strip().casefold()
            title = str(candidate.get("resource_title") or "").strip().casefold()
            source_title = str(candidate.get("source_title") or "").strip().casefold()
        else:
            url = str(getattr(candidate, "share_url", "") or "").strip().casefold()
            title = str(getattr(candidate, "resource_title", "") or "").strip().casefold()
            source_title = str(getattr(candidate, "source_title", "") or "").strip().casefold()
        key = (url,) if url else (title, source_title)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def source_cache_key(
        source: Any, keyword: Any, year: Any, media_type: Any,
        season: Optional[int]) -> tuple:
    return (
        str(source or "").strip().casefold(),
        str(keyword or "").strip().casefold(),
        str(year or "").strip(),
        str(getattr(media_type, "value", media_type) or "").strip().upper(),
        "" if season is None else str(int(season)),
    )


def _cn_label(number: int) -> str:
    if number < 10:
        return "零一二三四五六七八九"[number]
    if number < 20:
        return "十" + ("" if number == 10 else _cn_label(number - 10))
    if number < 100:
        tens, ones = divmod(number, 10)
        return _cn_label(tens) + "十" + ("" if not ones else _cn_label(ones))
    return str(number)


def season_keywords(base_names: Iterable[Any], season: Optional[int], limit: int = 6) -> List[str]:
    names: List[str] = []
    seen_names = set()
    for value in base_names or []:
        name = str(value or "").strip()
        key = name.casefold()
        if name and key not in seen_names:
            seen_names.add(key)
            names.append(name)
    if not names:
        return []
    if season is None:
        return names[:limit]

    max_items = max(1, int(limit))
    # Keep a bounded base-title fallback for TG messages whose share covers
    # several seasons but whose post title does not contain a season suffix.
    # Prefer the canonical title plus one Latin alias (for example NCIS).
    base_fallbacks = [names[0]]
    latin_alias = next(
        (name for name in names[1:] if re.search(r"[A-Za-z]", name)), None
    )
    if latin_alias and latin_alias.casefold() != names[0].casefold() and max_items > 1:
        base_fallbacks.append(latin_alias)
    qualified_limit = max(0, max_items - len(base_fallbacks))

    suffixes = ["S00", "特别篇", "Specials"] if season == 0 else [
        f"S{season:02d}", f"第{_cn_label(season)}季", f"Season {season}",
    ]
    result: List[str] = []
    if qualified_limit:
        for suffix in suffixes:
            for name in names:
                keyword = f"{name} {suffix}"
                if keyword.casefold() not in {item.casefold() for item in result}:
                    result.append(keyword)
                if len(result) >= qualified_limit:
                    break
            if len(result) >= qualified_limit:
                break
    for name in base_fallbacks:
        if name.casefold() not in {item.casefold() for item in result}:
            result.append(name)
        if len(result) >= max_items:
            break
    return result[:max_items]


def site_title_keyword(value: Any) -> str:
    """Remove only a generated trailing season suffix for title-indexed sites.

    Telegram searches benefit from a season-qualified query, while the target
    site's suggestion endpoint indexes a work page by its base title. Season
    selection remains strict after the detail page returns resource titles.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    return re.sub(
        r"\s+(?:S(?:eason)?\s*0?\d{1,2}|第[零一二三四五六七八九十百\d]+季|Specials?|特别篇)\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
