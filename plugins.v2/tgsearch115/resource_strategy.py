# -*- coding: utf-8 -*-
"""Candidate ordering for automatic MoviePilot/115 processing."""
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, List, Optional, Tuple


_BTIH_RE = re.compile(r"(?:^|[?&])xt=urn:btih:([a-z0-9]+)", re.IGNORECASE)


def is_magnet_url(value: str) -> bool:
    return str(value or "").strip().lower().startswith("magnet:")


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
    """Return deduplicated观影 magnets first, then deduplicated 115 shares."""
    magnets = []
    shares = []
    seen_magnets = set()
    seen_shares = set()

    for torrent in torrents or []:
        url = str(getattr(torrent, "page_url", "") or "").strip()
        pan_type = str(getattr(torrent, "_tg115_pan_type", "") or "").lower()
        if prefer_site_magnet and pan_type == "magnet" and is_magnet_url(url):
            if str(getattr(torrent, "site_name", "") or "") != "观影":
                continue
            if is_tv and not bool(getattr(torrent, "_tg115_is_complete", False)):
                continue
            key = _magnet_key(url)
            if key and key not in seen_magnets:
                seen_magnets.add(key)
                magnets.append(torrent)
            continue

        if is_115_url(url):
            key = url.lower()
            if key not in seen_shares:
                seen_shares.add(key)
                shares.append(torrent)

    return magnets + shares


@dataclass
class CandidateExecutionResult:
    candidate: Optional[Any] = None
    message: str = ""
    via_magnet: bool = False
    recognition_attempts: int = 0
    errors: List[str] = field(default_factory=list)


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
