# -*- coding: utf-8 -*-
"""115 网盘分享链接转存 + 目录操作（httpx + Cookie，无 p115client 依赖）。

背景：MoviePilot 内置的 ``U115Pan`` 是 OAuth 存储模块，不含分享链接转存接口。
115 转存属于 Cookie 鉴权的 Web API。早期版本用 ``p115client``，但它依赖很重
（拖一堆传递依赖），在 Docker 内 ``pip install`` 很慢、拖慢插件加载。本模块改用
``httpx``（tg_scraper/site_scraper 已依赖，轻量）直连 115 Web API，零额外依赖。

调用端点（Cookie 鉴权；转存/列目录用 webapi.115.com，目录名/建目录用 proapi 开放 API，
均与 p115client 内部端点逐一核对一致）：
  - 转存：GET  webapi /share/snap?share_code=&receive_code=&cid=0  -> 取 file_id
         POST webapi /share/receive  (form: share_code,receive_code,file_id,cid,user_id)
  - 列目录/验证 Cookie：GET webapi /files?cid={cid}&limit=50  (返回 cid/n/sha1)
  - 目录名：GET proapi /open/folder/get_info?file_id={cid}
  - 建目录：POST proapi /open/folder/add  (form: file_name, pid)
"""
import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qsl, urlparse

from app.log import logger


class P115Transfer:
    """115 分享链接转存 + 目录操作执行器（httpx + Cookie，无 p115client）。"""

    CLIENT_COOKIE_REQUIRED_KEYS = {"UID", "CID", "SEID"}
    _API = "https://webapi.115.com"
    _PROAPI = "https://proapi.115.com"  # 开放 API（与 p115client 的 fs_info/fs_mkdir 一致）

    def __init__(self, cookie: str = "", default_target_path: str = "/") -> None:
        self.cookie = self._normalize(cookie)
        self.default_target_path = self._normalize_path(default_target_path) or "/"
        self._http = None  # 懒加载 httpx.Client

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

        :param share_url: 115 分享链接（含提取码），如 ``https://115.com/s/xxxxxxxx?password=yyyy``
        :param target_path: 115 目标目录路径（如 ``/电影``）或数字 cid。留空用默认目录。
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

        logger.info(f"【TG115】手动转存 share_url={share_url} target={effective}")
        # 目标目录：纯数字视为 cid 直接用；否则按路径查找/创建
        try:
            if effective.isdigit():
                parent_id = effective
            else:
                parent_id = self._get_or_create_cid(effective)
        except Exception as e:
            return False, f"定位 115 目标目录失败: {e}", result

        # share_receive 需要在表单里带 user_id（UID 的数字部分）
        user_id = ""
        for _part in self.cookie.split(";"):
            _part = _part.strip()
            if _part.startswith("UID="):
                user_id = _part[4:].split("_")[0].strip()
                break

        # 1. share_snap 获取分享文件列表（含真实 file_id；file_id=0 会导致参数错误）
        file_id = 0
        try:
            snap = self._api_get("/share/snap", {
                "share_code": share_code, "receive_code": receive_code,
                "cid": 0, "limit": 32, "offset": 0,
            })
            logger.info(f"【TG115】share_snap 响应: {str(snap)[:400]}")
            if isinstance(snap, dict) and snap.get("state") not in (True, 1, "1"):
                snap_err = snap.get("error") or snap.get("message") or "分享不可用"
                return False, f"分享链接不可用：{snap_err}", result
            snap_data = snap.get("data") if isinstance(snap, dict) else None
            if isinstance(snap_data, dict):
                fl = snap_data.get("list") or snap_data.get("filelist") or []
                if fl and isinstance(fl[0], dict):
                    file_id = fl[0].get("fid") or fl[0].get("cid") or 0
            logger.info(f"【TG115】从分享信息提取 file_id={file_id}")
        except Exception as e:
            logger.warn(f"【TG115】share_snap 异常（继续用 file_id=0）: {e}")

        # 2. share_receive 转存（带真实 file_id + user_id）
        payload = {
            "share_code": share_code,
            "receive_code": receive_code,
            "file_id": file_id,
            "cid": str(parent_id),
            "is_check": 0,
            "user_id": user_id,
        }
        logger.info(f"【TG115】转存 payload={payload}")
        try:
            resp = self._api_post("/share/receive", payload)
            logger.info(f"【TG115】share_receive 响应: {str(resp)[:300]}")
        except Exception as e:
            logger.error(f"【TG115】share_receive 异常: {e}")
            return False, f"调用 115 转存接口失败: {e}", result

        if not self._response_ok(resp):
            err = self._response_error(resp) or "115 转存失败"
            if self._is_already_saved(err):  # 已转存视为成功（幂等）
                result.update({"share_code": share_code, "parent_id": parent_id})
                return True, "115 转存已存在（之前已转存）", result
            result.update({"parent_id": parent_id, "raw": self._jsonable(resp)})
            return False, err, result

        result.update({
            "share_code": share_code, "receive_code": receive_code,
            "parent_id": parent_id, "raw": self._jsonable(resp),
        })
        return True, "115 转存成功", result

    # ============================ 目录操作（供 __init__ 的浏览/验证 API 用）============================
    def fs_files(self, cid: Any = 0) -> Dict[str, Any]:
        """列某 cid 下的内容（GET /files）。cid=0 为根目录。返回 115 原始 JSON dict。"""
        return self._api_get("/files", {"cid": str(cid or 0), "limit": 50, "offset": 0})

    def fs_info(self, cid: Any) -> Dict[str, Any]:
        """查某 cid 的信息（GET proapi /open/folder/get_info?file_id=，与 p115client 一致）。
        返回 115 原始 JSON dict。"""
        return self._api_get("/open/folder/get_info", {"file_id": str(cid)}, base=self._PROAPI)

    # ============================ 内部工具 ============================
    def _get_or_create_cid(self, path: str) -> str:
        """根据路径获取目录 cid，不存在则创建。根目录返回 '0'。

        逐段导航：从根 cid=0 开始，对路径每一段在当前目录下查找同名子目录；
        找不到则 POST /files/add 创建。返回最终 cid（字符串）。
        """
        target = self._normalize_path(path) or "/"
        if target == "/":
            return "0"
        pid = "0"
        for seg in target.strip("/").split("/"):
            seg = seg.strip()
            if not seg:
                continue
            # 在 pid 下找同名目录
            cid = self._find_subdir(pid, seg)
            if cid:
                pid = cid
                continue
            # 不存在则创建
            cid = self._mkdir(pid, seg)
            if not cid:
                raise RuntimeError(f"无法创建 115 目录: {seg}（请手动创建 {target} 后重试）")
            pid = cid
        return pid

    def _find_subdir(self, parent_cid: str, name: str) -> str:
        """在 parent_cid 下查找名为 name 的子目录 cid，找不到返回 ''。"""
        try:
            resp = self.fs_files(parent_cid)
        except Exception:
            return ""
        if not isinstance(resp, dict) or resp.get("state") not in (True, 1, "1"):
            return ""
        data = resp.get("data")
        items = data if isinstance(data, list) else (data.get("data", []) if isinstance(data, dict) else [])
        for it in items:
            if not isinstance(it, dict):
                continue
            if it.get("sha1"):  # 文件才有 sha1，跳过
                continue
            n = it.get("name") or it.get("n") or ""
            if n == name:
                return str(it.get("cid", it.get("id", "")))
        return ""

    def _mkdir(self, parent_cid: str, name: str) -> str:
        """在 parent_cid 下创建子目录 name（POST proapi /open/folder/add {file_name, pid}，
        与 p115client fs_mkdir 一致）。创建后重新列父目录按名取新 cid（不依赖响应里的
        cid 字段，避免响应格式差异），失败返回 ''。"""
        try:
            self._api_post("/open/folder/add",
                           {"file_name": name, "pid": str(parent_cid)}, base=self._PROAPI)
        except Exception as e:
            logger.warn(f"【TG115】创建目录 {name} 异常: {e}")
            return ""
        # 重新列父目录按名找到新建目录 cid（可靠，不依赖 create 响应格式）
        return self._find_subdir(parent_cid, name)

    def _client(self):
        """懒加载 httpx.Client（带 Cookie + Chrome UA + 20s 超时）。"""
        if self._http is not None:
            return self._http
        import httpx
        self._http = httpx.Client(
            timeout=20.0,
            headers={
                "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cookie": self.cookie,
            },
            follow_redirects=True,
            trust_env=False,  # 115 接口直连，彻底绕过 docker HTTP_PROXY 环境变量
        )
        return self._http

    def _api_get(self, path: str, params: Dict[str, Any], base: str = None) -> Dict[str, Any]:
        from urllib.parse import urlencode
        base = base or self._API
        url = f"{base}{path}?{urlencode(params)}"
        resp = self._client().get(url)
        return self._parse_json(resp)

    def _api_post(self, path: str, data: Dict[str, Any], base: str = None) -> Dict[str, Any]:
        base = base or self._API
        url = f"{base}{path}"
        resp = self._client().post(url, data=data,
                                   headers={"Content-Type": "application/x-www-form-urlencoded"})
        return self._parse_json(resp)

    @staticmethod
    def _parse_json(resp) -> Dict[str, Any]:
        import json as _json
        try:
            return resp.json()
        except Exception:
            try:
                return _json.loads(resp.text)
            except Exception:
                return {"state": False, "error": resp.text[:200]}

    @staticmethod
    def _extract_payload(url: str) -> Tuple[str, str]:
        """从 115 分享链接解析 share_code / receive_code。"""
        url = str(url or "").strip()
        if not url:
            return "", ""
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
