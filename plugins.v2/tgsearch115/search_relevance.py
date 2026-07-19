# -*- coding: utf-8 -*-
"""Deterministic title/year checks for manual search results."""
import re
from typing import Optional


_YEAR_RE = re.compile(r"(?:[(（\[]\s*)?((?:19|20)\d{2})(?:\s*[)）\]])?")
_TITLE_PREFIX_RE = re.compile(r"^(?:电影|电视剧|剧集|动漫|动画)\s*[:：]\s*", re.IGNORECASE)
_SEASON_SUFFIX_RE = re.compile(
    r"(?:\s*(?:第\s*[一二三四五六七八九十百\d]+\s*季|season\s*\d+|s\d{1,2}))\s*$",
    re.IGNORECASE,
)


def extract_year(text: str) -> Optional[int]:
    match = _YEAR_RE.search(str(text or ""))
    return int(match.group(1)) if match else None


def canonical_title(text: str) -> str:
    title = str(text or "").strip()
    title = _TITLE_PREFIX_RE.sub("", title)
    title = _YEAR_RE.sub("", title)
    title = _SEASON_SUFFIX_RE.sub("", title)
    return "".join(re.findall(r"[a-z0-9\u3400-\u9fff\u3040-\u30ff]", title.lower()))


def is_relevant_result(
    query_title: str,
    query_year: Optional[int],
    candidate_title: str,
    candidate_year: Optional[int],
) -> bool:
    query_key = canonical_title(query_title)
    candidate_key = canonical_title(candidate_title)
    if not query_key or not candidate_key or query_key != candidate_key:
        return False
    if query_year and candidate_year and int(query_year) != int(candidate_year):
        return False
    return True
