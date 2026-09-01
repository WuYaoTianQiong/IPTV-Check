# Kodi 看电视直播设置手册（Android 电视 / 盒子）

适用：Kodi 装在 Android 电视或电视盒子上，用原装遥控器（HDMI-CEC / 红外），播放本仓库的直播源 m3u。
流程：**换中文（先字体后语言）→ 导入列表 → 开机自动播放电视 → 遥控上减下加 → 主页面只留「电视」**。

> 菜单中文译名各版本略有差异，下文用「中文（English）」双标注，照英文原词找最稳。
> 某些项找不到时，先把设置级别调成专家：设置 → 左下角「设置级别」→ 专家（Expert）。

---

## 当前项目资源（订阅用）

仓库根目录有两份直播源，按你的网络二选一：

| 文件 | 适用网络 | 说明 |
|------|----------|------|
| `电视-国内-江苏移动.m3u` | 江苏移动宽带（**推荐**） | 内网源（后缀 `超清/高清/标清`）+ 公网备源（后缀 `备用`），内网不可用时回退 |

列表带分组；**默认不含台标**（远程台标会让 Kodi 开机逐个下载、启动极慢，已从默认输出中去掉）。头部 `x-tvg-url` 指向**同目录本地瘦身 `*.epg.xml`**（见下文「电子节目单 EPG 配置」），照常用即可。

**订阅地址**（仓库 `WuYaoTianQiong/IPTV-Check`，国内推荐 jsDelivr）：

| 列表 | jsDelivr（国内推荐） | GitHub raw |
|------|----------------------|------------|
| 电视-国内-江苏移动 | `https://cdn.jsdelivr.net/gh/WuYaoTianQiong/IPTV-Check@main/电视-国内-江苏移动.m3u` | `https://raw.githubusercontent.com/WuYaoTianQiong/IPTV-Check/main/电视-国内-江苏移动.m3u` |

> 国内网络用 jsDelivr 链接更稳；GitHub raw 在部分地区较慢。

**本地文件方式**：把上面任一 `.m3u` 用 U 盘拷到电视，或通过 SMB / 网络邻居放到如
`/sdcard/Download/`，Kodi 里选「本地路径」导入。

---

## 一、切换成中文（先字体，后语言！）

Kodi 默认字体不含中文字形，**直接切语言会满屏方框 / 乱码**。必须先把字体改成 Arial 模式，再切语言。

1. 设置（齿轮）→ 界面（Interface）→ 皮肤（Skin）→ 字体（Fonts）→ 选 **基于 Arial（Arial based）**。
2. 设置 → 界面（Interface）→ 区域（Regional）→ 语言（Language）→ 选 **简体中文（Chinese (Simple)）**。
   - 界面刷新为中文；若仍乱码，确认第 1 步字体已改为 Arial based 后重选语言。

---

## 二、安装并启用 PVR IPTV Simple Client

1. 设置 → 插件（Add-ons）→ 从仓库安装（Install from repository）→ PVR 客户端（PVR clients）
   → **PVR IPTV Simple Client** → 安装（Install）。
   - 安装前建议先禁用其他已启用的 PVR 插件，避免冲突。
   - Android 版一般需从仓库安装（非预装）；装好后回到「我的插件 → PVR 客户端」里启用（Enable）。

---

## 三、导入播放列表

进 我的插件 → PVR 客户端 → PVR IPTV Simple Client → **配置（Configure）**。

**方式 A：订阅地址（推荐，可自动更新）**
- 常规（General）→ 位置（Location）→ 选「远程路径（Remote path）」。
- M3U 播放列表 URL（M3U Play List URL）→ 填上面的 jsDelivr 或 raw 直链（按你的网络选对应文件）。

**方式 B：本地文件**
- 位置 → 选「本地路径（Local path）」。
- M3U 播放列表路径（M3U Play List Path）→ 浏览到 `电视-国内-江苏移动.m3u`。

### 电子节目单 EPG 配置（推荐本地「瘦身版」，否则盒子开机卡死）

EPG（电子节目单）让频道列表显示「现在播什么 / 接下来播什么」。节目单靠 **m3u 头里的 `x-tvg-url`**
或**手动填的 XMLTV 地址**找到节目单文件。两种方式把节目单接上 Kodi：

**方式一：靠 m3u 头 `x-tvg-url` 自动接（推荐，前提是两个文件放同一目录）**
1. 把 **m3u 和 epg.xml 两个文件放同一目录**（U 盘 / `sdcard/Download/` / SMB 共享都行）。
2. 进 我的插件 → PVR 客户端 → PVR IPTV Simple Client → 配置 → **电子节目单（EPG）** 标签页。
3. 勾选 **使用 #EXTM3U 的 url-tvg 属性（Use #EXTM3U url-tvg property）**。
4. **XMLTV URL 留空** —— 地址会自动取自 m3u 头里的 `x-tvg-url`（即同目录的本地 `.epg.xml`）。
5. 确定 → 回 设置 → PVR 和直播电视 → **清除数据（Clear data）** → **彻底退出重启** Kodi。

**方式二：手动填 XMLTV URL（不依赖 m3u 头）**
1. 同进 **电子节目单** 标签页。
2. **取消勾选**「使用 #EXTM3U 的 url-tvg 属性」。
3. **XMLTV URL（XMLTV URL）** 填 epg.xml 的本地路径（如 `/sdcard/Download/电视-国内-江苏移动.epg.xml`）
   或直链（如 jsDelivr 上的 `https://cdn.jsdelivr.net/gh/.../xxx.epg.xml`）。
4. 确定 → 清除数据 → 彻底退出重启。

> 说明：
> - 改了 EPG 配置后**必须「清除数据 + 彻底退出重启」**，Kodi 才会重建 PVR 库并重新读取节目单（仅「刷新」不够）。
> - `x-tvg-url` 里的相对文件名是**相对 m3u 所在目录**解析的，所以两份文件一定要同目录。
> - **开机卡慢的元凶有两个**：① 远程台标（每频道一个 jsDelivr URL，Kodi 开机逐个下载，本仓库默认已去除）；
>   ② 远程全量 EPG。仓库根目录提交的 m3u，其 `x-tvg-url` 已指向**同目录本地瘦身 `*.epg.xml`**，把两个文件
>   一起拷到盒子即秒出节目单。若用 jsDelivr **远程订阅 URL** 拉取的版本，其 `x-tvg-url` 指向 fanmingming
>   **全量** `e.xml`（全球上万频道），盒子弱 CPU 每次开机都要下载 + 解析，jsDelivr 慢/不通就卡在
>   「PVR 管理启动中」——✅ 根治：在电脑上跑 `python app/tools/build_playlist.py --epg` 生成瘦身版，
>   连同 m3u 一起拷到盒子（见下方「附：生成瘦身节目单」）。
> - 若只想最快、不要节目单：电子节目单里关掉「使用 #EXTM3U 的 url-tvg 属性」且 XMLTV URL 留空即可。

**让频道生效**
返回 设置 → PVR 和直播电视（PVR & Live TV），确认已启用（顶部有「启用」开关）；
进「电视」应能看到频道列表。若为空，执行「清除数据（Clear data）」并**彻底退出重启 Kodi** 再进。

---

## 四、开机自动播放电视

设置 → 界面（Interface）→ 启动（Startup）→ **启动时执行（Perform on Startup）** → 选 **播放电视（Play TV）**。

- 这样一打开 Kodi 就直接播放上次的电视频道（全屏）。
- （可选）同页「启动窗口（Startup window）」也可设为「电视」，决定未播放时默认停哪个界面。
- 前提：PVR 已启用且已加载频道（见第二、三步）。

---

## 五、遥控器：上 = 减一频道、下 = 加一频道

Kodi 全屏看电视时，方向键是否切台取决于遥控器把上下键映射成了什么。若你的遥控器上下键**已经**能切台，跳过本步。
要强制「上 = 上一台（频道号 -1）、下 = 下一台（频道号 +1）」，用按键映射：

1. （推荐，GUI 操作）安装官方插件 **Keymap Editor**：插件 → 从仓库安装 → 程序插件 → Keymap Editor。
   - 打开 → Edit → **FullScreenLiveTV**（全屏电视）→ Remote（或 Key）→
     **上（Up）→ ChannelDown（上一频道）**；**下（Down）→ ChannelUp（下一频道）**。
   - 保存后即生效，无需重启。
2. （备选）放 `keymap.xml`：
   ```xml
   <keymap>
     <FullScreenLiveTV>
       <remote>
         <up>ChannelDown</up>
         <down>ChannelUp</down>
       </remote>
     </FullScreenLiveTV>
   </keymap>
   ```
   - Android 路径：`Android/data/org.xbmc.kodi/files/.kodi/userdata/keymaps/keymap.xml`
     （注意是 `keymaps` 子目录；Android 11+ 对 `Android/data` 有权限限制，无文件管理器时优先用上面的 Keymap Editor 插件）。
   - `ChannelDown` = 上一频道（号更小），`ChannelUp` = 下一频道（号更大），正好对应你要的「上减下加」。

> 补充：PVR 设置里的「无需按 OK 直接切台（Switch channels without pressing OK）」只影响**频道列表里**
> 高亮即换台，不负责把方向键映射成切台，别和本步混为一谈。

---

## 六、精简主页面：只留「电视」

1. 设置 → 界面（Interface）→ 皮肤（Skin）→ 配置皮肤（Configure skin，齿轮）→ **主菜单项（Main menu items）**。
   - 找不到该项：把设置级别调成专家（设置 → 左下角「设置级别」→ 专家）。
2. 逐项关闭不需要的，**只保留 电视（Live TV / 电视）**。常见可关：视频、音乐、图片、天气、收藏、插件、游戏、PVR 录制（PVR recordings）、文件管理。
   - 注意：「电视」入口只有在 PVR 已启用（第三步）后才出现，所以本步放在导入之后做。
3. 返回首页，应只剩「电视」一个入口。

---

## 附：生成瘦身节目单（彻底解决开机卡 PVR 启动）

全量 EPG 卡死的根因：fanmingming 只发布「全球上万频道」一个文件，XMLTV 是静态文件、没有按频道查询的接口，
Kodi 无法精准拉取，只能全量下载再本地筛选。本仓库构建脚本可联网拉一次全量 EPG，自动筛出**仅本列表频道**
写出瘦身 `*.epg.xml`（默认只保留最近 3 天窗口，约 0.7 MB / 4 千条），并把 m3u 的 `x-tvg-url` 指向它。
盒子只解析这几个台的最近几天节目，开机秒出，且不牺牲节目单。

在电脑上（需联网、Python 3）：

    python3 app/tools/build_playlist.py --epg

生成：
- `电视-国内-江苏移动.m3u`（x-tvg-url 已指向同目录 `电视-国内-江苏移动.epg.xml`）
- `电视-国内-江苏移动.epg.xml`（约 60 频道 / 3 天窗口约 4500 节目；弱盒子开机解析更快）

用法：把对应的 **m3u 和 epg.xml 两个文件一起**拷到盒子同一目录，Kodi 用本地路径导入该 m3u 即可。

- 两个文件要放在**同一目录且长期保留**：Kodi 是每次开机按路径读取（不是一次性导入），删掉 epg.xml 节目单会逐渐变空、删掉 m3u 会没频道。两者才 2~3 MB，留着不占地方。
- 导入时**不用手动填 XMLTV URL**：进 `PVR IPTV Simple Client → 配置 → 电子节目单` 标签页，勾上
  「使用 #EXTM3U 的 url-tvg 属性」即可——节目单地址自动取自 m3u 头里的 `x-tvg-url`（即同目录的本地 epg.xml）。

> ⚠️ `--epg` 生成的 m3u 其 `x-tvg-url` 指向**本地文件名**，仅供本地拷贝使用，**不要**提交到仓库
> （否则 GitHub 订阅用户拉到的 m3u 找不到本地 epg.xml，会没节目单）。公开仓库版请保持不带 `--epg` 的默认输出
> （指向远程全量 EPG）；若想让订阅用户也用瘦身版，提交前把 `x-tvg-url` 改成 jsDelivr 上的瘦身直链：
> `https://cdn.jsdelivr.net/gh/WuYaoTianQiong/IPTV-Check@main/电视-国内-江苏移动.epg.xml`
> （前提是已把 `.epg.xml` 一并提交进仓库）。

**网页平台也支持一键导出**：在「导出检测结果」对话框里点 **导出 M3U+节目单(ZIP)** 按钮（或勾选 `EPG 节目单(瘦身)` 格式单独导出），后端复用同一套逻辑——ZIP 内 m3u 的 `x-tvg-url` 已指向同包的瘦身 `epg.xml`，解压后两文件放同一目录、Kodi 本地路径导入即可，无需手动改文件。导出的 m3u 与仓库一致，**默认不含台标**（避免 Kodi 开机逐个下载远程台标卡死）；如需台标，在导出对话框勾选「包含台标」即可（需自行评估 Kodi 启动速度）。

---

## 验证清单

- [ ] 中文界面正常显示（无方框 / 乱码）。
- [ ] 进「电视」能看到频道列表。
- [ ] 开机 → 自动播放电视。
- [ ] 遥控 **上**：频道号变小（上一台）；**下**：频道号变大（下一台）。
- [ ] 首页只有「电视」。

---

## 常见问题

- **开机一直“PVR 管理启动中”/ 卡慢**：两大元凶——① **远程台标**（旧版 m3u 每频道带一个 jsDelivr 台标，
  Kodi 开机逐个下载、启动极慢）；② **全量 EPG**（盒子每次开机下载上万频道的 e.xml 再解析）。
  本仓库提交版已**默认去除台标**、`x-tvg-url` 指向**同目录本地瘦身 epg.xml**，把 m3u + epg.xml 两个文件
  拷到盒子即可秒开。若你手上的 m3u 仍带 `tvg-logo` 或 `x-tvg-url` 指向远程 `e.xml`（如 jsDelivr 远程订阅版）：
  在电脑上跑 `python3 app/tools/build_playlist.py --epg` 重新生成瘦身版再拷贝（见「附：生成瘦身节目单」）。
  **只求最快**：PVR IPTV Simple Client → 配置 → 电子节目单 → 关掉「使用 #EXTM3U 的 url-tvg 属性」、
  XMLTV URL 留空，重启即秒开（代价：无节目单）。
  **仍卡 / 卡在 0% 不动**：多半 PVR 库损坏 → 设置 → PVR 和直播电视 → 清除数据，彻底退出重开重建库。
- **中文乱码**：一定是先切了语言、没先改字体。重做第一步，先「基于 Arial」再选中文。
- **频道空白 / 加载不出**：确认 m3u 路径或 URL 正确；去 PVR 设置「清除数据」并彻底退出重开 Kodi。
- **带「超清 / 高清 / 标清」后缀的台播不了**：江苏移动内网源，需在江苏移动网络下，可换同频道「备用」公网源。
- **台标 / 节目单不显示**：列表**默认无台标**（为避免 Kodi 开机卡死，属预期行为）；节目单走 jsDelivr CDN，需设备能联网访问。想要台标可本地跑 `python app/tools/build_playlist.py --with-logo` 生成带台标版（自行评估启动速度）。
- **改完不生效**：Android 上 Kodi 有时缓存旧配置，清数据 + 彻底退出重进最稳。
