# -*- coding: utf-8 -*-
"""Telegram 公开频道网页爬虫（免登录，无需 TG 账号 / API 凭证）。

通过 httpx 抓取 ``https://t.me/s/{channel}`` 的网页预览版，
用 BeautifulSoup 解析消息正文，正则提取 115 分享链接和提取码。

v4.0 核心改进：使用 Telegram 网页预览版的 **服务端搜索** ``?q=关键字``，
让 Telegram 服务器在频道的 **全部历史消息** 中检索（而不是只抓最近 200 条再本地过滤），
大幅提升命中率，解决「明明有资源却搜不到」的问题。

搜索词只传片名（不含年份）—— TG 消息里大多不写年份，带年份会漏掉大量命中；
年份 / 分辨率 / 字幕组等精细过滤交给 MoviePilot 的规则引擎 ``_filter_resources`` 处理。

稳定性设计：
- 可配置低并发搜索 + 随机延迟 + 429/403 退避。
- timeout=10s + 全异常捕获，绝不崩溃主线程。
- pub_date 从 <time datetime="..."> 提取，兜底当前时间。
- 私有频道前置过滤。
- 翻页用 ?before=消息ID 加载更早的搜索结果。
"""
import asyncio
import random
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, quote, urlparse

from app.log import logger


# 115 分享链接正则
_115_LINK_RE = re.compile(
    r"https?://(?:[\w-]+\.)*(?:115\.com|anxia\.com|115cdn\.com)/(?:s/|share\.php\?)[^\s<>\"'）)]*",
    re.IGNORECASE,
)

# 提取码正则
_CODE_RE = re.compile(
    r"(?:提取码|访问码|密码|password|pwd|code)[\s:：]*([A-Za-z0-9]{4,8})",
    re.IGNORECASE,
)

# PC 端 Chrome UA
_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

_DEFAULT_PUB_DATE = "2000-01-01 00:00:00"

# 每个频道最多翻多少页搜索结果（每页约 20 条）
MAX_PAGES_PER_CHANNEL = 10


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
    pub_date: Optional[str] = None


def _is_private_channel(cid: str) -> bool:
    """判断是否为私有频道（无法网页抓取）。"""
    cid = cid.strip()
    if not cid:
        return True
    if "-100" in cid:
        return True
    if cid.startswith("-"):
        return True
    if cid.startswith("https://t.me/+"):
        return True
    if cid.isdigit():
        return True
    return False


class TgChannelScraper:
    """基于网页爬虫的 TG 公开频道搜索器（免登录，服务端 ?q= 搜索全历史）。"""

    def __init__(self, channels: Optional[List[Dict[str, str]]] = None,
                 proxy: Optional[str] = None,
                 max_pages: int = MAX_PAGES_PER_CHANNEL,
                 concurrency: int = 2,
                 page_delay: Tuple[float, float] = (0.8, 1.5),
                 max_retries: int = 2) -> None:
        self.channels = channels or []
        self.proxy = (proxy or "").strip() or None
        self.max_pages = max(1, int(max_pages))
        self.concurrency = min(3, max(1, int(concurrency or 2)))
        low, high = page_delay
        self.page_delay = (max(0.2, float(low)), max(float(low), float(high)))
        self.max_retries = min(3, max(0, int(max_retries)))
        self.last_error_status: Optional[int] = None
        self.last_error = ""

    def is_ready(self) -> bool:
        return bool(self.channels)

    def search(self, keyword: str) -> List[TgHit]:
        """同步入口：在所有频道搜索关键字，返回含 115 分享链接的命中列表。"""
        if not self.is_ready():
            logger.warn("【TG115】未配置任何 TG 频道")
            return []
        self.last_error_status = None
        self.last_error = ""
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
        """检查单个频道连通性。"""
        channel_id = (channel_id or "").strip()
        if not channel_id:
            return False, "频道 ID 为空"
        if channel_id.startswith("@"):
            channel_id = channel_id[1:]
        if _is_private_channel(channel_id):
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
        try:
            async with self._make_client() as client:
                url = f"https://t.me/s/{channel_id}"
                resp = await client.get(url)
                if resp.status_code != 200:
                    return False, f"HTTP {resp.status_code}"
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                msgs = soup.find_all("div", class_="tgme_widget_message_text")
                if not msgs:
                    return False, "频道页面无消息内容（可能是私有频道或不存在）"
                return True, f"连通正常，页面含 {len(msgs)} 条消息"
        except Exception as e:
            return False, f"网络异常: {e}"

    async def _async_search(self, keyword: str) -> List[TgHit]:
        """并发搜索所有频道（Semaphore(5) 限流 + 随机延迟防 429）。

        v4.0：用 ``?q=关键字`` 让 Telegram 服务器搜索频道全部历史，
        而不是只抓最近 N 条再本地过滤。搜索词只取片名（不含年份）。
        """
        search_term = (keyword or "").strip()
        if not search_term:
            logger.warn("【TG115】搜索关键字为空")
            return []
        encoded_term = quote(search_term)

        sem = asyncio.Semaphore(self.concurrency)

        # 前置过滤：跳过私有频道
        valid_channels = []
        for ch in self.channels:
            cid = (ch.get("id") or "").strip()
            cname = (ch.get("name") or "").strip() or cid
            if not cid:
                continue
            if cid.startswith("@"):
                cid = cid[1:]
            if _is_private_channel(cid):
                logger.warn(f"【TG115】频道 [{cname}] ({cid}) 为私有频道，网页爬虫跳过")
                continue
            valid_channels.append((cid, cname))

        if not valid_channels:
            logger.warn("【TG115】没有可爬取的公开频道")
            return []

        async with self._make_client() as client:
            tasks = [
                self._search_one_channel(client, cid, cname, encoded_term, sem)
                for cid, cname in valid_channels
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        all_hits: List[TgHit] = []
        for r in results:
            if isinstance(r, list):
                all_hits.extend(r)
            elif isinstance(r, Exception):
                logger.error(f"【TG115】频道搜索异常: {r}")

        logger.info(
            f"【TG115】共搜索 {len(valid_channels)} 个频道（TG 服务端 ?q= 搜全历史），"
            f"合计命中 {len(all_hits)} 条 115 资源"
        )
        return all_hits

    async def _search_one_channel(
        self, client, cid: str, cname: str, encoded_term: str, sem
    ) -> List[TgHit]:
        """用 TG 网页预览版搜索功能搜索单个频道的全部历史。

        使用 ``https://t.me/s/{channel}?q={keyword}`` 让 Telegram 服务器搜索，
        翻页用 ``&before=消息ID`` 加载更早的搜索结果。每页约 20 条，
        最多翻 max_pages 页。服务端已按关键字过滤，本地不再做关键词强匹配
        （年份/分辨率等精细过滤交给 MP 规则引擎）。
        """
        from bs4 import BeautifulSoup

        ch_hits: List[TgHit] = []
        async with sem:
            await asyncio.sleep(random.uniform(*self.page_delay))
            try:
                total_msgs = 0
                before_id = None  # 翻页用：上一页最旧的消息 ID

                for page in range(self.max_pages):
                    # 构造服务端搜索 URL
                    if before_id:
                        url = f"https://t.me/s/{cid}?q={encoded_term}&before={before_id}"
                    else:
                        url = f"https://t.me/s/{cid}?q={encoded_term}"

                    resp = await self._get_with_backoff(client, url, cname, page + 1)
                    if resp.status_code != 200:
                        self.last_error_status = resp.status_code
                        self.last_error = f"HTTP {resp.status_code}"
                        logger.warn(
                            f"【TG115】频道 [{cname}] 搜索第 {page+1} 页失败: HTTP {resp.status_code}"
                        )
                        break

                    soup = BeautifulSoup(resp.text, "html.parser")
                    msg_elements = soup.find_all("div", class_="tgme_widget_message")
                    if not msg_elements:
                        msg_elements = soup.find_all(attrs={"data-post": True})
                    if not msg_elements:
                        break  # 没有更多搜索结果

                    page_oldest_id = None

                    for msg_el in msg_elements:
                        try:
                            # 提取消息 ID（data-post="channel/123"）
                            post_attr = msg_el.get("data-post", "")
                            msg_id = 0
                            if "/" in post_attr:
                                try:
                                    msg_id = int(post_attr.split("/")[-1])
                                except Exception:
                                    pass
                            if not msg_id:
                                time_tag = msg_el.find("time")
                                if time_tag and time_tag.parent:
                                    href = time_tag.parent.get("href", "")
                                    m = re.search(r"/(\d+)$", href)
                                    if m:
                                        msg_id = int(m.group(1))
                            if msg_id and (page_oldest_id is None or msg_id < page_oldest_id):
                                page_oldest_id = msg_id

                            # 提取消息文本
                            text_div = msg_el.find("div", class_="tgme_widget_message_text")
                            if not text_div:
                                continue
                            text = text_div.get_text(separator="\n", strip=True)
                            if not text:
                                continue
                            total_msgs += 1

                            # 提取发布时间
                            pub_date = _extract_pub_date(msg_el)

                            # 提取 115 分享链接（服务端已按关键字过滤，无需本地再匹配）
                            for link in _115_LINK_RE.findall(text):
                                share_code, receive_code = _parse_payload(link)
                                if not share_code:
                                    continue
                                if not receive_code:
                                    code_match = _CODE_RE.search(text)
                                    if code_match:
                                        receive_code = code_match.group(1)

                                ch_hits.append(TgHit(
                                    msg_id=msg_id,
                                    text=text,
                                    share_url=link,
                                    share_code=share_code,
                                    receive_code=receive_code,
                                    resource_title=_guess_title(text),
                                    channel_name=cname,
                                    pub_date=pub_date,
                                ))
                        except Exception as e:
                            logger.warn(
                                f"【TG115】频道 [{cname}] 解析消息出错（跳过）: {e}"
                            )
                            continue

                    # 翻页：没有更旧的消息则停止
                    if page_oldest_id is None or page_oldest_id <= 1:
                        break
                    before_id = page_oldest_id
                    await asyncio.sleep(random.uniform(*self.page_delay))

                logger.info(
                    f"【TG115】频道 [{cname}] 搜索 '{encoded_term}' "
                    f"返回 {total_msgs} 条消息（{page+1} 页），命中 {len(ch_hits)} 条 115 资源"
                )
            except Exception as e:
                logger.warn(f"【TG115】搜索频道 [{cname}] 出错（跳过）: {e}")
            return ch_hits

    async def _get_with_backoff(self, client, url: str, channel: str, page: int):
        """Retry throttled requests while respecting Retry-After when present."""
        response = None
        for attempt in range(self.max_retries + 1):
            response = await client.get(url)
            if response.status_code not in (403, 429):
                return response
            if attempt >= self.max_retries:
                return response
            retry_after = response.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else float(2 ** (attempt + 1))
            except (TypeError, ValueError):
                delay = float(2 ** (attempt + 1))
            delay = min(60.0, max(1.0, delay)) + random.uniform(0.2, 0.8)
            logger.warn(
                f"【TG115】频道 [{channel}] 第 {page} 页触发 HTTP {response.status_code}，"
                f"{delay:.1f} 秒后重试（{attempt + 1}/{self.max_retries}）"
            )
            await asyncio.sleep(delay)
        return response

    def _make_client(self):
        """创建 httpx.AsyncClient，带 Chrome UA + 代理 + 10s 超时。"""
        import httpx
        kwargs = {
            "timeout": 10.0,
            "headers": {
                "User-Agent": _CHROME_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            "follow_redirects": True,
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy
            kwargs["trust_env"] = False
        else:
            kwargs["trust_env"] = False
        return httpx.AsyncClient(**kwargs)


# ============================ 解析工具 ============================
def _extract_pub_date(wrap_element) -> str:
    """从消息容器中提取发布时间。

    TG 网页预览版每条消息的 ``tgme_widget_message_wrap`` 内含
    ``<time datetime="2024-01-15T12:34:56+00:00">`` 标签。
    """
    try:
        time_tag = wrap_element.find("time")
        if time_tag:
            dt = time_tag.get("datetime", "")
            if dt:
                return _normalize_datetime(dt)
    except Exception:
        pass
    return _DEFAULT_PUB_DATE


def _normalize_datetime(dt_str: str) -> str:
    """将 ISO 8601 时间字符串归一化为 ``YYYY-MM-DD HH:MM:SS`` 格式。"""
    try:
        cleaned = re.sub(r"[+-]\d{2}:\d{2}$", "", dt_str)
        cleaned = cleaned.replace("T", " ").replace("Z", "")
        return cleaned[:19]
    except Exception:
        return dt_str


def _parse_payload(url: str) -> Tuple[str, str]:
    """从 115 分享链接解析 share_code / receive_code。"""
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


def _guess_title(text: str) -> str:
    """从消息文本里猜测资源发布名（供 MP 识别/过滤）。"""
    cleaned = re.sub(r"https?://\S+", "", text)
    for line in cleaned.splitlines():
        line = line.strip(" \t-–-·•|·:：")
        if line:
            return line[:200]
    return cleaned.strip()[:200]
