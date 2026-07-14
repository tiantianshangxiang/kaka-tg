# TG频道搜索115优先转存 (tgsearch115)

MoviePilot 插件：**订阅新增时优先到指定 Telegram 频道搜索 115 网盘资源**，命中并转存成功后自动完成订阅；未命中或转存失败则平滑回退到 MoviePilot 默认站点搜索。

## 安装方式

将本仓库地址加入 MoviePilot 的 `PLUGIN_MARKET` 环境变量（逗号分隔），重启后在「插件」页面搜索 "TG频道搜索115优先转存" 并安装。

```yaml
environment:
  - PLUGIN_MARKET=https://github.com/<你的用户名>/<你的仓库>
```

安装时 MoviePilot 会自动安装依赖 `telethon`、`p115client`。

## 目录结构

```
├── package.v2.json          # 插件清单（MP 市场识别用）
└── plugins.v2/
    └── tgsearch115/         # 插件目录（目录名=类名小写）
        ├── __init__.py      # 插件主类 TgSearch115
        ├── tg_searcher.py   # Telethon 频道搜索
        ├── p115_transfer.py # 115 分享转存
        ├── gen_tg_session.py# 本地生成 TG Session String
        ├── requirements.txt
        └── README.md        # 详细说明与实现解析
```

## 首次使用

1. 本地运行 `python plugins.v2/tgsearch115/gen_tg_session.py` 生成 TG Session String。
2. 准备 115 扫码客户端 Cookie（含 UID/CID/SEID）。
3. 在插件配置页填入 TG api_id/api_hash/session/频道 + 115 Cookie + 转存目标目录，启用。

详见 `plugins.v2/tgsearch115/README.md`。
