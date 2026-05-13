import os
import sys
import threading
from datetime import datetime
from tkinter import ttk, filedialog, messagebox
from ttkbootstrap.constants import *

from iptv_check.app.theme import ThemeManager
from iptv_check.config import APP_TITLE


class WizardView:
    STEPS = [
        ("welcome", "👋 欢迎使用"),
        ("network", "🌐 网络检测"),
        ("source", "📁 选择直播源"),
        ("settings", "⚙️ 参数设置"),
        ("tools", "🛠️ 工具箱"),
        ("finish", "🚀 开始检测"),
    ]

    def __init__(self, parent, app):
        self.app = app
        self.current_step = 0
        self.dont_show_again = app.dont_show_again_var
        self.frame = ttk.Frame(app.root)
        self._build_ui()
        self._show_step(0)

    def _build_ui(self):
        main = ttk.Frame(self.frame, padding=0)
        main.pack(fill=BOTH, expand=True)

        top_frame = ttk.Frame(main, padding=(20, 15, 20, 10), **ThemeManager.style("secondary_action"))
        top_frame.pack(fill=X)

        self.step_indicators = []
        for idx, (step_id, step_title) in enumerate(self.STEPS):
            step_frame = ttk.Frame(top_frame)
            step_frame.pack(side=LEFT, fill=X, expand=True, padx=5)
            circle = ttk.Label(step_frame, text=f"{idx + 1}", width=3, anchor=CENTER, font=ThemeManager.font("step_circle"), **ThemeManager.style("secondary_action"))
            circle.pack(side=LEFT, padx=(0, 8))
            label = ttk.Label(step_frame, text=step_title, font=ThemeManager.font("small"), anchor=W, cursor="hand2", **ThemeManager.style("secondary_action"))
            label.pack(side=LEFT, fill=X, expand=True)
            label.bind("<Button-1>", lambda e, i=idx: self._show_step(i))
            self.step_indicators.append({"frame": step_frame, "circle": circle, "label": label, "id": step_id})
            if idx < len(self.STEPS) - 1:
                ttk.Separator(top_frame, orient=VERTICAL).pack(side=LEFT, fill=Y, padx=5)

        content_frame = ttk.Frame(main, padding=20)
        content_frame.pack(fill=BOTH, expand=True)
        self.step_content = ttk.Frame(content_frame)
        self.step_content.pack(fill=BOTH, expand=True)

        bottom = ttk.Frame(main, padding=(20, 10, 20, 15))
        bottom.pack(fill=X)
        self.progress_label = ttk.Label(bottom, text="步骤 1/6", font=ThemeManager.font("small"), **ThemeManager.style("secondary_action"))
        self.progress_label.pack(side=LEFT)
        ttk.Checkbutton(bottom, text="下次启动不再显示此向导", variable=self.dont_show_again).pack(side=LEFT, padx=20)

        btn_nav = ttk.Frame(bottom)
        btn_nav.pack(side=RIGHT)
        self.prev_btn = ttk.Button(btn_nav, text="← 上一步", command=self._prev_step, **ThemeManager.style("secondary_outline"), state=DISABLED, width=12)
        self.prev_btn.pack(side=LEFT, padx=5)
        self.next_btn = ttk.Button(btn_nav, text="下一步 →", command=self._next_step, **ThemeManager.style("primary_action"), width=12)
        self.next_btn.pack(side=LEFT, padx=5)

    def _show_step(self, index):
        self.current_step = index
        for idx, indicator in enumerate(self.step_indicators):
            if idx < index:
                style = "success_action"
                text = "✓"
            elif idx == index:
                style = "primary_action"
                text = f"{idx + 1}"
            else:
                style = "secondary_action"
                text = f"{idx + 1}"
            indicator["circle"].config(text=text, **ThemeManager.style(style))
            indicator["label"].config(**ThemeManager.style(style))

        for widget in self.step_content.winfo_children():
            widget.destroy()

        self.prev_btn.config(state=NORMAL if index > 0 else DISABLED)
        if index == len(self.STEPS) - 1:
            self.next_btn.config(text=" 开始检测", command=self._finish, **ThemeManager.style("success_action"))
        else:
            self.next_btn.config(text="下一步 →", command=self._next_step, **ThemeManager.style("primary_action"))

        self.progress_label.config(text=f"步骤 {index + 1}/{len(self.STEPS)}")
        builders = [self._build_welcome, self._build_network, self._build_source, self._build_settings, self._build_tools, self._build_finish]
        builders[index]()

    def _build_welcome(self):
        ttk.Label(self.step_content, text="欢迎使用电视直播源检测工具！", font=ThemeManager.font("title"), **ThemeManager.style("primary_action")).pack(pady=(30, 10))
        ttk.Label(self.step_content, text="本工具可帮助您：", font=ThemeManager.font("body")).pack(pady=(0, 20))
        for f in ["✅ 自动检测本地宽带运营商（移动/电信/联通/广电）", "✅ 批量检测直播源链接的可用性和延迟", "✅ 支持在线直播源库，一键匹配运营商", "✅ 导出M3U/TXT/CSV/Excel多种格式", "✅ 支持IPv4/IPv6协议分类导出"]:
            ttk.Label(self.step_content, text=f, font=ThemeManager.font("small"), anchor=W).pack(fill=X, padx=20, pady=2)

    def _build_network(self):
        isp = self.app.local_isp if self.app.local_isp != "未知" else "检测中..."
        ttk.Label(self.step_content, text="网络运营商检测", font=ThemeManager.font("subtitle"), **ThemeManager.style("info_action")).pack(pady=(20, 10))
        ttk.Label(self.step_content, text=f"当前网络：{isp}宽带", font=ThemeManager.font("body"), **ThemeManager.style("success_action")).pack(pady=10)
        if isp == "检测中...":
            ttk.Label(self.step_content, text="⏳ 正在检测运营商信息，请稍候...", font=ThemeManager.font("small"), **ThemeManager.style("warning_action")).pack(pady=5)
        ttk.Label(self.step_content, text="运营商会影响在线直播源的匹配推荐。\n部分频道可能为特定运营商专属，更换宽带后可能无法播放。", font=ThemeManager.font("small"), anchor=CENTER, **ThemeManager.style("secondary_action")).pack(pady=(20, 0))

    def _build_source(self):
        ttk.Label(self.step_content, text="选择直播源", font=ThemeManager.font("subtitle"), **ThemeManager.style("primary_action")).pack(pady=(20, 10))
        ttk.Label(self.step_content, text="请选择要检测的直播源：", font=ThemeManager.font("body")).pack(pady=(0, 20))
        options_frame = ttk.Frame(self.step_content)
        options_frame.pack(fill=X, padx=20, pady=10)
        ttk.Button(options_frame, text="📁 选择本地文件", command=self._browse_file_in_wizard, **ThemeManager.style("primary_action"), width=20).pack(pady=5, fill=X)
        ttk.Button(options_frame, text="📡 选择在线源库", command=self._show_online_in_wizard, **ThemeManager.style("info_action"), width=20).pack(pady=5, fill=X)
        ttk.Label(self.step_content, text="💡 本地文件：选择已有的M3U/TXT文件\n在线源库：从预设源库中下载最新直播源", font=ThemeManager.font("tiny"), anchor=CENTER, **ThemeManager.style("secondary_action")).pack(pady=(15, 0))

    def _build_settings(self):
        ttk.Label(self.step_content, text="参数设置", font=ThemeManager.font("subtitle"), **ThemeManager.style("warning_action")).pack(pady=(20, 10))
        settings_frame = ttk.LabelFrame(self.step_content, text="检测参数")
        settings_frame.pack(fill=X, padx=20, pady=10)
        inner = ttk.Frame(settings_frame, padding=15)
        inner.pack(fill=X, expand=True)
        inner.columnconfigure(1, weight=1)
        params = [("连接超时(秒):", self.app.timeout_connect, 1, 30), ("读取超时(秒):", self.app.timeout_read, 1, 60), ("线程数:", self.app.max_threads, 1, 100)]
        for row, (label_text, var, from_, to_) in enumerate(params):
            ttk.Label(inner, text=label_text, font=ThemeManager.font("small")).grid(row=row, column=0, sticky=W, pady=8)
            ttk.Spinbox(inner, from_=from_, to=to_, textvariable=var, width=8).grid(row=row, column=1, sticky=W, padx=10, pady=8)
        extra = ttk.Frame(inner)
        extra.grid(row=len(params), column=0, columnspan=2, sticky=W, pady=(10, 0))
        ttk.Checkbutton(extra, text="速度测试(较慢但更准确)", variable=self.app.run_speed_test).pack(anchor=W, pady=2)
        ttk.Checkbutton(extra, text="使用缓存(加速重复检测)", variable=self.app.use_cache).pack(anchor=W, pady=2)

    def _build_tools(self):
        ttk.Label(self.step_content, text="工具箱", font=ThemeManager.font("subtitle"), **ThemeManager.style("info_action")).pack(pady=(20, 10))
        tools_frame = ttk.Frame(self.step_content)
        tools_frame.pack(fill=X, padx=20, pady=10)
        ttk.Button(tools_frame, text="🔄 格式转换", command=self.app.show_converter_dialog, **ThemeManager.style("warning_action"), width=20).pack(pady=5, fill=X)
        ttk.Button(tools_frame, text="🌐 M3U在线服务", command=self.app.toggle_m3u_server, **ThemeManager.style("info_action"), width=20).pack(pady=5, fill=X)
        ttk.Button(tools_frame, text="📦 在线源库管理", command=self.app.show_online_sources_dialog, **ThemeManager.style("secondary_action"), width=20).pack(pady=5, fill=X)

    def _build_finish(self):
        ttk.Label(self.step_content, text="准备就绪！", font=("Microsoft YaHei", 18, "bold"), **ThemeManager.style("success_action")).pack(pady=(30, 15))
        has_files = len(self.app.file_paths) > 0
        source_text = f"已选择 {len(self.app.file_paths)} 个本地文件" if has_files else "未选择本地文件"
        config_frame = ttk.LabelFrame(self.step_content, text=" 当前配置")
        config_frame.pack(fill=X, padx=50, pady=10)
        ttk.Label(config_frame, text=f"📁 直播源：{source_text}", font=ThemeManager.font("body")).pack(fill=X, pady=5)
        ttk.Label(config_frame, text=f"🌐 运营商：{self.app.local_isp}宽带", font=ThemeManager.font("body")).pack(fill=X, pady=5)
        start_btn = ttk.Button(self.step_content, text="🚀 开始检测", command=self._finish, **ThemeManager.style("success_action"), width=20)
        start_btn.pack(pady=(30, 10))
        if not has_files:
            ttk.Label(self.step_content, text="⚠️ 请先在步骤3选择直播源后再开始检测！", font=ThemeManager.font("small"), **ThemeManager.style("warning_action")).pack(pady=(10, 0))
            start_btn.config(state=DISABLED, **ThemeManager.style("secondary_outline"))

    def _browse_file_in_wizard(self):
        paths = filedialog.askopenfilenames(title="选择直播源文件(可多选)", filetypes=(("M3U/TXT", "*.m3u;*.txt"), ("All files", "*.*")))
        if paths:
            self.app.file_paths = list(paths)
            self.app.file_path_display.set(f"{len(paths)} 个文件" if len(paths) > 1 else os.path.basename(paths[0]))
            self.app.export_dir_var.set(os.path.dirname(paths[0]))
            self._show_step(self.current_step)

    def _show_online_in_wizard(self):
        self.app.show_online_sources_dialog()
        self._show_step(self.current_step)

    def _prev_step(self):
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    def _next_step(self):
        if self.current_step < len(self.STEPS) - 1:
            self._show_step(self.current_step + 1)

    def _finish(self):
        if self.dont_show_again.get():
            self.app.settings.set("skip_wizard", True)
        self.app.show_results_view()
        if len(self.app.file_paths) > 0:
            self.app.start_checking()
