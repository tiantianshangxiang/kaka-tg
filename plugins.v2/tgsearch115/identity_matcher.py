# -*- coding: utf-8 -*-
"""Reuse MoviePilot's native media recognition to confirm transfer candidates."""
from dataclasses import dataclass
from app.chain.media import MediaChain
from app.core.metainfo import MetaInfo
from app.helper.torrent import TorrentHelper
from app.log import logger
from .media_types import is_tv_media, same_media_type
from .season_support import candidate_seasons


@dataclass
class IdentityResult:
    confirmed: bool
    match_source: str = "rejected"
    candidate_media_id: str = ""
    reason: str = ""
    recognition_attempted: bool = False


def _normalize_id(value) -> str:
    return str(value or "").strip()


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
    except Exception as e:
        return IdentityResult(False, reason=f"MetaInfo 解析失败: {e}")

    try:
        local_match = TorrentHelper.match_torrent(
            mediainfo=target_media,
            torrent_meta=candidate_meta,
            torrent=torrent,
        )
    except Exception as e:
        if isinstance(e, AttributeError) and "value" in str(e):
            return IdentityResult(False, reason="媒体类型兼容错误，候选已安全拒绝")
        return IdentityResult(False, reason=f"本地身份初筛异常: {type(e).__name__}")
    # A 115 share's message often only has a generic title.  After an explicit
    # read-only file-name probe, MediaChain + exact media ID is safer than
    # rejecting a known alias before it can be confirmed.
    if not local_match and not getattr(torrent, "_tg115_metadata_verified", False):
        return IdentityResult(False, reason="标题、别名、年份或媒体类型不匹配")

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
            )

    target_tmdb = _normalize_id(
        getattr(subscribe, "tmdbid", None) or getattr(target_media, "tmdb_id", None)
    )
    target_douban = _normalize_id(
        getattr(subscribe, "doubanid", None) or getattr(target_media, "douban_id", None)
    )
    if not target_tmdb and not target_douban:
        return IdentityResult(False, reason="订阅缺少 TMDB/豆瓣 ID，禁止自动转存")

    try:
        if recognize_candidate:
            candidate_media = recognize_candidate(
                candidate_meta,
                getattr(subscribe, "episode_group", None),
            )
        else:
            candidate_media = MediaChain().recognize_by_meta(
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
        )
    if not candidate_media:
        return IdentityResult(
            False, reason="MoviePilot 无法识别候选媒体", recognition_attempted=True
        )

    if not same_media_type(getattr(candidate_media, "type", None), target_type):
        return IdentityResult(
            False, reason="候选媒体类型与订阅不一致", recognition_attempted=True
        )

    candidate_tmdb = _normalize_id(getattr(candidate_media, "tmdb_id", None))
    if target_tmdb:
        if candidate_tmdb == target_tmdb:
            return IdentityResult(
                True, "tmdb_id", candidate_tmdb, "TMDB ID 一致",
                recognition_attempted=True,
            )
        return IdentityResult(
            False,
            candidate_media_id=candidate_tmdb,
            reason=f"TMDB ID 不匹配: 需要 {target_tmdb}，候选 {candidate_tmdb or '无'}",
            recognition_attempted=True,
        )

    candidate_douban = _normalize_id(getattr(candidate_media, "douban_id", None))
    if target_douban:
        if candidate_douban == target_douban:
            return IdentityResult(
                True, "douban_id", candidate_douban, "豆瓣 ID 一致",
                recognition_attempted=True,
            )
        return IdentityResult(
            False,
            candidate_media_id=candidate_douban,
            reason=f"豆瓣 ID 不匹配: 需要 {target_douban}，候选 {candidate_douban or '无'}",
            recognition_attempted=True,
        )

    return IdentityResult(False, reason="候选缺少可比较的媒体 ID", recognition_attempted=True)
