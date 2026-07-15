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

2. TG 搜索：用 Telethon User Session 读取目标频道历史消息，按订阅标题/年份检索，
   提取其中的 115 分享链接（见 ``tg_searcher.py``）。支持多频道。

3. 规则匹配：每条命中构造为 ``TorrentInfo``，复用 MoviePilot 内置的
   ``SubscribeChain().filter_torrents`` 与 ``TorrentHelper.filter_torrent``，
   按用户在 MP 中配置的过滤规则二次校验。

4. 115 转存：命中后用 ``p115client`` + 用户 Cookie 调 ``share_receive`` 转存到
   指定 115 目录（见 ``p115_transfer.py``）。
   注意：MoviePilot 核心的 ``app.modules.filemanager.storages.u115.U115Pan``
   是基于 OAuth 的存储模块，仅提供 list/upload/download/move，**不包含**
   分享链接转存（share_receive）接口；官方插件仓 (jxxghp/MoviePilot-Plugins)
   中的 ``agentresourceofficer`` 同样自带 ``services/p115_transfer.py`` 走
   ``p115client``。故本插件沿用社区标准方案，不"手写 115 请求"，
   也无法引用一个并不存在的 MP 核心转存类。

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
# ============================ 依赖动态静默安装 ============================
# MoviePilot 运行在 Docker 容器内，容器重启后手动 pip 安装的第三方依赖会丢失。
# 这里在导入业务包之前检测 p115client / telethon，缺失则用当前解释器静默安装，
# 实现「开箱即用」。安装失败不阻断插件加载（业务模块均为懒导入，缺依赖时仅在
# 实际调用时报错并由上层捕获后平滑回退，不影响 MoviePilot 主流程）。
import subprocess as _subprocess
import sys as _sys


def _ensure_deps() -> None:
    missing = []
    for _mod, _pkg in (("p115client", "p115client"), ("telethon", "telethon")):
        try:
            __import__(_mod)
        except ImportError:
            missing.append(_pkg)
    if not missing:
        return
    try:
        _subprocess.run(
            [_sys.executable, "-m", "pip", "install", *missing],
            check=False,
            stdout=_subprocess.DEVNULL,
            stderr=_subprocess.DEVNULL,
            timeout=600,
        )
    except Exception:
        # 安装失败不抛出，避免影响 MoviePilot 插件加载
        pass


_ensure_deps()

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
from .tg_searcher import TgChannelSearcher


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
    plugin_version = "2.2.11"
    plugin_author = "MoviePilot User"
    plugin_icon = "T"
    plugin_config_prefix = "plugin.tgsearch115"
    author_url = ""
    plugin_url = ""

    # ============================ 运行态 ============================
    _enabled = False
    _lock = threading.Lock()
    _running_ids: set = set()
    _searcher: Optional[TgChannelSearcher] = None
    _transfer: Optional[P115Transfer] = None

    # 配置项（运行态缓存）
    _tg_api_id = 0
    _tg_api_hash = ""
    _tg_session = ""
    _tg_channels: List[Dict[str, Any]] = []
    _tg_max_messages = 200
    _tg_proxy = ""
    _p115_cookie = ""
    _p115_app = ""
    _p115_target = "/"
    _use_rule_groups = True
    _delay_seconds = 3
    _notify_success = True
    _notify_fail = False

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
        self._tg_api_id = self._safe_int(config.get("tg_api_id"), 0)
        self._tg_api_hash = config.get("tg_api_hash") or ""
        self._tg_session = config.get("tg_session") or ""
        self._tg_max_messages = self._safe_int(config.get("tg_max_messages"), 200)
        self._tg_proxy = config.get("tg_proxy") or ""
        self._p115_cookie = config.get("p115_cookie") or ""
        self._p115_app = config.get("p115_app") or ""
        self._p115_target = config.get("p115_target") or "/"
        self._use_rule_groups = self._to_bool(config.get("use_rule_groups"), True)
        self._delay_seconds = self._safe_int(config.get("delay_seconds"), 3)
        self._notify_success = self._to_bool(config.get("notify_success"), True)
        self._notify_fail = self._to_bool(config.get("notify_fail"), False)

        # TG 频道列表：自定义前端直接以数组/JSON 字符串形式提交 tg_channels
        self._tg_channels = self._parse_channels(config.get("tg_channels"))

        # 搜索器只接收「已启用」的频道
        enabled_channels = [ch for ch in self._tg_channels if ch.get("enabled", True)]
        self._searcher = TgChannelSearcher(
            api_id=self._tg_api_id,
            api_hash=self._tg_api_hash,
            session_string=self._tg_session,
            channels=enabled_channels,
            max_messages=self._tg_max_messages,
            proxy=self._tg_proxy,
        )
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
            logger.info(f"【TG115】订阅 [{subscribe.name}] 开始搜索 TG 频道，关键字: {keyword}")
            hits = self._searcher.search(keyword) if self._searcher else []
            if not hits:
                logger.info(f"【TG115】订阅 [{subscribe.name}] TG 频道未找到 115 资源，回退到默认搜索")
                self._notify_fail(subscribe, "TG 频道未找到 115 资源")
                return

            torrents = self._build_torrents(hits)
            matched = self._filter_resources(subscribe, mediainfo, torrents)
            if not matched:
                logger.info(f"【TG115】订阅 [{subscribe.name}] TG 资源均不符合 MP 过滤规则，回退到默认搜索")
                self._notify_fail(subscribe, "TG 资源不符合过滤规则")
                return

            best = matched[0]
            share_url = best.page_url or ""
            logger.info(f"【TG115】订阅 [{subscribe.name}] 命中: {best.title} -> {share_url}")

            ok, msg, _data = (
                self._transfer.transfer(share_url, self._p115_target)
                if self._transfer
                else (False, "转存模块未初始化", {})
            )
            if not ok:
                logger.warn(f"【TG115】订阅 [{subscribe.name}] 115 转存失败: {msg}，回退到默认搜索")
                self._notify_fail(subscribe, f"115 转存失败: {msg}")
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
        parts = [p for p in [subscribe.name, subscribe.year] if p]
        return " ".join(parts)

    @staticmethod
    def _build_torrents(hits) -> List[TorrentInfo]:
        torrents: List[TorrentInfo] = []
        for h in hits:
            torrents.append(TorrentInfo(
                title=h.resource_title or "未命名资源",
                description=h.text,
                page_url=h.share_url,
                site_name="TG频道",
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
        """转存成功：镜像 SubscribeChain.__finish_subscribe，标记订阅完成。"""
        try:
            oper = SubscribeOper()
            oper.add_history(**subscribe.to_dict())
            oper.delete(subscribe.id)
            eventmanager.send_event(EventType.SubscribeComplete, {
                "subscribe_id": subscribe.id,
                "subscribe_info": subscribe.to_dict(),
                "mediainfo": mediainfo.to_dict() if hasattr(mediainfo, "to_dict") else {},
            })
            logger.info(f"【TG115】订阅 [{subscribe.name}] 已通过 TG+115 完成并标记完结")
            if self._notify_success:
                try:
                    self.post_message(
                        mtype=NotificationType.Subscribe,
                        title=f"订阅完成 {subscribe.name}",
                        text=f"已通过 TG 频道找到 115 资源并转存完成。\n资源: {torrent.title}\n{transfer_msg}",
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"【TG115】标记订阅完成异常（不影响 MP 默认流程）: {e}")

    def _notify_fail(self, subscribe, reason: str):
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
        if not self._searcher or not (
            self._searcher.api_id and self._searcher.api_hash and self._searcher.session_string
        ):
            return JSONResponse({"success": False, "message": "TG 配置不完整（api_id/api_hash/session）"})
        ok, msg = self._searcher.check_channel(ch["id"])
        return JSONResponse({"success": ok, "message": f"[{ch.get('name') or ch['id']}] {msg}"})

    def __check_all_api(self):
        """GET /check_all：检查所有 TG 频道连通性。"""
        from starlette.responses import JSONResponse
        channels = self._tg_channels or []
        if not channels:
            return JSONResponse({"success": False, "message": "未配置任何频道"})
        if not self._searcher or not (
            self._searcher.api_id and self._searcher.api_hash and self._searcher.session_string
        ):
            return JSONResponse({"success": False, "message": "TG 配置不完整（api_id/api_hash/session）"})
        results = []
        for ch in channels:
            ok, msg = self._searcher.check_channel(ch["id"])
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
        或数字 cid。复用已有的 ``P115Transfer.transfer``（p115client share_receive）。
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

    def __search_api(self, keyword: str = ""):
        """GET /search?keyword=...：手动搜索 TG 频道中的 115 资源。

        Telethon 为异步库；搜索在独立线程中执行并新建事件循环，避免与 MoviePilot 主线程
        的事件循环冲突（与订阅事件处理器在守护线程中跑搜索的做法一致）。FastAPI 的同步
        端点本身跑在线程池里，阻塞等待搜索结果不会卡住主事件循环。
        """
        from starlette.responses import JSONResponse
        import concurrent.futures
        keyword = (keyword or "").strip()
        if not keyword:
            return JSONResponse({"success": False, "message": "请输入搜索关键字"}, status_code=400)
        if not self._searcher or not (self._tg_api_id and self._tg_api_hash and self._tg_session):
            return JSONResponse({"success": False, "message": "TG 配置不完整（需要 api_id/api_hash/session）"}, status_code=400)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                hits = ex.submit(self._searcher.search, keyword).result(timeout=180)
            results = [{
                "title": h.resource_title or "未命名资源",
                "share_url": h.share_url,
                "channel": h.channel_name or "",
                "pub_date": h.pub_date or "",
            } for h in hits]
            return JSONResponse({
                "success": True,
                "message": f"找到 {len(results)} 条 115 资源",
                "results": results,
            })
        except concurrent.futures.TimeoutError:
            return JSONResponse({"success": False, "message": "搜索超时（TG 连接或检索过久）"}, status_code=504)
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
            client = self._transfer._get_client()
            resp = client.fs_info(cid)
            data = resp.get("data") if isinstance(resp, dict) else None
            if isinstance(data, list) and data:
                data = data[0]
            if isinstance(data, dict):
                name = data.get("name") or data.get("n") or ""
                return JSONResponse({"success": True, "name": name, "cid": str(data.get("cid", cid))})
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
            client = self._transfer._get_client()
            resp = client.fs_files(cid)
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
            client = self._transfer._get_client()
            resp = client.fs_files(0)
            ok = isinstance(resp, dict) and resp.get("state") in (True, 1, "1")
            msg = "Cookie 有效" if ok else f"Cookie 已失效：{(resp.get('error') or resp.get('message') or '')[:80] if isinstance(resp, dict) else ''}"
            return JSONResponse({"success": True, "valid": bool(ok), "message": msg})
        except Exception as e:
            logger.error(f"【TG115】验证 Cookie 异常: {e}")
            return JSONResponse({"success": False, "valid": False, "message": f"验证失败: {e}"})

    # ============================ 依赖检查 ============================
    def _check_deps(self):
        missing = []
        try:
            import telethon  # noqa: F401
        except Exception:
            missing.append("telethon")
        try:
            import p115client  # noqa: F401
        except Exception:
            missing.append("p115client")
        if missing:
            logger.warn(f"【TG115】缺少依赖: {', '.join(missing)}，请安装后重启 MoviePilot 生效")
        if self._p115_cookie:
            ok, msg = P115Transfer.validate_cookie(self._p115_cookie)
            if not ok:
                logger.warn(f"【TG115】115 Cookie 校验: {msg}")
        if not (self._tg_api_id and self._tg_api_hash and self._tg_session):
            logger.warn("【TG115】TG 搜索配置不完整（需要 api_id/api_hash/session）")
        if self._tg_channels and not any(ch.get("enabled", True) for ch in self._tg_channels):
            logger.warn("【TG115】所有 TG 频道均已关闭，订阅将直接回退到默认搜索")

    # ============================ 默认配置 / 频道解析 ============================
    @staticmethod
    def _default_config() -> Dict[str, Any]:
        """首次加载 / 无配置时返回的默认结构，供前端初始化。"""
        return {
            "enabled": False,
            "tg_api_id": "",
            "tg_api_hash": "",
            "tg_session": "",
            "tg_max_messages": 200,
            "tg_proxy": "",
            "p115_cookie": "",
            "p115_app": "",
            "p115_target": "/电影",
            "use_rule_groups": True,
            "delay_seconds": 3,
            "notify_success": True,
            "notify_fail": False,
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
