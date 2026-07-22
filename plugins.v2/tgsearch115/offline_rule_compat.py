# -*- coding: utf-8 -*-
"""Rule-group compatibility for 115 shares without tracker metadata.

MoviePilot rule groups are designed around tracker torrents.  TG/115 shares do
not expose size, seeders, freeleech or publish-time metadata, so treating their
placeholder values as real data rejects otherwise valid resources.  This module
reuses the same rule expression semantics for observable fields and explicitly
skips only unavailable fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, Iterable, List, Tuple


_UNAVAILABLE_RULE_FIELDS = {
    "size_range": "size",
    "seeders": "seeders",
    "downloadvolumefactor": "downloadvolumefactor",
    "publish_time": "publish_time",
}


@dataclass
class RuleCompatibilityDiagnostics:
    input_count: int = 0
    matched_count: int = 0
    skipped_fields: set[str] = field(default_factory=set)
    rejected_by_semantic_rule: int = 0
    parse_errors: int = 0

    def summary(self) -> str:
        if self.matched_count:
            fields = "、".join(sorted(self.skipped_fields))
            suffix = f"；跳过不可验证字段：{fields}" if fields else ""
            return f"115 分享规则兼容命中 {self.matched_count} 条{suffix}"
        if self.parse_errors:
            return "MoviePilot 规则组表达式不可解析"
        if self.rejected_by_semantic_rule:
            return "候选未通过 MoviePilot 可验证规则"
        return "候选未通过 MoviePilot 规则"


class _ExpressionParser:
    """Small parser for MoviePilot rule IDs, !, &, | and parentheses."""

    _TOKEN_RE = re.compile(r"\s*([A-Za-z0-9]+|[!&|()])")

    def __init__(self, expression: str):
        raw_expression = str(expression or "")
        self._tokens = []
        position = 0
        while position < len(raw_expression):
            match = self._TOKEN_RE.match(raw_expression, position)
            if not match:
                if raw_expression[position:].strip():
                    raise ValueError("invalid rule expression character")
                break
            self._tokens.append(match.group(1))
            position = match.end()
        self._index = 0

    def parse(self):
        if not self._tokens:
            raise ValueError("empty rule expression")
        value = self._parse_or()
        if self._index != len(self._tokens):
            raise ValueError("unexpected rule expression token")
        return value

    def _parse_or(self):
        value = self._parse_and()
        while self._accept("|"):
            value = ("or", value, self._parse_and())
        return value

    def _parse_and(self):
        value = self._parse_not()
        while self._accept("&"):
            value = ("and", value, self._parse_not())
        return value

    def _parse_not(self):
        if self._accept("!"):
            return ("not", self._parse_not())
        if self._accept("("):
            value = self._parse_or()
            if not self._accept(")"):
                raise ValueError("unclosed rule expression")
            return value
        if self._index >= len(self._tokens):
            raise ValueError("missing rule operand")
        token = self._tokens[self._index]
        if token in {"!", "&", "|", "(", ")"}:
            raise ValueError("invalid rule operand")
        self._index += 1
        return ("rule", token)

    def _accept(self, expected: str) -> bool:
        if self._index < len(self._tokens) and self._tokens[self._index] == expected:
            self._index += 1
            return True
        return False


def _mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return vars(value)


def _regex_search(pattern: Any, content: str) -> bool:
    try:
        return bool(re.search(str(pattern), content, re.IGNORECASE))
    except re.error:
        return False


def _tmdb_matches(rule_tmdb: Dict[str, Any], mediainfo: Any) -> bool:
    if not rule_tmdb or mediainfo is None:
        return False
    for attr, expected in rule_tmdb.items():
        value = getattr(mediainfo, attr, None)
        if not value:
            return False
        if attr == "production_countries":
            actual = [str(item.get("iso_3166_1", "")).upper() for item in value]
        elif isinstance(value, (list, tuple, set)):
            actual = [str(item).upper() for item in value]
        else:
            actual = [str(value).upper()]
        expected_values = [item.strip().upper() for item in str(expected).split(",") if item.strip()]
        if not set(actual).intersection(expected_values):
            return False
    return True


def _content_for_rule(torrent: Any, rule: Dict[str, Any]) -> str:
    values = []
    for attr in rule.get("match") or []:
        value = getattr(torrent, attr, None)
        if isinstance(value, (list, tuple, set)):
            values.extend(str(item) for item in value if item)
        elif value:
            values.append(str(value))
    if values:
        return " ".join(values)
    return " ".join((
        str(getattr(torrent, "title", "") or ""),
        str(getattr(torrent, "description", "") or ""),
        " ".join(str(item) for item in (getattr(torrent, "labels", None) or [])),
    ))


def _rule_matches(
        torrent: Any, rule: Dict[str, Any], mediainfo: Any,
        diagnostics: RuleCompatibilityDiagnostics) -> bool:
    if _tmdb_matches(rule.get("tmdb") or {}, mediainfo):
        return True
    content = _content_for_rule(torrent, rule)
    includes = rule.get("include") or []
    excludes = rule.get("exclude") or []
    if not isinstance(includes, list):
        includes = [includes]
    if not isinstance(excludes, list):
        excludes = [excludes]
    if includes and not any(_regex_search(item, content) for item in includes):
        return False
    if any(_regex_search(item, content) for item in excludes):
        return False

    unavailable = set(getattr(torrent, "_tg115_unavailable_rule_fields", set()) or set())
    for rule_field, availability_field in _UNAVAILABLE_RULE_FIELDS.items():
        expected = rule.get(rule_field)
        if expected is None:
            continue
        if availability_field in unavailable:
            diagnostics.skipped_fields.add(availability_field)
            continue
        if rule_field == "seeders" and int(getattr(torrent, "seeders", 0) or 0) < int(expected):
            return False
        if rule_field == "downloadvolumefactor" and getattr(
                torrent, "downloadvolumefactor", None) != expected:
            return False
        if rule_field == "size_range" and not _size_matches(
                float(getattr(torrent, "size", 0) or 0), str(expected)):
            return False
        if rule_field == "publish_time" and not _publish_time_matches(torrent, str(expected)):
            return False
    return True


def _size_matches(size: float, size_range: str) -> bool:
    try:
        text = size_range.strip()
        if "-" in text:
            low, high = (float(item.strip()) * 1024 * 1024 for item in text.split("-", 1))
            return low <= size <= high
        if text.startswith(">"):
            return size >= float(text[1:].strip()) * 1024 * 1024
        if text.startswith("<"):
            return size <= float(text[1:].strip()) * 1024 * 1024
    except (TypeError, ValueError):
        return False
    return False


def _publish_time_matches(torrent: Any, publish_time: str) -> bool:
    try:
        values = [float(item) for item in publish_time.split("-")]
        minutes = float(torrent.pub_minutes())
    except (AttributeError, TypeError, ValueError):
        return False
    return minutes >= values[0] if len(values) == 1 else values[0] <= minutes <= values[1]


def _evaluate(node: Tuple, torrent: Any, rules: Dict[str, Dict[str, Any]], mediainfo: Any,
              diagnostics: RuleCompatibilityDiagnostics) -> bool:
    operator = node[0]
    if operator == "rule":
        rule = rules.get(node[1])
        return bool(rule) and _rule_matches(torrent, rule, mediainfo, diagnostics)
    if operator == "not":
        return not _evaluate(node[1], torrent, rules, mediainfo, diagnostics)
    if operator == "and":
        return _evaluate(node[1], torrent, rules, mediainfo, diagnostics) and _evaluate(
            node[2], torrent, rules, mediainfo, diagnostics
        )
    return _evaluate(node[1], torrent, rules, mediainfo, diagnostics) or _evaluate(
        node[2], torrent, rules, mediainfo, diagnostics
    )


def filter_offline_share_rules(
        torrents: Iterable[Any], rule_groups: Iterable[Any], rule_definitions: Dict[str, Any],
        mediainfo: Any) -> Tuple[List[Any], RuleCompatibilityDiagnostics]:
    """Evaluate groups while skipping only fields absent from 115 share metadata."""
    candidates = list(torrents or [])
    diagnostics = RuleCompatibilityDiagnostics(input_count=len(candidates))
    groups = [_mapping(group) for group in (rule_groups or [])]
    rules = {str(key): _mapping(value) for key, value in (rule_definitions or {}).items()}
    if not groups:
        diagnostics.matched_count = len(candidates)
        return candidates, diagnostics

    accepted = candidates
    for group in groups:
        levels = [part.strip() for part in str(group.get("rule_string") or "").split(">") if part.strip()]
        if not levels:
            continue
        try:
            expressions = [_ExpressionParser(level).parse() for level in levels]
        except ValueError:
            diagnostics.parse_errors += 1
            return [], diagnostics
        retained = []
        for torrent in accepted:
            for priority, expression in enumerate(expressions):
                if _evaluate(expression, torrent, rules, mediainfo, diagnostics):
                    setattr(torrent, "pri_order", 100 - priority)
                    retained.append(torrent)
                    break
            else:
                diagnostics.rejected_by_semantic_rule += 1
        accepted = retained
        if not accepted:
            break
    diagnostics.matched_count = len(accepted)
    return accepted, diagnostics
