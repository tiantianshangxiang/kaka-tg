# 拦截mp订阅（tgsearch115）

MoviePilot 插件：订阅新增时优先从 Telegram、观影和聚影搜索资源，经 MoviePilot 原生媒体识别确认后转存匹配的 115 分享，或把完整观影磁力通过 CMS 离线到 115；失败时平滑回退到 MoviePilot 默认搜索。

当前版本：`v4.6.0`。完整观影磁力经 MoviePilot 规则和媒体身份确认后，只通过 CMS 创建 115 离线任务；周期搜索使用单一优先队列、缓存、退避和来源熔断，CMS 任务按 BTIH 持久去重并等待 MoviePilot 整理历史确认完成。

---

## 一、核心特性

- **三源搜索**：TG 公开频道、观影资源站和聚影开发者 API
- **媒体身份确认**：使用 `MetaInfo`、`TorrentHelper` 和 `MediaChain` 校验标题、年份、类型、季号及 TMDB/豆瓣 ID
- **精准手动搜索**：TG/观影/聚影结果按规范化片名和年份过滤，并按分享码或 URL 去重
- **双客户端观影详情**：httpx/HTML 路径被 WAF 拒绝时，使用 urllib 独立 Cookie/PoW 会话降级
- **TG 服务端搜索**：用 `t.me/s/{channel}?q=片名` 让 Telegram 服务器搜频道**全部历史**（不是只看最近 200 条），解决「明明有资源却搜不到」
- **资源站 PoW 破解**：站点用 RSW 时间锁 PoW 反机器人，本插件用纯 Python `pow(x,1<<t,N)` 约 1.5 秒解出（C 层快速模幂），**无需浏览器、无新依赖**
- **115 自动转存**：命中 115 链接后用 `p115client` 的 `share_snap` + `share_receive` 转存到指定目录
- **115 磁力离线**：完整观影磁力经 MP 规则和媒体 ID 确认后，通过 CMS Token API 创建 115 离线任务
- **全网盘展示**：夸克/百度/阿里/迅雷等资源展示链接；115 分享可转存，磁力可通过 CMS 离线
- **115 扫码登录**：直连 115 二维码接口，扫码即得含 UID/CID/SEID 的 Cookie
- **订阅完成双模式**：`auto_finish` 开关——插件直接标记完成 / 让 MP 整理 115 后自己完成
- **自定义 Vue 前端**：Module Federation 暴露 Config/Page 组件，4 个标签页（手动转存 / 手动搜索 / TG 频道 / 插件设置）

---

## 二、目录结构

```
tgsearch115/
├── __init__.py          # 插件主类：事件监听 / 流程编排 / 12 个 API / 115 扫码登录
├── tg_scraper.py        # TG 频道爬虫：httpx + BS4，?q= 服务端搜全历史
├── site_scraper.py      # 目标资源站爬虫：解 PoW + 搜索 + 全网盘资源提取
├── juying_scraper.py    # 聚影开发者 API
├── identity_matcher.py  # MoviePilot 原生媒体身份确认
├── search_relevance.py  # 手动搜索片名/年份精准过滤
├── cms_client.py        # CMS 官方 Token API / 115 磁力离线
├── p115_transfer.py     # 115 转存：p115client share_snap + share_receive
├── requirements.txt     # beautifulsoup4 / p115client（httpx 随 p115client 安装）
├── README.md
└── frontend/            # Vue 3 + Vuetify 3 + Vite 5 (Module Federation)
    ├── src/components/Config.vue   # 配置弹窗（4 Tab）
    ├── src/components/Page.vue     # 详情页
    └── dist/assets/remoteEntry.js  # 构建产物（MP 前端远程加载）
```

安装：把整个 `tgsearch115` 目录放到 MoviePilot 插件目录（`/config/plugins` 或插件市场安装），重启即可。依赖（p115client / beautifulsoup4）启动时自动静默安装。

---

## 三、业务流程

```
订阅新增 (SubscribeAdded 事件)
  → 守护线程 _handle_subscribe（延迟 delay_seconds 抢跑 MP 默认搜索）
  → recognize_media 识别媒体
  → _build_keyword → 只用片名（不含年份）
  → 三源搜索：
      · TG 频道 scraper.search(keyword)          → 全 115 链接
      · 资源站 site_scraper.search(keyword, year) → 全网盘（115 占少数）
      · 聚影 juying_api.search(keyword, year)     → 官方 API 资源
  → _build_torrents 构造 TorrentInfo（115 链接自动补提取码）
  → _filter_resources 复用 MP 规则组 + include/exclude
  → 115 分享按 share_code 去重
  → 本地标题/别名/年份/类型/季号初筛
  → MediaChain 识别候选，TMDB/豆瓣 ID 与订阅一致
  → 完整观影磁力：CMS Token API → 115 离线任务 → 暂停订阅等待同步
  → 115 分享：transfer.transfer() → share_snap → share_receive → 完成订阅
  任何环节失败 → 静默 return，MP 默认搜索照常（平滑回退）
```

---

## 四、配置项

### 115 网盘登录区
| 项 | 说明 |
|----|------|
| 启用插件 | 总开关 |
| 115 Cookie | 扫码登录后自动填入（需含 UID/CID/SEID） |
| 115 转存目录 | 如 `/电影`，不存在自动创建；也可填数字 cid |

### 观影 Tab
| 项 | 说明 |
|----|------|
| 完整磁力优先离线到 115 | 启用后优先处理已确认的完整观影磁力 |
| CMS 服务地址 | Cloud Media Sync 地址，如 `http://host:9527` |
| CMS API Token | 对应 CMS 启动变量 `CMS_API_TOKEN` |
| 检查 CMS | 只读检查服务连通性，不创建离线任务 |

### 插件设置 Tab
| 项 | 说明 |
|----|------|
| 启用目标资源站 | 开启后搜索时同时查 xn--wcv59z.com |
| 资源站 app_auth | 登录站点后从浏览器 Cookie 取 `app_auth` 值 |
| 测试连通 | 解 PoW + 试搜，验证 app_auth 是否有效 |
| 插件直接标记完成 | auto_finish：True=插件标记完成；False=让 MP 整理 115 后完成 |
| MP 过滤规则组 | 复用 MoviePilot 订阅过滤规则组 |
| 触发延迟 / 通知开关 | 等 |

### TG 频道模块 Tab
- 单条添加 / JSON 批量导入 / 批量删除
- 仅支持公开用户名频道（如 `@share115`），私有频道无法网页抓取
- 代理自动用 MoviePilot 的 `settings.PROXY`

---

## 五、目标资源站原理（site_scraper.py）

站点 `xn--wcv59z.com` 用 **RSW 时间锁 PoW** 做反机器人：

1. `GET /` → 设 `browser_pow` cookie，返回验证页
2. `GET /res/pow` → 挑战 `{N, x, t}`（N=2048bit, t=200000）
3. 算 `y = x^(2^t) mod N`（连续平方 t 次）
4. `POST /res/pow {y}` → 设 `browser_verified` cookie 放行

**关键**：服务器只校验 `y` 的数学正确性，不校验耗时。JS 用解释型 worker 慢算（数秒），Python 内置 `pow(x, 1<<t, N)` 走 C 层快速模幂，**1.5 秒**算出相同 `y`。

资源 API：
- `GET /res/search_suggest?q=片名` → `[{title, id, dir, year, ename, score}]`
- `GET /res/downurl/{dir}/{id}` → `panlist: {url, name, p(提取码), tname(网盘类型)}`

网盘类型**按 URL 域名判定**（`tname` 是上传者自填，常不准）：115 / quark / baidu / aliyun / xunlei / cloud189 / uc。

> 注意：该站资源**大多是夸克/百度/阿里/迅雷，115 占比很小**。插件提取全部网盘；115 分享可直接转存，完整磁力可通过 CMS 离线到 115，其它网盘在手动搜索中展示链接与提取码。

---

## 六、后端 API（15 个，全部 `auth="bear"`）

挂载 `/api/v1/plugin/TgSearch115{path}`：

| 路径 | 作用 |
|------|------|
| `/config/get` `/config/save` | 读/存配置（即时生效） |
| `/check_channel` `/check_all` | 检查 TG 频道连通性 |
| `/qrcode/get` `/qrcode/status` | 115 扫码登录 |
| `/transfer` | 手动转存 115 分享链接 |
| `/magnet/offline` | 通过 CMS 创建 115 磁力离线任务 |
| `/check_cms` | 只读检查 CMS 服务与配置 |
| `/search` | 手动搜索（TG + 资源站，返回带网盘类型） |
| `/dir_info` `/dirs` | 115 目录查询/浏览 |
| `/verify_cookie` | 验证 115 Cookie |
| `/check_site` | 验证资源站 PoW + app_auth |

---

## 七、首次使用

1. **115 登录**：配置页点「扫码登录」，用 115 客户端扫码，Cookie 自动填入。
2. **TG 频道**：「TG 频道模块」Tab 添加公开频道（如 `@share115`）。
3. **资源站（可选）**：「插件设置」Tab 开启资源站，填入 `app_auth`（登录站点后从浏览器 Cookie 复制），点「测试连通」。
4. 开启插件，新增一个订阅，观察日志（关键字 `【TG115】`）。
5. 更新插件后若 UI 没变，**Ctrl+F5 强制刷新**或重启 MP（`remoteEntry.js` 无 cache-buster）。
