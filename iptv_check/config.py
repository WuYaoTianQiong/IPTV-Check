import os
import sys

APP_VERSION = "4.0"
APP_TITLE = f"电视直播源检测工具 V{APP_VERSION}"

CACHE_FILE = "check_cache.json"
CACHE_EXPIRY_HOURS = 24
SETTINGS_FILE = "user_settings.json"
PAGES_PER_VIEW = 50

ISP_KEYWORDS = {
    "移动": ["移动", "chinamobile", "cmcc", "cmcci", "cncmcc", "mobile", "mobaibox", "中国移动", "211.136", "223.110"],
    "电信": ["电信", "chinatelecom", "ctc", "chinanet", "中国电信", "telecom", "202.96", "202.101", "116.", "222.7"],
    "联通": ["联通", "chinaunicom", "cucc", "unicom", "中国联通", "cnc", "221.2", "221.12", "221.13", "123.1"],
    "广电": ["广电", "cbn", "chinabroadnet", "broadnet", "中国广电"],
    "其他": ["鹏博士", "长城宽带", "中信网络", "铁通", "教育网"],
}

ISP_APIS = [
    {"url": "https://myip.ipip.net/json", "fields": ["data", "location"], "priority": 1},
    {"url": "https://httpbin.org/ip", "fields": ["origin"], "priority": 2},
    {"url": "https://ip.360.cn/IPQuery/ipquery", "fields": ["data", "loc"], "priority": 3},
    {"url": "https://whois.pconline.com.cn/ipJson.jsp?json=true", "fields": ["company", "isp", "org"], "priority": 4},
    {"url": "https://qifu-api.baidubce.com/ip/local/geo/v1/district", "fields": ["isp", "org"], "priority": 5},
    {"url": "https://ipapi.co/json/", "fields": ["org", "isp", "asn"], "priority": 6},
]

IP_PREFIXES = {
    "移动": [
        "211.136", "211.137", "211.138", "211.139", "211.140", "211.142",
        "211.143", "211.144", "211.145", "211.146", "211.147", "211.148",
        "223.110", "223.111", "223.112", "223.113", "223.114", "223.115",
        "223.116", "223.117", "223.118", "223.119", "223.120", "223.121",
        "117.136", "117.137", "117.138", "117.139", "117.140", "117.141",
        "117.142", "117.143", "117.144", "117.145", "117.146", "117.147",
        "117.148", "117.149", "117.150", "117.151", "117.152", "117.153",
        "117.154", "117.155", "117.156", "117.157", "117.158", "117.159",
        "117.160", "117.161", "117.162", "117.163", "117.164", "117.165",
        "117.166", "117.167", "117.168", "117.169", "117.170", "117.171",
        "117.172", "117.173", "117.174", "117.175", "117.176", "117.177",
        "117.178", "117.179", "117.180", "117.181", "117.182", "117.183",
    ],
    "电信": [
        "202.96", "202.97", "202.98", "202.99", "202.100", "202.101",
        "202.102", "202.103", "202.104", "202.105", "202.106", "202.107",
        "202.108", "202.109", "202.110", "202.111", "202.112", "202.113",
        "202.114", "202.115", "202.116", "202.117", "202.118", "202.119",
        "202.120", "202.121", "202.122", "202.123", "202.124", "202.125",
        "202.126", "202.127", "202.128", "202.129", "202.130", "202.131",
        "222.72", "222.73", "222.74", "222.75", "222.76", "222.77",
        "222.78", "222.79", "222.80", "222.81", "222.82", "222.83",
        "222.84", "222.85", "222.86", "222.87", "222.88", "222.89",
        "222.90", "222.91", "222.92", "222.93", "222.94", "222.95",
    ],
    "联通": [
        "221.2", "221.3", "221.4", "221.5", "221.6", "221.7",
        "221.8", "221.9", "221.10", "221.11", "221.12", "221.13",
        "221.14", "221.15", "221.16", "221.17", "221.18", "221.19",
        "221.20", "221.21", "221.22", "221.23", "221.24", "221.25",
        "123.1", "123.2", "123.3", "123.4", "123.5", "123.6",
        "123.7", "123.8", "123.9", "123.10", "123.11", "123.12",
        "123.13", "123.14", "123.15", "123.16", "123.17", "123.18",
        "123.19", "123.20", "123.21", "123.22", "123.23", "123.24",
        "123.25", "123.26", "123.27", "123.28", "123.29", "123.30",
    ],
}

PLAYER_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>播放：{name}</title>
<script src="/hls-static/hls.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {{ --bg: #0f0f0f; --surface: #1a1a1a; --text: #f0f0f0; --muted: #888; --primary: #3b82f6; --error: #ef4444; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Inter', 'Noto Sans SC', sans-serif; background: var(--bg); color: var(--text); height: 100vh; display: flex; flex-direction: column; overflow: hidden; }}
.header {{ padding: 12px 16px; background: var(--surface); border-bottom: 1px solid #2a2a2a; display: flex; align-items: center; justify-content: space-between; }}
.header-title {{ font-size: 15px; font-weight: 600; display: flex; align-items: center; gap: 8px; }}
.header-title svg {{ width: 18px; height: 18px; color: var(--primary); }}
.header-meta {{ font-size: 12px; color: var(--muted); }}
.player-container {{ flex: 1; display: flex; align-items: center; justify-content: center; position: relative; background: #000; }}
video {{ width: 100%; height: 100%; max-height: calc(100vh - 100px); object-fit: contain; }}
.stream-info {{ position: absolute; top: 16px; right: 16px; padding: 8px 12px; border-radius: 6px; background: rgba(0,0,0,0.75); backdrop-filter: blur(8px); font-size: 11px; color: var(--muted); z-index: 10; font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; line-height: 1.6; min-width: 140px; cursor: pointer; transition: opacity 0.2s; user-select: none; }}
.stream-info:hover {{ opacity: 1; }}
.stream-info .info-row {{ display: flex; justify-content: space-between; gap: 12px; }}
.stream-info .info-label {{ color: #666; }}
.stream-info .info-value {{ color: var(--text); font-weight: 500; }}
.status-badge {{ position: absolute; top: 16px; left: 16px; padding: 6px 12px; border-radius: 6px; background: rgba(0,0,0,0.7); backdrop-filter: blur(8px); font-size: 12px; color: var(--muted); display: flex; align-items: center; gap: 6px; z-index: 10; cursor: pointer; user-select: none; }}
.status-badge::before {{ content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--primary); animation: pulse 2s infinite; }}
.status-badge.error::before {{ background: var(--error); animation: none; }}
@keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.4; }} }}
.error-overlay {{ position: absolute; inset: 0; display: none; flex-direction: column; align-items: center; justify-content: center; gap: 12px; background: rgba(0,0,0,0.85); z-index: 20; }}
.error-overlay.active {{ display: flex; }}
.error-overlay svg {{ width: 48px; height: 48px; color: var(--error); }}
.error-overlay h3 {{ font-size: 18px; font-weight: 600; }}
.error-overlay p {{ font-size: 14px; color: var(--muted); max-width: 400px; text-align: center; padding: 0 20px; }}
.controls {{ padding: 12px 16px; background: var(--surface); border-top: 1px solid #2a2a2a; display: flex; align-items: center; gap: 12px; }}
.control-btn {{ background: transparent; border: 1px solid #3a3a3a; color: var(--text); padding: 8px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; gap: 6px; }}
.control-btn:hover {{ background: #2a2a2a; border-color: #4a4a4a; }}
.control-btn.primary {{ background: var(--primary); border-color: var(--primary); }}
.control-btn.primary:hover {{ background: #2563eb; }}
.volume-slider {{ width: 80px; accent-color: var(--primary); }}
</style>
</head>
<body>
<div class="header">
  <div class="header-title">
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 20.25h12m-7.5-3v3m3-3v3m-10.125-3h17.25c.621 0 1.125-.504 1.125-1.125V4.875c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125Z" /></svg>
    {name}
  </div>
  <div class="header-meta" id="url-display"></div>
</div>

<div class="player-container">
  <div class="status-badge" id="status">加载中...</div>
  <div class="stream-info" id="stream-info">
    <div class="info-row"><span class="info-label">分辨率</span><span class="info-value" id="info-resolution">-</span></div>
    <div class="info-row"><span class="info-label">码率</span><span class="info-value" id="info-bitrate">-</span></div>
    <div class="info-row"><span class="info-label">编码</span><span class="info-value" id="info-codec">-</span></div>
    <div class="info-row"><span class="info-label">帧率</span><span class="info-value" id="info-fps">-</span></div>
    <div class="info-row"><span class="info-label">缓冲</span><span class="info-value" id="info-buffer">-</span></div>
  </div>
  <div class="error-overlay" id="error-overlay">
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" /></svg>
    <h3>播放失败</h3>
    <p id="error-msg"></p>
  </div>
  <video id="video" controls></video>
</div>

<div class="controls">
  <button class="control-btn primary" id="play-btn" onclick="togglePlay()">
    <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
    播放
  </button>
  <button class="control-btn" onclick="toggleFullscreen()">
    <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M3 7v4h4M21 7v4h-4M3 17v-4h4M21 17v-4h-4"/></svg>
    全屏
  </button>
  <input type="range" class="volume-slider" min="0" max="1" step="0.05" value="1" oninput="video.volume=this.value">
</div>

<script>
var video = document.getElementById('video');
var statusEl = document.getElementById('status');
var errorOverlay = document.getElementById('error-overlay');
var errorMsg = document.getElementById('error-msg');
var playBtn = document.getElementById('play-btn');
var originalUrl = '{url}';
var isHls = originalUrl.indexOf('.m3u8') !== -1 || originalUrl.indexOf('/m3u8') !== -1;

document.getElementById('url-display').textContent = originalUrl.length > 60 ? originalUrl.slice(0, 60) + '...' : originalUrl;

function buildProxyUrl(url) {{
    return '/proxy?url=' + btoa(encodeURIComponent(url));
}}

function buildHlsProxyUrl(url) {{
    return '/proxy?url=' + btoa(encodeURIComponent(url));
}}

function showError(msg) {{
    errorOverlay.classList.add('active');
    errorMsg.textContent = msg;
    statusEl.classList.add('error');
    statusEl.textContent = '播放失败';
}}

function updateStatus(text) {{
    statusEl.textContent = text;
}}

function togglePlay() {{
    if (video.paused) {{ video.play(); }}
    else {{ video.pause(); }}
}}

function toggleFullscreen() {{
    if (document.fullscreenElement) {{ document.exitFullscreen(); }}
    else {{ video.requestFullscreen(); }}
}}

function updatePlayBtn() {{
    if (video.paused) {{
        playBtn.innerHTML = '<svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> 播放';
    }} else {{
        playBtn.innerHTML = '<svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M6 4h4v16H6zm8 0h4v16h-4z"/></svg> 暂停';
    }}
}}

video.addEventListener('play', updatePlayBtn);
video.addEventListener('pause', updatePlayBtn);
video.addEventListener('playing', function() {{ updateStatus('播放中'); errorOverlay.classList.remove('active'); }});
video.addEventListener('waiting', function() {{ updateStatus('缓冲中...'); }});
video.addEventListener('ended', function() {{ updateStatus('播放结束'); }});
video.addEventListener('error', function() {{ showError('视频加载失败，请检查链接是否有效'); }});

function updateStreamInfo(resolution, bitrate, codec, fps, buffer) {{
    document.getElementById('info-resolution').textContent = resolution || '-';
    document.getElementById('info-bitrate').textContent = bitrate || '-';
    document.getElementById('info-codec').textContent = codec || '-';
    document.getElementById('info-fps').textContent = fps || '-';
    document.getElementById('info-buffer').textContent = buffer || '-';
}}

function formatBitrate(bps) {{
    if (!bps || bps <= 0) return '-';
    if (bps >= 1000000) return (bps / 1000000).toFixed(1) + ' Mbps';
    return (bps / 1000).toFixed(0) + ' kbps';
}}

function formatBuffer(buffered) {{
    if (!buffered || buffered.length === 0) return '-';
    var end = buffered.end(buffered.length - 1);
    var current = video.currentTime;
    return Math.max(0, (end - current)).toFixed(1) + 's';
}}

setInterval(function() {{
    if (video.videoWidth > 0) {{
        updateStreamInfo(
            video.videoWidth + 'x' + video.videoHeight,
            null,
            null,
            null,
            formatBuffer(video.buffered)
        );
    }}
}}, 1000);

function loadWithHlsJs() {{
    var proxyUrl = buildHlsProxyUrl(originalUrl);

    if (typeof Hls !== 'undefined' && Hls.isSupported()) {{
        var hls = new Hls({{
            debug: false,
            enableWorker: true,
            lowLatencyMode: true,
            maxBufferLength: 30,
            maxMaxBufferLength: 60,
            maxLoadingDelay: 10,
            minAutoBitrate: 0,
            xhrSetup: function(xhr, url) {{
                if (url.indexOf('http') === 0 && url.indexOf(window.location.origin) !== 0) {{
                    var proxyUrl = buildProxyUrl(url);
                    xhr.open('GET', proxyUrl);
                }}
            }},
            fetchSetup: function(context, initParams) {{
                if (context.url.indexOf('http') === 0 && context.url.indexOf(window.location.origin) !== 0) {{
                    context.url = buildProxyUrl(context.url);
                }}
                return new Request(context.url, initParams);
            }}
        }});

        hls.loadSource(proxyUrl);
        hls.attachMedia(video);

        hls.on(Hls.Events.MANIFEST_PARSED, function() {{
            updateStatus('准备就绪');
            video.play().catch(function() {{}});
        }});

        hls.on(Hls.Events.LEVEL_LOADED, function(event, data) {{
            updateStatus('播放中');
            var level = hls.levels[data.level];
            if (level) {{
                var res = level.width && level.height ? level.width + 'x' + level.height : '-';
                var br = formatBitrate(level.bitrate);
                var codec = level.codecs ? level.codecs.split(',')[0] : '-';
                var fps = level.frameRate ? level.frameRate.toFixed(1) : '-';
                updateStreamInfo(res, br, codec, fps, formatBuffer(video.buffered));
            }}
        }});

        hls.on(Hls.Events.LEVEL_SWITCHED, function(event, data) {{
            var level = hls.levels[data.level];
            if (level) {{
                var res = level.width && level.height ? level.width + 'x' + level.height : '-';
                var br = formatBitrate(level.bitrate);
                var codec = level.codecs ? level.codecs.split(',')[0] : '-';
                var fps = level.frameRate ? level.frameRate.toFixed(1) : '-';
                updateStreamInfo(res, br, codec, fps, formatBuffer(video.buffered));
            }}
        }});

        hls.on(Hls.Events.ERROR, function(event, data) {{
            if (data.fatal) {{
                switch(data.type) {{
                    case Hls.ErrorTypes.NETWORK_ERROR:
                        updateStatus('网络错误，尝试恢复...');
                        if (data.details === 'manifestLoadError' || data.details === 'levelLoadError') {{
                            hls.loadSource(proxyUrl);
                        }} else {{
                            hls.startLoad();
                        }}
                        break;
                    case Hls.ErrorTypes.MEDIA_ERROR:
                        updateStatus('媒体错误，尝试恢复...');
                        hls.recoverMediaError();
                        break;
                    default:
                        showError('播放失败: ' + data.details);
                        hls.destroy();
                        break;
                }}
            }}
        }});
    }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
        video.src = proxyUrl;
        video.addEventListener('loadedmetadata', function() {{
            updateStatus('准备就绪');
            video.play().catch(function() {{}});
        }});
        video.addEventListener('error', function() {{
            showError('原生HLS播放失败');
        }});
    }} else {{
        showError('浏览器不支持HLS播放，请使用Chrome/Edge/Firefox');
    }}
}}

if (typeof Hls !== 'undefined') {{
    loadWithHlsJs();
}} else {{
    window.onload = function() {{ loadWithHlsJs(); }};
}}

var streamInfoEl = document.getElementById('stream-info');
var statusEl2 = document.getElementById('status');
var infoVisible = true;
streamInfoEl.addEventListener('click', function(e) {{
    e.stopPropagation();
    infoVisible = !infoVisible;
    streamInfoEl.style.opacity = infoVisible ? '1' : '0';
}});
statusEl2.addEventListener('click', function() {{
    infoVisible = !infoVisible;
    streamInfoEl.style.opacity = infoVisible ? '1' : '0';
}});
</script>
</body>
</html>"""


def get_app_path():
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def get_asset_path(filename):
    return os.path.join(get_app_path(), "assets", filename)
