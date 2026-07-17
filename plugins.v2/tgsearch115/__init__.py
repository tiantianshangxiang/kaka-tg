# -*- coding: utf-8 -*-
"""MoviePilot 插件：拦截订阅 -> TG 频道搜索 115 -> 转存 -> 完成订阅（自定义 Vue 前端版 v2）。

================================================================================
 一、整体设计
================================================================================
1. 触发：监听 ``EventType.SubscribeAdded``（订阅新增）。该事件由
   ``SubscribeChain.add`` 发出，经 EventBus 的独立消费线程派发。本插件在处理器
   内再起一个守护线程执行实际工作，**绝不阻塞 MoviePilot 主流程**。

   说明：MoviePilot 的 EventBus 是「队列 + 独立消费线程」模型（见
   ``app/core/event.py``），事件处理器无法同步阻断事件发起方。因此"拦截并阻断
   原有搜索"采用的是「抢跑完成」策略——在 MP 默认的定时站点搜索跑起来之前，
   用 TG+115 把订阅完成掉（写历史 / 删订阅 / 发 SubscribeComplete），
   MP 的默认搜索自然无订阅可做；任何环节失败则静默 return，MP 默认搜索照常进行。
   系统中并不存在 ``EventType.SearchStart`` 之类可阻断的搜索事件，
   ``SubscribeAdded`` 是实现该目标的正确且唯一的钩子。

2. TG 搜索：用网页爬虫（httpx + BeautifulSoup）抓取 ``t.me/s/{channel}`` 公开频道，
   通过服务端搜索 ``?q=关键字`` 检索频道全部历史消息，提取其中的 115 分享链接
   （见 ``tg_scraper.py``）。免登录、无需 TG 账号，支持多频道与 MP 代理。

3. 规则匹配：每条命中构造为 ``TorrentInfo``，复用 MoviePilot 内置的
   ``SubscribeChain().filter_torrents`` 与 ``TorrentHelper.filter_torrent``，
   按用户在 MP 中配置的过滤规则二次校验。

4. 115 转存：命中后用 ``httpx`` + 用户 Cookie 直连 115 Web API（``share_snap``
   取 file_id -> ``share_receive`` 转存）到指定 115 目录（见 ``p115_transfer.py``）。
   注意：MoviePilot 核心的 ``app.modules.filemanager.storages.u115.U115Pan``
   是基于 OAuth 的存储模块，仅提供 list/upload/download/move，**不包含**
   分享链接转存（share_receive）接口。早期版本用 ``p115client``，但它依赖很重
   （冷启动 pip 安装慢、拖慢插件加载），故改为 ``httpx`` 直连同一组 webapi.115.com
   接口，零额外重依赖。

5. 完成订阅：转存成功后镜像 ``SubscribeChain.__finish_subscribe``，写历史、
   删订阅、发 ``SubscribeComplete`` 事件、推送通知。

6. 回退：任何环节失败都静默 ``return``，不删除/不修改订阅。

================================================================================
 二、与 v1 的区别（自定义 Vue 前端架构）
================================================================================
- 配置 UI 由自定义 Vue 前端接管：插件随包附带 ``frontend/dist/remoteEntry.js``
  （Module Federation，暴露 ``Config`` / ``Page`` 组件），MoviePilot 前端加载
  ``Config`` 组件渲染配置弹窗、``Page`` 组件渲染插件详情页。
- 后端因此把 ``get_form`` / ``get_page`` 返回空桩；配置的读写完全由
  ``get_api`` 暴露的 RESTful 接口驱动：
    GET  /api/v1/plugin/{plugin_id}/config/get   读取配置
    POST /api/v1/plugin/{plugin_id}/config/save  保存配置并即时生效
    GET  /api/v1/plugin/{plugin_id}/check_channel?index=N   检查单频道连通性
    GET  /api/v1/plugin/{plugin_id}/check_all               检查全部频道连通性
- 配置持久化改用 ``self.get_data("config")`` / ``self.save_data("config", ...)``
  （PluginData 表，自动 JSON 序列化），不再使用 VForm 的 update_config。
"""
# ============================ 依赖说明 ============================
# 本插件只用 beautifulsoup4 + httpx，均为懒导入（用到时才 import）。
# **不做运行时 pip 安装**：之前加载期 pip install 会触发 MP 的「主程序依赖恢复 +
# pip check 健康检查」，而 MP 自身存在 langchain 版本冲突（langchain-experimental
# vs langchain-community），导致健康检查失败、插件装不上/加载失败。去掉 pip 安装后
# MP 不再被触发该检查，插件正常加载。依赖由 MP 环境提供（httpx 核心必带；bs4 缺失
# 时 TG 频道搜索不可用，观影搜索/115转存仍正常，缺依赖会在日志告警）。

import json
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Body

from app.core.config import settings
from app.chain.subscribe import SubscribeChain, build_subscribe_meta
from app.core.context import MediaInfo, TorrentInfo
from app.core.event import Event, eventmanager
from app.db.subscribe_oper import SubscribeOper
from app.db.systemconfig_oper import SystemConfigOper
from app.helper.torrent import TorrentHelper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType, SystemConfigKey

from .p115_transfer import P115Transfer
from .tg_scraper import TgChannelScraper
from .site_scraper import FilejinScraper
from .juying_scraper import JuyingApi


# get_data / save_data 存储本插件配置使用的 key
CONFIG_KEY = "config"


# ============================ 115 扫码登录（直连稳定 115 二维码接口） ============================
# 说明：p115client 的扫码方法散落在 p115qrcode 子包（非 pip 安装内容）与 client 类方法
# 之间，随版本变化较大、 import 路径不稳定。为「最稳妥、不易报错」，这里直连 115 官方
# 稳定的二维码接口（与 p115client.p115qrcode 走的是同一组 URL），仅用标准库 urllib，
# 无额外依赖，且不随 p115client 版本波动。流程：
#   1) POST /api/1.0/web/1.0/token/            -> {uid, time, sign}
#   2) GET  /api/1.0/web/1.0/qrcode?uid=<uid>  -> 二维码图片
#   3) GET  /get/status/?uid=&time=&sign=      -> {status, msg}  (0等待 1已扫描 2已确认 -1过期)
#   4) POST /app/1.0/<app>/1.0/login/qrcode/   -> 登录成功，返回含 UID/CID/SEID 的 Cookie
import re as _re
import urllib.parse as _urlparse
import urllib.request as _urlreq

_QR_BASE = "http://qrcodeapi.115.com"
# 不同 app 的 User-Agent（与 p115client.p115qrcode.qrcode_result 一致）
_QR_UA_MAP = {
    "ios": "UPhone/1.0.0",
    "qios": "OfficePhone/1.0.0",
    "ipad": "UPad/1.0.0",
    "qipad": "OfficePad/1.0.0",
}


def _qr_normalize_app(app: str) -> str:
    """归一化 app 名（与 p115qrcode 一致）：desktop->web，ios/qios/ipad/qipad->ios。"""
    a = (app or "web").strip().lower()
    if a == "desktop":
        return "web"
    if a in ("ios", "qios", "ipad", "qipad"):
        return "ios"
    return a


def _qr_request(method: str, path: str, params: dict = None, data: dict = None,
                headers: dict = None, timeout: int = 20):
    url = _QR_BASE + path
    body = None
    hdrs = {"User-Agent": "Mozilla/5.0 (MoviePilot-TgSearch115)"}
    if headers:
        hdrs.update(headers)
    if params:
        url = f"{url}?{_urlparse.urlencode(params)}"
    if data is not None:
        body = _urlparse.urlencode(data).encode("utf-8")
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    req = _urlreq.Request(url, data=body, headers=hdrs, method=method)
    with _urlreq.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
        # UID/CID/SEID 可能分别落在多个 Set-Cookie 头里，必须用 get_all 取全部，
        # 否则 headers.get 只返回第一个，会漏掉 CID/SEID 导致 Cookie 提取失败。
        set_cookies = resp.headers.get_all("Set-Cookie") or []
        set_cookie = "; ".join(set_cookies)
        return raw, set_cookie


def _qr_token() -> dict:
    """获取二维码 token：GET /api/1.0/web/1.0/token/ -> {state, data:{uid, time, sign, qrcode}}。"""
    raw, _ = _qr_request("GET", "/api/1.0/web/1.0/token/")
    return json.loads(raw)


def _qr_image_data_url(uid: str) -> str:
    """拉取二维码图片并转 data URL，避免前端 HTTPS 页面引用 HTTP 图片被混合内容拦截。"""
    import base64
    url = f"{_QR_BASE}/api/1.0/web/1.0/qrcode?uid={uid}"
    req = _urlreq.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with _urlreq.urlopen(req, timeout=15) as resp:
        return "data:image/png;base64," + base64.b64encode(resp.read()).decode("ascii")


def _qr_status(uid: str, t: str, sign: str) -> dict:
    """轮询扫码状态（仅用于展示「已扫描/过期」）。115 该接口为长轮询，这里用 10s
    超时；登录成功的判定靠 ``_qr_result`` 直接取 Cookie，不依赖此接口的 status 字段。"""
    raw, _ = _qr_request("GET", "/get/status/",
                         params={"uid": uid, "time": t, "sign": sign}, timeout=10)
    return json.loads(raw)


def _pick_uid_cid_seid(text: str) -> str:
    """从任意文本（响应体 / Set-Cookie 头）提取 UID、CID、SEID，拼成标准 Cookie 串。"""
    text = text or ""
    found = {}
    for k in ("UID", "CID", "SEID", "KID"):
        m = _re.search(rf"\b{k}\s*=\s*([^;,\"\s]+)", text)
        if m:
            found[k] = m.group(1).strip()
    if {"UID", "CID", "SEID"} <= set(found):
        return "; ".join(f"{k}={found[k]}" for k in ("UID", "CID", "SEID", "KID") if k in found)
    return ""


def _qr_result(uid: str, app: str):
    """扫码确认后获取 Cookie：POST /app/1.0/{app}/1.0/login/qrcode/，返回 (raw_body, set_cookie)。"""
    a = _qr_normalize_app(app)
    ua = _QR_UA_MAP.get((app or "").strip().lower(), "Mozilla/5.0 (MoviePilot-TgSearch115)")
    return _qr_request(
        "POST", f"/app/1.0/{a}/1.0/login/qrcode/",
        data={"account": uid}, headers={"User-Agent": ua}, timeout=15,
    )


class TgSearch115(_PluginBase):
    """订阅新增 -> TG 频道搜索 115 -> 转存 -> 完成订阅；失败平滑回退。"""

    # ============================ 插件元信息 ============================
    plugin_name = "拦截mp订阅"
    plugin_desc = (
        "订阅新增时优先到指定 Telegram 频道搜索 115 资源，命中并转存成功后自动完成订阅；"
        "未命中或转存失败则平滑回退到 MoviePilot 默认站点搜索。"
    )
    plugin_version = "4.2.12"
    plugin_author = "MoviePilot User"
    plugin_icon = "T"
    plugin_config_prefix = "plugin.tgsearch115"
    author_url = ""
    plugin_url = ""

    # ============================ 运行态 ============================
    _enabled = False
    _lock = threading.Lock()
    _running_ids: set = set()
    _scraper: Optional[TgChannelScraper] = None
    _site_scraper: Optional[FilejinScraper] = None
    _juying_api: Optional[JuyingApi] = None
    _mp_proxy: str = ""
    _transfer: Optional[P115Transfer] = None

    # 配置项（运行态缓存）
    _tg_channels: List[Dict[str, Any]] = []
    _p115_cookie = ""
    _p115_app = ""
    _p115_target = "/"
    _use_rule_groups = True
    _delay_seconds = 3
    _notify_success = True
    _notify_fail = False
    _auto_finish = True  # True=插件直接标记完成(不用MP整理); False=只阻断搜索让MP自己整理
    _site_enabled = False
    _site_app_auth = ""
    # ============================ 生命周期 ============================
    def init_plugin(self, config: dict = None):
        """生效配置。

        - 自定义前端 ``POST /config`` 会显式传入 config 并即时调用本方法；
        - MoviePilot 启动 / 重载插件时，框架调用 ``init_plugin(get_config())``。
          由于本插件用 ``get_data`` 持久化，``get_config()`` 为空，故 config 为
          None 时回退到 ``get_data(CONFIG_KEY)`` 读取已保存配置。
        """
        if config is None:
            config = self.get_data(CONFIG_KEY) or {}
        if not isinstance(config, dict):
            config = {}

        self._apply_config(config)

        # 持久化（保证 get_data 可读、字段干净）
        try:
            self.save_data(CONFIG_KEY, config)
        except Exception as e:
            logger.warn(f"【TG115】保存配置失败: {e}")

        if self._enabled:
            logger.info("【TG115】插件已启用")
            self._check_deps()

    def _apply_config(self, config: dict):
        """把配置字典解析到运行态字段，并重建搜索器 / 转存器。"""
        self._enabled = self._to_bool(config.get("enabled"), False)
        # 如果用户没配 TG 代理，自动用 MoviePilot 的代理（settings.PROXY）
        self._p115_cookie = config.get("p115_cookie") or ""
        self._p115_app = config.get("p115_app") or ""
        self._p115_target = config.get("p115_target") or "/"
        self._use_rule_groups = self._to_bool(config.get("use_rule_groups"), True)
        self._delay_seconds = self._safe_int(config.get("delay_seconds"), 3)
        self._notify_success = self._to_bool(config.get("notify_success"), True)
        self._notify_fail = self._to_bool(config.get("notify_fail"), False)
        self._auto_finish = self._to_bool(config.get("auto_finish"), True)
        # TG 频道列表：自定义前端直接以数组/JSON 字符串形式提交 tg_channels
        self._tg_channels = self._parse_channels(config.get("tg_channels"))

        # 爬虫只接收「已启用」的频道；代理自动用 MP 的 settings.PROXY
        enabled_channels = [ch for ch in self._tg_channels if ch.get("enabled", True)]
        _proxy = ""
        try:
            _mp_proxy = settings.PROXY
            if _mp_proxy:
                _proxy = _mp_proxy.get("https") or _mp_proxy.get("http") or ""
        except Exception:
            pass
        self._scraper = TgChannelScraper(channels=enabled_channels, proxy=_proxy)
        self._mp_proxy = _proxy  # 供 /check_site 临时测试用
        # 观影爬虫（PoW + 搜索 + 全网盘提取；仅 115 参与自动转存）
        self._site_enabled = self._to_bool(config.get("site_enabled"), False)
        self._site_app_auth = config.get("site_app_auth") or ""
        # 观影专用代理：优先用配置的，否则默认不走代理（与 TG 区分开）。
        # 因为观影站对国外代理节点/机房IP往往会封锁 downurl 导致 403，直连反而更稳。
        # 如果填了 'proxy' 则强制用全局代理，留空或填 direct 都是直连。
        sp = (config.get("site_proxy") or "").strip()
        self._site_proxy = _proxy if sp == 'proxy' else (None if not sp or sp == 'direct' else sp)
        self._site_domain = (config.get("site_domain") or "").strip()  # 观影域名（换域名时改这里）
        if self._site_enabled and self._site_app_auth:
            self._site_scraper = FilejinScraper(
                app_auth=self._site_app_auth, proxy=self._site_proxy, site_base=self._site_domain,
            )
        else:
            self._site_scraper = None
        # 聚影开发者 API（官方接口，稳定无 IP 封锁；需 AppID+API Key+域名）
        self._juying_enabled = self._to_bool(config.get("juying_enabled"), False)
        self._juying_app_id = config.get("juying_app_id") or ""
        self._juying_api_key = config.get("juying_api_key") or ""
        self._juying_domain = (config.get("juying_domain") or "").strip()
        # 聚影也加专用代理机制，逻辑同观影
        jp = (config.get("juying_proxy") or "").strip()
        self._juying_proxy = None if jp == 'direct' else (jp or None)
        if self._juying_enabled and self._juying_app_id and self._juying_api_key and self._juying_domain:
            self._juying_api = JuyingApi(
                app_id=self._juying_app_id, api_key=self._juying_api_key,
                domain=self._juying_domain, proxy=self._juying_proxy,
            )
        else:
            self._juying_api = None
        self._transfer = P115Transfer(
            cookie=self._p115_cookie, default_target_path=self._p115_target
        )

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """注册插件 RESTful API，供自定义 Vue 前端调用。

        MoviePilot 会把每个端点挂载到 ``/api/v1/plugin/{plugin_id}{path}``，
        并按需校验 apikey。端点为「绑定方法」，形参会从 query / body 中按名注入。
        """
        # 路径与官方插件仓 agentresourceofficer 保持一致：get/save 拆成独立路径，
        # 避免 MoviePilot 插件路由对「同路径不同方法」的兼容性差异。
        # 鉴权：MP 自定义前端 props.api 默认携带 Authorization: Bearer <用户令牌>，
        # 故端点统一用 "bear"(verify_token) 鉴权；若用默认 apikey 鉴权，前端调用会 401。
        apis = [
            {
                "path": "/config/get",
                "endpoint": self.__get_config_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取插件配置",
                "description": "返回当前插件配置，供自定义前端 Config.vue 初始化读取",
            },
            {
                "path": "/config/save",
                "endpoint": self.__save_config_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "保存插件配置",
                "description": "保存配置并即时生效（写入 get_data 并重新 init_plugin）",
            },
            {
                "path": "/check_channel",
                "endpoint": self.__check_channel_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "检查指定 TG 频道连通性",
            },
            {
                "path": "/check_all",
                "endpoint": self.__check_all_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "检查所有 TG 频道连通性",
            },
            {
                "path": "/qrcode/get",
                "endpoint": self.__qrcode_get_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取 115 登录二维码",
                "description": "GET /qrcode/get?app=web|tv|ipad|android|ios，返回二维码图片(data URL)及会话凭证",
            },
            {
                "path": "/qrcode/status",
                "endpoint": self.__qrcode_status_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "轮询 115 扫码状态",
                "description": "GET /qrcode/status?uid=&time=&sign=&app=，扫码成功时自动提取并保存 Cookie",
            },
            {
                "path": "/transfer",
                "endpoint": self.__transfer_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "手动转存 115 分享链接",
                "description": "GET /transfer?share_url=&target=，target 留空用默认目录",
            },
            {
                "path": "/search",
                "endpoint": self.__search_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "手动搜索 TG 频道 115 资源",
                "description": "GET /search?keyword=",
            },
            {
                "path": "/dir_info",
                "endpoint": self.__dir_info_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "根据 cid 查询 115 目录名称",
                "description": "GET /dir_info?cid=",
            },
            {
                "path": "/dirs",
                "endpoint": self.__dirs_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "列出 115 子目录（目录浏览）",
                "description": "GET /dirs?cid=0",
            },
            {
                "path": "/verify_cookie",
                "endpoint": self.__verify_cookie_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "验证 115 Cookie 是否有效",
                "description": "调 fs_files(0) 实测 Cookie 有效性",
            },
            {
                "path": "/check_site",
                "endpoint": self.__check_site_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "检查观影连通性与登录态",
                "description": "解 PoW + 试搜，验证 app_auth 是否有效",
            },
            {
                "path": "/check_juying",
                "endpoint": self.__check_juying_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "检查聚影 API 鉴权",
                "description": "用 AppID+API Key 试搜，验证聚影开发者接口是否可用",
            },
        ]
        return apis

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """配置页由自定义 Vue 前端（Config.vue）接管，这里返回空桩。

        若尚未构建前端产物（frontend/dist/remoteEntry.js），可临时改为返回
        Vuetify/VForm schema 作为兜底；当前面向自定义前端架构，故返回空。
        """
        return [], {}

    def get_page(self) -> List[dict]:
        """详情页由自定义 Vue 前端（Page.vue）接管，这里返回空桩。"""
        return []

    @staticmethod
    def get_render_mode() -> Tuple[str, Optional[str]]:
        """声明使用自定义 Vue 前端渲染配置页/详情页。

        MoviePilot 通过 ``plugin.get_render_mode()`` 判断插件是否使用 Vue 自定义前端：
        返回 ``("vue", dist_path)`` 时，MP 会把本插件登记进 ``plugin/remotes``，
        前端再经 Module Federation 加载 ``{dist_path}/remoteEntry.js`` 暴露的
        Config / Page 组件；否则回退到 ``get_form()``（本插件返回空，故表现为空白）。

        ``dist_path`` 为 remoteEntry.js 所在目录（相对插件目录）。本插件构建产物在
        ``frontend/dist/assets/remoteEntry.js``，故返回 ``frontend/dist/assets``。
        """
        return "vue", "frontend/dist/assets"

    def stop_service(self):
        """停止插件：清理运行态。守护线程为 daemon，随主进程退出。"""
        with self._lock:
            self._running_ids.clear()

    # ============================ 事件入口 ============================
    @eventmanager.register(EventType.SubscribeAdded)
    def on_subscribe_added(self, event: Event):
        """订阅新增事件：异步触发 TG+115 优先处理。

        EventBus 在独立消费线程派发事件，本方法只做最轻量校验后另起守护线程，
        避免占用事件消费线程、影响其它插件事件的处理。
        """
        if not self._enabled:
            return
        data = getattr(event, "event_data", None) or {}
        subscribe_id = data.get("subscribe_id")
        if not subscribe_id:
            return
        threading.Thread(
            target=self._handle_subscribe,
            args=(int(subscribe_id),),
            name="tg115-subscribe",
            daemon=True,
        ).start()

    # ============================ 核心流程 ============================
    def _handle_subscribe(self, subscribe_id: int):
        """单订阅的 TG 搜索 -> 匹配 -> 转存 -> 完成流程；任何失败均平滑回退。"""
        try:
            with self._lock:
                if subscribe_id in self._running_ids:
                    return
                self._running_ids.add(subscribe_id)

            # 抢跑延迟：给 TG+115 一个先于 MP 默认搜索完成的窗口
            if self._delay_seconds and self._delay_seconds > 0:
                time.sleep(min(self._delay_seconds, 300))

            subscribe = SubscribeOper().get(subscribe_id)
            if not subscribe:
                return

            try:
                meta = build_subscribe_meta(subscribe)
            except Exception as e:
                logger.warn(f"【TG115】构造订阅 meta 失败，回退: {e}")
                return
            mediainfo = self._recognize(subscribe, meta)
            if not mediainfo:
                logger.warn(f"【TG115】订阅 {subscribe.name} 未识别到媒体信息，回退到默认搜索")
                return

            keyword = self._build_keyword(subscribe)
            logger.info(f"【TG115】订阅 [{subscribe.name}] 开始搜索，关键字: {keyword}")
            # 双源搜索：TG 频道（全 115）+ 观影（全网盘，115 占少数）
            hits = []
            if self._scraper:
                hits.extend(self._scraper.search(keyword))
            if self._site_scraper:
                site_hits, _ = self._site_scraper.search(keyword, year=subscribe.year)
                hits.extend(site_hits)
            if not hits:
                logger.info(f"【TG115】订阅 [{subscribe.name}] 未找到资源，回退到默认搜索")
                self._send_fail_notify(subscribe, "TG 频道与观影均未找到资源")
                return

            torrents = self._build_torrents(hits)
            matched = self._filter_resources(subscribe, mediainfo, torrents)
            if not matched:
                logger.info(f"【TG115】订阅 [{subscribe.name}] 资源均不符合 MP 过滤规则，回退到默认搜索")
                self._send_fail_notify(subscribe, "资源不符合过滤规则")
                return

            # 只自动转存 115 资源（非 115 如夸克/百度/阿里不自动转存，仅展示）
            matched_115 = [t for t in matched
                           if P115Transfer._is_115_share_url(t.page_url or "")]
            if not matched_115:
                logger.info(
                    f"【TG115】订阅 [{subscribe.name}] 命中 {len(matched)} 条资源但无 115 可转存"
                    f"（仅夸克/百度/阿里等），回退到默认搜索"
                )
                self._send_fail_notify(subscribe, f"命中 {len(matched)} 条但无 115 可转存")
                return
            best = matched_115[0]
            share_url = best.page_url or ""
            logger.info(f"【TG115】订阅 [{subscribe.name}] 命中: {best.title} -> {share_url}")

            ok, msg, _data = (
                self._transfer.transfer(share_url, self._p115_target)
                if self._transfer
                else (False, "转存模块未初始化", {})
            )
            if not ok:
                logger.warn(f"【TG115】订阅 [{subscribe.name}] 115 转存失败: {msg}，回退到默认搜索")
                self._send_fail_notify(subscribe, f"115 转存失败: {msg}")
                return

            self._finish_subscribe(subscribe, meta, mediainfo, best, msg)
        except Exception as e:
            logger.error(f"【TG115】处理订阅 {subscribe_id} 异常，回退到默认搜索: {e}")
        finally:
            with self._lock:
                self._running_ids.discard(subscribe_id)

    # ============================ 辅助方法 ============================
    def _recognize(self, subscribe, meta) -> Optional[MediaInfo]:
        try:
            mediainfo = SubscribeChain().recognize_media(
                meta=meta, mtype=meta.type,
                tmdbid=subscribe.tmdbid, doubanid=subscribe.doubanid,
                episode_group=subscribe.episode_group, cache=False,
            )
            if mediainfo:
                return mediainfo
        except Exception as e:
            logger.warn(f"【TG115】recognize_media 异常: {e}")
        try:
            return MediaInfo(
                type=subscribe.type, title=subscribe.name, year=subscribe.year,
                tmdb_id=subscribe.tmdbid, douban_id=subscribe.doubanid,
            )
        except Exception:
            return None

    @staticmethod
    def _build_keyword(subscribe) -> str:
        """构建搜索关键字：只用片名（不含年份）。

        v4.0：TG 服务端 ``?q=`` 搜索频道全部历史。TG 消息里大多不写年份，
        带年份会漏掉大量命中，故搜索词只取片名；年份 / 分辨率等精细过滤
        交给 MoviePilot 的规则引擎 ``_filter_resources`` 处理。
        """
        return str(subscribe.name or "").strip()

    @staticmethod
    def _build_torrents(hits) -> List[TorrentInfo]:
        torrents: List[TorrentInfo] = []
        for h in hits:
            url = h.share_url or ""
            rc = getattr(h, "receive_code", "") or ""
            # 115 链接：若提取码未附在 URL 上，补上（share_receive 需要 receive_code）
            if url and P115Transfer._is_115_share_url(url) and rc \
                    and "password=" not in url and "receive_code=" not in url and "pwd=" not in url:
                url = url + ("&" if "?" in url else "?") + f"password={rc}"
            torrents.append(TorrentInfo(
                title=h.resource_title or "未命名资源",
                description=h.text,
                page_url=url,
                site_name=getattr(h, "channel_name", None) or "TG频道",
                pubdate=h.pub_date,
                size=0.0, seeders=0, peers=0,
            ))
        return torrents

    def _filter_resources(self, subscribe, mediainfo, torrents: List[TorrentInfo]) -> List[TorrentInfo]:
        """复用 MP 内置过滤规则：先规则组，再 include/exclude/清晰度等参数。"""
        if not torrents:
            return []
        if self._use_rule_groups:
            rule_groups = self._get_rule_groups(subscribe)
            if rule_groups:
                try:
                    torrents = SubscribeChain().filter_torrents(
                        rule_groups=rule_groups, torrent_list=torrents, mediainfo=mediainfo,
                    ) or []
                except Exception as e:
                    logger.warn(f"【TG115】filter_torrents 异常，跳过规则组过滤: {e}")
        filter_params = self._get_filter_params(subscribe)
        if filter_params:
            torrents = [t for t in torrents if TorrentHelper.filter_torrent(t, filter_params)]
        return torrents

    @staticmethod
    def _get_rule_groups(subscribe) -> List[str]:
        if getattr(subscribe, "best_version", None):
            groups = subscribe.filter_groups or SystemConfigOper().get(
                SystemConfigKey.BestVersionFilterRuleGroups) or []
        else:
            groups = subscribe.filter_groups or SystemConfigOper().get(
                SystemConfigKey.SubscribeFilterRuleGroups) or []
        return list(groups or [])

    @staticmethod
    def _get_filter_params(subscribe) -> Dict[str, str]:
        return {k: v for k, v in {
            "include": subscribe.include, "exclude": subscribe.exclude,
            "quality": subscribe.quality, "resolution": subscribe.resolution,
            "effect": subscribe.effect,
        }.items() if v}

    def _finish_subscribe(self, subscribe, meta, mediainfo, torrent: TorrentInfo, transfer_msg: str):
        """转存成功后处理订阅，两种模式由 ``auto_finish`` 开关控制：

        ``auto_finish=True``（默认，不依赖 MP 整理 115）：
          - 电影：写历史 -> 删订阅 -> 发 SubscribeComplete -> 通知
          - 剧集：设 lack_episode=0 + state=P -> 发 SubscribeComplete -> 通知
          - 适合：不用 MP 整理 115 资源的用户，插件直接标记完成。

        ``auto_finish=False``（让 MP 整理 115 后自己完成）：
          - 电影/剧集统一：只设 state=P（+ 剧集 lack_episode=0），不删订阅、不写历史
          - MP 文件监控检测 115 目录新文件 -> 整理（刮削+入库）-> 写历史 -> 删订阅
          - 适合：用 MP 整理 115 资源的用户，MP 有完整整理历史。
        """
        try:
            oper = SubscribeOper()
            is_tv = (subscribe.type == "TV" or
                     getattr(mediainfo, "type", None) == "电视剧" or
                     getattr(meta, "type", None) == "TV")

            raw_text = torrent.description or torrent.title or ""
            episode_info = self._parse_episode_info(raw_text) if is_tv else ""
            season_str = f"第 {subscribe.season or 1} 季" if subscribe.season else "当季"

            if self._auto_finish:
                # ===== 模式一：插件直接标记完成 =====
                if not is_tv:
                    # 电影：写历史 + 删订阅
                    oper.add_history(**subscribe.to_dict())
                    oper.delete(subscribe.id)
                    logger.info(f"【TG115】电影订阅 [{subscribe.name}] 已通过 TG+115 完成并标记完结")
                else:
                    # 剧集：设 lack_episode=0 + state=P（不删订阅）
                    try:
                        oper.update(subscribe.id, {
                            "lack_episode": 0,
                            "state": "P",
                        })
                        logger.info(f"【TG115】剧集订阅 [{subscribe.name}] {season_str} 已更新"
                                    f"（lack_episode=0, state=P）")
                    except Exception as e:
                        logger.warn(f"【TG115】更新剧集订阅失败（不影响转存）: {e}")
            else:
                # ===== 模式二：只阻断搜索，让 MP 整理后自己完成 =====
                update_payload = {"state": "P"}
                if is_tv:
                    update_payload["lack_episode"] = 0
                try:
                    oper.update(subscribe.id, update_payload)
                    logger.info(
                        f"【TG115】订阅 [{subscribe.name}] 已设 state=P 阻断搜索"
                        f"{'，lack_episode=0（剧集本季已齐）' if is_tv else '（电影）'}"
                        f"，等待 MP 整理 115 资源后自动标记完成"
                    )
                except Exception as e:
                    logger.warn(f"【TG115】更新订阅状态失败（不影响转存结果）: {e}")

            # 发送 SubscribeComplete 事件
            eventmanager.send_event(EventType.SubscribeComplete, {
                "subscribe_id": subscribe.id,
                "subscribe_info": subscribe.to_dict(),
                "mediainfo": mediainfo.to_dict() if hasattr(mediainfo, "to_dict") else {},
            })

            # 通知用户
            if self._notify_success:
                try:
                    if is_tv:
                        self.post_message(
                            mtype=NotificationType.Subscribe,
                            title=f"\U0001F4FA 剧集订阅更新：{subscribe.name}",
                            text=f"TG115 插件已转存《{subscribe.name}》{season_str}的资源"
                                 f"（{episode_info}）。\n"
                                 + (f"资源: {torrent.title}\n{transfer_msg}" if self._auto_finish
                                    else f"已阻断 MP 搜索，等待系统整理 115 资源并刮削入库。\n"
                                         f"资源: {torrent.title}\n{transfer_msg}"),
                        )
                    else:
                        self.post_message(
                            mtype=NotificationType.Subscribe,
                            title=f"\U0001F3AC 电影订阅完成：{subscribe.name}",
                            text=f"TG115 插件已成功将《{subscribe.name}》转存至 115 网盘。\n"
                                 + (f"资源: {torrent.title}\n{transfer_msg}" if self._auto_finish
                                    else f"已阻断 MP 搜索，等待系统整理 115 资源并刮削入库。\n"
                                         f"资源: {torrent.title}\n{transfer_msg}"),
                        )
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"【TG115】更新订阅状态异常（不影响 MP 默认流程）: {e}")

    @staticmethod
    def _parse_episode_info(text: str) -> str:
        """从 TG 消息文本中提取剧集集数信息。

        高兼容性正则，支持以下格式：
          - "EP01-08" / "E01-08" / "EP01~08" -> "EP01-08"
          - "更新至05集" / "更新至 5 集" -> "更新至05集"
          - "全12集" / "全 12 集" -> "全12集（完整）"
          - "第01-12集" / "第1-12集" -> "第01-12集"
          - "S01E01-E12" / "S01E01-12" -> "S01E01-E12"
          - "1-12集" / "01-12 集" -> "EP01-12"
          - 无匹配 -> "本季合集"
        """
        if not text:
            return "本季合集"

        # S01E01-E12 / S01E01-12
        m = _re.search(r'[Ss]\d{1,2}[Ee](\d{1,3})\s*[-~]\s*[Ee]?(\d{1,3})', text)
        if m:
            return f"EP{int(m.group(1)):02d}-{int(m.group(2)):02d}"

        # EP01-08 / E01-08 / EP01~08
        m = _re.search(r'[Ee][Pp]?(\d{1,3})\s*[-~]\s*(\d{1,3})', text)
        if m:
            return f"EP{int(m.group(1)):02d}-{int(m.group(2)):02d}"

        # 更新至05集 / 更新至 5 集
        m = _re.search(r'更新至\s*(\d{1,3})\s*集', text)
        if m:
            return f"更新至{int(m.group(1))}集"

        # 全12集 / 全 12 集
        m = _re.search(r'全\s*(\d{1,3})\s*集', text)
        if m:
            return f"全{int(m.group(1))}集（完整）"

        # 第01-12集 / 第1-12集
        m = _re.search(r'第\s*(\d{1,3})\s*[-~]\s*(\d{1,3})\s*集', text)
        if m:
            return f"第{int(m.group(1)):02d}-{int(m.group(2)):02d}集"

        # 1-12集 / 01-12 集
        m = _re.search(r'(?<![\d])(\d{1,3})\s*[-~]\s*(\d{1,3})\s*集', text)
        if m:
            return f"EP{int(m.group(1)):02d}-{int(m.group(2)):02d}"

        # 完结 / 全集
        if _re.search(r'完结|全集|全季', text):
            return "全集（完结）"

        return "本季合集"

    @staticmethod
    def _parse_resource_meta(text: str) -> dict:
        """从资源标题解析展示元数据，供详情页卡片展示与排序。

        返回:
          - display_name: "片名 (年份)"（无年份则只片名）
          - meta: "完结 - S01E177  4K  WEB-DL" 风格的元信息行
          - is_complete: 是否完结（排序用）
          - episode_num: 最大集数（排序用，0 表示无集数信息）
        """
        t = (text or "").strip()
        if not t:
            return {"display_name": "", "meta": "", "is_complete": False, "episode_num": 0}

        # ---- 年份 ----
        ym = _re.search(r'[(（](\d{4})[)）]', t)
        year = ym.group(1) if ym else ""

        # ---- 名称：优先标签取值(TG消息)，否则扫描行找像片名的 ----
        qual = (r'4K|2160P|1080[PI]?|720P|480P|UHD|蓝光|原盘|REMUX|WEB-?DL|WEBRip|WEB-?Rip'
                r'|Blu-?Ray|BluRay|BD-?Rip|BR-?Rip|HDTV|PDTV|SATRip|DSR|DVD-?Rip|DVDScr'
                r'|HDCAM|\bCAM\b|HDTC|\bTC\b|HDTS|\bTS\b|H\.?26[45]|AVC|HEVC|x26[45]'
                r'|Dolby\s?Vision|DoVi|杜比|HDR10?\+?|国语|粤语|英语|日语|中字|简繁|特效|字幕'
                r'|完结|更新至|全集|全季|类型|无广告|正式版|抢先版|枪版|内封|外挂|双音')
        ep_pat = r'[Ss]\d{1,2}[Ee]\d{1,3}|[Ee][Pp]?\s?\d{1,3}\b|全\s*\d{1,3}\s*集|更新至\s*\d|第\s*\d{1,3}(?:[-~]\d{1,3})?\s*集'
        name = ""
        # 1. "名称：/资源名称：/片名：/剧名：value" 标签取值（TG 消息常见格式）
        for _lm in _re.finditer(r'(?:资源名称|片名|剧名|名称)\s*[:：]\s*([^\n【】|]{1,60})', t):
            nv = _re.split(rf'(?:{qual})|(?:{ep_pat})', _lm.group(1), maxsplit=1)[0]
            nv = _re.sub(r'\s*[(（]\d{4}[)）]', '', nv).strip(' -–-·•|:：【】')
            if nv:
                name = nv
                break
        # 2. 启发式：扫描行，跳过头部词/纯符号/标签行；优先带标题特征(年份/集数/清晰度/【】)的行
        if not name:
            _headers = ('观影', '影视', '资源', '分享', '频道', '剧迷', '推荐', '福利',
                        '网盘', '影库', '片库', '分享群', '合集', '整理')
            _cands = []
            for _line in t.splitlines():
                ln = _re.sub(r'https?://\S+', '', _line).strip()
                if not ln or _re.fullmatch(r'[\W\s_]+', ln):
                    continue  # 空 / 纯符号(emoji 头部)
                if _re.match(r'^(?:集数|清晰度|大小|链接|提取码|状态|季数|年份|类型|格式|来源|分辨率|编码|备注)\s*[:：]', ln):
                    continue  # 其它字段标签行
                head = _re.sub(r'^[\s\W_]+', '', ln)
                _mm = _re.search(rf'(?:{qual})|【|(?:{ep_pat})', head)
                name_raw = head[:_mm.start()] if _mm else head
                name_raw = _re.sub(r'[━◀▶▉▔▂▃▅▆▇【】\[\]]', '', name_raw).strip(' -–-·•|:：')
                name_raw = _re.sub(r'\s*[(（]\d{4}[)）]', '', name_raw).strip(' -–-·•|:：')
                if not name_raw or not (_re.search(r'[一-鿿぀-ヿ]', name_raw) or _re.search(r'[A-Za-z]{3,}', name_raw)):
                    continue
                # 跳过纯头部词（如"观影""影视分享"等短头部）
                if len(name_raw) <= 8 and any(name_raw.startswith(w) for w in _headers):
                    continue
                _feat = bool(_re.search(r'[(（]\d{4}[)）]|[Ss]\d{1,2}[Ee]\d|全\s*\d{1,3}\s*集|更新至|【', ln))
                _cands.append((name_raw, _feat))
                if _feat:
                    name = name_raw
                    break
            if not name and _cands:
                name = _cands[0][0]
        # 3. 兜底：第一个【】内容
        if not name:
            bm = _re.search(r'【([^】]{1,60})】', t)
            if bm:
                name = _re.sub(r'\s*[(（]\d{4}[)）]', '', bm.group(1)).strip(' -–-·•|:：')

        # ---- 状态 + 集数（status 只标完结；ongoing 由 episode 表达，避免重复）----
        is_complete = bool(_re.search(r'完结|全集|全季', t))
        episode = ""
        episode_num = 0
        m = _re.search(r'[Ss]\d{1,2}[Ee](\d{1,3})\s*(?:[-~]\s*[Ee]?(\d{1,3}))?', t)
        if m:
            a = int(m.group(1)); b = int(m.group(2)) if m.group(2) else a
            episode = _re.sub(r'\s+', '', m.group(0))
            episode_num = max(a, b)
        elif (m := _re.search(r'全\s*(\d{1,3})\s*集', t)):
            episode = _re.sub(r'\s+', '', m.group(0)); episode_num = int(m.group(1)); is_complete = True
        elif (m := _re.search(r'更新至\s*(\d{1,3})\s*集', t)):
            episode = _re.sub(r'\s+', '', m.group(0)); episode_num = int(m.group(1))
        elif (m := _re.search(r'(?:EP|E|第)(\d{1,3})\s*[-~]\s*(\d{1,3})', t, _re.IGNORECASE)):
            a = int(m.group(1)); b = int(m.group(2))
            episode = f"EP{a:02d}-{b:02d}"; episode_num = max(a, b)
        status = "完结" if is_complete else ""

        # ---- 清晰度（分辨率）----
        qm = _re.search(r'(4K|2160P|1080[PI]?|720P|480P|UHD)', t, _re.IGNORECASE)
        quality = qm.group(1).upper() if qm else ""
        if quality == "UHD":
            quality = "4K"

        # ---- 来源/发布类型（电影常见格式标识，全量匹配，去重）----
        source_tokens = []
        for pat, label in [
            (r'WEB-?DL', 'WEB-DL'), (r'WEBRip|WEB-?Rip', 'WEBRip'),
            (r'Blu-?Ray|BluRay|蓝光', 'BluRay'),
            (r'BD-?Rip', 'BDRip'), (r'BR-?Rip', 'BRRip'),
            (r'REMUX|原盘', 'REMUX'),
            (r'HDTV|PDTV|SATRip|DSR', 'HDTV'),
            (r'DVD-?Rip', 'DVDRip'), (r'DVDScr', 'DVDScr'),
            (r'HDCAM|\bCAM\b', 'CAM'), (r'HDTC|\bTC\b', 'TC'), (r'HDTS|\bTS\b', 'TS'),
        ]:
            if _re.search(pat, t, _re.IGNORECASE) and label not in source_tokens:
                source_tokens.append(label)
        source = " ".join(source_tokens)

        # ---- 编码 ----
        codec = ""
        cm = _re.search(r'(H\.?26[45]|x\.?26[45]|HEVC|AVC)', t, _re.IGNORECASE)
        if cm:
            c = cm.group(1).upper().replace('.', '')
            codec = {'X264': 'x264', 'X265': 'x265'}.get(c, c)

        # ---- HDR / 杜比视界 ----
        hdr = ""
        if _re.search(r'Dolby\s?Vision|DoVi|杜比视界|杜比', t, _re.IGNORECASE):
            hdr = "DV"
        elif _re.search(r'HDR10\+|HDR10', t, _re.IGNORECASE):
            hdr = "HDR10"
        elif _re.search(r'\bHDR\b', t, _re.IGNORECASE):
            hdr = "HDR"

        # ---- 组装 ----
        display_name = f"{name} ({year})" if name and year else (name or "")
        meta_head = " - ".join([p for p in [status, episode] if p])
        meta_tail = "  ".join([p for p in [quality, source, codec, hdr] if p])
        meta = "  ".join([x for x in [meta_head, meta_tail] if x])
        return {"display_name": display_name, "meta": meta,
                "is_complete": is_complete, "episode_num": episode_num}

    def _send_fail_notify(self, subscribe, reason: str):
        if not self._notify_fail:
            return
        try:
            self.post_message(
                mtype=NotificationType.Subscribe,
                title=f"TG115 未命中 {subscribe.name}",
                text=f"原因: {reason}，将使用 MoviePilot 默认搜索。",
            )
        except Exception:
            pass

    # ============================ REST API ============================
    def __get_config_api(self):
        """GET /config：返回当前配置（供自定义前端 Config.vue 读取）。"""
        from starlette.responses import JSONResponse
        config = self.get_data(CONFIG_KEY) or self._default_config()
        ck = config.get("p115_cookie", "") if isinstance(config, dict) else ""
        logger.info(f"【TG115】/config/get p115_cookie_len={len(ck or '')} valid={bool(_pick_uid_cid_seid(ck or ''))}")
        return JSONResponse(config)

    def __save_config_api(self, config: dict = Body(default=None)):
        """POST /config/save：保存配置并即时生效。

        使用 FastAPI ``Body`` 显式声明 ``config`` 取自请求体（与官方插件 agenttokens
        的 save_config_api 一致），避免 ``Any`` / ``**kwargs`` 导致 FastAPI 422。
        """
        from starlette.responses import JSONResponse
        if not isinstance(config, dict) or not config:
            return JSONResponse({"success": False, "message": "配置数据无效"}, status_code=400)
        # 兼容 {"config": {...}} 包裹
        if isinstance(config.get("config"), dict) and len(config) == 1:
            config = config["config"]
        try:
            self.save_data(CONFIG_KEY, config)
            self.init_plugin(config)
            return JSONResponse({"success": True, "message": "配置已保存并生效"})
        except Exception as e:
            logger.error(f"【TG115】保存配置失败: {e}")
            return JSONResponse({"success": False, "message": f"保存失败: {e}"}, status_code=500)

    def __check_channel_api(self, index: int = -1):
        """GET /check_channel?index=N：检查指定 TG 频道连通性。"""
        from starlette.responses import JSONResponse
        try:
            index = int(index)
        except Exception:
            index = -1
        channels = self._tg_channels or []
        if index < 0 or index >= len(channels):
            return JSONResponse({"success": False, "message": "频道序号无效"})
        ch = channels[index]
        if not self._scraper:
            return JSONResponse({"success": False, "message": "未配置任何频道"})
        ok, msg = self._scraper.check_channel(ch["id"])
        return JSONResponse({"success": ok, "message": f"[{ch.get('name') or ch['id']}] {msg}"})

    def __check_all_api(self):
        """GET /check_all：检查所有 TG 频道连通性。"""
        from starlette.responses import JSONResponse
        channels = self._tg_channels or []
        if not channels:
            return JSONResponse({"success": False, "message": "未配置任何频道"})
        if not self._scraper:
            return JSONResponse({"success": False, "message": "未配置任何频道"})
        results = []
        for ch in channels:
            ok, msg = self._scraper.check_channel(ch["id"])
            results.append({
                "name": ch.get("name") or ch["id"], "id": ch["id"],
                "enabled": ch.get("enabled", True), "ok": ok, "message": msg,
            })
        ok_count = sum(1 for r in results if r["ok"])
        return JSONResponse({
            "success": True,
            "message": f"检查完成：{ok_count}/{len(results)} 个频道连通正常",
            "results": results,
        })

    # ---------------------------- 115 扫码登录 API ----------------------------
    def __qrcode_get_api(self, app: str = "web"):
        """GET /qrcode/get?app=...：获取 115 登录二维码及会话凭证。

        ``app`` 为登录端类型（web/tv/ipad/android/ios/alipaymini 等），决定最终 Cookie
        的设备归属。返回二维码图片（data URL，规避 HTTPS 混合内容）及 uid/time/sign。
        """
        from starlette.responses import JSONResponse
        try:
            token = _qr_token()
            data = token.get("data") if isinstance(token, dict) else None
            data = data or {}
            uid = str(data.get("uid", "") or "")
            if not uid:
                msg = token.get("message", "") if isinstance(token, dict) else ""
                return JSONResponse({"success": False, "message": f"115 未返回 uid: {msg}"}, status_code=502)
            return JSONResponse({
                "success": True,
                "uid": uid,
                "time": data.get("time"),
                "sign": data.get("sign"),
                "app": _qr_normalize_app(app),
                "qrcode_url": _qr_image_data_url(uid),
            })
        except Exception as e:
            logger.error(f"【TG115】获取 115 二维码失败: {e}")
            return JSONResponse({"success": False, "message": f"获取二维码失败: {e}"}, status_code=500)

    def __qrcode_status_api(self, uid: str = "", time: str = "", sign: str = "", app: str = "web"):
        """GET /qrcode/status?uid=&time=&sign=&app=：轮询扫码状态，成功则提取并保存 Cookie。

        status: 0=等待扫码 1=已扫描待确认 2=已确认登录 -1=已过期 -2=已取消 -99=异常。
        status==2 时调 ``_qr_result`` 取含 UID/CID/SEID 的 Cookie，写回配置并 ``init_plugin``
        即时生效（重建 P115Transfer）。
        """
        from starlette.responses import JSONResponse
        if not uid or not sign:
            return JSONResponse({"status": -99, "msg": "缺少 uid/sign", "login_ok": False}, status_code=400)
        _msg_map = {0: "等待扫码", 1: "已扫描，请在手机上确认", 2: "已确认登录",
                    -1: "二维码已过期", -2: "已取消", -99: "异常"}
        # 1) 先直接尝试取 Cookie。115 在用户手机端确认后，qrcode_result 即可拿到含
        #    UID/CID/SEID 的 Cookie；这样不依赖 status 响应里可能缺失的 status 字段，
        #    避免出现「已确认但前端一直等待」的问题。未确认时返回空，无副作用。
        try:
            raw, set_cookie = _qr_result(uid, app)
        except Exception as e:
            raw, set_cookie = "", ""
            logger.warn(f"【TG115】qrcode_result 请求异常: {e}")
        logger.info(f"【TG115】qrcode_result app={app} uid={uid[:10]}.. => "
                    f"raw={raw[:300]} set_cookie={set_cookie[:150]}")
        cookie_str = _pick_uid_cid_seid(raw + "\n" + set_cookie)
        if cookie_str:
            cfg = self.get_data(CONFIG_KEY) or self._default_config()
            cfg["p115_cookie"] = cookie_str
            cfg["p115_app"] = _qr_normalize_app(app)
            self.save_data(CONFIG_KEY, cfg)
            self.init_plugin(cfg)
            return JSONResponse({"status": 2, "msg": "扫码登录成功，Cookie 已保存并生效", "login_ok": True})
        # 注意：「老乡验证失败」(errno 40101017) 在未扫码时也会返回，故不据此中断轮询；
        # 若手机端确认后仍持续返回该错误，说明 115 异地风控拒绝下发 Cookie，需改用 Cookie
        # 登录。具体见 MP 日志里 qrcode_result 的原始响应。
        # 2) 未确认：查状态用于展示（等待/已扫描/过期）
        try:
            resp = _qr_status(uid, str(time or ""), sign)
            data = resp.get("data") if isinstance(resp, dict) else None
            data = data or {}
            status = data.get("status")
            if status is None:
                status = resp.get("status") if isinstance(resp, dict) else None
            if status is None:
                status = 0 if (isinstance(resp, dict) and resp.get("state") == 1) else -1
            status = int(status)
            msg = (data.get("msg") or (resp.get("message") if isinstance(resp, dict) else "")
                   or _msg_map.get(status, ""))
            return JSONResponse({"status": status, "msg": msg, "login_ok": False})
        except Exception:
            # 状态接口长轮询超时（无事件），视为等待
            return JSONResponse({"status": 0, "msg": "等待扫码", "login_ok": False})

    # ---------------------------- 手动转存 / 手动搜索 API ----------------------------
    def __transfer_api(self, share_url: str = "", target: str = ""):
        """GET /transfer?share_url=...&target=...：手动转存 115 分享链接到指定目录。

        ``target`` 留空则用配置中的默认转存目录（``p115_target``）；可填路径（如 /电影）
        或数字 cid。复用已有的 ``P115Transfer.transfer``（httpx 直连 share_receive）。
        """
        from starlette.responses import JSONResponse
        share_url = (share_url or "").strip()
        if not share_url:
            return JSONResponse({"success": False, "message": "请输入 115 分享链接"}, status_code=400)
        if not self._transfer or not self._p115_cookie:
            return JSONResponse({"success": False, "message": "未配置 115 Cookie，请先扫码登录"}, status_code=400)
        target_path = (target or "").strip() or self._p115_target
        try:
            ok, msg, data = self._transfer.transfer(share_url, target_path)
            logger.info(f"【TG115】手动转存 {share_url} -> {target_path}: ok={ok} msg={msg}")
            return JSONResponse({"success": ok, "message": msg})
        except Exception as e:
            logger.error(f"【TG115】手动转存异常: {e}")
            return JSONResponse({"success": False, "message": f"转存失败: {e}"}, status_code=500)

    def __search_api(self, keyword: str = "", offset: int = 0, source: str = "all"):
        """GET /search?keyword=...&offset=N&source=all|tg|site：手动搜索。

        source：all=全部(默认) / tg=仅TG频道 / site=仅观影。
        返回全部网盘类型（115/夸克/百度/阿里/迅雷…/磁力），前端按类型展示；仅 115 可自动转存。
        offset 用于观影翻页（按作品分批，每批 3 部）；TG 仅在首批(offset=0)搜索一次。
        返回 has_more 标记是否还有更多观影作品可翻页；warning 携带 app_auth 失效等提示。
        """
        from starlette.responses import JSONResponse
        import concurrent.futures
        keyword = (keyword or "").strip()
        if not keyword:
            return JSONResponse({"success": False, "message": "请输入搜索关键字"}, status_code=400)
        if (not self._scraper or not self._tg_channels) and not self._site_scraper:
            return JSONResponse({"success": False, "message": "未配置任何搜索源（TG 频道或观影）"}, status_code=400)
        try:
            offset = int(offset or 0)
        except Exception:
            offset = 0
        # 从关键字分离年份（如"法警小队（2026）"->"法警小队"+2026）：观影按年份精确过滤，
        # 去掉年份让站点能搜到（带年份会搜不到、返回模糊匹配）
        _y = _re.search(r'[(（](\d{4})[)）]', keyword)
        manual_year = int(_y.group(1)) if _y else None
        search_kw = _re.sub(r'\s*[(（]\d{4}[)）]', '', keyword).strip() or keyword

        def _do_search():
            hits = []
            has_more = False
            src = (source or "all").lower()
            # TG 仅首批搜索一次（已抓全 max_pages 页）；翻页(offset>0)只追加观影作品
            if src in ("all", "tg") and self._scraper and offset == 0:
                hits.extend(self._scraper.search(search_kw))
            if src in ("all", "site") and self._site_scraper:
                site_hits, has_more = self._site_scraper.search(
                    search_kw, year=manual_year, offset=offset, count=3)
                hits.extend(site_hits)
            if src in ("all", "juying") and self._juying_api:
                hits.extend(self._juying_api.search(search_kw, year=manual_year))
            return hits, has_more

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                hits, has_more = ex.submit(_do_search).result(timeout=180)
            results = []
            for h in hits:
                pt = getattr(h, "pan_type", "") or ""
                if not pt:
                    pt = "115" if P115Transfer._is_115_share_url(h.share_url or "") else "other"
                title = h.resource_title or h.text or "未命名资源"
                meta = self._parse_resource_meta(h.text or title)
                # 观影资源：用 search_suggest 的作品名(source_title)+年份做标题，
                # 比 panlist 里杂乱的名称（含装饰/分类前缀/《》等）干净
                src_title = getattr(h, "source_title", "") or ""
                src_year = getattr(h, "year", None)
                if src_title:
                    display_name = f"{src_title} ({src_year})" if src_year else src_title
                else:
                    display_name = meta["display_name"] or title
                results.append({
                    "title": title,
                    "display_name": display_name,
                    "meta": meta["meta"],
                    "is_complete": meta["is_complete"],
                    "episode_num": meta["episode_num"],
                    "share_url": h.share_url,
                    "receive_code": getattr(h, "receive_code", "") or "",
                    "channel": getattr(h, "channel_name", "") or "",
                    "pan_type": pt,
                    "pub_date": h.pub_date or "",
                    "text": (h.text or "")[:500],
                })
            # 排序：完结优先，然后按最大集数降序
            results.sort(key=lambda r: (r["is_complete"], r["episode_num"]), reverse=True)
            # app_auth 失效提示（观影搜不到资源时给出明确原因）
            warning = ""
            if self._site_scraper and not getattr(self._site_scraper, "app_auth_valid", True):
                warning = "观影 app_auth 已失效，请在「观影」Tab 更新 app_auth 后重试"
            elif self._juying_api and not getattr(self._juying_api, "app_auth_valid", True):
                warning = "聚影 AppID/API Key 无效(401)，请在「聚影」Tab 检查凭证"
            return JSONResponse({
                "success": True,
                "message": f"找到 {len(results)} 条资源",
                "results": results,
                "has_more": has_more,
                "warning": warning,
            })
        except concurrent.futures.TimeoutError:
            return JSONResponse({"success": False, "message": "搜索超时（连接或检索过久）"}, status_code=504)
        except Exception as e:
            logger.error(f"【TG115】手动搜索异常: {e}")
            return JSONResponse({"success": False, "message": f"搜索失败: {e}"}, status_code=500)

    # ---------------------------- 115 目录查询 / 浏览 API ----------------------------
    def __dir_info_api(self, cid: str = ""):
        """GET /dir_info?cid=...：根据 cid 查询 115 目录名称，便于用户核对。"""
        from starlette.responses import JSONResponse
        cid = (cid or "").strip()
        if not cid:
            return JSONResponse({"success": False, "message": "请输入 cid"}, status_code=400)
        if not self._p115_cookie:
            return JSONResponse({"success": False, "message": "未配置 115 Cookie，请先扫码登录"}, status_code=400)
        try:
            resp = self._transfer.fs_info(cid)
            data = resp.get("data") if isinstance(resp, dict) else None
            if isinstance(data, list) and data:
                data = data[0]
            if isinstance(data, dict):
                # proapi 用 file_name/file_id，webapi 用 name/n/cid，都兼容
                name = data.get("file_name") or data.get("name") or data.get("n") or ""
                c = data.get("file_id") or data.get("cid") or cid
                return JSONResponse({"success": True, "name": name, "cid": str(c)})
            return JSONResponse({"success": False, "message": "未找到该 cid 对应的目录"})
        except Exception as e:
            logger.error(f"【TG115】查询目录信息失败: {e}")
            return JSONResponse({"success": False, "message": f"查询失败: {e}"}, status_code=500)

    def __dirs_api(self, cid: str = "0"):
        """GET /dirs?cid=...：列出某 cid 下的子目录（用于目录浏览）。cid=0 为根目录。

        通过 ``fs_files(cid)`` 拿目录内容，过滤出文件夹（文件夹无 sha1，文件有）。
        """
        from starlette.responses import JSONResponse
        cid = (cid or "0").strip() or "0"
        if not self._p115_cookie:
            return JSONResponse({"success": False, "message": "未配置 115 Cookie，请先扫码登录"}, status_code=400)
        try:
            resp = self._transfer.fs_files(cid)
            logger.info(f"【TG115】/dirs cid={cid} state={resp.get('state') if isinstance(resp, dict) else '?'} msg={(resp.get('message') or resp.get('error') or '')[:80] if isinstance(resp, dict) else ''}")
            if isinstance(resp, dict) and resp.get("state") not in (True, 1, "1"):
                err = resp.get("error") or resp.get("message") or resp.get("msg") or "获取失败"
                return JSONResponse({"success": False, "message": f"115 返回：{err}"})
            data = resp.get("data") if isinstance(resp, dict) else None
            items = data if isinstance(data, list) else (data.get("data", []) if isinstance(data, dict) else [])
            dirs = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                if it.get("sha1"):  # 文件才有 sha1，跳过
                    continue
                name = it.get("name") or it.get("n") or ""
                c = str(it.get("cid", it.get("id", "")))
                if name and c:
                    dirs.append({"cid": c, "name": name})
            return JSONResponse({"success": True, "cid": cid, "dirs": dirs})
        except Exception as e:
            logger.error(f"【TG115】获取子目录失败: {e}")
            return JSONResponse({"success": False, "message": f"获取目录失败: {e}"}, status_code=500)

    def __verify_cookie_api(self):
        """GET /verify_cookie：实测 115 Cookie 是否有效（调 fs_files(0)）。"""
        from starlette.responses import JSONResponse
        if not self._p115_cookie:
            return JSONResponse({"success": False, "valid": False, "message": "未配置 115 Cookie"})
        try:
            resp = self._transfer.fs_files(0)
            ok = isinstance(resp, dict) and resp.get("state") in (True, 1, "1")
            msg = "Cookie 有效" if ok else f"Cookie 已失效：{(resp.get('error') or resp.get('message') or '')[:80] if isinstance(resp, dict) else ''}"
            return JSONResponse({"success": True, "valid": bool(ok), "message": msg})
        except Exception as e:
            logger.error(f"【TG115】验证 Cookie 异常: {e}")
            return JSONResponse({"success": False, "valid": False, "message": f"验证失败: {e}"})

    def __check_site_api(self, app_auth: str = "", site_domain: str = ""):
        """GET /check_site?app_auth=...&site_domain=...：检查观影 PoW + app_auth 登录态。

        传 ``app_auth``/``site_domain`` 则测**当前输入**（无需先保存），否则测已保存配置。
        """
        from starlette.responses import JSONResponse
        auth = (app_auth or "").strip()
        dom = (site_domain or "").strip() or self._site_domain
        if auth:
            # 临时 scraper 测当前输入的 app_auth（不依赖保存），用观影专用代理+域名
            sp = (config.get("site_proxy") or "").strip()
            proxy = None if sp == 'direct' else (sp or None)
            scraper = FilejinScraper(app_auth=auth, proxy=proxy, site_base=dom)
            ok, msg = scraper.check()
            return JSONResponse({"success": ok, "message": msg})
        if not self._site_scraper:
            return JSONResponse({"success": False, "message": "观影未启用或未配置 app_auth"})
        ok, msg = self._site_scraper.check()
        return JSONResponse({"success": ok, "message": msg})

    def __check_juying_api(self, app_id: str = "", api_key: str = "", domain: str = ""):
        """GET /check_juying?app_id=...&api_key=...&domain=...：检查聚影 API 鉴权。

        传参则测当前输入（无需保存），否则测已保存配置。
        """
        from starlette.responses import JSONResponse
        aid = (app_id or "").strip()
        akey = (api_key or "").strip()
        dom = (domain or "").strip() or self._juying_domain
        if aid or akey:
            api = JuyingApi(app_id=aid, api_key=akey, domain=dom, proxy=self._juying_proxy)
            ok, msg = api.check()
            return JSONResponse({"success": ok, "message": msg})
        if not self._juying_api:
            return JSONResponse({"success": False, "message": "聚影未启用或未配置 AppID/API Key/域名"})
        ok, msg = self._juying_api.check()
        return JSONResponse({"success": ok, "message": msg})

    # ============================ 依赖检查 ============================
    def _check_deps(self):
        missing = []
        try:
            import bs4  # noqa: F401
        except Exception:
            missing.append("beautifulsoup4")
        try:
            import httpx  # noqa: F401
        except Exception:
            missing.append("httpx")
        if missing:
            logger.warn(f"【TG115】缺少依赖: {', '.join(missing)}，请安装后重启 MoviePilot 生效")
        if self._p115_cookie:
            ok, msg = P115Transfer.validate_cookie(self._p115_cookie)
            if not ok:
                logger.warn(f"【TG115】115 Cookie 校验: {msg}")
        # TG 爬虫无需额外配置（只需频道列表 + 网络/代理）
        if self._tg_channels and not any(ch.get("enabled", True) for ch in self._tg_channels):
            logger.warn("【TG115】所有 TG 频道均已关闭，订阅将直接回退到默认搜索")

    # ============================ 默认配置 / 频道解析 ============================
    @staticmethod
    def _default_config() -> Dict[str, Any]:
        """首次加载 / 无配置时返回的默认结构，供前端初始化。"""
        return {
            "enabled": False,
            "p115_cookie": "",
            "p115_app": "",
            "p115_target": "/电影",
            "use_rule_groups": True,
            "delay_seconds": 3,
            "notify_success": True,
            "notify_fail": False,
            "auto_finish": True,
            "site_enabled": False,
            "site_app_auth": "",
            "site_proxy": "",
            "site_domain": "",
            "juying_enabled": False,
            "juying_app_id": "",
            "juying_api_key": "",
            "juying_domain": "",
            "juying_proxy": "",
            "tg_channels": [],
        }

    @staticmethod
    def _parse_channels(raw: Any) -> List[Dict[str, Any]]:
        """解析 TG 频道列表。

        兼容自定义前端直接传入的数组，以及历史 JSON 字符串：
          - list：[{"name":"..","id":"..","enabled":true}, ...] 或 ["@xxx", ...]
          - str ：JSON 字符串
        每条归一化为 {"name","id","enabled"}。
        """
        channels: List[Dict[str, Any]] = []

        def push(name: str, cid: str, enabled: bool = True):
            cid = (cid or "").strip()
            if not cid:
                return
            channels.append({
                "name": (name or "").strip() or cid,
                "id": cid,
                "enabled": bool(enabled),
            })

        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    push(
                        str(item.get("name") or ""),
                        str(item.get("id") or item.get("link") or item.get("channel") or ""),
                        item.get("enabled", True),
                    )
                elif isinstance(item, str):
                    push(item, item)
        elif isinstance(raw, str):
            text = raw.strip()
            if text:
                try:
                    data = json.loads(text)
                except Exception as e:
                    logger.warn(f"【TG115】TG 频道列表 JSON 解析失败：{e}")
                    data = None
                if isinstance(data, list):
                    return TgSearch115._parse_channels(data)
        return channels

    # ============================ 静态工具 ============================
    @staticmethod
    def _safe_int(v: Any, default: int = 0) -> int:
        try:
            return int(v)
        except Exception:
            return default

    @staticmethod
    def _to_bool(v: Any, default: bool = False) -> bool:
        if v is None:
            return default
        if isinstance(v, bool):
            return v
        return str(v).lower() in ("1", "true", "yes", "on")
