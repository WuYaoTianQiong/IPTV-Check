# IPTV-Check · 江苏移动宽带看电视直播源

![License](https://img.shields.io/badge/License-MIT-yellow.svg)

一份适配**江苏移动网络**的电视直播源列表，附带一个开源的直播源检测 / 管理平台。

## 📺 直接订阅，开始看电视

把下面任一地址导入你的 IPTV 播放器（TiviMate、IPTV、PotPlayer、VLC、Kodi 等均可）：

| 列表 | 适用场景 | jsDelivr（国内推荐） | GitHub raw |
|------|----------|----------------------|------------|
| **电视-国内-江苏移动.m3u** | 江苏移动宽带（内网源 + 外网备源，推荐） | `https://cdn.jsdelivr.net/gh/WuYaoTianQiong/IPTV-Check@main/电视-国内-江苏移动.m3u` | `https://raw.githubusercontent.com/WuYaoTianQiong/IPTV-Check/main/电视-国内-江苏移动.m3u` |

> 国内网络推荐用 jsDelivr 链接；GitHub raw 直链在部分地区访问较慢。

- `电视-国内-江苏移动.m3u`：项目主推版本，以江苏移动内网源（命名带 `超清/高清/标清` 后缀）为主；无内网源的频道才保留外部公网源，每频道仅一条、已去重，均为国内频道。

列表含央视 / 卫视 / 江苏地方台 / 少儿 / NEWTV / 港澳台等分组。**默认不含台标**——远程台标会让 Kodi 等播放器开机逐个下载、启动极慢（一直 loading），普通用户开箱即用优先；EPG 来自 [fanmingming/live](https://github.com/fanmingming/live)（jsDelivr CDN 加速），仓库提交版已瘦身并指向同目录本地 `*.epg.xml`。需要台标时可本地跑 `python app/tools/build_playlist.py --with-logo` 生成带台标版（自行评估 Kodi 启动速度）。

---

## 📡 分洲公网源（单频道择优版）

除江苏移动内网源外，另附按「媒体类型 × 大洲」分类的**公网源集**。源来自公开 IPTV 源集的逐条甄选（媒体类型实测 + 国家/大洲归类）。**根目录即"单频道择优版"**：同一频道的多路来源已逐路实测（可达 + 延迟），每频道只保留质量最优的一路，并已通过**播放级验证**（逐条真实拉流解码、剔除无法播放的源）——导入即用，无需自行去重。全量多路容错版存放在 [`多源/`](多源/) 子目录。

> ⚠️ **分类 ≠ 可用保证**：公网源随时可能失效，本批源为甄选快照，非持续维护；某频道失效想找备份路时，可改订 `多源/` 下同名文件的对应频道。

**订阅地址**（把 `<文件名>` 换成下表文件名，中文可直接使用）：

- jsDelivr（国内推荐）：`https://cdn.jsdelivr.net/gh/WuYaoTianQiong/IPTV-Check@main/<文件名>`
- GitHub raw：`https://raw.githubusercontent.com/WuYaoTianQiong/IPTV-Check/main/<文件名>`

| 文件 | 条数 | 说明 |
|------|------|------|
| [电视-国内.m3u](电视-国内.m3u) | 339 | 央视/卫视/地方台，CCTV/CETV 编号频道带中文台名（如 CCTV-5 体育） |
| [电视-亚洲.m3u](电视-亚洲.m3u) | 29 | 日韩/东南亚/南亚/西亚 |
| [电视-欧洲.m3u](电视-欧洲.m3u) | 189 | 欧洲各国电视台 |
| [电视-美洲.m3u](电视-美洲.m3u) | 10 | 北美/拉美 |
| [电视-非洲大洋洲.m3u](电视-非洲大洋洲.m3u) | 1 | 非洲/澳洲 |
| [电台-国内.m3u](电台-国内.m3u) | 196 | 央广/省市电台/港澳台 |
| [电台-亚洲.m3u](电台-亚洲.m3u) | 160 | 亚洲各国电台 |
| [电台-欧洲.m3u](电台-欧洲.m3u) | 2449 | 欧洲电台（主力） |
| [电台-美洲.m3u](电台-美洲.m3u) | 821 | 北美/拉美电台 |
| [电台-非洲大洋洲.m3u](电台-非洲大洋洲.m3u) | 101 | 非洲/澳洲电台 |
| [电视-国内-影视轮播.m3u](电视-国内-影视轮播.m3u) | 73 | 剧集/动画等 24h 轮播（非直播） |

> 📁 **`多源/` 全量多路版**：与上表同名文件的"完整备份版"（每频道多路源，共 5553 条），订阅地址把前缀换成 `https://cdn.jsdelivr.net/gh/WuYaoTianQiong/IPTV-Check@main/多源/<文件名>`（或 GitHub raw 的 `.../main/多源/<文件名>`）。需要多路容错、或想自行对比择优时使用。

**怎么选**：江苏移动网络、求开箱即用稳定 → 用上面江苏移动版；通用公网或非江苏网络 → 默认用根目录单频道版（省心）；某台播不动想找备用源 → 到 `多源/` 对应文件里捞该频道其它路。

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
python app/tools/build_playlist.py               # 重新生成 电视-国内-江苏移动.m3u（默认无台标，避免 Kodi 开机卡死）
python app/tools/build_playlist.py --with-logo   # 生成并写入远程台标（会拖慢 Kodi 启动，谨慎）
python app/tools/build_playlist.py --check-logo  # 生成并联网校验台标可达性（隐含 --with-logo）
python app/tools/build_playlist.py --prune-dead  # 生成并联网剔除外部公网死链（运营商内网源始终保留）
python app/tools/build_playlist.py --epg         # 生成瘦身本地 EPG，x-tvg-url 指向同目录 *.epg.xml（本地拷贝用）
```

> 可用性探测仅做「HTTP 能否连通」的烟雾测试（返回 2xx 即视为可达），**不校验响应内容是否为合法媒体流、不测响应时延与播放质量**。需要更严格的播放级验证请用 `app/tools/probe_playlist.py`（可加 `--include-internal` 在对应运营商网络下实测内网源）。

### 命名规范

仓库根目录的订阅文件统一采用 `介质-区域-网络.m3u` 三段式命名，与电台、国外源并列时一眼可区分：

| 片段 | 取值示例 | 说明 |
|------|----------|------|
| 介质 | `电视` / `电台` | 内容类型，固定置于最前 |
| 区域 | `国内`(含港澳台) / `含国外` / `国际` | 是否含国外源，固定第二位 |
| 网络 | `公网` / `江苏移动` | 适用网络或运营商，置末位 |

示例：`电视-国内-江苏移动.m3u`（江苏移动内网 + 外网备源，国内频道）。将来含国外的版本可命名为 `电视-含国外-公网.m3u` / `电视-国际-公网.m3u`，广播类则为 `电台-国内-公网.m3u`。新增源请沿用此前缀约定，保持整份仓库命名成体系。

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
