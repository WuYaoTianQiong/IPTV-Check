# IPTV-Check · 江苏移动宽带看电视直播源

![License](https://img.shields.io/badge/License-MIT-yellow.svg)

一份适配**江苏移动网络**的电视直播源列表，附带一个开源的直播源检测 / 管理平台。

## 📺 直接订阅，开始看电视

把下面任一地址导入你的 IPTV 播放器（TiviMate、IPTV、PotPlayer、VLC、Kodi 等均可）：

| 列表 | 适用场景 | jsDelivr（国内推荐） | GitHub raw |
|------|----------|----------------------|------------|
| **jiangsu-mobile.m3u** | 江苏移动宽带（内网源 + 外网备源，推荐） | `https://cdn.jsdelivr.net/gh/<用户名>/IPTV-Check@main/jiangsu-mobile.m3u` | `https://raw.githubusercontent.com/<用户名>/IPTV-Check/main/jiangsu-mobile.m3u` |
| **live.m3u** | 任意公网（仅含外网可播源） | `https://cdn.jsdelivr.net/gh/<用户名>/IPTV-Check@main/live.m3u` | `https://raw.githubusercontent.com/<用户名>/IPTV-Check/main/live.m3u` |

> 国内网络推荐用 jsDelivr 链接；GitHub raw 直链在部分地区访问较慢。

- `jiangsu-mobile.m3u`：项目主推版本，含江苏移动内网源（命名带 `超清/高清/标清` 后缀）和公网备源（`备用` 后缀），内网不可用时自动回退。
- `live.m3u`：纯公网版本，剔除所有运营商内网 IP，适合非江苏移动网络。

列表含央视 / 卫视 / 江苏地方台 / 少儿 / NEWTV / 港澳台等分组，台标与 EPG 来自 [fanmingming/live](https://github.com/fanmingming/live)（jsDelivr CDN 加速）。

---

## 🔧 检测 / 管理平台

运行 `python -m iptv_check.server.main` 启动服务，浏览器访问 `http://127.0.0.1:9528`；也可 Docker 一键部署：`docker compose up -d`。

### 核心功能

| 模块 | 功能亮点 |
|------|---------|
| 📺 播放 | HLS 在线播放（hls.js）、服务端代理、自定义防盗链头、自动错误恢复、分片 URL 重写 |
| 🔍 检测 | 流式检测、WebSocket 实时推送、多源合并去重、24h 缓存、运营商感知、IPv6/广播电台识别 |
| 📋 EPG 节目单 | XMLTV 解析、三级频道匹配、当前节目高亮、48h 缓存、手动刷新 |
| 🖼️ 台标 | 自动加载、多源匹配、30d 缓存、批量下载、Fallback 占位 |
| 📊 报告 / 趋势 | 关键指标、延迟分布、源排行；稳定频道 TOP50、单频道趋势、历史对比 |
| 🎯 智能推荐 | 多维度评分、自动优选、ISP 专属推荐、推荐 M3U 下载 |
| 📡 在线源管理 | 内置 18 个精选源、运营商匹配、IPv4/IPv6 标识、S/A/B/C 评级、国内镜像加速 |
| 💾 数据持久化 | SQLite 存储、历史快照、多级 diskcache 缓存、缓存管理 API |
| ⭐ 收藏 | 一键收藏、收藏夹分组、持久存储 |
| 📤 导出 / 服务 | M3U/TXT/CSV/Excel 导出、合并/分别模式、M3U 在线服务、格式转换、智能优选 |
| ⏰ 定时调度 | 定时自动检测、灵活配置、状态查询 |

### 快速开始

```bash
# 安装依赖
cd app/backend
pip install -e .

# 启动服务
python -m iptv_check.server.main

# 浏览器访问
# http://127.0.0.1:9528
```

### 配置说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| 连接超时 | 3 秒 | TCP 连接建立超时，建议 1-5 秒 |
| 读取超时 | 8 秒 | 接收响应数据超时，建议 5-30 秒 |
| 线程数 | 30 | 并发检测的线程数，建议 10-50 |
| 速度测试 | 关闭 | 开启后会测试每个源的下载速度（较慢） |
| 使用缓存 | 开启 | 开启后 24 小时内重复检测直接使用缓存 |

### 在线直播源库

内置源分为三大类（持续更新）：

- **国内电视**：范明明、vbskycn、Guovin、Kimentanm、suxuang、zbefine、ChinaIPTV、YueChan 等
- **国际电视**：iptv-org 中国频道、iptv-org 全球精选
- **广播电台**：IPRD 中国 / 美国 / 英国广播

**如何添加自定义源？** 编辑 `local_sources.json` 文件，按现有格式添加。

### 播放列表生成

```bash
python app/tools/build_playlist.py               # 重新生成 live.m3u + jiangsu-mobile.m3u
python app/tools/build_playlist.py --check-logo  # 生成并校验台标可达性
```

### 技术栈

- **后端**：FastAPI + Uvicorn · SQLModel/SQLite · aiohttp · diskcache · alembic
- **前端**：Vue 3 + Vite + shadcn-vue + Tailwind CSS · hls.js
- **架构**：Repository + Service Layer + Event Bus

---

## GitHub Actions 自动化

- `ci.yml`：backend 单元测试（Python 3.11/3.12 + ruff）+ frontend 构建与单测
- `probe-sources.yml`：手动触发的直播源可达性探测

## 许可证

MIT License
