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
import random
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

from app.log import logger


# 站点基址（punycode 域名，对应中文域）
SITE_BASE = "https://www.xn--wcv59z.com"
_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

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
                 count: int = 3) -> None:
        self.app_auth = (app_auth or "").strip()
        self.proxy = (proxy or "").strip() or None
        self.count = count  # 每次（每页）取多少部作品的网盘资源
        self._http = None            # 持久 httpx.Client（复用 PoW 会话）
        self._pow_solved = False
        self._cache_key = None       # (keyword, year) 缓存键
        self._cache_items = None     # search_suggest 作品列表缓存

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
                    time.sleep(random.uniform(0.4, 0.8))
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
            ok, msg, _ = self._search_suggest("测试")
            if not ok and "未登录" in msg:
                return False, "app_auth 已失效（站点返回未登录）"
            return True, "连通正常，登录态有效"
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
            if year_items:
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
            resp = self._get_client().get(SITE_BASE + "/", headers={"Accept": "text/html"})
            if "未登录" in resp.text:
                logger.warn("【TG115】观影 app_auth 已失效（返回未登录），请更新 app_auth")
        except Exception:
            pass

    def _solve_pow(self):
        """解 RSW 时间锁 PoW：GET /res/pow -> 算 y=x^(2^t)%N -> POST /res/pow。"""
        import json as _json
        # 先 GET / 触发 browser_pow cookie
        try:
            self._get_client().get(SITE_BASE + "/", headers={"Accept": "text/html"})
        except Exception:
            pass
        resp = self._get_client().get(SITE_BASE + "/res/pow", headers={"Accept": "application/json"})
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
            SITE_BASE + "/res/pow",
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
        url = SITE_BASE + "/res/search_suggest?q=" + quote(term)
        resp = self._get_client().get(url, headers={"Accept": "application/json"})
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}", []
        text = resp.text or ""
        if "浏览器安全验证" in text or "powSolve" in text:
            # cookie 失效，重解 PoW 再试一次
            self._pow_solved = False
            self._ensure_access()
            resp = self._get_client().get(url, headers={"Accept": "application/json"})
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
        url = f"{SITE_BASE}/res/downurl/{dir_}/{id_}"
        resp = self._get_client().get(url, headers={"Accept": "application/json"})
        if resp.status_code != 200:
            logger.warn(f"【TG115】观影 downurl {dir_}/{id_} 失败: HTTP {resp.status_code}")
            return []
        try:
            data = resp.json()
        except Exception as e:
            logger.warn(f"【TG115】观影 downurl 非 JSON: {e}")
            return []
        if data.get("code") not in (200, "200"):
            logger.warn(f"【TG115】观影 downurl 返回错误: {data}")
            return []
        hits: List[SiteHit] = []
        # 1. panlist: 网盘链接（115/夸克/百度/阿里/迅雷/天翼/UC...）
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
            # 提取码清洗：站点常填 "无提取码" / emoji 装饰
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
        # 2. downlist: 磁力链接（list.m=明文btih, list.t=标题, list.s=大小, list.e=做种, list.n=时间）
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
                continue  # 非法 btih
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
        return hits

    def _make_client(self):
        """创建 httpx.Client（同步），带 Chrome UA + 代理 + cookie jar。

        app_auth 通过 cookies jar 注入（不用手动 Cookie 头），以便服务端 Set-Cookie
        下发的 browser_pow / browser_verified 与 app_auth 共存于同一 jar。
        """
        import httpx
        kwargs = {
            "timeout": 20.0,
            "headers": {
                "User-Agent": _CHROME_UA,
                "Accept": "application/json,text/html,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": SITE_BASE + "/",
            },
            "follow_redirects": True,
            "cookies": {"app_auth": self.app_auth} if self.app_auth else None,
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy
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
