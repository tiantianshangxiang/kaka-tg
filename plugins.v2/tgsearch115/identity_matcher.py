# -*- coding: utf-8 -*-
"""Reuse MoviePilot's native media recognition to confirm transfer candidates."""
from dataclasses import dataclass
from app.chain.media import MediaChain
from app.core.metainfo import MetaInfo
from app.helper.torrent import TorrentHelper
from app.log import logger
from .media_types import is_tv_media, same_media_type
from .season_support import candidate_seasons
from .year_policy import decide_year_policy


@dataclass
class IdentityResult:
    confirmed: bool
    match_source: str = "rejected"
    candidate_media_id: str = ""
    reason: str = ""
    recognition_attempted: bool = False
    year_policy: str = ""
    identity_path: str = "rejected_before_recognition"
    candidate_year: int | None = None
    target_season_year: int | None = None


def _normalize_id(value) -> str:
    return str(value or "").strip()


def _select_recognized_media(value, target_tmdb: str, target_douban: str):
    """Prefer an exact-ID item when MoviePilot TMDB search returns a list."""
    candidates = list(value) if isinstance(value, (list, tuple)) else [value]
    candidates = [item for item in candidates if item]
    if target_tmdb:
        return next(
            (item for item in candidates
             if _normalize_id(getattr(item, "tmdb_id", None)) == target_tmdb),
            candidates[0] if candidates else None,
        )
    if target_douban:
        return next(
            (item for item in candidates
             if _normalize_id(getattr(item, "douban_id", None)) == target_douban),
            candidates[0] if candidates else None,
        )
    return candidates[0] if candidates else None


def confirm_candidate_identity(
        subscribe, target_media, torrent, recognize_candidate=None) -> IdentityResult:
    """Confirm one candidate without causing download or subscription side effects."""
    identity_title = str(
        getattr(torrent, "_tg115_identity_title", "") or torrent.title or ""
    ).strip()
    if not identity_title:
        return IdentityResult(False, reason="候选缺少可识别标题")

    try:
        candidate_meta = MetaInfo(
            title=identity_title,
            subtitle=str(torrent.description or ""),
        )
    except Exception:
        return IdentityResult(False, reason="候选元信息解析失败")

    year_decision = decide_year_policy(subscribe, target_media, identity_title)
    diagnostic = {
        "year_policy": year_decision.policy,
        "candidate_year": year_decision.candidate_year,
        "target_season_year": year_decision.target_season_year,
    }
    if year_decision.hard_reject:
        return IdentityResult(False, reason="电影候选年份不匹配", **diagnostic)
    try:
        local_match = TorrentHelper.match_torrent(
            mediainfo=target_media,
            torrent_meta=candidate_meta,
            torrent=torrent,
        )
    except Exception as e:
        if isinstance(e, AttributeError) and "value" in str(e):
            return IdentityResult(False, reason="媒体类型兼容错误，候选已安全拒绝", **diagnostic)
        return IdentityResult(False, reason=f"本地身份初筛异常: {type(e).__name__}", **diagnostic)
    # A 115 share's message often only has a generic title.  After an explicit
    # read-only file-name probe, MediaChain + exact media ID is safer than
    # rejecting a known alias before it can be confirmed.
    if not local_match and not getattr(torrent, "_tg115_metadata_verified", False):
        return IdentityResult(False, reason="标题、别名、年份或媒体类型不匹配", **diagnostic)

    target_type = getattr(target_media, "type", None)
    if is_tv_media(target_type):
        expected_season = getattr(subscribe, "season", None)
        if expected_season is None:
            expected_season = getattr(target_media, "season", None)
        expected_season = int(expected_season if expected_season is not None else 1)
        seasons = candidate_seasons(torrent)
        if not seasons:
            seasons.update(int(item) for item in (
                getattr(candidate_meta, "season_list", None) or []
            ))
        if not seasons:
            candidate_season = getattr(candidate_meta, "begin_season", None)
            if candidate_season is not None:
                seasons.add(int(candidate_season))
        if expected_season not in seasons:
            candidate_text = ",".join(f"S{item:02d}" for item in sorted(seasons)) \
                or "无明确季号"
            return IdentityResult(
                False,
                reason=f"季号不匹配: 需要 S{expected_season:02d}，候选 {candidate_text}",
                **diagnostic,
            )

    target_tmdb = _normalize_id(
        getattr(subscribe, "tmdbid", None) or getattr(target_media, "tmdb_id", None)
    )
    target_douban = _normalize_id(
        getattr(subscribe, "doubanid", None) or getattr(target_media, "douban_id", None)
    )
    if not target_tmdb and not target_douban:
        return IdentityResult(False, reason="订阅缺少 TMDB/豆瓣 ID，禁止自动转存", **diagnostic)

    try:
        if recognize_candidate:
            recognized = recognize_candidate(
                candidate_meta,
                getattr(subscribe, "episode_group", None),
            )
        else:
            recognized = MediaChain().recognize_by_meta(
                candidate_meta,
                episode_group=getattr(subscribe, "episode_group", None),
                obtain_images=False,
            )
    except Exception as e:
        logger.warn(f"【TG115】MoviePilot 候选媒体识别异常 type={type(e).__name__}")
        return IdentityResult(
            False,
            match_source="identity_unavailable",
            reason="MoviePilot 媒体识别暂时不可用，将在下一周期重试",
            recognition_attempted=True,
            identity_path=("share_metadata_tmdb_fallback" if not local_match else "local_match"),
            **diagnostic,
        )
    candidate_media = _select_recognized_media(recognized, target_tmdb, target_douban)
    if not candidate_media:
        return IdentityResult(
            False, reason="MoviePilot 无法识别候选媒体", recognition_attempted=True,
            identity_path=("share_metadata_tmdb_fallback" if not local_match else "local_match"),
            **diagnostic,
        )

    if not same_media_type(getattr(candidate_media, "type", None), target_type):
        return IdentityResult(
            False, reason="候选媒体类型与订阅不一致", recognition_attempted=True,
            identity_path=("share_metadata_tmdb_fallback" if not local_match else "local_match"),
            **diagnostic,
        )

    candidate_tmdb = _normalize_id(getattr(candidate_media, "tmdb_id", None))
    if target_tmdb:
        if candidate_tmdb == target_tmdb:
            return IdentityResult(
                True, "tmdb_id", candidate_tmdb, "TMDB ID 一致",
                recognition_attempted=True,
                identity_path=("share_metadata_tmdb_fallback" if not local_match else "local_match"),
                **diagnostic,
            )
        return IdentityResult(
            False,
            candidate_media_id=candidate_tmdb,
            reason="TMDB ID 不匹配",
            recognition_attempted=True,
            identity_path=("share_metadata_tmdb_fallback" if not local_match else "local_match"),
            **diagnostic,
        )

    candidate_douban = _normalize_id(getattr(candidate_media, "douban_id", None))
    if target_douban:
        if candidate_douban == target_douban:
            return IdentityResult(
                True, "douban_id", candidate_douban, "豆瓣 ID 一致",
                recognition_attempted=True,
                identity_path=("share_metadata_tmdb_fallback" if not local_match else "local_match"),
                **diagnostic,
            )
        return IdentityResult(
            False,
            candidate_media_id=candidate_douban,
            reason="豆瓣 ID 不匹配",
            recognition_attempted=True,
            identity_path=("share_metadata_tmdb_fallback" if not local_match else "local_match"),
            **diagnostic,
        )

    return IdentityResult(
        False, reason="候选缺少可比较的媒体 ID", recognition_attempted=True,
        identity_path=("share_metadata_tmdb_fallback" if not local_match else "local_match"),
        **diagnostic,
    )
