# -*- coding: utf-8 -*-
"""Telegram 公开频道网页爬虫（免登录，无需 TG 账号 / API 凭证）。

通过 httpx 抓取 ``https://t.me/s/{channel}`` 的网页预览版，
用 BeautifulSoup 解析消息正文，正则提取 115 分享链接和提取码。

与 v1 的 ``tg_searcher.py``（Telethon User Session）的区别：
- 不需要 API ID / API Hash / Session String，零配置开箱即用。
- 只能访问**公开频道**（用户名频道，如 ``@share115``）。
  私有频道（邀请链接 / 数字 ID）无法访问，会跳过。
- 依赖 ``httpx``（p115client 已自带）+ ``beautifulsoup4``。
"""
import asyncio
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlparse

from app.log import logger


# 115 分享链接正则：匹配 115.com / anxia.com / 115cdn.com 的 /s/ 链接
_115_LINK_RE = re.compile(
    r"https?://(?:[\w-]+\.)*(?:115\.com|anxia\.com|115cdn\.com)/(?:s/|share\.php\?)[^\s<>\"'）)]*",
    re.IGNORECASE,
)

# 提取码正则（高鲁棒性，兼容多种写法）：
#   - "提取码: abcd" / "提取码：abcd" / "提取码 abcd"
#   - "访问码: abcd" / "密码: abcd"
#   - "password: abcd" / "pwd abcd" / "code: abcd"
# 匹配 4-8 位英数字符串
_CODE_RE = re.compile(
    r"(?:提取码|访问码|密码|password|pwd|code)[\s:：]*([A-Za-z0-9]{4,8})",
    re.IGNORECASE,
)


@dataclass
class TgHit:
    """一条命中的 115 资源。"""
    msg_id: int = 0
    text: str = ""
    share_url: str = ""
    share_code: str = ""
    receive_code: str = ""
    resource_title: str = ""
    channel_name: str = ""


class TgChannelScraper:
    """基于网页爬虫的 TG 公开频道搜索器（免登录）。"""

    def __init__(self, channels: Optional[List[Dict[str, str]]] = None,
                 proxy: Optional[str] = None) -> None:
        # channels: [{"name": "频道名", "id": "@username"}, ...]
        self.channels = channels or []
        self.proxy = (proxy or "").strip() or None

    def is_ready(self) -> bool:
        return bool(self.channels)

    def search(self, keyword: str) -> List[TgHit]:
        """同步入口：在所有频道搜索关键字，返回含 115 分享链接的命中列表。

        内部用 asyncio.new_event_loop 在调用线程跑异步爬虫，
        与 MoviePilot 主事件循环隔离（同 v1 Telethon 方案）。
        """
        if not self.is_ready():
            logger.warn("【TG115】未配置任何 TG 频道")
            return []
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._async_search(keyword))
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"【TG115】TG 频道爬虫搜索失败: {e}")
            return []

    def check_channel(self, channel_id: str) -> Tuple[bool, str]:
        """检查单个频道连通性：能否抓取到网页预览。"""
        channel_id = (channel_id or "").strip()
        if not channel_id:
            return False, "频道 ID 为空"
        if channel_id.startswith("@"):
            channel_id = channel_id[1:]
        # 只支持公开用户名频道
        if channel_id.startswith("-") or channel_id.startswith("https://t.me/+") or channel_id.isdigit():
            return False, "网页爬虫仅支持公开用户名频道（如 @share115），不支持私有频道/数字 ID"
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._async_check(channel_id))
            finally:
                loop.close()
        except Exception as e:
            return False, f"检查异常: {e}"

    # ============================ 异步实现 ============================
    async def _async_check(self, channel_id: str) -> Tuple[bool, str]:
        import httpx
        async with self._make_client() as client:
            url = f"https://t.me/s/{channel_id}"
            resp = await client.get(url)
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}"
            # 检查是否有消息内容
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            msgs = soup.find_all("div", class_="tgme_widget_message_text")
            if not msgs:
                return False, "频道页面无消息内容（可能是私有频道或不存在）"
            return True, f"连通正常，页面含 {len(msgs)} 条消息"

    async def _async_search(self, keyword: str) -> List[TgHit]:
        import httpx
        from bs4 import BeautifulSoup

        all_hits: List[TgHit] = []
        keywords = [k.strip().lower() for k in keyword.split() if k.strip()]

        async with self._make_client() as client:
            for ch in self.channels:
                cid = (ch.get("id") or "").strip()
                cname = (ch.get("name") or "").strip() or cid
                if not cid:
                    continue
                if cid.startswith("@"):
                    cid = cid[1:]
                # 跳过私有频道（网页版只支持公开用户名）
                if cid.startswith("-") or cid.startswith("https://t.me/+") or cid.isdigit():
                    logger.warn(f"【TG115】频道 [{cname}] ({cid}) 不是公开用户名，网页爬虫跳过")
                    continue

                ch_hits: List[TgHit] = []
                try:
                    url = f"https://t.me/s/{cid}"
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        logger.warn(f"【TG115】频道 [{cname}] 请求失败: HTTP {resp.status_code}")
                        continue

                    soup = BeautifulSoup(resp.text, "html.parser")
                    messages = soup.find_all("div", class_="tgme_widget_message_text")
                    # 倒序遍历（最新优先）
                    for msg in reversed(messages):
                        text = msg.get_text(separator="\n", strip=True)
                        if not text:
                            continue
                        # 关键词过滤：所有关键词都要包含（不区分大小写）
                        text_lower = text.lower()
                        if not all(kw in text_lower for kw in keywords):
                            continue

                        # 提取 115 分享链接
                        for link in _115_LINK_RE.findall(text):
                            share_code, receive_code = _parse_payload(link)
                            if not share_code:
                                continue
                            # 提取码：先从 URL 参数提取，再从文本正则提取
                            if not receive_code:
                                code_match = _CODE_RE.search(text)
                                if code_match:
                                    receive_code = code_match.group(1)

                            ch_hits.append(TgHit(
                                text=text,
                                share_url=link,
                                share_code=share_code,
                                receive_code=receive_code,
                                resource_title=_guess_title(text),
                                channel_name=cname,
                            ))
                    logger.info(f"【TG115】频道 [{cname}] 检索 '{keyword}' 命中 {len(ch_hits)} 条 115 资源")
                except Exception as e:
                    logger.error(f"【TG115】爬取频道 [{cname}] 出错: {e}")
                    continue
                all_hits.extend(ch_hits)

        logger.info(f"【TG115】共爬取 {len(self.channels)} 个频道，合计命中 {len(all_hits)} 条 115 资源")
        return all_hits

    def _make_client(self):
        """创建 httpx.AsyncClient，带 UA 伪装 + 代理。"""
        import httpx
        kwargs = {
            "timeout": 30,
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            "follow_redirects": True,
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy
        return httpx.AsyncClient(**kwargs)


# ============================ 解析工具 ============================
def _parse_payload(url: str) -> Tuple[str, str]:
    """从 115 分享链接解析 share_code / receive_code。"""
    parsed = urlparse(url)
    share_code = ""
    m = re.search(r"/s/([^/?#]+)", parsed.path or "")
    if m:
        share_code = m.group(1).strip()
    q = dict(parse_qsl(parsed.query, keep_blank_values=True))
    receive_code = str(q.get("password") or q.get("receive_code") or q.get("pwd") or "").strip()
    return share_code, receive_code


def _guess_title(text: str) -> str:
    """从消息文本里猜测资源发布名（供 MP 识别/过滤）。"""
    cleaned = re.sub(r"https?://\S+", "", text)
    for line in cleaned.splitlines():
        line = line.strip(" \t-–-·•|·:：")
        if line:
            return line[:200]
    return cleaned.strip()[:200]
