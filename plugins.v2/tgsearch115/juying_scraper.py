# -*- coding: utf-8 -*-
"""聚影开发者 API 爬虫：通过官方 /api/dev/search/aggregate/ 搜索资源。

聚影是独立于观影的资源站，提供官方开发者 API（AppID + API Key 鉴权），
比网页爬虫稳定（无 PoW、无 IP 封锁）。非开发者用开发者的 AppID + 自己的 API Key。

================================================================================
 鉴权
================================================================================
Header 传参：X-App-Id（开发者 AppID）+ X-App-Key（用户个人 API Key）
限流：每凭证 20 次/分钟（聚合搜索），超限返回 429。

================================================================================
 搜索
================================================================================
GET /api/dev/search/aggregate/?q={关键字}&source=all&year={年份}&local_limit=10&pansou_limit=30
返回 {status, resources:[{provider, movie_title, resource_type, share_link, description, extraction_code?}]}
resource_type：quark/baidu/115/aliyun/xunlei/cloud189/uc/magnet 等。
share_link 是明文分享链接，extraction_code 是提取码（也可能在 share_link 的 ?pwd= 里）。
"""
from typing import List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse

from app.log import logger

from .site_scraper import SiteHit, _classify_pan


# API 返回的 resource_type -> 插件 pan_type 映射
_TYPE_MAP = {
    "115": "115", "quark": "quark", "baidu": "baidu",
    "aliyun": "aliyun", "aliyundrive": "aliyun", "alipan": "aliyun",
    "xunlei": "xunlei", "cloud189": "cloud189", "189": "cloud189",
    "uc": "uc", "magnet": "magnet", "bt": "magnet", "ed2k": "magnet",
}


class JuyingApi:
    """聚影开发者 API 搜索器（/api/dev/search/aggregate/）。"""

    def __init__(self, app_id: str = "", api_key: str = "", domain: str = "",
                 proxy: Optional[str] = None) -> None:
        self.app_id = (app_id or "").strip()
        self.api_key = (api_key or "").strip()
        self.domain = (domain or "").strip().rstrip("/")
        self.proxy = (proxy or "").strip() or None
        self._http = None
        self.app_auth_valid = True  # 兼容 /search 的 warning 检查（401 时置 False）

    def is_ready(self) -> bool:
        return bool(self.app_id and self.api_key and self.domain)

    # ============================ 同步入口 ============================
    def search(self, keyword: str, year: Optional[int] = None) -> List[SiteHit]:
        """搜索关键字，返回 SiteHit 列表。year 精确匹配年份。"""
        if not self.is_ready():
            logger.warn("【TG115】聚影未配置 AppID/API Key/域名，跳过")
            return []
        kw = (keyword or "").strip()
        if not kw:
            return []
        try:
            return self._do_search(kw, year)
        except Exception as e:
            logger.error(f"【TG115】聚影搜索失败: {e}")
            return []

    def check(self) -> Tuple[bool, str]:
        """检查连通性 + 鉴权（用一次轻量搜索验证）。"""
        if not self.is_ready():
            return False, "未配置 AppID/API Key/域名"
        try:
            params = {"q": "测试", "source": "all", "local_limit": 1, "pansou_limit": 1}
            url = f"{self.domain}/api/dev/search/aggregate/?{urlencode(params)}"
            resp = self._client().get(url, headers=self._headers())
            if resp.status_code == 401:
                self.app_auth_valid = False
                return False, "AppID/API Key 无效（401）"
            if resp.status_code == 429:
                return False, "API 限流（429），稍后重试"
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}"
            data = resp.json()
            if data.get("status") == "success":
                return True, "连通正常，鉴权有效"
            return False, data.get("message") or "未知错误"
        except Exception as e:
            return False, f"检查异常: {e}"

    # ============================ 内部实现 ============================
    def _do_search(self, kw: str, year: Optional[int]) -> List[SiteHit]:
        params = {"q": kw, "source": "all", "local_limit": 10, "pansou_limit": 30}
        if year:
            params["year"] = year
        url = f"{self.domain}/api/dev/search/aggregate/?{urlencode(params)}"
        resp = self._client().get(url, headers=self._headers())
        if resp.status_code == 429:
            logger.warn("【TG115】聚影 API 限流(429)，稍后重试")
            return []
        if resp.status_code == 401:
            logger.warn("【TG115】聚影 AppID/API Key 无效(401)")
            self.app_auth_valid = False
            return []
        if resp.status_code != 200:
            logger.warn(f"【TG115】聚影搜索失败: HTTP {resp.status_code} {resp.text[:200]}")
            return []
        try:
            data = resp.json()
        except Exception as e:
            logger.warn(f"【TG115】聚影响应非JSON: {e}")
            return []
        if data.get("status") != "success":
            logger.warn(f"【TG115】聚影搜索错误: {data.get('message')}")
            return []
        resources = data.get("resources") or []
        hits: List[SiteHit] = []
        for r in resources:
            link = str(r.get("share_link") or "").strip()
            if not link or link == "javascript:;":
                continue
            rtype = str(r.get("resource_type") or "").strip().lower()
            pan_type = _TYPE_MAP.get(rtype) or _classify_pan(link)
            # 提取码：优先 extraction_code 字段，否则从链接 ?pwd=/?password= 解析
            code = str(r.get("extraction_code") or "").strip()
            if not code:
                q = dict(parse_qsl(urlparse(link).query, keep_blank_values=True))
                code = str(q.get("pwd") or q.get("password") or q.get("receive_code") or "").strip()
            movie_title = str(r.get("movie_title") or "").strip()
            desc = str(r.get("description") or "").strip()
            hits.append(SiteHit(
                share_url=link,
                receive_code=code,
                resource_title=desc or movie_title,
                text=desc or movie_title,
                pan_type=pan_type,
                pan_label=rtype,
                source_title=movie_title,
                channel_name="聚影",
            ))
        logger.info(f"【TG115】聚影搜索 '{kw}' 命中 {len(hits)} 条资源")
        return hits

    def _headers(self):
        return {
            "X-App-Id": self.app_id,
            "X-App-Key": self.api_key,
            "Accept": "application/json",
        }

    def _client(self):
        if self._http is None:
            import httpx
            kwargs = {
                "timeout": 20.0,
                "headers": {"User-Agent": "Mozilla/5.0 (MoviePilot-TgSearch115)"},
                "follow_redirects": True,
            }
            if self.proxy:
                kwargs["proxy"] = self.proxy
                kwargs["trust_env"] = False
            else:
                kwargs["trust_env"] = False
            self._http = httpx.Client(**kwargs)
        return self._http
