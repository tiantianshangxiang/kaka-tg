# TG频道搜索115优先转存（tgsearch115）

MoviePilot 插件：**订阅新增时，优先到指定的 Telegram 频道搜索 115 网盘资源**，命中并转存成功后自动完成订阅；未命中或转存失败则**平滑回退**到 MoviePilot 默认的 BT/PT 站点搜索流程，不影响主程序。

---

## 一、目录结构

```
tgsearch115/
├── __init__.py          # 插件主类：配置页面 / 事件监听 / 流程编排 / 回退
├── tg_searcher.py       # Telethon User Session 读取 TG 频道历史 + 提取 115 链接
├── p115_transfer.py     # p115client + Cookie 调 share_receive 转存到 115 目录
├── gen_tg_session.py    # 本地一次性生成 Telethon Session String 的辅助脚本
├── requirements.txt     # 依赖：telethon、p115client
└── README.md
```

安装方式：把整个 `tgsearch115` 目录放到 MoviePilot 的插件目录（通常为 `/config/plugins` 或在插件市场安装），重启后在「插件」页面配置即可。

---

## 二、实现解析

### 1. 拦截哪个事件 / 方法

**选择：监听广播事件 `EventType.SubscribeAdded`**（`@eventmanager.register(EventType.SubscribeAdded)`）。

原因：

- `SubscribeAdded` 事件由 `app/chain/subscribe.py` 的 `SubscribeChain.add` / `async_add` 在订阅创建时发出，事件数据为 `{subscribe_id, username, mediainfo}`，是最早能拿到"新订阅"的时机，满足"优先拦截"。
- 它是**广播事件**，由 `EventManager` 的独立消费者线程派发；本插件在处理器内**再起一个守护线程**执行 TG 搜索 + 115 转存，因此**绝不会阻塞 MoviePilot 主流程或事件总线**。
- MoviePilot 自带的定时订阅搜索（`SubscribeChain.search`）对新订阅有 `1 分钟 + 随机 1~5 分钟` 的延迟才开始；只要本插件在这之前转存成功并标记订阅完成（订阅被删除），默认搜索就再也不会处理它——天然实现"优先拦截"。若本插件任何环节 return，订阅仍在，默认搜索照常进行——天然实现"平滑回退"。
- 没有选择介入 `SubscribeChain.search` 内部或 `ResourceSelection` 链式事件，是因为那样需要侵入/替换 MP 的搜索链路，副作用大、升级易碎；事件驱动 + 独立线程是最稳妥、最解耦的方式。

### 2. 如何调用 MoviePilot 内置的识别与过滤逻辑

- **媒体识别**：`SubscribeChain().recognize_media(meta=meta, mtype=..., tmdbid=..., doubanid=..., episode_group=..., cache=False)`，与 `SubscribeChain.search` 完全一致；识别失败时用订阅字段构造最小 `MediaInfo` 兜底。
- **规则匹配（核心）**：把每条 TG 命中构造成 `TorrentInfo`，调用 `SubscribeChain().filter_torrents(rule_groups=..., torrent_list=..., mediainfo=...)`。`filter_torrents` 会调用 MoviePilot 的 `app/modules/filter` 过滤模块（Rust 加速 + Python 兜底），按用户在 MP 中配置的**过滤规则组**（分辨率、字幕组、特效字幕、包含/排除等）进行匹配并赋予优先级，**只有符合 MP 规则的资源才返回**。
- **规则组选取**：与 `SubscribeChain.search` 完全一致——`subscribe.filter_groups` 优先，否则取系统默认 `SystemConfigKey.SubscribeFilterRuleGroups`（洗版取 `BestVersionFilterRuleGroups`）。
- **内联过滤**：再叠加订阅自身的 `include/exclude/quality/resolution/effect`（基于 `MetaInfo` 识别结果比对），作为规则组的补充。

### 3. 如何调用 115 转存（关键事实 + 选型）

**事实：MoviePilot 并没有公开的 115 转存 API。** 经源码核对：

- `app/modules/filemanager/storages/u115.py` 的 `U115Pan` 是基于 **OAuth** 的存储模块，只提供 `list / create_folder / upload / download / move / copy` 等能力，**没有 `share_receive`（分享链接转存）方法**。
- `app/schemas/types.py` 虽定义了 `DownloaderType.U115`，但 `app/modules` 下**并没有对应的 U115 下载器实现**（下载器只有 qbittorrent / transmission / rtorrent）。

因此"分享链接转存"无法走 OAuth 的 `U115Pan`，而必须走 **Cookie 鉴权的 115 Web API**。本插件采用社区标准方案（与插件市场中 P115StrmHelper、agentresourceofficer 的转存实现一致）：

- 使用 `p115client`，以用户配置的 **115 扫码客户端 Cookie** 初始化 `P115Client`；
- 解析分享链接的 `share_code` / `receive_code`（优先用 `p115client.util.share_extract_payload`，兜底正则）；
- 解析/创建目标目录 `cid`（`client.fs_dir_getid`，不存在则 `client.fs_makedirs_app`）；
- 调用 `client.share_receive({share_code, receive_code, file_id:0, cid:目标cid, is_check:0})` 完成转存；
- "已转存"视为成功（幂等），转存失败则整体回退。

这正是用户要求的"若 MP 内置 115 接口为非公开 API，给出最稳妥的调用方式"——`p115client` 是对 115 Web API 的成熟封装，比手写反射 `U115Pan._request_api` 更稳健，且 `share_receive` 是 OAuth 开放平台未暴露的接口。

### 4. 转存成功后如何标记订阅完成

按用户选择"直接标记订阅完成"，镜像 `SubscribeChain.__finish_subscribe` 的公开实现：

1. `SubscribeOper().add_history(**subscribe.to_dict())` 写入订阅历史；
2. `SubscribeOper().delete(subscribe.id)` 删除订阅；
3. `eventmanager.send_event(EventType.SubscribeComplete, {...})` 发出订阅完成事件，保持与 MP 原生完结流程一致（其他插件/统计能正常感知）；
4. `self.post_message(...)` 推送成功通知。

### 5. 失败回退机制

任何环节失败都 `return` 且**不修改订阅**，确保 MP 默认搜索继续：

| 阶段 | 失败情形 | 处理 |
|------|----------|------|
| 识别 | `recognize_media` 失败且兜底也失败 | return |
| TG 搜索 | 频道未命中 / Session 失效 / 网络异常 | return |
| 规则匹配 | 无资源符合 MP 过滤规则 | return |
| 115 转存 | Cookie 无效 / 解析失败 / `share_receive` 失败 | return |
| 兜底 | 任何未预期异常（try/except 包裹） | return |

全程守护线程 + 异常兜底，**不会导致主程序卡死或报错**。

---

## 三、配置项（UI）

| 配置项 | 说明 |
|--------|------|
| 启用插件 | 功能总开关 |
| TG API ID / TG API Hash | my.telegram.org 申请 |
| TG 频道 | `@username` / `t.me/xxx` 链接 / 数字 ID |
| TG Session String | 用 `gen_tg_session.py` 本地生成后粘贴 |
| 最大检索消息数 | 默认 200 |
| TG 代理 | 可选，如 `socks5://127.0.0.1:1080`（需 `telethon[socks]`） |
| 触发延迟（秒） | 留出 DB 提交与用户编辑订阅窗口，默认 3 |
| 115 Cookie | 扫码客户端 Cookie，需含 `UID/CID/SEID` |
| 115 转存目标目录 | 路径如 `/电影`，不存在自动创建 |
| 使用 MP 过滤规则组二次匹配 | 默认开 |
| 转存成功通知 / 未命中失败通知 | 消息开关 |

---

## 四、依赖说明

`requirements.txt`：

```
telethon>=1.36.0
p115client>=0.9.7
```

Docker 内安装：

```bash
docker exec -it moviepilot pip install telethon p115client
```

使用 SOCKS 代理还需 `pip install "telethon[socks]"`（即 `python-socks`）。

> 依赖在插件代码中均为**延迟导入**（`telethon` / `p115client` 在方法内 import），因此即使依赖未安装，插件也能正常加载，仅在使用时给出清晰告警。

---

## 五、首次使用步骤

1. `pip install telethon` 后本地运行 `python gen_tg_session.py`，得到 Session String。
2. 获取 115 Cookie：用 115 客户端扫码登录后抓取 Cookie，确保含 `UID/CID/SEID`（网页版 Cookie 不可用）。
3. 把 `tgsearch115` 目录放入 MP 插件目录，重启 MP，安装依赖。
4. 在插件配置页填入上述信息，启用插件。
5. 新增一个订阅，观察日志（关键字 `【TG115】`）即可看到优先搜索 -> 匹配 -> 转存 -> 完成的全流程；未命中时会自动回退到默认站点搜索。
