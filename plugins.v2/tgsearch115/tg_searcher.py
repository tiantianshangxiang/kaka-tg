# -*- coding: utf-8 -*-
"""Telegram 频道历史消息搜索 + 115 分享链接提取（Telethon User Session）。

为什么用 Telethon User Session 而不是 Bot API：
- 读取非公开频道的历史消息并按关键字检索，Bot API 无法可靠完成（Bot 只能收到
  被加入后的新消息，且无法翻历史）。
- Telethon 以用户身份登录，可读取已加入频道的全部历史并支持 ``search`` 检索。
- Docker 环境下用 **Session String**（一次本地生成）即可，无需运行时交互登录。
"""
import asyncio
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import parse_qsl, urlparse

from app.log import logger


# 115 分享链接正则：匹配 115.com / anxia.com / 115cdn.com 的 /s/ 链接
_115_LINK_RE = re.compile(
    r"https?://(?:[\w-]+\.)*(?:115\.com|anxia\.com|115cdn\.com)/(?:s/|share\.php\?)[^\s<>\"'）)]*",
    re.IGNORECASE,
)


@dataclass
class TgHit:
    """一条命中的 115 资源。"""
    msg_id: int
    text: str
    share_url: str
    share_code: str
    receive_code: str
    resource_title: str
    pub_date: Optional[str] = None


class TgChannelSearcher:
    """基于 Telethon User Session 的 TG 频道历史消息搜索器。"""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_string: str,
        channel: str,
        max_messages: int = 200,
        proxy: Optional[str] = None,
    ) -> None:
        self.api_id = api_id
        self.api_hash = api_hash or ""
        self.session_string = session_string or ""
        self.channel = (channel or "").strip()
        self.max_messages = int(max_messages or 200)
        self.proxy = (proxy or "").strip() or None

    def is_ready(self) -> bool:
        return bool(
            self.api_id and self.api_hash and self.session_string and self.channel
        )

    def search(self, keyword: str, limit: Optional[int] = None) -> List[TgHit]:
        """同步入口：搜索频道历史消息，返回包含 115 分享链接的命中列表。"""
        if not self.is_ready():
            logger.warn("【TG115】TG 搜索器配置不完整（需要 api_id/api_hash/session/channel）")
            return []
        try:
            # 事件处理器运行在独立线程，可安全创建新事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._async_search(keyword, limit))
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"【TG115】TG 频道搜索失败: {e}")
            return []

    # ============================ 异步实现 ============================
    async def _async_search(self, keyword: str, limit: Optional[int]) -> List[TgHit]:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        proxy = self._parse_proxy(self.proxy)
        client = TelegramClient(
            StringSession(self.session_string),
            self.api_id,
            self.api_hash,
            proxy=proxy,
            connection_retries=3,
            retry_delay=2,
            request_retries=3,
        )
        hits: List[TgHit] = []
        await client.connect()
        try:
            if not await client.is_user_authorized():
                logger.error("【TG115】TG Session 未授权或已失效，请重新生成 session string")
                return []
            try:
                entity = await client.get_entity(self.channel)
            except Exception as e:
                logger.error(f"【TG115】解析 TG 频道 {self.channel} 失败: {e}")
                return []

            kw = (keyword or "").strip()
            search_limit = int(limit or self.max_messages)
            async for msg in client.iter_messages(
                entity, search=kw or None, limit=search_limit
            ):
                text = getattr(msg, "message", None) or ""
                if not text:
                    continue
                hits.extend(self._extract_hits(msg.id, text, msg))
                if len(hits) >= search_limit:
                    break
            logger.info(
                f"【TG115】频道 {self.channel} 检索 '{kw}' 完成，命中 {len(hits)} 条 115 资源"
            )
            return hits
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

    # ============================ 解析工具 ============================
    def _extract_hits(self, msg_id: int, text: str, msg) -> List[TgHit]:
        hits: List[TgHit] = []
        for url in _115_LINK_RE.findall(text):
            share_code, receive_code = self._parse_payload(url)
            if not share_code:
                continue
            hits.append(TgHit(
                msg_id=msg_id,
                text=text,
                share_url=url,
                share_code=share_code,
                receive_code=receive_code,
                resource_title=self._guess_title(text, url),
                pub_date=self._fmt_date(getattr(msg, "date", None)),
            ))
        return hits

    @staticmethod
    def _parse_payload(url: str) -> Tuple[str, str]:
        parsed = urlparse(url)
        share_code = ""
        m = re.search(r"/s/([^/?#]+)", parsed.path or "")
        if m:
            share_code = m.group(1).strip()
        q = dict(parse_qsl(parsed.query, keep_blank_values=True))
        receive_code = str(
            q.get("password") or q.get("receive_code") or q.get("pwd") or ""
        ).strip()
        return share_code, receive_code

    @staticmethod
    def _guess_title(text: str, url: str) -> str:
        """从消息文本里猜测资源发布名（供 MP 识别/过滤）。"""
        # 去掉所有链接
        cleaned = re.sub(r"https?://\S+", "", text)
        # 取第一个非空、非纯符号行
        for line in cleaned.splitlines():
            line = line.strip(" \t-–—·•|·:：")
            if line:
                return line[:200]
        return cleaned.strip()[:200]

    @staticmethod
    def _fmt_date(d) -> Optional[str]:
        if not d:
            return None
        try:
            return d.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(d)

    @staticmethod
    def _parse_proxy(proxy: Optional[str]):
        """解析代理字符串为 Telethon 可接受的 proxy 参数。

        支持 ``socks5://host:port`` / ``socks4://host:port`` / ``http://host:port``。
        SOCKS 代理需要安装 ``python-socks``（即 ``telethon[socks]``）。
        """
        if not proxy:
            return None
        try:
            p = urlparse(proxy)
            scheme = (p.scheme or "").lower()
            host, port = p.hostname, p.port
            if not host or not port:
                logger.warn(f"【TG115】代理格式无法解析: {proxy}")
                return None
            if scheme.startswith("socks"):
                stype = "socks5" if "5" in scheme else "socks4"
                return (stype, host, port)
            if scheme in ("http", "https"):
                return (host, port)
            logger.warn(f"【TG115】不支持的代理协议: {scheme}")
        except Exception as e:
            logger.warn(f"【TG115】解析代理失败，将不使用代理: {e}")
        return None
