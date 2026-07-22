# -*- coding: utf-8 -*-
"""Candidate ordering for automatic MoviePilot/115 processing."""
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, List, Optional, Tuple


_BTIH_RE = re.compile(r"(?:^|[?&])xt=urn:btih:([a-z0-9]+)", re.IGNORECASE)
_CHINESE_SUBTITLE_RE = re.compile(
    r"(?:中文字幕|国语中字|中字|简中|繁中|简繁|内封.{0,6}(?:简|繁|中)|(?:chs|cht|chinese).{0,8}(?:sub|subtitle))",
    re.IGNORECASE,
)
_AUTO_MAGNET_QUALITY_RE = re.compile(r"(?:1080[pi]?|2160p|\b4k\b|\buhd\b)", re.IGNORECASE)


def is_magnet_url(value: str) -> bool:
    return str(value or "").strip().lower().startswith("magnet:")


def filter_with_offline_seed_override(
    torrents: Iterable,
    filter_callback: Callable[[List[Any]], List[Any]],
) -> List[Any]:
    """Ignore swarm seed thresholds for 115 server-side magnet offline tasks."""
    torrent_list = list(torrents or [])
    original_seeders = []
    for torrent in torrent_list:
        url = str(
            getattr(torrent, "enclosure", "")
            or getattr(torrent, "page_url", "")
            or ""
        )
        if is_magnet_url(url):
            original_seeders.append((torrent, getattr(torrent, "seeders", 0)))
            setattr(torrent, "seeders", 2_147_483_647)
    try:
        return filter_callback(torrent_list)
    finally:
        for torrent, seeders in original_seeders:
            setattr(torrent, "seeders", seeders)


def _magnet_key(value: str) -> str:
    url = str(value or "").strip()
    match = _BTIH_RE.search(url)
    return (match.group(1) if match else url).lower()


def select_auto_candidates(
    torrents: Iterable,
    prefer_site_magnet: bool,
    is_tv: bool,
    is_115_url: Callable[[str], bool],
) -> List:
    """Order safe candidates: TG, Guanying 115 CHS, Guanying magnet CHS, Juying."""
    buckets = {"tg": [], "site_share": [], "site_magnet": [], "juying": []}
    bucket_seen = {name: set() for name in buckets}

    def add(bucket: str, key: str, torrent: Any) -> None:
        if key and key not in bucket_seen[bucket]:
            bucket_seen[bucket].add(key)
            buckets[bucket].append(torrent)

    for torrent in torrents or []:
        url = str(getattr(torrent, "page_url", "") or "").strip()
        pan_type = str(getattr(torrent, "_tg115_pan_type", "") or "").lower()
        source = str(getattr(torrent, "_tg115_source", "") or "").lower()
        description = " ".join((
            str(getattr(torrent, "title", "") or ""),
            str(getattr(torrent, "description", "") or ""),
        ))
        has_chinese_subtitle = bool(_CHINESE_SUBTITLE_RE.search(description))

        if source == "tg" and is_115_url(url):
            add("tg", url.lower(), torrent)
            continue

        if source == "site" and is_115_url(url) and has_chinese_subtitle:
            add("site_share", url.lower(), torrent)
            continue

        if source == "site" and prefer_site_magnet and pan_type == "magnet" and is_magnet_url(url):
            if not has_chinese_subtitle or not _AUTO_MAGNET_QUALITY_RE.search(description):
                continue
            if is_tv and not bool(getattr(torrent, "_tg115_is_complete", False)):
                continue
            add("site_magnet", _magnet_key(url), torrent)
            continue

        if source == "juying" and is_115_url(url):
            add("juying", url.lower(), torrent)

    ordered = buckets["tg"] + buckets["site_share"] + buckets["site_magnet"] + buckets["juying"]
    result = []
    seen = set()
    for torrent in ordered:
        url = str(getattr(torrent, "page_url", "") or "").strip()
        key = ("magnet", _magnet_key(url)) if is_magnet_url(url) else ("share", url.lower())
        if key not in seen:
            seen.add(key)
            result.append(torrent)
    return result


@dataclass
class CandidateExecutionResult:
    candidate: Optional[Any] = None
    message: str = ""
    via_magnet: bool = False
    recognition_attempts: int = 0
    errors: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)

    def rejection_summary(self) -> str:
        """Return a safe, stable reason without leaking candidate data."""
        if not self.rejection_reasons:
            return ""
        counts = {}
        for reason in self.rejection_reasons:
            counts[reason] = counts.get(reason, 0) + 1
        return max(counts, key=counts.get)


def _identity_rejection_category(identity: Any) -> str:
    reason = str(getattr(identity, "reason", "") or "")
    source = str(getattr(identity, "match_source", "") or "")
    if source == "identity_unavailable" or "识别" in reason:
        return "MoviePilot 媒体识别不可用"
    if "TMDB ID 不匹配" in reason:
        return "TMDB ID 不一致"
    if "豆瓣 ID 不匹配" in reason:
        return "豆瓣 ID 不一致"
    if "季号" in reason:
        return "候选季号不匹配"
    if "媒体类型" in reason:
        return "候选媒体类型不一致"
    if "标题" in reason or "别名" in reason or "年份" in reason:
        return "候选标题、年份或别名不匹配"
    if "缺少 TMDB/豆瓣 ID" in reason:
        return "订阅缺少媒体 ID，已安全拒绝"
    return "候选未通过 MoviePilot/TMDB 身份确认"


def execute_auto_candidates(
    candidates: Iterable,
    confirm_identity: Callable[[Any], Any],
    submit_magnet: Callable[[Any], Tuple[bool, str]],
    transfer_share: Callable[[Any], Tuple[bool, str]],
    max_recognition_attempts: int = 3,
) -> CandidateExecutionResult:
    """Try magnets then shares while preserving the safe CMS failure fallback."""
    result = CandidateExecutionResult()
    cms_submit_failed = False
    for candidate in candidates or []:
        candidate_url = str(getattr(candidate, "page_url", "") or "")
        candidate_is_magnet = is_magnet_url(candidate_url)
        if candidate_is_magnet and cms_submit_failed:
            continue
        identity = confirm_identity(candidate)
        if bool(getattr(identity, "recognition_attempted", False)):
            result.recognition_attempts += 1
        if not bool(getattr(identity, "confirmed", False)):
            result.rejection_reasons.append(_identity_rejection_category(identity))
            if result.recognition_attempts >= max_recognition_attempts:
                break
            continue
        if candidate_is_magnet:
            ok, message = submit_magnet(candidate)
            action = "CMS 115 磁力离线任务提交"
        else:
            ok, message = transfer_share(candidate)
            action = "115 转存"
        if ok:
            result.candidate = candidate
            result.message = message
            result.via_magnet = candidate_is_magnet
            return result
        result.errors.append(f"{action}失败: {message}")
        if candidate_is_magnet:
            cms_submit_failed = True
        if result.recognition_attempts >= max_recognition_attempts:
            break
    return result


def submit_magnet_with_fallback(
    mode: str,
    submit_direct: Callable[[], Tuple[bool, str]],
    submit_cms: Callable[[], Tuple[bool, str]],
) -> Tuple[bool, str, str]:
    """Apply direct/CMS mode without treating task creation as completion."""
    normalized = str(mode or "direct_then_cms").lower()
    if normalized in {"direct_115", "direct_then_cms"}:
        ok, message = submit_direct()
        if ok:
            return True, message, "115_direct"
        if normalized == "direct_115":
            return False, message, "115_direct"
    ok, message = submit_cms()
    return ok, message, "cms"
