import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import threading
import queue
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import time
import re
import json
import csv
import hashlib
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin
import os
import sys
import subprocess
from http.server import HTTPServer, SimpleHTTPRequestHandler
import webbrowser
import io
import socket

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


class PaginationWidget:
    def __init__(self, parent_frame, items_per_page=50, on_page_change=None):
        self.items_per_page = items_per_page
        self.on_page_change = on_page_change
        self.current_page = 1
        self.total_pages = 1
        self.frame = ttk.Frame(parent_frame)
        self.frame.pack(fill=X, pady=(5, 0))
        self._build_ui()

    def _build_ui(self):
        left_frame = ttk.Frame(self.frame)
        left_frame.pack(side=LEFT)

        self.prev_btn = ttk.Button(left_frame, text="← 上一页", command=self._prev_page, bootstyle="secondary-outline", width=10, state=DISABLED)
        self.prev_btn.pack(side=LEFT, padx=2)

        self.page_label = ttk.Label(left_frame, text="第 1 页 / 共 1 页", font=("Microsoft YaHei", 9), bootstyle="secondary")
        self.page_label.pack(side=LEFT, padx=10)

        self.next_btn = ttk.Button(left_frame, text="下一页 →", command=self._next_page, bootstyle="secondary-outline", width=10, state=DISABLED)
        self.next_btn.pack(side=LEFT, padx=2)

        right_frame = ttk.Frame(self.frame)
        right_frame.pack(side=RIGHT)

        self.jump_label = ttk.Label(right_frame, text="跳转到:", font=("Microsoft YaHei", 9))
        self.jump_label.pack(side=LEFT, padx=(0, 5))

        self.jump_var = tk.StringVar()
        self.jump_entry = ttk.Entry(right_frame, textvariable=self.jump_var, width=5)
        self.jump_entry.pack(side=LEFT, padx=2)
        self.jump_entry.bind("<Return>", lambda e: self._jump_to_page())

        self.jump_btn = ttk.Button(right_frame, text="跳转", command=self._jump_to_page, bootstyle="info", width=6)
        self.jump_btn.pack(side=LEFT, padx=2)

    def update_pagination(self, total_items):
        self.total_pages = max(1, (total_items + self.items_per_page - 1) // self.items_per_page)
        if self.current_page > self.total_pages:
            self.current_page = self.total_pages
        
        self.page_label.config(text=f"第 {self.current_page} 页 / 共 {self.total_pages} 页")
        self.prev_btn.config(state=NORMAL if self.current_page > 1 else DISABLED)
        self.next_btn.config(state=NORMAL if self.current_page < self.total_pages else DISABLED)
        self.jump_var.set("")

    def get_page_range(self):
        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, self.total_items if hasattr(self, 'total_items') else start_idx + self.items_per_page)
        return start_idx, end_idx

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.update_pagination(self.total_items)
            if self.on_page_change:
                self.on_page_change(self.current_page)

    def _next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.update_pagination(self.total_items)
            if self.on_page_change:
                self.on_page_change(self.current_page)

    def _jump_to_page(self):
        try:
            page_num = int(self.jump_var.get())
            if 1 <= page_num <= self.total_pages:
                self.current_page = page_num
                self.update_pagination(self.total_items)
                if self.on_page_change:
                    self.on_page_change(self.current_page)
        except ValueError:
            pass

    def set_total_items(self, total_items):
        self.total_items = total_items
        self.update_pagination(total_items)


class WizardDialog:
    STEPS = [
        ("welcome", "👋 欢迎使用"),
        ("network", "🌐 网络检测"),
        ("source", "📁 选择直播源"),
        ("settings", "⚙️ 参数设置"),
        ("tools", "️ 工具箱"),
        ("finish", "🚀 开始检测"),
    ]

    def __init__(self, parent_app):
        self.parent = parent_app
        self.root = parent_app.root
        self.current_step = 0
        self.dont_show_again = tk.BooleanVar(value=False)
        self.wizard_frame = ttk.Frame(self.root)
        self.wizard_frame.pack(fill=BOTH, expand=True)
        self._build_ui()
        self._show_step(0)

    def _build_ui(self):
        self.root.title(APP_TITLE)
        self.root.geometry("1100x750")
        
        if getattr(sys, "frozen", False):
            application_path = sys._MEIPASS
        else:
            application_path = os.path.dirname(os.path.abspath(__file__))
        
        icon_filename = "icon.ico"
        icon_path = os.path.join(application_path, "assets", icon_filename)
        
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except tk.TclError:
                pass
        
        main = ttk.Frame(self.wizard_frame, padding=0)
        main.pack(fill=BOTH, expand=True)
        
        # Top stepper bar
        top_frame = ttk.Frame(main, padding=(20, 15, 20, 10), bootstyle="light")
        top_frame.pack(fill=X)
        
        self.step_indicators = []
        for idx, (step_id, step_title) in enumerate(self.STEPS):
            step_frame = ttk.Frame(top_frame)
            step_frame.pack(side=LEFT, fill=X, expand=True, padx=5)
            
            # Step number circle
            circle = ttk.Label(step_frame, text=f"{idx + 1}", width=3, anchor=CENTER,
                              font=("Microsoft YaHei", 10, "bold"), bootstyle="secondary")
            circle.pack(side=LEFT, padx=(0, 8))
            
            # Step title
            label = ttk.Label(step_frame, text=step_title, font=("Microsoft YaHei", 9),
                              anchor=W, cursor="hand2", bootstyle="secondary")
            label.pack(side=LEFT, fill=X, expand=True)
            
            label.bind("<Button-1>", lambda e, i=idx: self._on_step_click(i))
            self.step_indicators.append({"frame": step_frame, "circle": circle, "label": label, "id": step_id})
            
            # Add separator line (except for last step)
            if idx < len(self.STEPS) - 1:
                sep = ttk.Separator(top_frame, orient=VERTICAL)
                sep.pack(side=LEFT, fill=Y, padx=5)
        
        # Content area
        content_frame = ttk.Frame(main, padding=20)
        content_frame.pack(fill=BOTH, expand=True)
        
        self.step_content = ttk.Frame(content_frame)
        self.step_content.pack(fill=BOTH, expand=True)
        
        # Bottom action bar
        bottom = ttk.Frame(main, padding=(20, 10, 20, 15))
        bottom.pack(fill=X)
        
        self.progress_label = ttk.Label(bottom, text="步骤 1/6", font=("Microsoft YaHei", 9), bootstyle="secondary")
        self.progress_label.pack(side=LEFT)
        
        self.dont_show_cb = ttk.Checkbutton(bottom, text="下次启动不再显示此向导", variable=self.dont_show_again)
        self.dont_show_cb.pack(side=LEFT, padx=20)
        
        btn_nav = ttk.Frame(bottom)
        btn_nav.pack(side=RIGHT)
        
        self.prev_btn = ttk.Button(btn_nav, text="← 上一步", command=self._prev_step, bootstyle="secondary-outline", state=DISABLED, width=12)
        self.prev_btn.pack(side=LEFT, padx=5)
        
        self.next_btn = ttk.Button(btn_nav, text="下一步 →", command=self._next_step, bootstyle="primary", width=12)
        self.next_btn.pack(side=LEFT, padx=5)

    def _on_step_click(self, index):
        self._show_step(index)

    def _show_step(self, index):
        self.current_step = index
        for idx, indicator in enumerate(self.step_indicators):
            if idx < index:
                indicator["circle"].config(text="✓", bootstyle="success")
                indicator["label"].config(bootstyle="success")
            elif idx == index:
                indicator["circle"].config(text=f"{idx + 1}", bootstyle="primary")
                indicator["label"].config(bootstyle="primary")
            else:
                indicator["circle"].config(text=f"{idx + 1}", bootstyle="secondary")
                indicator["label"].config(bootstyle="secondary")

        for widget in self.step_content.winfo_children():
            widget.destroy()

        self.prev_btn.config(state=NORMAL if index > 0 else DISABLED)

        if index == len(self.STEPS) - 1:
            self.next_btn.config(text=" 开始检测", bootstyle="success", command=self._finish)
        else:
            self.next_btn.config(text="下一步 →", bootstyle="primary", command=self._next_step)

        self.progress_label.config(text=f"步骤 {index + 1}/{len(self.STEPS)}")

        step_builders = [
            self._build_welcome,    # 0 - welcome
            self._build_network,    # 1 - network  
            self._build_source,     # 2 - source
            self._build_settings,   # 3 - settings
            self._build_tools,      # 4 - tools
            self._build_finish,     # 5 - finish
        ]
        step_builders[index]()

    def _build_welcome(self):
        title = ttk.Label(self.step_content, text="欢迎使用电视直播源检测工具！",
                          font=("Microsoft YaHei", 14, "bold"), bootstyle="primary")
        title.pack(pady=(30, 10))

        desc = ttk.Label(self.step_content, text="本工具可帮助您：", font=("Microsoft YaHei", 10))
        desc.pack(pady=(0, 20))

        features = [
            "✅ 自动检测本地宽带运营商（移动/电信/联通/广电）",
            "✅ 批量检测直播源链接的可用性和延迟",
            "✅ 支持在线直播源库，一键匹配运营商",
            "✅ 导出M3U/TXT/CSV/Excel多种格式",
            "✅ 支持IPv4/IPv6协议分类导出",
        ]
        for f in features:
            ttk.Label(self.step_content, text=f, font=("Microsoft YaHei", 9), anchor=W).pack(fill=X, padx=20, pady=2)

    def _build_network(self):
        title = ttk.Label(self.step_content, text="网络运营商检测", font=("Microsoft YaHei", 12, "bold"), bootstyle="info")
        title.pack(pady=(20, 10))

        isp = self.parent.local_isp if self.parent.local_isp != "未知" else "检测中..."
        status_label = ttk.Label(self.step_content, text=f"当前网络：{isp}宽带",
                                 font=("Microsoft YaHei", 11), bootstyle="success")
        status_label.pack(pady=10)

        if isp == "检测中...":
            hint = ttk.Label(self.step_content, text="⏳ 正在检测运营商信息，请稍候...",
                             font=("Microsoft YaHei", 9), bootstyle="warning")
            hint.pack(pady=5)

        info = ttk.Label(self.step_content,
                         text="运营商会影响在线直播源的匹配推荐。\n部分频道可能为特定运营商专属，更换宽带后可能无法播放。",
                         font=("Microsoft YaHei", 9), anchor=CENTER, bootstyle="secondary")
        info.pack(pady=(20, 0))

    def _build_source(self):
        title = ttk.Label(self.step_content, text="选择直播源", font=("Microsoft YaHei", 12, "bold"), bootstyle="primary")
        title.pack(pady=(20, 10))

        desc = ttk.Label(self.step_content, text="请选择要检测的直播源：", font=("Microsoft YaHei", 10))
        desc.pack(pady=(0, 20))

        options_frame = ttk.Frame(self.step_content)
        options_frame.pack(fill=X, padx=20, pady=10)

        ttk.Button(options_frame, text="📁 选择本地文件",
                   command=self._browse_file_in_wizard, bootstyle="primary", width=20).pack(pady=5, fill=X)

        ttk.Button(options_frame, text="📡 选择在线源库",
                   command=self._show_online_in_wizard, bootstyle="info", width=20).pack(pady=5, fill=X)

        hint = ttk.Label(self.step_content, text="💡 本地文件：选择已有的M3U/TXT文件\n在线源库：从预设源库中下载最新直播源",
                         font=("Microsoft YaHei", 8), anchor=CENTER, bootstyle="secondary")
        hint.pack(pady=(15, 0))

    def _build_tools(self):
        title = ttk.Label(self.step_content, text="工具箱", font=("Microsoft YaHei", 12, "bold"), bootstyle="info")
        title.pack(pady=(20, 10))

        desc = ttk.Label(self.step_content, text="常用工具和功能：", font=("Microsoft YaHei", 10))
        desc.pack(pady=(0, 20))

        tools_frame = ttk.Frame(self.step_content)
        tools_frame.pack(fill=X, padx=20, pady=10)

        ttk.Button(tools_frame, text="🔄 格式转换",
                   command=self.parent.show_converter_dialog, bootstyle="warning", width=20).pack(pady=5, fill=X)

        ttk.Button(tools_frame, text="🌐 M3U在线服务",
                   command=self.parent.toggle_m3u_server, bootstyle="info", width=20).pack(pady=5, fill=X)

        ttk.Button(tools_frame, text="📦 在线源库管理",
                   command=self.parent.show_online_sources_dialog, bootstyle="secondary", width=20).pack(pady=5, fill=X)

        hint = ttk.Label(self.step_content, text=" 这些工具可以帮助您更好地管理和转换直播源",
                         font=("Microsoft YaHei", 8), anchor=CENTER, bootstyle="secondary")
        hint.pack(pady=(15, 0))

    def _build_settings(self):
        title = ttk.Label(self.step_content, text="参数设置", font=("Microsoft YaHei", 12, "bold"), bootstyle="warning")
        title.pack(pady=(20, 10))

        settings_frame = ttk.LabelFrame(self.step_content, text="检测参数")
        settings_frame.pack(fill=X, padx=20, pady=10)

        inner_frame = ttk.Frame(settings_frame, padding=15)
        inner_frame.pack(fill=X, expand=True)
        inner_frame.columnconfigure(1, weight=1)

        params = [
            ("连接超时(秒):", self.parent.timeout_connect, 1, 30),
            ("读取超时(秒):", self.parent.timeout_read, 1, 60),
            ("线程数:", self.parent.max_threads, 1, 100),
        ]
        for row, (label_text, var, from_, to_) in enumerate(params):
            ttk.Label(inner_frame, text=label_text, font=("Microsoft YaHei", 9)).grid(row=row, column=0, sticky=W, pady=8)
            ttk.Spinbox(inner_frame, from_=from_, to=to_, textvariable=var, width=8).grid(row=row, column=1, sticky=W, padx=10, pady=8)

        extra_frame = ttk.Frame(inner_frame)
        extra_frame.grid(row=len(params), column=0, columnspan=2, sticky=W, pady=(10, 0))

        ttk.Checkbutton(extra_frame, text="速度测试(较慢但更准确)", variable=self.parent.run_speed_test).pack(anchor=W, pady=2)
        ttk.Checkbutton(extra_frame, text="使用缓存(加速重复检测)", variable=self.parent.use_cache).pack(anchor=W, pady=2)

        hint = ttk.Label(self.step_content, text="💡 默认参数已优化，普通用户可直接使用默认值",
                         font=("Microsoft YaHei", 9), anchor=CENTER, bootstyle="secondary")
        hint.pack(pady=(15, 0))

    def _build_finish(self):
        title = ttk.Label(self.step_content, text="准备就绪！", font=("Microsoft YaHei", 18, "bold"), bootstyle="success")
        title.pack(pady=(30, 15))

        has_files = len(self.parent.file_paths) > 0
        source_text = f"已选择 {len(self.parent.file_paths)} 个本地文件" if has_files else "未选择本地文件"

        config_frame = ttk.LabelFrame(self.step_content, text=" 当前配置")
        config_frame.config(borderwidth=2, relief="groove")
        config_frame.pack(fill=X, padx=50, pady=10)

        ttk.Label(config_frame, text=f" 直播源：{source_text}", font=("Microsoft YaHei", 10)).pack(fill=X, pady=5)
        ttk.Label(config_frame, text=f"🌐 运营商：{self.parent.local_isp}宽带", font=("Microsoft YaHei", 10)).pack(fill=X, pady=5)
        ttk.Label(config_frame, text=f"⏱️ 连接超时：{self.parent.timeout_connect.get()}秒", font=("Microsoft YaHei", 10)).pack(fill=X, pady=5)
        ttk.Label(config_frame, text=f"🧵 线程数：{self.parent.max_threads.get()}", font=("Microsoft YaHei", 10)).pack(fill=X, pady=5)

        start_btn = ttk.Button(self.step_content, text="🚀 开始检测", command=self._finish, bootstyle="success", width=20)
        start_btn.pack(pady=(30, 10))

        if not has_files:
            warn = ttk.Label(self.step_content, text="️ 请先在步骤3选择直播源后再开始检测！", font=("Microsoft YaHei", 9), bootstyle="warning")
            warn.pack(pady=(10, 0))
            start_btn.config(state=DISABLED, bootstyle="secondary-outline")

    def _browse_file_in_wizard(self):
        paths = filedialog.askopenfilenames(
            title="选择直播源文件(可多选)",
            filetypes=(("M3U/TXT", "*.m3u;*.txt"), ("All files", "*.*")),
        )
        if paths:
            self.parent.file_paths = list(paths)
            display_text = f"{len(paths)} 个文件" if len(paths) > 1 else os.path.basename(paths[0])
            self.parent.file_path_display.set(display_text)
            directory = os.path.dirname(paths[0])
            basename = os.path.splitext(os.path.basename(paths[0]))[0]
            if len(paths) > 1:
                basename = "批量检测_" + datetime.now().strftime("%Y%m%d_%H%M%S")
            self.parent.export_dir.set(directory)
            self.parent.source_file_basename.set(basename)
            self._show_step(self.current_step)

    def _show_online_in_wizard(self):
        self.parent.show_online_sources_dialog()
        self._show_step(self.current_step)

    def _prev_step(self):
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    def _next_step(self):
        if self.current_step < len(self.STEPS) - 1:
            self._show_step(self.current_step + 1)

    def _finish(self):
        if self.dont_show_again.get():
            self.parent.save_setting("skip_wizard", True)
        self.parent.show_results_view()
        if len(self.parent.file_paths) > 0:
            self.parent.start_checking()


class StreamCheckerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1300x850")

        if getattr(sys, "frozen", False):
            application_path = sys._MEIPASS
        else:
            application_path = os.path.dirname(os.path.abspath(__file__))

        icon_filename = "icon.ico"
        icon_path = os.path.join(application_path, "assets", icon_filename)

        print(f"尝试从: {icon_path} 加载图标")

        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
                print("图标设置成功！")
            except tk.TclError as e:
                print(f"设置图标时发生错误 (iconbitmap): {e}")
        else:
            print(f"警告: 图标文件 {icon_path} 未找到，将使用默认图标。")

        self.file_paths = []
        self.file_path_display = tk.StringVar(value="未选择文件")
        self.export_dir = tk.StringVar()
        self.source_file_basename = tk.StringVar()
        self.timeout_connect = tk.IntVar(value=3)
        self.timeout_read = tk.IntVar(value=8)
        self.max_threads = tk.IntVar(value=30)
        self.min_threads = 5
        self.run_speed_test = tk.BooleanVar(value=True)
        self.use_cache = tk.BooleanVar(value=True)
        self.status_message = tk.StringVar()
        self.total_links, self.checked_links = tk.IntVar(value=0), tk.IntVar(value=0)
        self.valid_links, self.invalid_links = tk.IntVar(value=0), tk.IntVar(value=0)
        self.links_to_check = []
        self.last_export_path = None
        self.is_running, self.stop_requested, self.executor = False, False, None
        self.result_queue = queue.Queue()
        self.sort_state = {
            "all": {"col": "原始序号", "rev": False},
            "valid": {"col": "原始序号", "rev": False},
            "invalid": {"col": "原始序号", "rev": False},
        }
        self.current_workers = 30
        self.consecutive_success = 0
        self.consecutive_fail = 0
        self.thread_lock = threading.Lock()
        self.cache = {}
        self.local_isp = "未知"
        self.source_isp = set()
        self.online_sources = []
        self.selected_online_sources = []
        self.http_server = None
        self.http_server_thread = None
        self.player_server = None
        self.player_server_thread = None
        self.player_server_port = None
        self.load_cache()
        self.load_local_sources()
        self.load_settings()
        threading.Thread(target=self.detect_local_isp, daemon=True).start()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.wizard = None
        self.wizard_frame = None
        self.results_frame = None
        
        if not self.get_setting("skip_wizard", False):
            self.show_wizard()
        else:
            self.show_results_view()

    def detect_local_isp(self):
        """检测本地宽带运营商（带重试和降级机制）"""
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/json"}
        detected_isp = None
        
        for api_config in ISP_APIS:
            api_url = api_config["url"]
            fields = api_config.get("fields", ["isp", "org", "company"])
            try:
                resp = requests.get(api_url, headers=headers, timeout=5, verify=False)
                if resp.status_code != 200:
                    continue
                    
                content_type = resp.headers.get("Content-Type", "").lower()
                if "json" in content_type:
                    data = resp.json()
                elif "xml" in content_type or "text" in content_type:
                    try:
                        data = json.loads(resp.text.split("(", 1)[-1].rsplit(")", 1)[0])
                    except:
                        try:
                            data = json.loads(resp.text)
                        except:
                            continue
                else:
                    continue
                    
                isp_text_parts = [str(data.get(f, "")).lower() for f in fields if data.get(f)]
                isp_text = " ".join(isp_text_parts)
                
                if not isp_text:
                    all_text = str(data).lower()
                    isp_text = all_text[:500]
                
                print(f"API {api_url} 返回: {isp_text[:100]}")
                
                for isp_name, keywords in ISP_KEYWORDS.items():
                    if any(kw.lower() in isp_text for kw in keywords):
                        detected_isp = isp_name
                        print(f"检测到运营商: {isp_name}")
                        break
                
                if detected_isp:
                    break
                    
            except Exception as e:
                print(f"API {api_url} 失败: {e}")
                continue
        
        if not detected_isp:
            detected_isp = self._detect_by_ip_segment()
            
        self.local_isp = detected_isp or "其他/未知"
        self.root.after(0, self.update_isp_display)
        print(f"最终运营商: {self.local_isp}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException, json.JSONDecodeError)),
        reraise=True
    )
    def _api_request_with_retry(self, url, timeout=5):
        """带重试机制的API请求"""
        response = requests.get(url, timeout=timeout, verify=False)
        response.raise_for_status()
        return response

    def _detect_by_ip_segment(self):
        """通过IP段检测运营商（降级方案）"""
        try:
            resp = self._api_request_with_retry("https://api.myip.com", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                ip = data.get("ip", "")
                if ip:
                    return self._match_ip_to_isp(ip)
        except Exception as e:
            print(f"IP段检测API失败: {e}")
        
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            if local_ip:
                return self._match_ip_to_isp(local_ip)
        except Exception as e:
            print(f"本地IP检测失败: {e}")
        
        return None

    def _match_ip_to_isp(self, ip):
        first_octet = ip.split(".")[0] if ip else ""
        second_octet = ip.split(".")[1] if "." in ip else ""
        
        ip_prefixes = {
            "移动": ["211.136", "211.137", "211.138", "211.139", "211.140", "211.142",
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
                     "117.178", "117.179", "117.180", "117.181", "117.182", "117.183"],
            "电信": ["202.96", "202.97", "202.98", "202.99", "202.100", "202.101",
                     "202.102", "202.103", "202.104", "202.105", "202.106", "202.107",
                     "202.108", "202.109", "202.110", "202.111", "202.112", "202.113",
                     "202.114", "202.115", "202.116", "202.117", "202.118", "202.119",
                     "202.120", "202.121", "202.122", "202.123", "202.124", "202.125",
                     "202.126", "202.127", "202.128", "202.129", "202.130", "202.131",
                     "222.72", "222.73", "222.74", "222.75", "222.76", "222.77",
                     "222.78", "222.79", "222.80", "222.81", "222.82", "222.83",
                     "222.84", "222.85", "222.86", "222.87", "222.88", "222.89",
                     "222.90", "222.91", "222.92", "222.93", "222.94", "222.95"],
            "联通": ["221.2", "221.3", "221.4", "221.5", "221.6", "221.7",
                     "221.8", "221.9", "221.10", "221.11", "221.12", "221.13",
                     "221.14", "221.15", "221.16", "221.17", "221.18", "221.19",
                     "221.20", "221.21", "221.22", "221.23", "221.24", "221.25",
                     "123.1", "123.2", "123.3", "123.4", "123.5", "123.6",
                     "123.7", "123.8", "123.9", "123.10", "123.11", "123.12",
                     "123.13", "123.14", "123.15", "123.16", "123.17", "123.18",
                     "123.19", "123.20", "123.21", "123.22", "123.23", "123.24",
                     "123.25", "123.26", "123.27", "123.28", "123.29", "123.30"],
        }
        
        prefix = f"{first_octet}.{second_octet}"
        for isp_name, prefixes in ip_prefixes.items():
            if prefix in prefixes:
                print(f"通过IP段 {prefix} 检测到运营商: {isp_name}")
                return isp_name
        
        return None

    def update_isp_display(self):
        if hasattr(self, "isp_label"):
            self.isp_label.config(text=f"🌐 当前网络: {self.local_isp}宽带", bootstyle="info")
        if hasattr(self, "isp_match_label"):
            self.check_isp_mismatch()

    def check_isp_mismatch(self):
        if not hasattr(self, "isp_match_label") or not self.source_isp:
            return
        mismatch = self.source_isp - {self.local_isp}
        if mismatch and self.local_isp not in ("其他/未知", "未知"):
            hint = f" 您正在使用{self.local_isp}宽带，但检测的直播源可能为{', '.join(mismatch)}专属频道，部分可能无法播放"
            self.isp_match_label.config(text=hint, bootstyle="warning")
        elif self.source_isp:
            self.isp_match_label.config(text=f"✅ 直播源运营商({', '.join(self.source_isp)})与您的宽带匹配", bootstyle="success")
        else:
            self.isp_match_label.config(text="")

    def detect_source_isp(self):
        self.source_isp.clear()
        for path in self.file_paths:
            fname = os.path.basename(path).lower()
            for isp_name, keywords in ISP_KEYWORDS.items():
                if any(kw in fname for kw in keywords):
                    self.source_isp.add(isp_name)
                    break
        for link in self.links_to_check:
            url = link["url"].lower()
            for isp_name, keywords in ISP_KEYWORDS.items():
                if any(kw in url for kw in keywords):
                    self.source_isp.add(isp_name)
                    break
        self.check_isp_mismatch()

    def load_local_sources(self):
        try:
            if getattr(sys, "frozen", False):
                app_path = sys._MEIPASS
            else:
                app_path = os.path.dirname(os.path.abspath(__file__))
            
            sources_file = os.path.join(app_path, "local_sources.json")
            if os.path.exists(sources_file):
                with open(sources_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.online_sources = data.get("sources", [])
                print(f"加载了 {len(self.online_sources)} 个在线直播源")
        except Exception as e:
            print(f"加载本地源配置失败: {e}")
            self.online_sources = []

    def load_settings(self):
        try:
            settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), SETTINGS_FILE)
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    self.user_settings = json.load(f)
                print(f"加载用户设置: {len(self.user_settings)} 条")
            else:
                self.user_settings = {}
        except Exception as e:
            print(f"加载用户设置失败: {e}")
            self.user_settings = {}

    def save_settings(self):
        try:
            settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), SETTINGS_FILE)
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(self.user_settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存用户设置失败: {e}")

    def get_setting(self, key, default=None):
        return self.user_settings.get(key, default)

    def save_setting(self, key, value):
        self.user_settings[key] = value
        self.save_settings()

    def detect_protocol_type(self, url):
        if "ipv6" in url.lower() or "/v6/" in url.lower():
            return "IPv6"
        try:
            import socket
            domain = url.split("//")[1].split("/")[0].split(":")[0]
            try:
                socket.getaddrinfo(domain, None, socket.AF_INET6)
                return "IPv4/IPv6"
            except socket.gaierror:
                return "IPv4"
        except:
            return "未知"

    def load_cache(self):
        cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CACHE_FILE)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                now = time.time()
                expired = []
                for url, data in self.cache.items():
                    if now - data.get("timestamp", 0) > CACHE_EXPIRY_HOURS * 3600:
                        expired.append(url)
                for url in expired:
                    del self.cache[url]
                if expired:
                    self.save_cache()
                print(f"加载缓存: {len(self.cache)} 条记录")
            except Exception as e:
                print(f"加载缓存失败: {e}")
                self.cache = {}

    def save_cache(self):
        cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CACHE_FILE)
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存缓存失败: {e}")

    def create_widgets(self):
        self.results_frame = ttk.Frame(self.root)
        self.results_frame.pack(fill=BOTH, expand=True)
        
        main_frame = ttk.Frame(self.results_frame, padding="10")
        main_frame.pack(fill=BOTH, expand=True)
        
        # Back button to return to wizard
        back_btn = ttk.Button(main_frame, text="← 返回向导", command=self.show_wizard, bootstyle="secondary-outline")
        back_btn.pack(side=TOP, anchor=W, pady=(0, 5))
        
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=X, pady=5)
        top_frame.grid_columnconfigure(0, weight=1)
        config_frame = ttk.Labelframe(top_frame, text="配置选项", padding="10")
        config_frame.grid(row=0, column=0, sticky="ew")
        config_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(config_frame, text="源文件:").grid(
            row=0, column=0, padx=5, pady=5, sticky=W
        )
        self.file_entry = ttk.Entry(config_frame, textvariable=self.file_path_display, state="readonly", cursor="hand2")
        self.file_entry.grid(
            row=0, column=1, columnspan=3, padx=5, pady=5, sticky=EW
        )
        self.file_entry.bind("<Button-1>", lambda e: self.browse_file())
        self.file_entry.bind("<Double-1>", lambda e: self.browse_file())
        self.browse_button = ttk.Button(
            config_frame, text="浏览(可多选)...", command=self.browse_file, style="primary-outline"
        )
        self.browse_button.grid(row=0, column=4, padx=5, pady=5)
        
        ttk.Label(config_frame, text="导出位置:").grid(
            row=1, column=0, padx=5, pady=5, sticky=W
        )
        self.export_dir_entry = ttk.Entry(config_frame, textvariable=self.export_dir, cursor="hand2")
        self.export_dir_entry.grid(
            row=1, column=1, columnspan=3, padx=5, pady=5, sticky=EW
        )
        self.export_dir_entry.bind("<Button-1>", lambda e: self.browse_export_dir())
        self.browse_export_dir_button = ttk.Button(
            config_frame, text="更改...", command=self.browse_export_dir, style="primary-outline"
        )
        self.browse_export_dir_button.grid(row=1, column=4, padx=5, pady=5)
        
        ttk.Label(config_frame, text="连接超时(s):").grid(
            row=2, column=0, padx=5, pady=5, sticky=W
        )
        self.timeout_connect_spinbox = ttk.Spinbox(
            config_frame, from_=1, to=30, textvariable=self.timeout_connect, width=8
        )
        self.timeout_connect_spinbox.grid(row=2, column=1, padx=5, pady=5, sticky=W)
        
        ttk.Label(config_frame, text="读取超时(s):").grid(
            row=2, column=2, padx=(10, 5), pady=5, sticky=W
        )
        self.timeout_read_spinbox = ttk.Spinbox(
            config_frame, from_=1, to=60, textvariable=self.timeout_read, width=8
        )
        self.timeout_read_spinbox.grid(row=2, column=3, padx=5, pady=5, sticky=W)
        
        ttk.Label(config_frame, text="线程数:").grid(
            row=3, column=0, padx=5, pady=5, sticky=W
        )
        self.threads_spinbox = ttk.Spinbox(
            config_frame, from_=1, to=100, textvariable=self.max_threads, width=8
        )
        self.threads_spinbox.grid(row=3, column=1, padx=5, pady=5, sticky=W)
        
        check_options_frame = ttk.Frame(config_frame)
        check_options_frame.grid(row=3, column=2, columnspan=3, padx=5, pady=5, sticky=W)
        
        self.speed_test_btn = ttk.Checkbutton(
            check_options_frame, text="速度测试(慢)", variable=self.run_speed_test,
            style="success.Roundtoggle.Toolbutton",
        )
        self.speed_test_btn.pack(side=LEFT, padx=(0, 5))
        
        self.cache_btn = ttk.Checkbutton(
            check_options_frame, text="使用缓存", variable=self.use_cache,
            style="info.Roundtoggle.Toolbutton",
        )
        self.cache_btn.pack(side=LEFT)

        self.isp_status_frame = ttk.Frame(main_frame)
        self.isp_status_frame.pack(fill=X, pady=(0, 5))
        self.isp_label = ttk.Label(self.isp_status_frame, text=f"当前网络: 检测中...", bootstyle="info")
        self.isp_label.pack(side=LEFT, padx=5)
        self.isp_match_label = ttk.Label(self.isp_status_frame, text="", bootstyle="success")
        self.isp_match_label.pack(side=LEFT)

        control_theme_frame = ttk.Frame(main_frame)
        control_theme_frame.pack(fill=X, pady=10)
        self.start_button = ttk.Button(
            control_theme_frame, text="开始检测", command=self.start_checking, style="success"
        )
        self.start_button.pack(side=LEFT, padx=5, fill=X, expand=True)
        self.stop_button = ttk.Button(
            control_theme_frame, text="停止检测", command=self.stop_checking,
            bootstyle="danger", state=DISABLED,
        )
        self.stop_button.pack(side=LEFT, padx=5, fill=X, expand=True)
        self.export_button = ttk.Button(
            control_theme_frame, text="导出结果", command=self.export_results,
            bootstyle="info", state=DISABLED,
        )
        self.export_button.pack(side=LEFT, padx=5, fill=X, expand=True)
        self.online_source_btn = ttk.Button(
            control_theme_frame, text="📡 在线源库", command=self.show_online_sources_dialog, bootstyle="primary"
        )
        self.online_source_btn.pack(side=LEFT, padx=5, fill=X, expand=True)
        self.converter_btn = ttk.Button(
            control_theme_frame, text="🔄 格式转换", command=self.show_converter_dialog, bootstyle="warning"
        )
        self.converter_btn.pack(side=LEFT, padx=5, fill=X, expand=True)
        self.help_btn = ttk.Button(
            control_theme_frame, text="❓ 帮助", command=self.show_wizard, bootstyle="info"
        )
        self.help_btn.pack(side=LEFT, padx=5, fill=X, expand=True)
        self.m3u_server_btn = ttk.Button(
            control_theme_frame, text="🌐 在线服务", command=self.toggle_m3u_server, bootstyle="secondary"
        )
        self.m3u_server_btn.pack(side=LEFT, padx=5, fill=X, expand=True)
        self.theme_button = ttk.Button(
            control_theme_frame, text="切换主题", command=self.toggle_theme, bootstyle="secondary"
        )
        self.theme_button.pack(side=LEFT, padx=5, fill=X, expand=True)
        
        status_frame = ttk.Labelframe(main_frame, text="检测状态", padding="10")
        status_frame.pack(fill=X, pady=5)
        status_frame.grid_columnconfigure(1, weight=1)
        self.status_label = ttk.Label(
            status_frame, textvariable=self.status_message, anchor=W
        )
        self.status_label.grid(
            row=4, column=0, columnspan=2, padx=5, pady=(10, 5), sticky=EW
        )
        self.progress_bar = ttk.Progressbar(status_frame, mode="determinate")
        self.progress_bar.grid(row=0, column=0, columnspan=4, padx=5, pady=5, sticky=EW)
        stats_inner_frame = ttk.Frame(status_frame)
        stats_inner_frame.grid(row=1, column=0, columnspan=4, sticky=E)
        ttk.Label(stats_inner_frame, text="总数:").pack(side=LEFT, padx=(0, 2))
        ttk.Label(stats_inner_frame, textvariable=self.total_links).pack(side=LEFT, padx=(0, 10))
        ttk.Label(stats_inner_frame, text="已检:").pack(side=LEFT, padx=(0, 2))
        ttk.Label(stats_inner_frame, textvariable=self.checked_links).pack(side=LEFT, padx=(0, 10))
        ttk.Label(stats_inner_frame, text="有效:").pack(side=LEFT, padx=(0, 2))
        ttk.Label(stats_inner_frame, textvariable=self.valid_links, foreground="green").pack(side=LEFT, padx=(0, 10))
        ttk.Label(stats_inner_frame, text="无效:").pack(side=LEFT, padx=(0, 2))
        ttk.Label(stats_inner_frame, textvariable=self.invalid_links, foreground="red").pack(side=LEFT)
        self.thread_status_label = ttk.Label(stats_inner_frame, text="", foreground="gray")
        self.thread_status_label.pack(side=LEFT, padx=(10, 0))
        self.export_path_label = ttk.Label(
            status_frame, text="", style="info", cursor="hand2"
        )
        self.export_path_label.grid(
            row=3, column=0, columnspan=4, padx=5, pady=(10, 5), sticky=W
        )
        self.export_path_label.bind("<Button-1>", self.open_export_folder)

        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill=X, pady=(0, 5))
        ttk.Label(search_frame, text="搜索:").pack(side=LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.apply_search_filter())
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 5))
        self.clear_search_btn = ttk.Button(
            search_frame, text="清除", command=self.clear_search, state=DISABLED, width=8
        )
        self.clear_search_btn.pack(side=LEFT)

        result_frame = ttk.Labelframe(
            main_frame, text="检测结果 (支持Ctrl/Shift多选, 右键可复制)", padding="10"
        )
        result_frame.pack(fill=BOTH, expand=True, pady=5)
        
        self.notebook = ttk.Notebook(result_frame)
        self.notebook.pack(fill=BOTH, expand=True)
        self.create_result_tab("all", "全部")
        self.create_result_tab("valid", "有效源")
        self.create_result_tab("invalid", "无效源")
        
        self.all_items_data = {"all": [], "valid": [], "invalid": []}
        
        result_bottom = ttk.Frame(result_frame)
        result_bottom.pack(fill=X, pady=(5, 0))
        
        self.pagination_widgets = {}
        for tab_name in ["all", "valid", "invalid"]:
            pagination = PaginationWidget(
                result_bottom,
                items_per_page=PAGES_PER_VIEW,
                on_page_change=lambda page, t=tab_name: self._on_page_change(page, t)
            )
            self.pagination_widgets[tab_name] = pagination
            pagination.frame.pack_forget()
        
        self.current_active_tab = "all"
        self.pagination_widgets["all"].frame.pack(fill=X)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def clear_search(self):
        self.search_var.set("")
        self.apply_search_filter()

    def apply_search_filter(self):
        query = self.search_var.get().strip().lower()
        self.clear_search_btn.config(state=NORMAL if query else DISABLED)
        for tab_name in ["all", "valid", "invalid"]:
            tree = getattr(self, f"tree_{tab_name}")
            tree.delete(*tree.get_children())
            pagination = self.pagination_widgets.get(tab_name)
            
            if pagination:
                start_idx, end_idx = pagination.get_page_range()
                filtered_items = []
                for item in self.all_items_data[tab_name]:
                    values = item["values"]
                    if not query or any(query in str(v).lower() for v in values):
                        filtered_items.append(item)
                
                for item in filtered_items[start_idx:end_idx]:
                    tree.insert("", END, values=item["values"], tags=(item["tag"],))
                
                pagination.set_total_items(len(filtered_items))

    def create_result_tab(self, name, text):
        tab = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(tab, text=text)
        cols = ("原始序号", "来源文件", "频道名称", "URL", "状态", "延迟(ms)", "速度(KB/s)", "信息", "播放")
        tree = ttk.Treeview(tab, columns=cols, show="headings", height=15, selectmode="extended")
        setattr(self, f"tree_{name}", tree)
        tree.bind("<Button-3>", lambda event, t=tree: self.show_context_menu(event, t))
        tree.bind("<Control-a>", lambda event, t=tree: self.select_all_items(t))
        tree.bind("<Control-A>", lambda event, t=tree: self.select_all_items(t))
        tree.bind("<ButtonRelease-1>", lambda event, t=tree, t_name=name: self._on_tree_click(event, t, t_name))
        for col in cols:
            tree.heading(
                col, text=col,
                command=lambda _col=col, _tree_name=name: self.sort_treeview_column(
                    getattr(self, f"tree_{_tree_name}"), _col, _tree_name
                ),
            )
        tree.column("原始序号", width=60, anchor=CENTER)
        tree.column("来源文件", width=90, anchor=W)
        tree.column("频道名称", width=130, anchor=W)
        tree.column("URL", width=300, anchor=W)
        tree.column("状态", width=60, anchor=CENTER)
        tree.column("延迟(ms)", width=80, anchor=CENTER)
        tree.column("速度(KB/s)", width=90, anchor=CENTER)
        tree.column("信息", width=130, anchor=W)
        tree.column("播放", width=50, anchor=CENTER)
        vsb = ttk.Scrollbar(tab, orient=VERTICAL, command=tree.yview)
        hsb = ttk.Scrollbar(tab, orient=HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=RIGHT, fill=Y)
        hsb.pack(side=BOTTOM, fill=X)
        tree.pack(fill=BOTH, expand=True)
        tree.tag_configure("valid", foreground="green")
        tree.tag_configure("invalid", foreground="red")

    def _on_tab_change(self, event=None):
        current_tab_index = self.notebook.index(self.notebook.select())
        tab_names = ["all", "valid", "invalid"]
        new_tab = tab_names[current_tab_index] if current_tab_index < len(tab_names) else "all"
        
        if new_tab != self.current_active_tab:
            if self.current_active_tab in self.pagination_widgets:
                self.pagination_widgets[self.current_active_tab].frame.pack_forget()
            if new_tab in self.pagination_widgets:
                self.pagination_widgets[new_tab].frame.pack(fill=X)
            self.current_active_tab = new_tab
            self._refresh_current_page()

    def _on_page_change(self, page, tab_name):
        self._refresh_current_page()

    def _on_tree_click(self, event, tree, tab_name):
        region = tree.identify("region", event.x, event.y)
        column = tree.identify_column(event.x)
        col_index = int(column.replace("#", ""))
        
        if region == "cell" and col_index == 9:
            item_id = tree.identify_row(event.y)
            if item_id:
                values = tree.item(item_id, "values")
                if len(values) >= 4:
                    channel_name = values[2]
                    channel_url = values[3]
                    status = values[4]
                    
                    if status == "有效" or messagebox.askyesno("提示", f"频道 [{channel_name}] 检测为无效源，是否仍尝试播放？"):
                        self.play_url(channel_url, channel_name)
    
    def _ensure_player_server(self):
        if self.player_server is not None:
            return self.player_server_port

        class PlayerHandler(SimpleHTTPRequestHandler):
            player_html_content = ""

            def do_GET(self):
                if self.path == "/" or self.path == "/player.html":
                    self.send_response(200)
                    self.send_header("Content-type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.end_headers()
                    self.wfile.write(self.player_html_content.encode("utf-8"))
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass

        self._player_handler_class = PlayerHandler

        for port in range(19527, 19537):
            try:
                server = HTTPServer(("127.0.0.1", port), PlayerHandler)
                self.player_server = server
                self.player_server_port = port
                self.player_server_thread = threading.Thread(
                    target=server.serve_forever, daemon=True
                )
                self.player_server_thread.start()
                return port
            except OSError:
                continue

        return None

    def play_url(self, url, name):
        player_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>播放：{name}</title>
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<style>
body {{ margin: 0; background: #000; display: flex; align-items: center; justify-content: center; height: 100vh; }}
video {{ width: 100%; max-height: 100vh; }}
#status {{ position: absolute; top: 10px; left: 10px; color: #fff; font-size: 14px; font-family: monospace; z-index: 10; }}
#error {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); color: #ff6b6b; font-size: 18px; font-family: 'Microsoft YaHei',sans-serif; text-align: center; display: none; background: rgba(0,0,0,0.8); padding: 30px 40px; border-radius: 10px; max-width: 80%; }}
</style>
</head>
<body>
<div id="status">加载中...</div>
<div id="error"></div>
<video id="video" controls autoplay></video>
<script>
var video = document.getElementById('video');
var statusEl = document.getElementById('status');
var errorEl = document.getElementById('error');
var url = '{url}';

function showError(msg) {{
    errorEl.style.display = 'block';
    errorEl.textContent = msg;
    statusEl.textContent = '';
}}

function loadWithHlsJs() {{
    if (typeof Hls !== 'undefined' && Hls.isSupported()) {{
        var hls = new Hls({{
            debug: false,
            enableWorker: true,
            lowLatencyMode: true,
            maxBufferLength: 30,
            maxMaxBufferLength: 60
        }});
        hls.loadSource(url);
        hls.attachMedia(video);
        hls.on(Hls.Events.MIFEST_PARSED, function() {{
            statusEl.textContent = '播放中';
            video.play().catch(function() {{}});
        }});
        hls.on(Hls.Events.ERROR, function(event, data) {{
            if (data.fatal) {{
                switch(data.type) {{
                    case Hls.ErrorTypes.NETWORK_ERROR:
                        statusEl.textContent = '网络错误，重试中...';
                        hls.startLoad();
                        break;
                    case Hls.ErrorTypes.MEDIA_ERROR:
                        statusEl.textContent = '媒体错误，恢复中...';
                        hls.recoverMediaError();
                        break;
                    default:
                        showError('播放失败：' + data.details + '\\n频道：{name}');
                        hls.destroy();
                        break;
                }}
            }}
        }});
    }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
        video.src = url;
        video.addEventListener('loadedmetadata', function() {{
            statusEl.textContent = '播放中';
            video.play().catch(function() {{}});
        }});
        video.addEventListener('error', function() {{
            showError('原生HLS播放失败\\n频道：{name}');
        }});
    }} else {{
        showError('浏览器不支持HLS播放');
    }}
}}

if (typeof Hls !== 'undefined') {{
    loadWithHlsJs();
}} else {{
    window.onload = function() {{ loadWithHlsJs(); }};
}}

video.addEventListener('playing', function() {{ statusEl.textContent = '播放中'; }});
video.addEventListener('waiting', function() {{ statusEl.textContent = '缓冲中...'; }});
video.addEventListener('pause', function() {{ statusEl.textContent = '已暂停'; }});
video.addEventListener('ended', function() {{ statusEl.textContent = '播放结束'; }});
</script>
</body>
</html>"""

        port = self._ensure_player_server()
        if port is None:
            temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_player")
            os.makedirs(temp_dir, exist_ok=True)
            player_file = os.path.join(temp_dir, "player.html")
            with open(player_file, "w", encoding="utf-8") as f:
                f.write(player_html)
            webbrowser.open(f"file:///{player_file.replace(os.sep, '/')}")
        else:
            self._player_handler_class.player_html_content = player_html
            webbrowser.open(f"http://127.0.0.1:{port}/player.html")

        self.set_status_message(f"正在播放: {name}", duration=3000)

    def _refresh_current_page(self):
        tab_name = self.current_active_tab
        tree = getattr(self, f"tree_{tab_name}")
        pagination = self.pagination_widgets.get(tab_name)
        
        if not pagination:
            return
        
        tree.delete(*tree.get_children())
        start_idx, end_idx = pagination.get_page_range()
        
        all_data = self.all_items_data.get(tab_name, [])
        page_data = all_data[start_idx:end_idx]
        
        for item in page_data:
            tree.insert("", END, values=item["values"], tags=(item["tag"],))

    def insert_result_with_pagination(self, values, tag):
        play_icon = "▶"
        values_with_play = values + (play_icon,)
        item_data = {"values": values_with_play, "tag": tag}
        tab_name = "valid" if tag == "valid" else "invalid"
        
        self.all_items_data["all"].append(item_data)
        self.all_items_data[tab_name].append(item_data)
        
        if tab_name == self.current_active_tab or self.current_active_tab == "all":
            tree = getattr(self, f"tree_{self.current_active_tab}")
            tree.insert("", END, values=values_with_play, tags=(tag,))
        
        for tab_name_update in ["all", "valid", "invalid"]:
            if tab_name_update in self.pagination_widgets:
                self.pagination_widgets[tab_name_update].set_total_items(len(self.all_items_data[tab_name_update]))

    def select_all_items(self, tree):
        tree.selection_set(tree.get_children())
        return "break"

    def show_context_menu(self, event, tree):
        clicked_item = tree.identify_row(event.y)
        if not clicked_item:
            return
        selected_items = tree.selection()
        num_selected = len(selected_items)
        if clicked_item not in selected_items:
            tree.selection_set(clicked_item)
            selected_items = tree.selection()
            num_selected = 1
        context_menu = tk.Menu(tree, tearoff=0)
        if num_selected <= 1:
            context_menu.add_command(label="▶ 播放此频道", command=lambda: self.play_channel(tree))
            context_menu.add_separator()
            context_menu.add_command(label="复制 URL", command=lambda: self.copy_cell_value(tree, "URL"))
            context_menu.add_command(label="复制 频道名称", command=lambda: self.copy_cell_value(tree, "频道名称"))
            context_menu.add_separator()
            context_menu.add_command(label="复制 整行数据", command=lambda: self.copy_cell_value(tree, None))
        else:
            context_menu.add_command(label="▶ 播放选中频道", command=lambda: self.play_channel(tree))
            context_menu.add_separator()
            context_menu.add_command(
                label=f"复制 {num_selected} 个 URL (每行一个)",
                command=lambda: self.copy_multiple_values(tree, "URL"),
            )
            context_menu.add_command(
                label=f"复制 {num_selected} 个 频道名称",
                command=lambda: self.copy_multiple_values(tree, "频道名称"),
            )
            context_menu.add_separator()
            context_menu.add_command(
                label=f"复制 {num_selected} 行的全部数据",
                command=lambda: self.copy_multiple_values(tree, None),
            )
        context_menu.add_separator()
        context_menu.add_command(label="⚡ 智能优选（同频道选最快源）", command=lambda: self.smart_select_optimize())
        context_menu.post(event.x_root, event.y_root)

    def copy_cell_value(self, tree, column_name):
        selected_items = tree.selection()
        if not selected_items:
            return
        item_id = selected_items[0]
        all_values = tree.item(item_id, "values")
        if column_name is None:
            text_to_copy = ", ".join(map(str, all_values))
            message = "整行数据已复制到剪贴板"
        else:
            try:
                col_index = tree["columns"].index(column_name)
                text_to_copy = all_values[col_index]
                message = f"{column_name} 已复制到剪贴板"
            except (ValueError, IndexError):
                self.set_status_message("错误：找不到指定的列", error=True)
                return
        self.root.clipboard_clear()
        self.root.clipboard_append(text_to_copy)
        self.set_status_message(message)

    def copy_multiple_values(self, tree, column_name):
        selected_items = tree.selection()
        if not selected_items:
            return
        data_to_copy = []
        try:
            col_index = tree["columns"].index(column_name) if column_name else -1
            for item_id in selected_items:
                all_values = tree.item(item_id, "values")
                if column_name is None:
                    data_to_copy.append(", ".join(map(str, all_values)))
                else:
                    data_to_copy.append(all_values[col_index])
            text_to_copy = "\n".join(data_to_copy)
            self.root.clipboard_clear()
            self.root.clipboard_append(text_to_copy)
            noun = "行数据" if column_name is None else column_name
            self.set_status_message(f"已复制 {len(data_to_copy)} 个 {noun} 到剪贴板")
        except (ValueError, IndexError):
            self.set_status_message("错误：处理批量复制时出错", error=True)

    def set_status_message(self, message, error=False, duration=3000):
        self.status_message.set(message)
        self.status_label.config(bootstyle="danger" if error else "primary")
        self.root.after(duration, lambda: self.status_message.set(""))

    def sort_treeview_column(self, tv, col, tree_name):
        sort_info = self.sort_state[tree_name]
        reverse = not sort_info["rev"] if col == sort_info["col"] else False
        sort_info["col"] = col
        sort_info["rev"] = reverse
        l = [(tv.set(k, col), k) for k in tv.get_children("")]
        def safe_float_convert(s):
            try:
                return float(s)
            except (ValueError, TypeError):
                return -1
        if col in ("原始序号", "延迟(ms)", "速度(KB/s)"):
            l.sort(key=lambda t: safe_float_convert(t[0]), reverse=reverse)
        else:
            l.sort(key=lambda t: str(t[0]).lower(), reverse=reverse)
        for index, (val, k) in enumerate(l):
            tv.move(k, "", index)

    def browse_file(self):
        paths = filedialog.askopenfilenames(
            title="选择直播源文件(可多选)",
            filetypes=(("M3U/TXT", "*.m3u;*.txt"), ("All files", "*.*")),
        )
        if paths:
            self.file_paths = list(paths)
            display_text = f"{len(paths)} 个文件" if len(paths) > 1 else os.path.basename(paths[0])
            self.file_path_display.set(display_text)
            directory = os.path.dirname(paths[0])
            basename = os.path.splitext(os.path.basename(paths[0]))[0]
            if len(paths) > 1:
                basename = "批量检测_" + datetime.now().strftime("%Y%m%d_%H%M%S")
            self.export_dir.set(directory)
            self.source_file_basename.set(basename)

    def browse_export_dir(self):
        directory = filedialog.askdirectory(title="选择导出位置")
        if directory:
            self.export_dir.set(directory)

    def toggle_theme(self):
        current_theme = self.root.style.theme_use()
        if current_theme == "litera":
            self.root.style.theme_use("darkly")
        else:
            self.root.style.theme_use("litera")

    def show_online_sources_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("📡 在线直播源库")
        dialog.geometry("600x550")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="选择在线直播源（自动匹配您的宽带运营商）", font=("Microsoft YaHei", 10, "bold")).pack(pady=(15, 5))
        ttk.Label(dialog, text=f"当前网络：{self.local_isp}宽带", foreground="gray").pack(pady=(0, 10))
        
        sources_frame = ttk.Frame(dialog)
        sources_frame.pack(fill=BOTH, expand=True, padx=15, pady=5)
        
        canvas = tk.Canvas(sources_frame)
        scrollbar = ttk.Scrollbar(sources_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        source_vars = []
        categorized_sources = {}
        for source in self.online_sources:
            if source.get("disabled", False):
                continue
            category = source.get("category", "其他")
            if category not in categorized_sources:
                categorized_sources[category] = []
            categorized_sources[category].append(source)
        
        row = 0
        for category, sources in categorized_sources.items():
            ttk.Label(scrollable_frame, text=f"--- {category} ---", font=("Microsoft YaHei", 9, "bold")).grid(row=row, column=0, columnspan=4, sticky=W, pady=(10, 2))
            row += 1
            
            for source in sources:
                var = tk.BooleanVar(value=False)
                source_vars.append({"var": var, "source": source})
                
                isp_match = self.local_isp in source.get("isp", []) or "其他" in source.get("isp", [])
                protocol = source.get("protocol", "ipv4").upper()
                
                state = "normal" if isp_match else "disabled"
                label_text = f"{source['name']}"
                hint_text = f"[{protocol}]"
                if not isp_match:
                    hint_text += " (可能不兼容)"
                
                chk = ttk.Checkbutton(scrollable_frame, text=label_text, variable=var, state=state)
                chk.grid(row=row, column=0, columnspan=3, sticky=W, padx=5)
                
                lbl = ttk.Label(scrollable_frame, text=hint_text, bootstyle="success" if isp_match else "warning", font=("Microsoft YaHei", 8))
                lbl.grid(row=row, column=3, sticky=E, padx=5)
                row += 1
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=X, padx=15, pady=15)
        
        def select_all():
            for item in source_vars:
                if item["source"].get("isp") and (self.local_isp in item["source"].get("isp", []) or "其他" in item["source"].get("isp", [])):
                    item["var"].set(True)
        
        def deselect_all():
            for item in source_vars:
                item["var"].set(False)
        
        def download_and_check():
            selected = [item["source"] for item in source_vars if item["var"].get()]
            if not selected:
                messagebox.showwarning("提示", "请至少选择一个直播源！", parent=dialog)
                return
            
            dialog.destroy()
            self.download_and_check_online_sources(selected)
        
        ttk.Button(btn_frame, text="全选匹配", command=select_all, width=10).pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text="取消全选", command=deselect_all, width=10).pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text="一键检测选中源", command=download_and_check, style="success", width=15).pack(side=RIGHT, padx=5)

    def download_and_check_online_sources(self, selected_sources):
        self.file_paths = []
        all_links = []
        url_seen = {}
        
        for idx, source in enumerate(selected_sources):
            self.set_status_message(f"正在下载: {source['name']}...")
            try:
                url = source.get("url", "")
                if source.get("mirror_url") and self.local_isp not in source.get("isp", []):
                    url = source.get("mirror_url")
                
                resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    content = resp.text
                    file_name = source["name"]
                    lines = content.splitlines()
                    name = "N/A"
                    group = ""
                    
                    for line in lines:
                        line = line.strip()
                        if not line or line.startswith("#EXTM3U") or line.startswith("# "):
                            continue
                        if line.startswith("#EXTINF:"):
                            match = re.search(r",(.+)", line)
                            name = match.group(1).strip() if match else "N/A"
                            group_match = re.search(r'group-title="([^"]+)"', line)
                            group = group_match.group(1) if group_match else ""
                        elif "://" in line and not line.startswith("#"):
                            url_line = line
                            if "," in line and "://" in line.split(",", 1)[1]:
                                parts = line.split(",", 1)
                                name, url_line = parts[0].strip(), parts[1].strip()
                            
                            url_key = hashlib.md5(url_line.encode()).hexdigest()
                            if url_key in url_seen:
                                existing = url_seen[url_key]
                                if file_name not in existing["sources"]:
                                    existing["sources"].append(file_name)
                            else:
                                link_info = {
                                    "name": name,
                                    "url": url_line,
                                    "group": group,
                                    "sources": [file_name],
                                    "index": len(all_links) + 1,
                                }
                                url_seen[url_key] = link_info
                                all_links.append(link_info)
                            name = "N/A"
                            group = ""
                    
                    self.set_status_message(f"已下载: {source['name']} ({len([k for k, v in url_seen.items() if file_name in v['sources']])} 个频道)", duration=2000)
                else:
                    self.set_status_message(f"下载失败: {source['name']} (HTTP {resp.status_code})", error=True, duration=3000)
            except Exception as e:
                self.set_status_message(f"下载失败: {source['name']} ({str(e)})", error=True, duration=3000)
        
        if not all_links:
            messagebox.showerror("错误", "未解析到任何直播源链接！")
            return
        
        self.links_to_check = all_links
        self.source_isp.clear()
        for link in all_links:
            for src in selected_sources:
                for isp_name in src.get("isp", []):
                    self.source_isp.add(isp_name)
        
        self.is_running, self.stop_requested = True, False
        self.current_workers = self.max_threads.get()
        self.consecutive_success = 0
        self.consecutive_fail = 0
        self.toggle_controls(True)
        self.reset_ui()
        self.total_links.set(len(self.links_to_check))
        self.progress_bar["maximum"] = len(self.links_to_check)
        self.file_path_display.set(f"在线源库 ({len(selected_sources)} 个源)")
        self.source_file_basename.set("在线源库_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        
        threading.Thread(target=self.submit_tasks, daemon=True).start()
        self.root.after(100, self.process_queue)

    def show_converter_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("🔄 直播源格式转换")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="选择要转换的文件", font=("Microsoft YaHei", 10, "bold")).pack(pady=(15, 5))
        
        file_frame = ttk.LabelFrame(dialog, text="输入文件")
        file_frame.pack(fill=X, padx=15, pady=5)
        
        input_file_var = tk.StringVar(value="未选择文件")
        input_files = []
        
        def browse_input():
            paths = filedialog.askopenfilenames(
                title="选择直播源文件",
                filetypes=(("M3U/TXT", "*.m3u;*.txt"), ("All files", "*.*"))
            )
            if paths:
                input_files.clear()
                input_files.extend(paths)
                display = f"{len(paths)} 个文件" if len(paths) > 1 else os.path.basename(paths[0])
                input_file_var.set(display)
        
        ttk.Entry(file_frame, textvariable=input_file_var, state="readonly").pack(fill=X, pady=5)
        ttk.Button(file_frame, text="浏览文件", command=browse_input).pack(pady=5)
        
        output_frame = ttk.LabelFrame(dialog, text="输出格式")
        output_frame.pack(fill=X, padx=15, pady=10)
        
        output_format = tk.StringVar(value="m3u")
        ttk.Radiobutton(output_frame, text="转换为 M3U 格式", variable=output_format, value="m3u").pack(anchor=W, pady=2)
        ttk.Radiobutton(output_frame, text="转换为 TXT 格式", variable=output_format, value="txt").pack(anchor=W, pady=2)
        
        def do_convert():
            if not input_files:
                messagebox.showwarning("提示", "请先选择要转换的文件！", parent=dialog)
                return
            
            output_dir = os.path.dirname(input_files[0])
            success_count = 0
            
            for input_path in input_files:
                try:
                    base_name = os.path.splitext(os.path.basename(input_path))[0]
                    output_ext = output_format.get()
                    output_path = os.path.join(output_dir, f"{base_name}_converted.{output_ext}")
                    
                    with open(input_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    
                    if output_format.get() == "m3u":
                        with open(output_path, "w", encoding="utf-8") as f:
                            f.write("#EXTM3U\n")
                            name = "N/A"
                            for line in content.splitlines():
                                line = line.strip()
                                if line.startswith("#EXTINF:"):
                                    match = re.search(r",(.+)", line)
                                    name = match.group(1).strip() if match else "N/A"
                                    f.write(f"{line}\n")
                                elif "://" in line and not line.startswith("#"):
                                    f.write(f"{line}\n")
                                    name = "N/A"
                    else:
                        with open(output_path, "w", encoding="utf-8") as f:
                            name = "N/A"
                            for line in content.splitlines():
                                line = line.strip()
                                if line.startswith("#EXTINF:"):
                                    match = re.search(r",(.+)", line)
                                    name = match.group(1).strip() if match else "N/A"
                                elif "://" in line and not line.startswith("#"):
                                    f.write(f"{name},{line}\n")
                                    name = "N/A"
                    
                    success_count += 1
                except Exception as e:
                    messagebox.showerror("转换失败", f"转换 {input_path} 时出错: {e}", parent=dialog)
                    return
            
            messagebox.showinfo("成功", f"成功转换 {success_count} 个文件！\n输出目录: {output_dir}", parent=dialog)
            dialog.destroy()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=X, padx=15, pady=15)
        ttk.Button(btn_frame, text="开始转换", command=do_convert, style="success", width=15).pack(side=LEFT, padx=5, fill=X, expand=True)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy, width=15).pack(side=LEFT, padx=5, fill=X, expand=True)

    def show_wizard(self):
        self.wizard_shown = False
        # Hide results view
        if hasattr(self, 'results_frame') and self.results_frame:
            self.results_frame.pack_forget()
        # Show wizard
        if not hasattr(self, 'wizard') or not self.wizard:
            self.wizard = WizardDialog(self)
        else:
            self.wizard.wizard_frame.pack(fill=BOTH, expand=True)

    def show_results_view(self):
        # Hide wizard
        if hasattr(self, 'wizard') and self.wizard:
            self.wizard.wizard_frame.pack_forget()
        # Show results view
        if not hasattr(self, 'results_frame') or not self.results_frame:
            self.create_widgets()
        else:
            self.results_frame.pack(fill=BOTH, expand=True)

    def toggle_m3u_server(self):
        if self.http_server:
            self.stop_m3u_server()
        else:
            self.start_m3u_server()

    def start_m3u_server(self):
        valid_items = []
        if hasattr(self, "tree_all"):
            for i in self.tree_all.get_children(""):
                v = self.tree_all.item(i, "values")
                if v[4] == "有效":
                    valid_items.append(v)
        
        if not valid_items:
            messagebox.showwarning("提示", "没有有效的直播源！请先检测并获取有效源。")
            return
        
        class M3UHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, items=valid_items, **kwargs):
                self.valid_items = items
                super().__init__(*args, directory=None, **kwargs)
            
            def do_GET(self):
                if self.path == "/playlist.m3u":
                    self.send_response(200)
                    self.send_header("Content-type", "audio/x-mpegurl")
                    self.send_header("Content-Disposition", "attachment; filename=playlist.m3u")
                    self.end_headers()
                    content = "#EXTM3U\n"
                    for item in self.valid_items:
                        content += f"#EXTINF:-1,{item[2]}\n{item[3]}\n"
                    self.wfile.write(content.encode("utf-8"))
                elif self.path == "/playlist.txt":
                    self.send_response(200)
                    self.send_header("Content-type", "text/plain")
                    self.end_headers()
                    content = ""
                    for item in self.valid_items:
                        content += f"{item[2]},{item[3]}\n"
                    self.wfile.write(content.encode("utf-8"))
                else:
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    html = f"""
                    <html>
                    <head><title>IPTV-Check 在线服务</title></head>
                    <body>
                        <h2>IPTV-Check 在线M3U服务</h2>
                        <p>有效频道: {len(valid_items)} 个</p>
                        <ul>
                            <li><a href="/playlist.m3u">下载 M3U 播放列表</a></li>
                            <li><a href="/playlist.txt">下载 TXT 列表</a></li>
                        </ul>
                        <p>在手机/电视播放器中输入URL即可使用</p>
                    </body>
                    </html>
                    """
                    self.wfile.write(html.encode("utf-8"))
            
            def log_message(self, format, *args):
                pass
        
        try:
            port = 9527
            self.http_server = HTTPServer(("0.0.0.0", port), M3UHandler)
            self.http_server_thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
            self.http_server_thread.start()
            
            import socket
            ip = socket.gethostbyname(socket.gethostname())
            url = f"http://{ip}:{port}/playlist.m3u"
            
            self.m3u_server_btn.config(text="🌐 停止服务", bootstyle="danger")
            
            dialog = tk.Toplevel(self.root)
            dialog.title("🌐 在线M3U服务")
            dialog.geometry("450x300")
            dialog.transient(self.root)
            dialog.grab_set()
            
            ttk.Label(dialog, text="在线服务已启动", font=("Microsoft YaHei", 11, "bold")).pack(pady=(20, 10))
            ttk.Label(dialog, text="您的播放列表URL:", foreground="gray").pack()
            
            url_var = tk.StringVar(value=url)
            url_entry = ttk.Entry(dialog, textvariable=url_var, font=("Consolas", 10))
            url_entry.pack(fill=X, padx=20, pady=10)
            
            ttk.Label(dialog, text="在手机/电视播放器中输入此URL", foreground="gray", font=("Microsoft YaHei", 8)).pack()
            
            def copy_url():
                self.root.clipboard_clear()
                self.root.clipboard_append(url)
                self.set_status_message("URL已复制到剪贴板", duration=2000)
            
            def stop_server():
                self.stop_m3u_server()
                self.m3u_server_btn.config(text="🌐 在线服务", style="secondary")
                dialog.destroy()
            
            btn_frame = ttk.Frame(dialog)
            btn_frame.pack(fill=X, padx=20, pady=15)
            ttk.Button(btn_frame, text="复制URL", command=copy_url, width=12, bootstyle="success").pack(side=LEFT, padx=5, fill=X, expand=True)
            ttk.Button(btn_frame, text="停止服务", command=stop_server, bootstyle="danger", width=12).pack(side=LEFT, padx=5, fill=X, expand=True)
        except Exception as e:
            messagebox.showerror("错误", f"启动服务失败: {e}")

    def stop_m3u_server(self):
        if self.http_server:
            self.http_server.shutdown()
            self.http_server = None
            self.http_server_thread = None
            self.set_status_message("在线服务已停止", duration=2000)

    def play_channel(self, tree):
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择一个频道！", parent=self.root)
            return
        
        item_id = selected[0]
        values = tree.item(item_id, "values")
        channel_name = values[2]
        channel_url = values[3]
        
        if values[4] != "有效":
            if messagebox.askyesno("警告", f"频道 [{channel_name}] 检测为无效源，是否仍尝试播放？"):
                pass
            else:
                return
        
        player_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>播放：{channel_name}</title>
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<style>
body {{ margin: 0; background: #000; display: flex; align-items: center; justify-content: center; height: 100vh; }}
video {{ width: 100%; max-height: 100vh; }}
</style>
</head>
<body>
<video id="video" controls autoplay></video>
<script>
var video = document.getElementById('video');
var url = '{channel_url}';
if(Hls.isSupported()) {{
    var hls = new Hls({{debug: false}});
    hls.loadSource(url);
    hls.attachMedia(video);
    hls.on(Hls.Events.MANIFEST_PARSED, function() {{ video.play(); }});
    hls.on(Hls.Events.ERROR, function(event, data) {{
        console.error('HLS Error:', data);
    }});
}} else if(video.canPlayType('application/vnd.apple.mpegurl')) {{
    video.src = url;
    video.addEventListener('loadedmetadata', function() {{ video.play(); }});
}}
</script>
</body>
</html>"""
        
        import tempfile
        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_player")
        os.makedirs(temp_dir, exist_ok=True)
        player_file = os.path.join(temp_dir, "player.html")
        with open(player_file, "w", encoding="utf-8") as f:
            f.write(player_html)
        
        webbrowser.open(f"file:///{player_file.replace(os.sep, '/')}")
        self.set_status_message(f"正在播放: {channel_name}", duration=3000)

    def smart_select_optimize(self):
        all_items = []
        for i in self.tree_all.get_children(""):
            v = self.tree_all.item(i, "values")
            if v[4] == "有效":
                all_items.append(v)
        
        if not all_items:
            messagebox.showinfo("提示", "没有有效源可供优选！", parent=self.root)
            return
        
        channel_groups = {}
        for item in all_items:
            name = item[2]
            name_key = re.sub(r'[\s\-_|]', '', name).lower()
            if name_key not in channel_groups:
                channel_groups[name_key] = []
            channel_groups[name_key].append(item)
        
        original_count = len(all_items)
        optimized_items = []
        for name_key, items in channel_groups.items():
            if len(items) == 1:
                optimized_items.append(items[0])
            else:
                best_item = None
                best_delay = float('inf')
                for item in items:
                    try:
                        delay_str = item[5].strip().replace(" ms", "").replace("ms", "").strip()
                        delay = float(delay_str) if delay_str else float('inf')
                    except:
                        delay = float('inf')
                    
                    if delay < best_delay:
                        best_delay = delay
                        best_item = item
                
                if best_item:
                    optimized_items.append(best_item)
        
        removed_count = original_count - len(optimized_items)
        
        self.tree_all.delete(*self.tree_all.get_children())
        self.tree_valid.delete(*self.tree_valid.get_children())
        self.tree_invalid.delete(*self.tree_invalid.get_children())
        
        for item in optimized_items:
            tag = "valid" if item[4] == "有效" else "invalid"
            self.tree_all.insert("", END, values=item, tags=(tag,))
            if tag == "valid":
                self.tree_valid.insert("", END, values=item, tags=("valid",))
            else:
                self.tree_invalid.insert("", END, values=item, tags=("invalid",))
        
        self.all_items_data["all"] = [{"values": item} for item in optimized_items]
        self.all_items_data["valid"] = [{"values": item} for item in optimized_items if item[4] == "有效"]
        self.all_items_data["invalid"] = [{"values": item} for item in optimized_items if item[4] == "无效"]
        
        self.total_links.set(len(optimized_items))
        self.valid_links.set(len([i for i in optimized_items if i[4] == "有效"]))
        self.invalid_links.set(len([i for i in optimized_items if i[4] == "无效"]))
        
        self.results = []
        for idx, item in enumerate(optimized_items, 1):
            self.results.append({
                "index": idx,
                "name": item[2],
                "url": item[3],
                "status": item[4],
                "delay": item[5],
                "speed": item[6],
                "error": item[7],
                "sources": item[1]
            })
        
        messagebox.showinfo("智能优选完成", 
                          f"原始有效源: {original_count} 个\n"
                          f"优选后: {len(optimized_items)} 个\n"
                          f"去除重复: {removed_count} 个\n\n"
                          f"已自动保留每个频道的最低延迟源",
                          parent=self.root)

    def parse_files(self):
        all_links = []
        url_seen = {}
        for file_idx, path in enumerate(self.file_paths):
            file_name = os.path.splitext(os.path.basename(path))[0]
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                name = "N/A"
                group = ""
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith("#EXTM3U") or line.startswith("# "):
                        continue
                    if line.startswith("#EXTINF:"):
                        match = re.search(r",(.+)", line)
                        name = match.group(1).strip() if match else "N/A"
                        group_match = re.search(r'group-title="([^"]+)"', line)
                        group = group_match.group(1) if group_match else ""
                    elif "://" in line and not line.startswith("#"):
                        url = line
                        if "," in line and "://" in line.split(",", 1)[1]:
                            parts = line.split(",", 1)
                            name, url = parts[0].strip(), parts[1].strip()
                        
                        url_key = hashlib.md5(url.encode()).hexdigest()
                        if url_key in url_seen:
                            existing = url_seen[url_key]
                            if file_name not in existing["sources"]:
                                existing["sources"].append(file_name)
                        else:
                            link_info = {
                                "name": name,
                                "url": url,
                                "group": group,
                                "sources": [file_name],
                                "index": len(all_links) + 1,
                            }
                            url_seen[url_key] = link_info
                            all_links.append(link_info)
                        name = "N/A"
                        group = ""
            except Exception as e:
                messagebox.showerror("文件读取错误", f"解析文件 {path} 时出错: {e}")
                return []
        return all_links

    def start_checking(self):
        if not self.file_paths:
            messagebox.showwarning("提示", "请先选择至少一个源文件！")
            return
        self.links_to_check = self.parse_files()
        if not self.links_to_check:
            messagebox.showwarning("提示", "未解析到任何链接！")
            return
        self.detect_source_isp()
        self.is_running, self.stop_requested = True, False
        self.current_workers = self.max_threads.get()
        self.consecutive_success = 0
        self.consecutive_fail = 0
        self.toggle_controls(True)
        self.reset_ui()
        self.total_links.set(len(self.links_to_check))
        self.progress_bar["maximum"] = len(self.links_to_check)
        threading.Thread(target=self.submit_tasks, daemon=True).start()
        self.root.after(100, self.process_queue)

    def submit_tasks(self):
        with ThreadPoolExecutor(max_workers=self.current_workers) as executor:
            self.executor = executor
            for link_info in self.links_to_check:
                if self.stop_requested:
                    break
                url = link_info["url"]
                url_key = hashlib.md5(url.encode()).hexdigest()
                cached = self.get_cached_result(url_key)
                if cached and self.use_cache.get():
                    result = cached.copy()
                    result["index"] = link_info["index"]
                    result["name"] = link_info["name"]
                    result["sources"] = ", ".join(link_info["sources"])
                    self.result_queue.put(result)
                else:
                    executor.submit(
                        self.check_url,
                        link_info,
                        self.timeout_connect.get(),
                        self.timeout_read.get(),
                        self.run_speed_test.get(),
                    )

    def get_cached_result(self, url_key):
        if url_key in self.cache:
            cached = self.cache[url_key]
            return {
                "index": 0,
                "name": cached.get("name", "N/A"),
                "url": cached.get("url", ""),
                "status": cached.get("status", "无效"),
                "latency": cached.get("latency", "-"),
                "speed": cached.get("speed", "-"),
                "details": cached.get("details", "缓存结果"),
                "sources": "",
            }
        return None

    def stop_checking(self):
        if not self.is_running:
            return
        self.stop_requested = True
        if self.executor:
            self.executor.shutdown(wait=False, cancel_futures=True)
        self.is_running = False
        self.toggle_controls(False)
        self.root.title(self.root.title().split(" - ")[0] + " - 已由用户中断")

    def toggle_controls(self, is_checking):
        state = DISABLED if is_checking else NORMAL
        for widget in [
            self.start_button, self.browse_button, self.browse_export_dir_button,
            self.timeout_connect_spinbox, self.timeout_read_spinbox, self.threads_spinbox,
        ]:
            widget.config(state=state)
        self.stop_button.config(state=NORMAL if is_checking else DISABLED)

    def reset_ui(self):
        self.checked_links.set(0)
        self.valid_links.set(0)
        self.invalid_links.set(0)
        self.progress_bar["value"] = 0
        self.root.title(f"{APP_TITLE.split(' - ')[0]} - 检测中...")
        self.set_status_message("", duration=1)
        self.all_items_data = {"all": [], "valid": [], "invalid": []}
        self.search_var.set("")
        self.clear_search_btn.config(state=DISABLED)
        for name in ["all", "valid", "invalid"]:
            tree = getattr(self, f"tree_{name}")
            tree.delete(*tree.get_children())
            self.sort_state[name] = {"col": "原始序号", "rev": False}
            if name in self.pagination_widgets:
                self.pagination_widgets[name].current_page = 1
                self.pagination_widgets[name].set_total_items(0)
        self.export_path_label.config(text="")
        self.last_export_path = None

    def _create_result_dict(self, link_info):
        return {
            "index": link_info["index"],
            "name": link_info["name"],
            "url": link_info["url"],
            "status": "无效",
            "latency": "-",
            "speed": "-",
            "details": "",
            "sources": ", ".join(link_info["sources"]),
        }

    def adjust_thread_count(self, is_success):
        with self.thread_lock:
            if is_success:
                self.consecutive_success += 1
                self.consecutive_fail = 0
                if self.consecutive_success >= 20 and self.current_workers < self.max_threads.get():
                    old = self.current_workers
                    self.current_workers = min(self.current_workers + 5, self.max_threads.get())
                    self.set_status_message(f"网络良好，线程数 {old} → {self.current_workers}", duration=2000)
                    self.thread_status_label.config(text=f"当前线程: {self.current_workers}")
            else:
                self.consecutive_fail += 1
                self.consecutive_success = 0
                if self.consecutive_fail >= 10 and self.current_workers > self.min_threads:
                    old = self.current_workers
                    self.current_workers = max(self.current_workers // 2, self.min_threads)
                    self.set_status_message(f"失败过多，线程数 {old} → {self.current_workers}", duration=2000)
                    self.thread_status_label.config(text=f"当前线程: {self.current_workers}")

    def _test_speed(self, response_iterator, timeout):
        try:
            start_time = time.time()
            downloaded_size = 0
            for chunk in response_iterator:
                downloaded_size += len(chunk)
                if downloaded_size >= 256 * 1024:
                    break
                if time.time() - start_time > timeout / 2:
                    return "N/A"
            elapsed_time = time.time() - start_time
            if elapsed_time > 0:
                speed_kbps = (downloaded_size / 1024) / elapsed_time
                return f"{speed_kbps:.2f}"
            return "∞"
        except Exception:
            return "N/A"

    def check_url(self, link_info, timeout_connect, timeout_read, run_speed_test):
        if self.stop_requested:
            return
        result = self._create_result_dict(link_info)
        base_url = link_info["url"]
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        start_time = time.time()
        try:
            timeout = (timeout_connect, timeout_read)
            with requests.get(base_url, headers=headers, timeout=timeout, stream=True, allow_redirects=True) as r:
                r.raise_for_status()
                latency = int((time.time() - start_time) * 1000)
                speed = "-"
                content_type = r.headers.get("Content-Type", "").lower()
                is_m3u8 = "mpegurl" in content_type or base_url.lower().endswith(".m3u8")
                
                if run_speed_test:
                    if is_m3u8:
                        playlist_content = r.text
                        if not playlist_content.strip().startswith("#EXTM3U"):
                            raise ValueError("非标准M3U8内容")
                        speed = self._get_m3u8_speed(base_url, playlist_content, headers, timeout)
                    else:
                        speed = self._test_speed(r.iter_content(chunk_size=8192), timeout_read)
                else:
                    if is_m3u8:
                        playlist_content = r.text
                        if not playlist_content.strip().startswith("#EXTM3U"):
                            raise ValueError("非标准M3U8内容")
                        self._validate_m3u8_recursive(base_url, playlist_content, headers, timeout, depth=0)
                    elif not next(r.iter_content(chunk_size=1024), None):
                        raise ValueError("无数据流")
                
                result.update({
                    "status": "有效",
                    "latency": latency,
                    "speed": speed,
                    "details": f"OK ({r.status_code})",
                })
                self.adjust_thread_count(True)
        except requests.exceptions.Timeout:
            result["details"] = f"超时 (连接>{timeout_connect}s/读取>{timeout_read}s)"
            self.adjust_thread_count(False)
        except requests.exceptions.SSLError as e:
            result["details"] = f"SSL证书错误: {str(e)[:30]}"
            self.adjust_thread_count(False)
        except requests.exceptions.ConnectionError as e:
            err_str = str(e).lower()
            if "dns" in err_str or "name resolution" in err_str:
                result["details"] = "DNS解析失败"
            elif "refused" in err_str or "actively refused" in err_str:
                result["details"] = "连接被拒绝"
            elif "reset" in err_str:
                result["details"] = "连接被重置"
            else:
                result["details"] = "连接失败"
            self.adjust_thread_count(False)
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            if status == 403:
                result["details"] = "访问被拒绝(403)"
            elif status == 404:
                result["details"] = "资源不存在(404)"
            elif status >= 500:
                result["details"] = f"服务器错误({status})"
            else:
                result["details"] = f"HTTP错误({status})"
            self.adjust_thread_count(False)
        except requests.exceptions.RequestException as e:
            result["details"] = f"请求异常: {str(e)[:30]}"
            self.adjust_thread_count(False)
        except ValueError as e:
            result["details"] = str(e)
            self.adjust_thread_count(False)
        except Exception as e:
            result["details"] = f"未知错误: {str(e)[:30]}"
            self.adjust_thread_count(False)
        
        if not self.stop_requested:
            url_key = hashlib.md5(link_info["url"].encode()).hexdigest()
            if result["status"] == "无效" and self.source_isp and self.local_isp not in ("其他/未知", "未知"):
                mismatch = self.source_isp - {self.local_isp}
                if mismatch:
                    result["details"] += f" (可能为{', '.join(mismatch)}专属源)"
            self.cache[url_key] = {
                "url": link_info["url"],
                "name": link_info["name"],
                "status": result["status"],
                "latency": result["latency"],
                "speed": result["speed"],
                "details": result["details"],
                "timestamp": time.time(),
            }
            self.result_queue.put(result)

    def _get_m3u8_speed(self, base_url, playlist_content, headers, timeout):
        segment_url = self._find_segment_url(base_url, playlist_content)
        if not segment_url:
            return "-"
        
        try:
            with requests.get(segment_url, headers=headers, timeout=timeout, stream=True) as seg_r:
                seg_r.raise_for_status()
                seg_content_type = seg_r.headers.get("Content-Type", "").lower()
                if "mpegurl" in seg_content_type or segment_url.lower().endswith(".m3u8"):
                    nested_playlist = seg_r.text
                    if nested_playlist.strip().startswith("#EXTM3U"):
                        nested_segment = self._find_segment_url(segment_url, nested_playlist)
                        if nested_segment:
                            with requests.get(nested_segment, headers=headers, timeout=timeout, stream=True) as nested_r:
                                nested_r.raise_for_status()
                                return self._test_speed(nested_r.iter_content(chunk_size=8192), timeout[1])
                return self._test_speed(seg_r.iter_content(chunk_size=8192), timeout[1])
        except Exception:
            return "-"

    def _validate_m3u8_recursive(self, base_url, playlist_content, headers, timeout, depth=0, max_depth=5):
        if depth >= max_depth:
            return
        
        segment_url = self._find_segment_url(base_url, playlist_content)
        if not segment_url:
            raise ValueError("M3U8无有效分片")
        
        try:
            with requests.get(segment_url, headers=headers, timeout=timeout, stream=True) as r:
                r.raise_for_status()
                content_type = r.headers.get("Content-Type", "").lower()
                if "mpegurl" in content_type or segment_url.lower().endswith(".m3u8"):
                    nested_playlist = r.text
                    if nested_playlist.strip().startswith("#EXTM3U"):
                        self._validate_m3u8_recursive(segment_url, nested_playlist, headers, timeout, depth + 1, max_depth)
                elif not next(r.iter_content(chunk_size=1024), None):
                    raise ValueError("分片无数据")
        except Exception as e:
            raise ValueError(f"M3U8深度验证失败: {str(e)[:30]}")

    def _find_segment_url(self, base_url, playlist_content):
        for line in playlist_content.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return urljoin(base_url, line)
        return None

    def process_queue(self):
        try:
            while not self.result_queue.empty():
                result = self.result_queue.get_nowait()
                self.checked_links.set(self.checked_links.get() + 1)
                values = (
                    result["index"],
                    result.get("sources", ""),
                    result["name"],
                    result["url"],
                    result["status"],
                    result["latency"],
                    result["speed"],
                    result["details"],
                )
                tag = "valid" if result["status"] == "有效" else "invalid"
                
                if result["status"] == "有效":
                    self.valid_links.set(self.valid_links.get() + 1)
                else:
                    self.invalid_links.set(self.invalid_links.get() + 1)
                
                self.insert_result_with_pagination(values, tag)
                self.progress_bar["value"] = self.checked_links.get()
        except queue.Empty:
            pass
        finally:
            if self.is_running and not self.stop_requested:
                if self.checked_links.get() == self.total_links.get():
                    self.is_running = False
                    self.toggle_controls(False)
                    self.export_button.config(state=NORMAL)
                    self.save_cache()
                    self.root.title(f"{APP_TITLE.split(' - ')[0]} - 检测完成")
                    for name in ["all", "valid", "invalid"]:
                        self.sort_state[name]["rev"] = True
                        self.sort_treeview_column(getattr(self, f"tree_{name}"), "原始序号", name)
                    messagebox.showinfo(
                        "完成",
                        f"检测完成！结果已按原始序号排序。\n有效: {self.valid_links.get()}\n无效: {self.invalid_links.get()}",
                    )
                else:
                    self.root.after(100, self.process_queue)

    def export_results(self):
        export_dir = self.export_dir.get().strip()
        base_name = self.source_file_basename.get().strip()
        if not export_dir or not base_name:
            messagebox.showerror("错误", "无法导出，请先选择一个源文件。")
            return
        
        valid_items = [self.tree_all.item(i, "values") for i in self.tree_all.get_children("") if self.tree_all.item(i, "values")[4] == "有效"]
        invalid_items = [self.tree_all.item(i, "values") for i in self.tree_all.get_children("") if self.tree_all.item(i, "values")[4] == "无效"]
        total_valid = len(valid_items)
        total_invalid = len(invalid_items)
        total_all = total_valid + total_invalid
        
        export_dialog = tk.Toplevel(self.root)
        export_dialog.title("导出选项")
        export_dialog.geometry("420x520")
        export_dialog.transient(self.root)
        export_dialog.grab_set()
        
        ttk.Label(export_dialog, text="数据概览", font=("Microsoft YaHei", 10, "bold")).pack(pady=(15, 5))
        ttk.Label(export_dialog, text=f"有效频道: {total_valid} 个    无效频道: {total_invalid} 个    总计: {total_all} 条", foreground="gray").pack(pady=(0, 15))
        
        format_frame = ttk.LabelFrame(export_dialog, text="选择导出格式")
        format_frame.pack(fill=X, padx=15, pady=5)
        
        export_m3u = tk.BooleanVar(value=True)
        export_txt = tk.BooleanVar(value=True)
        export_csv = tk.BooleanVar(value=True)
        export_xlsx = tk.BooleanVar(value=True)
        
        ttk.Checkbutton(format_frame, text="M3U 播放列表 (仅有效源，可直接导入播放器)", variable=export_m3u).pack(anchor=W, pady=2)
        ttk.Checkbutton(format_frame, text="TXT 无效源列表 (含错误原因)", variable=export_txt).pack(anchor=W, pady=2)
        ttk.Checkbutton(format_frame, text="CSV 完整明细 (所有数据，含延迟/速度)", variable=export_csv).pack(anchor=W, pady=2)
        ttk.Checkbutton(format_frame, text="Excel 表格 (带颜色标注和筛选)", variable=export_xlsx).pack(anchor=W, pady=2)
        
        mode_frame = ttk.LabelFrame(export_dialog, text="导出模式")
        mode_frame.pack(fill=X, padx=15, pady=10)
        
        export_mode = tk.StringVar(value="merged")
        ttk.Radiobutton(mode_frame, text="合并导出 - 所有数据合并到一个文件中", variable=export_mode, value="merged").pack(anchor=W, pady=2)
        ttk.Radiobutton(mode_frame, text="分别导出 - 按有效/无效分别生成文件", variable=export_mode, value="separate").pack(anchor=W, pady=2)
        
        ipv_frame = ttk.LabelFrame(export_dialog, text="协议分类")
        ipv_frame.pack(fill=X, padx=15, pady=5)
        
        ipv_split = tk.BooleanVar(value=False)
        ttk.Checkbutton(ipv_frame, text="按 IPv4 / IPv6 分别导出（生成 _IPv4 和 _IPv6 文件）", variable=ipv_split).pack(anchor=W, pady=2)
        
        btn_frame = ttk.Frame(export_dialog)
        btn_frame.pack(fill=X, padx=15, pady=15)
        
        def do_export():
            if not any([export_m3u.get(), export_txt.get(), export_csv.get(), export_xlsx.get()]):
                messagebox.showwarning("提示", "请至少选择一种导出格式！", parent=export_dialog)
                return
            
            export_dialog.destroy()
            if ipv_split.get():
                all_items = []
                for i in self.tree_all.get_children(""):
                    v = self.tree_all.item(i, "values")
                    protocol = self.detect_protocol_type(v[3])
                    all_items.append((v, protocol))
                
                ipv4_items = [item for item, proto in all_items if proto == "IPv4"]
                ipv6_items = [item for item, proto in all_items if proto == "IPv6"]
                
                if ipv4_items:
                    ipv4_valid = [v for v in ipv4_items if v[4] == "有效"]
                    ipv4_invalid = [v for v in ipv4_items if v[4] == "无效"]
                    self._do_export(export_dir, f"{base_name}_IPv4", ipv4_valid, ipv4_invalid,
                                  export_m3u.get(), export_txt.get(), export_csv.get(), export_xlsx.get(),
                                  export_mode.get())
                
                if ipv6_items:
                    ipv6_valid = [v for v in ipv6_items if v[4] == "有效"]
                    ipv6_invalid = [v for v in ipv6_items if v[4] == "无效"]
                    self._do_export(export_dir, f"{base_name}_IPv6", ipv6_valid, ipv6_invalid,
                                  export_m3u.get(), export_txt.get(), export_csv.get(), export_xlsx.get(),
                                  export_mode.get())
                
                messagebox.showinfo("导出成功", f"IPv4: {len(ipv4_items)} 条\nIPv6: {len(ipv6_items)} 条\n\n文件已保存到:\n{export_dir}")
            else:
                self._do_export(export_dir, base_name, valid_items, invalid_items,
                              export_m3u.get(), export_txt.get(), export_csv.get(), export_xlsx.get(),
                              export_mode.get())
        
        ttk.Button(btn_frame, text="确认导出", command=do_export, style="success", width=12).pack(side=LEFT, padx=5, fill=X, expand=True)
        ttk.Button(btn_frame, text="取消", command=export_dialog.destroy, width=12).pack(side=LEFT, padx=5, fill=X, expand=True)

    def _do_export(self, export_dir, base_name, valid_items, invalid_items,
                   export_m3u, export_txt, export_csv, export_xlsx, export_mode):
        exported_files = []
        
        try:
            if export_mode == "merged":
                if export_m3u:
                    path = os.path.join(export_dir, f"{base_name}_有效源.m3u")
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(f"#EXTM3U\n")
                        f.write(f"# 检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        f.write(f"# 本地网络: {self.local_isp}宽带\n")
                        f.write(f"# 检测说明: 仅包含当前网络环境下可正常播放的频道\n")
                        f.write(f"# 注意: 更换宽带运营商后部分频道可能无法播放\n\n")
                        for v in valid_items:
                            f.write(f"#EXTINF:-1,{v[2]}\n{v[3]}\n")
                    exported_files.append((path, f"M3U播放列表({len(valid_items)}个)"))
                
                if export_txt:
                    path = os.path.join(export_dir, f"{base_name}_无效源.txt")
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(f"# 本地网络: {self.local_isp}宽带\n")
                        if self.source_isp:
                            f.write(f"# 直播源运营商: {', '.join(self.source_isp)}\n")
                        if self.source_isp and self.local_isp not in ("其他/未知", "未知"):
                            mismatch = self.source_isp - {self.local_isp}
                            if mismatch:
                                f.write(f"# 提示: 部分频道为{', '.join(mismatch)}专属，在{self.local_isp}宽带下可能无法播放\n")
                        f.write("\n")
                        for v in invalid_items:
                            f.write(f"{v[2]},{v[3]} # 错误: {v[7]}\n")
                    exported_files.append((path, f"无效源列表({len(invalid_items)}个)"))
                
                if export_csv:
                    path = os.path.join(export_dir, f"{base_name}_检测结果.csv")
                    with open(path, "w", encoding="utf-8-sig", newline="") as f:
                        writer = csv.writer(f)
                        writer.writerow(["原始序号", "来源文件", "频道名称", "URL", "状态", "延迟(ms)", "速度(KB/s)", "信息"])
                        for i in self.tree_all.get_children(""):
                            v = self.tree_all.item(i, "values")
                            writer.writerow(v)
                    exported_files.append((path, f"CSV明细({len(valid_items)+len(invalid_items)}条)"))
                
                if export_xlsx:
                    try:
                        import openpyxl
                        from openpyxl.styles import Font, Alignment, PatternFill
                        wb = openpyxl.Workbook()
                        ws = wb.active
                        ws.title = "检测结果"
                        headers = ["原始序号", "来源文件", "频道名称", "URL", "状态", "延迟(ms)", "速度(KB/s)", "信息"]
                        header_font = Font(bold=True, color="FFFFFF")
                        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
                        for col_idx, header in enumerate(headers, 1):
                            cell = ws.cell(row=1, column=col_idx, value=header)
                            cell.font = header_font
                            cell.fill = header_fill
                            cell.alignment = Alignment(horizontal="center")
                        for row_idx, i in enumerate(self.tree_all.get_children(""), 2):
                            v = self.tree_all.item(i, "values")
                            for col_idx, val in enumerate(v, 1):
                                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                                if val == "有效":
                                    cell.font = Font(color="00B050")
                                elif val == "无效":
                                    cell.font = Font(color="FF0000")
                        ws.auto_filter.ref = ws.dimensions
                        for col in ws.columns:
                            max_length = max(len(str(cell.value or "")) for cell in col)
                            ws.column_dimensions[col[0].column_letter].width = min(max_length + 4, 50)
                        path = os.path.join(export_dir, f"{base_name}_检测结果.xlsx")
                        wb.save(path)
                        exported_files.append((path, f"Excel表格({len(valid_items)+len(invalid_items)}条)"))
                    except ImportError:
                        exported_files.append((None, "Excel(需pip install openpyxl)"))
            else:
                if export_m3u and valid_items:
                    path = os.path.join(export_dir, f"{base_name}_有效源.m3u")
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(f"#EXTM3U\n")
                        for v in valid_items:
                            f.write(f"#EXTINF:-1,{v[2]}\n{v[3]}\n")
                    exported_files.append((path, f"有效源M3U({len(valid_items)}个)"))
                
                if export_txt and invalid_items:
                    path = os.path.join(export_dir, f"{base_name}_无效源.txt")
                    with open(path, "w", encoding="utf-8") as f:
                        for v in invalid_items:
                            f.write(f"{v[2]},{v[3]} # 错误: {v[7]}\n")
                    exported_files.append((path, f"无效源TXT({len(invalid_items)}个)"))
                
                if export_csv:
                    path = os.path.join(export_dir, f"{base_name}_检测结果.csv")
                    with open(path, "w", encoding="utf-8-sig", newline="") as f:
                        writer = csv.writer(f)
                        writer.writerow(["原始序号", "来源文件", "频道名称", "URL", "状态", "延迟(ms)", "速度(KB/s)", "信息"])
                        for i in self.tree_all.get_children(""):
                            v = self.tree_all.item(i, "values")
                            writer.writerow(v)
                    exported_files.append((path, f"CSV明细({len(valid_items)+len(invalid_items)}条)"))
                
                if export_xlsx:
                    try:
                        import openpyxl
                        from openpyxl.styles import Font, Alignment, PatternFill
                        wb = openpyxl.Workbook()
                        ws = wb.active
                        ws.title = "检测结果"
                        headers = ["原始序号", "来源文件", "频道名称", "URL", "状态", "延迟(ms)", "速度(KB/s)", "信息"]
                        header_font = Font(bold=True, color="FFFFFF")
                        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
                        for col_idx, header in enumerate(headers, 1):
                            cell = ws.cell(row=1, column=col_idx, value=header)
                            cell.font = header_font
                            cell.fill = header_fill
                            cell.alignment = Alignment(horizontal="center")
                        for row_idx, i in enumerate(self.tree_all.get_children(""), 2):
                            v = self.tree_all.item(i, "values")
                            for col_idx, val in enumerate(v, 1):
                                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                                if val == "有效":
                                    cell.font = Font(color="00B050")
                                elif val == "无效":
                                    cell.font = Font(color="FF0000")
                        ws.auto_filter.ref = ws.dimensions
                        for col in ws.columns:
                            max_length = max(len(str(cell.value or "")) for cell in col)
                            ws.column_dimensions[col[0].column_letter].width = min(max_length + 4, 50)
                        path = os.path.join(export_dir, f"{base_name}_检测结果.xlsx")
                        wb.save(path)
                        exported_files.append((path, f"Excel表格({len(valid_items)+len(invalid_items)}条)"))
                    except ImportError:
                        exported_files.append((None, "Excel(需pip install openpyxl)"))
            
            self.last_export_path = export_dir
            self.export_path_label.config(text=f"导出位置: {export_dir}")
            
            file_info = "\n".join([f"  {name}: {path}" if path else f"  {name}" for path, name in exported_files])
            note = "\n💡 多个源文件已自动合并去重，以上为统一检测结果"
            
            messagebox.showinfo(
                "导出成功",
                f"检测结果已导出到:\n{export_dir}\n\n导出文件:\n{file_info}{note}\n\n点击下方的蓝色链接可直接打开文件夹。",
            )
        except Exception as e:
            messagebox.showerror("导出失败", f"导出文件时出错: {e}")

    def open_export_folder(self, event=None):
        if not self.last_export_path or not os.path.isdir(self.last_export_path):
            messagebox.showwarning("提示", "未找到有效的导出文件夹。请先导出结果。")
            return
        try:
            if sys.platform == "win32":
                os.startfile(self.last_export_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", self.last_export_path])
            else:
                subprocess.run(["xdg-open", self.last_export_path])
        except Exception as e:
            messagebox.showerror(
                "打开失败",
                f"无法自动打开文件夹，请手动访问：\n{self.last_export_path}\n错误: {e}",
            )

    def _stop_player_server(self):
        if self.player_server:
            try:
                self.player_server.shutdown()
            except Exception:
                pass
            self.player_server = None
            self.player_server_thread = None
            self.player_server_port = None

    def on_closing(self):
        if self.is_running and messagebox.askyesno("退出", "检测正在进行中，确定要退出吗？"):
            self.stop_checking()
            self.stop_m3u_server()
            self._stop_player_server()
            self.save_cache()
            self.root.destroy()
        elif not self.is_running:
            self.stop_m3u_server()
            self._stop_player_server()
            self.save_cache()
            self.root.destroy()


if __name__ == "__main__":
    root = ttk.Window(themename="litera")
    app = StreamCheckerApp(root)
    root.mainloop()
