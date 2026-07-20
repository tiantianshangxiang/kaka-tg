# -*- coding: utf-8 -*-
"""目标资源站（xn--wcv59z.com）爬虫：PoW 验证 + 搜索 + 全网盘资源提取。

================================================================================
 为什么单独一个模块
================================================================================
该站用 **RSW 时间锁 PoW** 做反机器人验证，且资源是 **JS 渲染**（后端 JSON API），
与 TG 频道的「抓 HTML 网页」完全不同，故独立成模块。

================================================================================
 PoW 反机器人（已用纯 Python 破解）
================================================================================
站点对未验证请求返回「浏览器安全验证」页，流程：
  1. GET /            -> 设 browser_pow cookie，返回验证页（引用 powSolve.js）
  2. GET /res/pow     -> {N, x, t}  挑战（RSW 时间锁谜题）
  3. 算 y = x^(2^t) mod N   （连续平方 t 次）
  4. POST /res/pow {y} -> {"success":true} 设 browser_verified cookie
  5. 此后请求带 browser_verified 即放行

关键：服务器**只校验 y 的数学正确性，不校验耗时**。JS 用解释型 worker 循环慢算
（数秒），而 Python 内置 ``pow(x, 1 << t, N)`` 走 C 层快速模幂，t=200000 时仅 ~1.5s
即算出完全相同的 y。无需浏览器 / 无新依赖。

================================================================================
 登录态
================================================================================
PoW 只是反机器人层，访问真实资源还需 ``app_auth`` cookie（用户在站点登录后获取）。
app_auth 失效时站点返回「未登录，访问受限」，本模块会日志告警。

================================================================================
 资源 API
================================================================================
  搜索：GET /res/search_suggest?q={片名}
        -> [{"title","id","dir"(mv/tv/ac),"year","ename","score"}, ...]
  取资源：GET /res/downurl/{dir}/{id}
        -> {"code":200, "panlist":{"url":[...],"name":[...],"p":[...提取码...],
                                   "tname":[...网盘类型名...],...},
            "downlist":{...BT磁力(加密)...}, ...}

``panlist.url`` 是**明文分享链接**，``panlist.p`` 是提取码，``panlist.tname`` 是网盘类型名。
注意：``tname`` 是上传者自填，常与实际域名不符（如 tname="115网盘" 但链接是迅雷），
故网盘类型 **按 URL 域名判定**，tname 仅作展示标签。

站点资源大多是夸克/百度/阿里/迅雷，115 占比很小；本模块提取**全部网盘**链接并标注类型，
转存层自行决定只转 115（见 ``__init__.py`` 的订阅流程）。
"""
import html
import http.cookiejar
import json
import random
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlencode, urlparse
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

from app.log import logger


# 站点基址（punycode 域名，对应中文域）
DEFAULT_SITE_BASE = "https://www.xn--wcv59z.com"  # 默认域名（可被 site_base 参数覆盖）
_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def _normalize_app_auth(value: str) -> str:
    """Accept either the raw token or a copied Cookie header fragment."""
    raw = str(value or "").strip()
    match = re.search(r"(?:^|[;\s])app_auth\s*=\s*([^;\s]+)", raw, re.IGNORECASE)
    return match.group(1).strip() if match else raw

# 网盘类型判定（按 URL 域名，可靠；tname 不可靠仅作展示）
_PAN_DOMAINS: List[Tuple[str, str]] = [
    ("115.com", "115"), ("anxia.com", "115"), ("115cdn.com", "115"),
    ("pan.quark.cn", "quark"), ("quark.cn", "quark"),
    ("pan.baidu.com", "baidu"), ("yun.baidu.com", "baidu"),
    ("aliyundrive.com", "aliyun"), ("alipan.com", "aliyun"),
    ("pan.xunlei.com", "xunlei"),
    ("cloud.189.cn", "cloud189"), ("cloud.21cn.com", "cloud189"),
    ("drive.uc.cn", "uc"), ("pan.uc.cn", "uc"),
]


def _classify_pan(url: str) -> str:
    """按 URL 域名判定网盘类型。"""
    u = (url or "").lower()
    for frag, ptype in _PAN_DOMAINS:
        if frag in u:
            return ptype
    return "other"


@dataclass
class SiteHit:
    """一条命中的网盘资源（来自目标资源站）。"""
    share_url: str = ""
    receive_code: str = ""
    resource_title: str = ""
    text: str = ""
    pan_type: str = ""        # 115/quark/baidu/aliyun/xunlei/cloud189/uc/other
    pan_label: str = ""       # 站点原始 tname（展示用，可能不准）
    source_title: str = ""    # 搜索命中的片名
    channel_name: str = "观影"
    pub_date: Optional[str] = None
    year: Optional[int] = None

    @property
    def is_115(self) -> bool:
        return self.pan_type == "115"


class FilejinScraper:
    """目标资源站爬虫：解 PoW -> 搜索 -> 提取全网盘资源。"""

    def __init__(self, app_auth: str = "", proxy: Optional[str] = None,
                 count: int = 3, site_base: str = "",
                 detail_delay: Tuple[float, float] = (1.5, 3.0),
                 max_retries: int = 1) -> None:
        self.app_auth = _normalize_app_auth(app_auth)
        self.proxy = (proxy or "").strip() or None
        self.count = count  # 每次（每页）取多少部作品的网盘资源
        self._http = None            # 持久 httpx.Client（复用 PoW 会话）
        self._pow_solved = False
        self._cache_key = None       # (keyword, year) 缓存键
        self._cache_items = None     # search_suggest 作品列表缓存
        self.app_auth_valid = True   # app_auth 是否有效（失效则置 False，供 /search 提示）
        self.last_detail_error = ""  # 最近一次详情失败原因，供 API/连通测试展示
        low, high = detail_delay
        self.detail_delay = (max(0.5, float(low)), max(float(low), float(high)))
        self.max_retries = min(3, max(0, int(max_retries)))
        self.last_error_status: Optional[int] = None
        self.site_base = (site_base or DEFAULT_SITE_BASE).rstrip("/")  # 观影域名（可配置，换域名时改这里）

    def is_ready(self) -> bool:
        return bool(self.app_auth)

    # ============================ 同步入口 ============================
    def search(self, keyword: str, year: Optional[int] = None,
               offset: int = 0, count: Optional[int] = None) -> Tuple[List[SiteHit], bool]:
        """搜索关键字，返回 (命中列表, 是否还有更多)。

        按 search_suggest 返回的作品分批：每批 count 部作品的网盘资源。
        offset=0 取首批，offset=N 取第 N 批。作品列表按 keyword+year 缓存，
        同一关键字翻页时复用缓存与 PoW 会话，不重复请求 search_suggest。

        :param year: 订阅流程传入年份，精确匹配同名作品，避免模糊匹配混入。
        """
        if not self.is_ready():
            logger.warn("【TG115】观影未配置 app_auth，跳过")
            return [], False
        term = (keyword or "").strip()
        if not term:
            return [], False
        self.last_detail_error = ""
        self.last_error_status = None
        cnt = count or self.count
        try:
            items = self._get_items(term, year)
            if items is None:
                return [], False
            batch = items[offset:offset + cnt]
            hits: List[SiteHit] = []
            for idx, it in enumerate(batch):
                dir_ = str(it.get("dir") or "")
                id_ = str(it.get("id") or "")
                if not dir_ or not id_:
                    continue
                # 防风控：作品间随机延迟（首批除外），模仿人工浏览，避免短时连发 downurl
                if idx > 0:
                    time.sleep(random.uniform(*self.detail_delay))
                pan_hits = self._fetch_resources(dir_, id_)
                for ph in pan_hits:
                    ph.source_title = str(it.get("title") or "")
                    ph.year = it.get("year")
                hits.extend(pan_hits)
                if pan_hits:
                    n115 = sum(1 for h in pan_hits if h.is_115)
                    logger.info(
                        f"【TG115】观影 [{it.get('title')}] ({dir_}/{id_}) "
                        f"共 {len(pan_hits)} 条网盘资源，其中 115 {n115} 条"
                    )
            has_more = (offset + cnt) < len(items)
            return hits, has_more
        except Exception as e:
            logger.error(f"【TG115】观影搜索失败: {e}")
            return [], False

    def check(self) -> Tuple[bool, str]:
        """检查站点连通性 + 登录态（解 PoW 后尝试一次搜索）。"""
        if not self.is_ready():
            return False, "未配置 app_auth"
        try:
            self._ensure_access()
            ok, msg, items = self._search_suggest("测试")
            if not ok and "未登录" in msg:
                return False, "app_auth 已失效（站点返回未登录）"
            if not ok:
                return False, f"搜索接口不可用：{msg}"
            if items:
                item = items[0]
                dir_ = str(item.get("dir") or "")
                id_ = str(item.get("id") or "")
                if dir_ and id_:
                    hits = self._fetch_resources(dir_, id_)
                    if hits:
                        return True, f"连通正常，搜索和详情均可用（样本 {len(hits)} 条资源）"
                    if self.last_detail_error:
                        return False, f"搜索可用，但详情不可用：{self.last_detail_error}"
            return True, "搜索可用，登录态有效；测试词无详情样本"
        except Exception as e:
            return False, f"检查异常: {e}"

    # ============================ 内部实现 ============================
    def _get_client(self):
        """懒加载持久 httpx.Client（带 Cookie + 代理）。PoW 会话复用，翻页不重建。"""
        if self._http is None:
            self._http = self._make_client()
        return self._http

    def _get_items(self, term: str, year: Optional[int]):
        """获取 search_suggest 作品列表，按 (keyword, year) 缓存。失败返回 None。"""
        key = (term, year)
        if self._cache_key == key and self._cache_items is not None:
            return self._cache_items
        self._ensure_access()
        ok, msg, items = self._search_suggest(term)
        if not ok:
            logger.warn(f"【TG115】观影搜索 '{term}' 失败: {msg}")
            return None
        # 年份精确匹配（订阅流程）
        if year:
            yr = str(year)
            year_items = [it for it in items if str(it.get("year", "")) == yr]
            items = year_items
        logger.info(
            f"【TG115】观影搜索 '{term}' 命中 {len(items)} 部作品"
            + (f"（年份 {year} 匹配）" if year else "")
        )
        self._cache_key = key
        self._cache_items = items
        return items

    def _ensure_access(self):
        """确保 PoW 已解（拿到 browser_verified）。app_auth 失效则告警。"""
        if self._pow_solved:
            return
        self._solve_pow()
        self._pow_solved = True
        # 解完 PoW 后探一次首页确认登录态
        try:
            resp = self._get_client().get(self.site_base + "/", headers={"Accept": "text/html"})
            if "未登录" in resp.text:
                self.app_auth_valid = False
                logger.warn("【TG115】观影 app_auth 已失效（返回未登录），请更新 app_auth")
        except Exception:
            pass

    def _solve_pow(self):
        """解 RSW 时间锁 PoW：GET /res/pow -> 算 y=x^(2^t)%N -> POST /res/pow。"""
        import json as _json
        # 先 GET / 触发 browser_pow cookie
        try:
            self._get_client().get(self.site_base + "/", headers={"Accept": "text/html"})
        except Exception:
            pass
        resp = self._get_client().get(self.site_base + "/res/pow", headers={"Accept": "application/json"})
        if resp.status_code != 200:
            logger.warn(f"【TG115】观影取 PoW 挑战失败: HTTP {resp.status_code}")
            return
        try:
            ch = resp.json()
        except Exception as e:
            logger.warn(f"【TG115】观影 PoW 挑战非 JSON: {e}")
            return
        try:
            N = int(str(ch["N"]), 16)
            x = int(str(ch["x"]), 16)
            t = int(ch["t"])
        except Exception as e:
            logger.warn(f"【TG115】观影 PoW 挑战字段异常: {e}")
            return
        # y = x^(2^t) mod N —— C 层快速模幂，t=200000 约 1.5s
        y = pow(x, 1 << t, N)
        y_hex = format(y, "x")
        resp = self._get_client().post(
            self.site_base + "/res/pow",
            data={"y": y_hex},
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "application/json"},
        )
        try:
            vj = resp.json()
            if vj.get("success"):
                logger.info(f"【TG115】观影 PoW 解算成功 (t={t})")
            else:
                logger.warn(f"【TG115】观影 PoW 验证未通过: {vj}")
        except Exception:
            logger.warn("【TG115】观影 PoW 验证响应非 JSON")

    def _search_suggest(self, term: str):
        """GET /res/search_suggest?q= -> 作品列表。返回 (ok, msg, items)。"""
        url = self.site_base + "/res/search_suggest?q=" + quote(term)
        resp = self._get_with_backoff(url, headers={"Accept": "application/json"})
        if resp.status_code != 200:
            self.last_error_status = resp.status_code
            return False, f"HTTP {resp.status_code}", []
        text = resp.text or ""
        if "浏览器安全验证" in text or "powSolve" in text:
            # cookie 失效，重解 PoW 再试一次
            self._pow_solved = False
            self._ensure_access()
            resp = self._get_with_backoff(url, headers={"Accept": "application/json"})
            text = resp.text or ""
        if "未登录" in text:
            return False, "未登录（app_auth 失效）", []
        try:
            items = resp.json()
        except Exception as e:
            return False, f"非JSON: {e}", []
        if not isinstance(items, list):
            return False, "响应非数组", []
        return True, "ok", items

    def _fetch_resources(self, dir_: str, id_: str) -> List[SiteHit]:
        """GET /res/downurl/{dir}/{id} -> 提取 panlist(网盘) + downlist(磁力) 全部资源。"""
        url = f"{self.site_base}/res/downurl/{dir_}/{id_}"
        self.last_detail_error = ""
        try:
            resp = self._get_with_backoff(url, headers={"Accept": "application/json"})
        except Exception as e:
            self.last_detail_error = f"网络异常: {e}"
            urllib_hits = self._fetch_resources_urllib(dir_, id_)
            if urllib_hits is not None:
                self.last_detail_error = ""
                return urllib_hits
            logger.warn(f"【TG115】观影 downurl {dir_}/{id_} {self.last_detail_error}")
            return []

        hits = self._parse_detail_response(resp)
        if hits is not None:
            return hits
        if self._looks_like_html(resp):
            html_hits = self._parse_resources_from_html(resp.text or "")
            if html_hits:
                self.last_detail_error = ""
                return html_hits

        # WAF 常只封 API 特征；以同一会话模拟页面导航再试一次。
        if resp.status_code in (403, 404) or self._looks_like_html(resp):
            retry_headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Origin": self.site_base,
                "Referer": self.site_base + "/",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
            }
            try:
                if resp.status_code == 403:
                    delay = self._retry_delay(resp, 0)
                    logger.warn(f"【TG115】观影触发 HTTP 403，{delay:.1f} 秒后以页面请求重试")
                    time.sleep(delay)
                retry = self._get_client().get(url, headers=retry_headers)
                hits = self._parse_detail_response(retry)
                if hits is not None:
                    self.last_error_status = None
                    return hits
                html_hits = self._parse_resources_from_html(retry.text or "")
                if html_hits:
                    self.last_detail_error = ""
                    self.last_error_status = None
                    logger.info(
                        f"【TG115】观影 downurl 页面兜底提取 {len(html_hits)} 条资源"
                    )
                    return html_hits
                resp = retry
            except Exception as e:
                self.last_detail_error = f"页面重试异常: {e}"
                resp = None

        if not self.last_detail_error and resp is not None:
            self.last_detail_error = f"HTTP {resp.status_code}"

        urllib_hits = self._fetch_resources_urllib(dir_, id_)
        if urllib_hits is not None:
            self.last_detail_error = ""
            self.last_error_status = None
            logger.info(
                f"【TG115】观影 downurl urllib 直连兜底成功，提取 {len(urllib_hits)} 条资源"
            )
            return urllib_hits

        logger.warn(
            f"【TG115】观影 downurl {dir_}/{id_} 失败: {self.last_detail_error}"
        )
        return []

    def _get_with_backoff(self, url: str, headers: Optional[dict] = None):
        """Retry WAF/throttle responses and honor Retry-After when supplied."""
        response = None
        for attempt in range(self.max_retries + 1):
            response = self._get_client().get(url, headers=headers)
            if response.status_code != 429:
                if response.status_code == 403:
                    self.last_error_status = 403
                else:
                    self.last_error_status = None
                return response
            self.last_error_status = response.status_code
            if attempt >= self.max_retries:
                return response
            delay = self._retry_delay(response, attempt)
            logger.warn(
                f"【TG115】观影触发 HTTP {response.status_code}，{delay:.1f} 秒后重试"
                f"（{attempt + 1}/{self.max_retries}）"
            )
            time.sleep(delay)
        return response

    @staticmethod
    def _retry_delay(response, attempt: int) -> float:
        retry_after = getattr(response, "headers", {}).get("Retry-After")
        try:
            delay = float(retry_after) if retry_after else float(2 ** (attempt + 1))
        except (TypeError, ValueError):
            delay = float(2 ** (attempt + 1))
        return min(60.0, max(1.0, delay)) + random.uniform(0.2, 0.8)

    def _fetch_resources_urllib(self, dir_: str, id_: str) -> Optional[List[SiteHit]]:
        """httpx 被 WAF 拒绝时，用独立 urllib CookieJar + PoW 会话直连重试。"""
        host = urlparse(self.site_base).hostname or ""
        if not host or not self.app_auth:
            return None
        jar = http.cookiejar.CookieJar()
        jar.set_cookie(http.cookiejar.Cookie(
            version=0,
            name="app_auth",
            value=self.app_auth,
            port=None,
            port_specified=False,
            domain=host,
            domain_specified=True,
            domain_initial_dot=False,
            path="/",
            path_specified=True,
            secure=self.site_base.startswith("https://"),
            expires=None,
            discard=True,
            comment=None,
            comment_url=None,
            rest={},
        ))
        opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(jar))
        opener.addheaders = [
            ("User-Agent", _CHROME_UA),
            ("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8"),
            ("Referer", self.site_base + "/"),
        ]

        def request(path: str, method: str = "GET", data: bytes = None):
            headers = {"Accept": "application/json"}
            if method == "POST":
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            req = Request(
                self.site_base + path,
                data=data,
                method=method,
                headers=headers,
            )
            with opener.open(req, timeout=30) as response:
                return response.status, response.read().decode("utf-8", "replace")

        try:
            request("/")
            try:
                pow_status, pow_text = request("/res/pow")
                if pow_status == 200:
                    challenge = json.loads(pow_text)
                    modulus = int(str(challenge["N"]), 16)
                    base = int(str(challenge["x"]), 16)
                    iterations = int(challenge["t"])
                    answer = format(pow(base, 1 << iterations, modulus), "x")
                    request(
                        "/res/pow",
                        method="POST",
                        data=urlencode({"y": answer}).encode(),
                    )
            except HTTPError as e:
                if e.code != 404:
                    raise

            status, body = request(f"/res/downurl/{dir_}/{id_}")
            if status != 200:
                self.last_detail_error = f"urllib HTTP {status}"
                return None
            data = json.loads(body)
            if not isinstance(data, dict) or data.get("code") not in (200, "200"):
                message = data.get("message") or data.get("msg") or data.get("code") \
                    if isinstance(data, dict) else "响应格式错误"
                self.last_detail_error = f"urllib 业务错误: {message}"
                return None
            return self._parse_downurl_data(data)
        except HTTPError as e:
            self.last_detail_error = f"urllib HTTP {e.code}"
            return None
        except Exception as e:
            self.last_detail_error = f"urllib 异常: {e}"
            return None

    @staticmethod
    def _looks_like_html(resp) -> bool:
        content_type = str(resp.headers.get("content-type") or "").lower()
        text = (resp.text or "").lstrip().lower()
        return "text/html" in content_type or text.startswith("<!doctype") or text.startswith("<html")

    def _parse_detail_response(self, resp) -> Optional[List[SiteHit]]:
        """解析 JSON 详情；响应不是可识别 JSON 时返回 None，交给 HTML 兜底。"""
        if resp.status_code != 200:
            self.last_detail_error = f"HTTP {resp.status_code}"
            return None
        try:
            data = resp.json()
        except Exception as e:
            self.last_detail_error = f"响应非 JSON: {e}"
            return None
        if not isinstance(data, dict):
            self.last_detail_error = "JSON 响应不是对象"
            return None
        if data.get("code") not in (200, "200"):
            message = data.get("message") or data.get("msg") or data.get("code")
            self.last_detail_error = f"业务错误: {message}"
            logger.warn(f"【TG115】观影 downurl 返回错误: {self.last_detail_error}")
            return []
        self.last_detail_error = ""
        return self._parse_downurl_data(data)

    @staticmethod
    def _parse_downurl_data(data: dict) -> List[SiteHit]:
        """解析 downurl JSON 中的网盘和磁力资源。"""
        hits: List[SiteHit] = []
        # panlist
        pl = data.get("panlist") or {}
        urls = pl.get("url") or []
        names = pl.get("name") or []
        ps = pl.get("p") or []
        tnames = pl.get("tname") or []
        for i, u in enumerate(urls):
            u = str(u or "").strip()
            if not u or u == "javascript:;":
                continue
            pwd = str(ps[i]).strip() if i < len(ps) else ""
            if pwd in ("", "无提取码", "无"):
                pwd = ""
            name = str(names[i]).strip() if i < len(names) else ""
            label = str(tnames[i]).strip() if i < len(tnames) else ""
            hits.append(SiteHit(
                share_url=u,
                receive_code=pwd,
                resource_title=_clean_title(name),
                text=name,
                pan_type=_classify_pan(u),
                pan_label=label,
            ))
        # downlist: 磁力
        dl = data.get("downlist") or {}
        lst = dl.get("list") or {}
        ms = lst.get("m") or []
        ts = lst.get("t") or []
        ss = lst.get("s") or []
        es = lst.get("e") or []
        ns = lst.get("n") or []
        for i, btih in enumerate(ms):
            btih = str(btih or "").strip().lower()
            if len(btih) != 40 or not all(c in "0123456789abcdef" for c in btih):
                continue
            title = str(ts[i]).strip() if i < len(ts) else ""
            size = str(ss[i]).strip() if i < len(ss) else ""
            seeders = str(es[i]).strip() if i < len(es) else ""
            pub = str(ns[i]).strip() if i < len(ns) else ""
            magnet = f"magnet:?xt=urn:btih:{btih}&dn={quote(title)}"
            extra = []
            if size:
                extra.append(size)
            if seeders:
                extra.append(f"{seeders}做种")
            text = title + (f" [{' / '.join(extra)}]" if extra else "")
            hits.append(SiteHit(
                share_url=magnet,
                resource_title=_clean_title(title) or title[:200],
                text=text,
                pan_type="magnet",
                pan_label="磁力",
                pub_date=pub or None,
            ))
        return FilejinScraper._deduplicate_hits(hits)

    @staticmethod
    def _parse_resources_from_html(text: str) -> List[SiteHit]:
        """从 HTML/脚本内容中兜底提取磁力和常见网盘链接。"""
        content = html.unescape(text or "")
        hits: List[SiteHit] = []
        magnet_pattern = r'magnet:\?xt=urn:btih:[a-fA-F0-9]{40}(?:&[^"\s<>]*)?'
        for match in re.finditer(magnet_pattern, content, re.IGNORECASE):
            magnet = match.group(0)
            title_match = re.search(r'(?:[?&])dn=([^&]+)', magnet, re.IGNORECASE)
            title = unquote(title_match.group(1)) if title_match else ""
            hits.append(SiteHit(
                share_url=magnet,
                resource_title=_clean_title(title),
                text=title,
                pan_type="magnet",
                pan_label="磁力",
            ))

        pan_pattern = (
            r'https?://[^\s"\'<>]*(?:115\.com|anxia\.com|115cdn\.com|quark\.cn|'
            r'baidu\.com|aliyundrive\.com|alipan\.com|xunlei\.com|189\.cn|'
            r'21cn\.com|uc\.cn)[^\s"\'<>]*'
        )
        for match in re.finditer(pan_pattern, content, re.IGNORECASE):
            url = match.group(0).rstrip(".,;:)]}")
            nearby = content[match.end():match.end() + 160]
            code_match = re.search(r'(?:提取码|访问码|密码)\s*[：:]?\s*([A-Za-z0-9]{4,8})', nearby)
            hits.append(SiteHit(
                share_url=url,
                receive_code=code_match.group(1) if code_match else "",
                pan_type=_classify_pan(url),
            ))
        return FilejinScraper._deduplicate_hits(hits)

    @staticmethod
    def _deduplicate_hits(hits: List[SiteHit]) -> List[SiteHit]:
        seen = set()
        result = []
        for hit in hits:
            key = (hit.share_url or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(hit)
        return result

    def _make_client(self):
        """创建 httpx.Client（同步），带 Chrome UA + 代理 + cookie jar。
        
        关键：无论是否配置代理，都彻底禁用环境变量代理（trust_env=False + mounts）。
        解决 Windows/Docker 下 HTTP_PROXY 环境变量污染导致 403 的问题。
        
        app_auth 通过 cookies jar 注入（不用手动 Cookie 头），以便服务端 Set-Cookie
        下发的 browser_pow / browser_verified 与 app_auth 共存于同一 jar。
        """
        import httpx
        # 禁用所有协议的环境代理（彻底切断 Docker/Windows 系统代理污染）
        # httpx 0.28.x 没有 Mount 类，直接将 HTTPTransport 传给 mounts 参数
        kwargs = {
            "timeout": 20.0,
            "headers": {
                "User-Agent": _CHROME_UA,
                "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Referer": self.site_base + "/",
            },
            "follow_redirects": True,
            "cookies": {"app_auth": self.app_auth} if self.app_auth else None,
            # 关键修复：所有协议都禁用环境代理
            "mounts": {
                "https://": httpx.HTTPTransport(trust_env=False),
                "http://": httpx.HTTPTransport(trust_env=False),
            },
        }
        if self.proxy:
            # 如果用户配置了专用代理（如 http://host.docker.internal:10809），则使用该代理
            kwargs["proxy"] = self.proxy
            # mounts 已设置 trust_env=False，proxy 与 mounts 共存时，httpx 会优先使用 proxy，
            # 且仍不读取环境变量
        # 否则 proxy 为 None，mounts 确保不读取任何环境代理，真正直连
        return httpx.Client(**kwargs)


# ============================ 工具 ============================
def _clean_title(text: str) -> str:
    """清洗资源标题：去 emoji/装饰符，取可读片段。"""
    t = (text or "").strip()
    if not t:
        return ""
    # 去掉开头的旗帜/装饰 emoji 堆叠
    t = re.sub(r"^[\U0001F000-\U0001FAFF☀-➿◀▉▶]+\s*", "", t)
    t = re.sub(r"https?://\S+", "", t)
    return t.strip()[:200]
