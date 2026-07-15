# -*- coding: utf-8 -*-
"""115 网盘分享链接转存（share_receive）封装。

背景：MoviePilot 内置的 ``app.modules.filemanager.storages.u115.U115Pan`` 是基于
OAuth 的存储模块，仅提供 list / upload / download / move 等能力，**不包含**
"分享链接转存（share_receive）"接口。115 的转存属于 Cookie 鉴权的 Web API，
因此本模块采用社区标准方案：使用 ``p115client`` + 用户配置的 115 Cookie，调用
``client.share_receive(...)`` 将分享链接转存到指定 115 目录。

这与 MoviePilot 插件市场中 P115StrmHelper、agentresourceofficer 等插件的转存
实现一致，是最稳妥的"反射调用 115 转存"方式。
"""
import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qsl, urlparse

from app.log import logger


class P115Transfer:
    """115 分享链接转存执行器（基于 p115client + Cookie）。"""

    # 合法客户端 Cookie 必备字段（扫码登录得到的 Cookie 才有）
    CLIENT_COOKIE_REQUIRED_KEYS = {"UID", "CID", "SEID"}

    def __init__(self, cookie: str = "", default_target_path: str = "/") -> None:
        self.cookie = self._normalize(cookie)
        self.default_target_path = self._normalize_path(default_target_path) or "/"

    # ============================ 公共方法 ============================
    def is_ready(self) -> Tuple[bool, str]:
        """检查 Cookie 是否可用。"""
        if not self.cookie:
            return False, "未配置 115 Cookie"
        ok, msg = self.validate_cookie(self.cookie)
        if not ok:
            return False, msg
        return True, ""

    @classmethod
    def validate_cookie(cls, cookie: str) -> Tuple[bool, str]:
        if not cls._normalize(cookie):
            return False, "115 Cookie 为空"
        pairs = cls._parse_cookie_pairs(cookie)
        missing = sorted(cls.CLIENT_COOKIE_REQUIRED_KEYS - set(pairs))
        if missing:
            return False, (
                f"115 Cookie 缺少 {'/'.join(missing)}，请使用 115 客户端扫码登录得到的 "
                f"Cookie（网页版 Cookie 无法转存）"
            )
        return True, ""

    def transfer(self, share_url: str, target_path: str = "") -> Tuple[bool, str, Dict[str, Any]]:
        """转存分享链接到目标目录。

        :param share_url: 115 分享链接（含提取码），如
            ``https://115.com/s/xxxxxxxx?password=yyyy``
        :param target_path: 115 目标目录路径（如 ``/电影``）。留空则用默认目录。
        :return: (ok, message, data)
        """
        share_url = self._normalize(share_url)
        effective = self._normalize(target_path) or self.default_target_path
        result: Dict[str, Any] = {"url": share_url, "path": effective}

        if not share_url or not self._is_115_share_url(share_url):
            return False, "不是有效的 115 分享链接", result

        ok, msg = self.is_ready()
        if not ok:
            return False, msg, result

        share_code, receive_code = self._extract_payload(share_url)
        if not share_code or not receive_code:
            return False, "解析 115 分享链接失败，缺少分享码或提取码", result

        # 初始化 p115client
        try:
            client = self._get_client()
        except Exception as e:
            return False, f"115 客户端初始化失败: {e}", result

        logger.info(f"【TG115】手动转存 share_url={share_url} target={effective}")
        # 目标目录：纯数字视为 cid 直接用；否则按路径查找/创建
        try:
            if effective.isdigit():
                parent_id = effective
            else:
                parent_id = self._get_or_create_cid(client, effective)
        except Exception as e:
            return False, f"定位 115 目标目录失败: {e}", result

        # 115 share_receive 需要在表单里带 user_id（UID 的数字部分），否则报「参数错误」
        user_id = ""
        for _part in self.cookie.split(";"):
            _part = _part.strip()
            if _part.startswith("UID="):
                user_id = _part[4:].split("_")[0].strip()
                break
        payload = {
            "share_code": share_code,
            "receive_code": receive_code,
            "file_id": 0,
            "cid": int(parent_id),
            "is_check": 0,
            "user_id": user_id,
        }
        logger.info(f"【TG115】转存 payload={payload}")
        try:
            resp = self._direct_share_receive(share_code, receive_code, parent_id, user_id)
            logger.info(f"【TG115】share_receive 响应: {str(resp)[:300]}")
        except Exception as e:
            logger.error(f"【TG115】share_receive 异常: {e}")
            return False, f"调用 115 转存接口失败: {e}", result

        if not self._response_ok(resp):
            err = self._response_error(resp) or "115 转存失败"
            # "已转存" 视为成功（幂等）
            if self._is_already_saved(err):
                result.update({"share_code": share_code, "parent_id": parent_id})
                return True, "115 转存已存在（之前已转存）", result
            result.update({"parent_id": parent_id, "raw": self._jsonable(resp)})
            return False, err, result

        result.update({
            "share_code": share_code,
            "receive_code": receive_code,
            "parent_id": parent_id,
            "raw": self._jsonable(resp),
        })
        return True, "115 转存成功", result

    # ============================ 内部工具 ============================
    def _direct_share_receive(self, share_code: str, receive_code: str,
                              cid, user_id: str, file_id=0) -> dict:
        """直连 115 /share/receive（POST form data + cookie），绕过 p115client。

        p115client 的 request 方法可能把 data 当 JSON 发，而 115 要求 form data。
        这里用 urllib 直接发 urlencoded form data + Cookie 头，与 115 网页端一致。
        """
        import urllib.request as _ureq
        import urllib.parse as _uparse
        url = "https://webapi.115.com/share/receive"
        data = _uparse.urlencode({
            "share_code": share_code,
            "receive_code": receive_code,
            "file_id": file_id,
            "cid": str(cid),
            "is_check": 0,
            "user_id": user_id,
        }).encode("utf-8")
        req = _ureq.Request(url, data=data, method="POST", headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Cookie": self.cookie,
            "Content-Type": "application/x-www-form-urlencoded",
        })
        with _ureq.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))

    def _get_client(self):
        """延迟导入 p115client，避免插件加载期强依赖。

        p115client 不同版本 ``P115Client.__init__`` 形参有差异：新版本移除了
        ``check_for_relogin`` / ``ensure_cookies`` / ``console_qrcode`` 等参数，
        传了会抛 ``TypeError: unexpected keyword argument``。这里按「从全到简」
        依次尝试，兼容各版本；最终兜底仅传 cookie。
        """
        from p115client import P115Client
        for kwargs in (
            {"check_for_relogin": False, "ensure_cookies": False, "console_qrcode": False},
            {"ensure_cookies": False, "console_qrcode": False},
            {"ensure_cookies": False},
        ):
            try:
                return P115Client(self.cookie, **kwargs)
            except TypeError:
                continue
        return P115Client(self.cookie)

    def _get_or_create_cid(self, client, path: str) -> int:
        """根据路径获取目录 cid，不存在则创建。根目录返回 0。"""
        target = self._normalize_path(path) or "/"
        if target == "/":
            return 0
        # 优先直接读取
        try:
            resp = client.fs_dir_getid(target)
            pid = self._safe_int(resp.get("id") if isinstance(resp, dict) else None, -1)
            if pid > 0:
                return pid
        except Exception:
            pass
        # 不存在则创建
        try:
            resp = client.fs_makedirs_app(target, pid=0)
            cid = self._safe_int(resp.get("cid") if isinstance(resp, dict) else None, -1)
            if cid >= 0:
                return cid
            if self._response_ok(resp):
                data = resp.get("data") if isinstance(resp, dict) else None
                cid = self._safe_int(data.get("cid") if isinstance(data, dict) else None, -1)
                if cid >= 0:
                    return cid
            raise RuntimeError(self._response_error(resp) or "创建目录失败")
        except Exception as e:
            raise RuntimeError(f"无法创建或定位 115 目录 {target}: {e}") from e

    @staticmethod
    def _extract_payload(url: str) -> Tuple[str, str]:
        """从 115 分享链接解析 share_code / receive_code。"""
        url = str(url or "").strip()
        if not url:
            return "", ""
        # 优先使用 p115client 内置解析
        try:
            from p115client.util import share_extract_payload
            payload = share_extract_payload(url) or {}
            return (
                str(payload.get("share_code") or "").strip(),
                str(payload.get("receive_code") or "").strip(),
            )
        except Exception:
            pass
        # 兜底正则解析
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
    def _is_115_share_url(url: str) -> bool:
        host = urlparse(str(url or "")).netloc.lower()
        return (
            host == "115.com"
            or host.endswith(".115.com")
            or "115cdn.com" in host
            or host == "anxia.com"
        )

    @staticmethod
    def _normalize(v: Any) -> str:
        return "" if v is None else str(v).strip()

    @staticmethod
    def _normalize_path(v: Any) -> str:
        t = str(v or "").strip()
        if not t:
            return ""
        if not t.startswith("/"):
            t = "/" + t
        return t.rstrip("/") or "/"

    @classmethod
    def _parse_cookie_pairs(cls, cookie: str) -> Dict[str, str]:
        pairs: Dict[str, str] = {}
        for part in cls._normalize(cookie).strip(";").split(";"):
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            k, v = k.strip(), v.strip()
            if k and v:
                pairs[k] = v
        return pairs

    @staticmethod
    def _safe_int(v: Any, default: int = -1) -> int:
        try:
            return int(v)
        except Exception:
            return default

    @staticmethod
    def _response_ok(resp: Any) -> bool:
        if not isinstance(resp, dict):
            return False
        if resp.get("state") is True:
            return True
        if resp.get("code") in (0, "0") and resp.get("state") not in (False, 0):
            return True
        if resp.get("errno") in (0, "0") and resp.get("state") not in (False, 0):
            return True
        return False

    @staticmethod
    def _response_error(resp: Any) -> str:
        if not isinstance(resp, dict):
            return str(resp or "")
        for k in ("error", "message", "msg", "errno"):
            v = resp.get(k)
            if v not in (None, ""):
                return str(v)
        return str(resp)

    @staticmethod
    def _is_already_saved(text: Any) -> bool:
        t = str(text or "")
        return any(m in t for m in (
            "已经转存", "已转存", "已经保存", "已保存", "already", "exist",
        ))

    @staticmethod
    def _jsonable(v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, (str, int, float, bool, list, dict)):
            return v
        if hasattr(v, "model_dump"):
            try:
                return v.model_dump()
            except Exception:
                pass
        if hasattr(v, "__dict__"):
            return {k: val for k, val in vars(v).items() if not k.startswith("_")}
        return str(v)
