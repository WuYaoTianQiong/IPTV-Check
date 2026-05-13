import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from ttkbootstrap.constants import *

from iptv_check.app.theme import ThemeManager
from iptv_check.config import APP_TITLE, PAGES_PER_VIEW
from iptv_check.models.check_result import CheckResult


RESULT_COLUMNS = ("原始序号", "来源文件", "频道名称", "URL", "状态", "延迟(ms)", "速度(KB/s)", "信息", "播放")


class ResultView:
    def __init__(self, parent, app):
        self.app = app
        self.frame = ttk.Frame(parent, padding="10")
        self.frame.pack(fill=BOTH, expand=True)
        self.all_items_data = {"all": [], "valid": [], "invalid": []}
        self.sort_state = {k: {"col": "原始序号", "rev": False} for k in ["all", "valid", "invalid"]}
        self.current_active_tab = "all"
        self.pagination_widgets = {}
        self._build_ui()

    def _build_ui(self):
        self._build_top_bar()
        self._build_isp_status()
        self._build_control_bar()
        self._build_status_bar()
        self._build_search_bar()
        self._build_result_table()

    def _build_top_bar(self):
        top_frame = ttk.Frame(self.frame)
        top_frame.pack(fill=X, pady=5)
        top_frame.grid_columnconfigure(0, weight=1)

        config_frame = ttk.LabelFrame(top_frame, text="配置选项", padding="10")
        config_frame.grid(row=0, column=0, sticky="ew")
        config_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(config_frame, text="源文件:").grid(row=0, column=0, padx=5, pady=5, sticky=W)
        self.file_entry = ttk.Entry(config_frame, textvariable=self.app.file_path_display, state="readonly", cursor="hand2")
        self.file_entry.grid(row=0, column=1, columnspan=3, padx=5, pady=5, sticky=EW)
        self.file_entry.bind("<Button-1>", lambda e: self.app.browse_file())
        self.browse_button = ttk.Button(config_frame, text="浏览(可多选)...", command=self.app.browse_file, **ThemeManager.style("primary_outline"))
        self.browse_button.grid(row=0, column=4, padx=5, pady=5)

        ttk.Label(config_frame, text="导出位置:").grid(row=1, column=0, padx=5, pady=5, sticky=W)
        self.export_dir_entry = ttk.Entry(config_frame, textvariable=self.app.export_dir_var, cursor="hand2")
        self.export_dir_entry.grid(row=1, column=1, columnspan=3, padx=5, pady=5, sticky=EW)
        self.export_dir_entry.bind("<Button-1>", lambda e: self.app.browse_export_dir())
        self.browse_export_dir_button = ttk.Button(config_frame, text="更改...", command=self.app.browse_export_dir, **ThemeManager.style("primary_outline"))
        self.browse_export_dir_button.grid(row=1, column=4, padx=5, pady=5)

        ttk.Label(config_frame, text="连接超时(s):").grid(row=2, column=0, padx=5, pady=5, sticky=W)
        self.timeout_connect_spinbox = ttk.Spinbox(config_frame, from_=1, to=30, textvariable=self.app.timeout_connect, width=8)
        self.timeout_connect_spinbox.grid(row=2, column=1, padx=5, pady=5, sticky=W)

        ttk.Label(config_frame, text="读取超时(s):").grid(row=2, column=2, padx=(10, 5), pady=5, sticky=W)
        self.timeout_read_spinbox = ttk.Spinbox(config_frame, from_=1, to=60, textvariable=self.app.timeout_read, width=8)
        self.timeout_read_spinbox.grid(row=2, column=3, padx=5, pady=5, sticky=W)

        ttk.Label(config_frame, text="线程数:").grid(row=3, column=0, padx=5, pady=5, sticky=W)
        self.threads_spinbox = ttk.Spinbox(config_frame, from_=1, to=100, textvariable=self.app.max_threads, width=8)
        self.threads_spinbox.grid(row=3, column=1, padx=5, pady=5, sticky=W)

        check_frame = ttk.Frame(config_frame)
        check_frame.grid(row=3, column=2, columnspan=3, padx=5, pady=5, sticky=W)
        ttk.Checkbutton(check_frame, text="速度测试(慢)", variable=self.app.run_speed_test, **ThemeManager.style("success_toggle")).pack(side=LEFT, padx=(0, 5))
        ttk.Checkbutton(check_frame, text="使用缓存", variable=self.app.use_cache, **ThemeManager.style("info_toggle")).pack(side=LEFT)

    def _build_isp_status(self):
        self.isp_status_frame = ttk.Frame(self.frame)
        self.isp_status_frame.pack(fill=X, pady=(0, 5))
        self.isp_label = ttk.Label(self.isp_status_frame, text="当前网络: 检测中...", **ThemeManager.style("info_action"))
        self.isp_label.pack(side=LEFT, padx=5)
        self.isp_match_label = ttk.Label(self.isp_status_frame, text="", **ThemeManager.style("success_action"))
        self.isp_match_label.pack(side=LEFT)

    def _build_control_bar(self):
        ctrl_frame = ttk.Frame(self.frame)
        ctrl_frame.pack(fill=X, pady=10)

        self.start_button = ttk.Button(ctrl_frame, text="开始检测", command=self.app.start_checking, **ThemeManager.style("success_action"))
        self.start_button.pack(side=LEFT, padx=5, fill=X, expand=True)

        self.stop_button = ttk.Button(ctrl_frame, text="停止检测", command=self.app.stop_checking, **ThemeManager.style("danger_action"), state=DISABLED)
        self.stop_button.pack(side=LEFT, padx=5, fill=X, expand=True)

        self.export_button = ttk.Button(ctrl_frame, text="导出结果", command=self.app.export_results, **ThemeManager.style("info_action"), state=DISABLED)
        self.export_button.pack(side=LEFT, padx=5, fill=X, expand=True)

        ttk.Button(ctrl_frame, text="📡 在线源库", command=self.app.show_online_sources_dialog, **ThemeManager.style("primary_action")).pack(side=LEFT, padx=5, fill=X, expand=True)
        ttk.Button(ctrl_frame, text="🔄 格式转换", command=self.app.show_converter_dialog, **ThemeManager.style("warning_action")).pack(side=LEFT, padx=5, fill=X, expand=True)
        ttk.Button(ctrl_frame, text="❓ 帮助", command=self.app.show_wizard, **ThemeManager.style("info_action")).pack(side=LEFT, padx=5, fill=X, expand=True)
        ttk.Button(ctrl_frame, text="🌐 在线服务", command=self.app.toggle_m3u_server, **ThemeManager.style("secondary_action")).pack(side=LEFT, padx=5, fill=X, expand=True)
        ttk.Button(ctrl_frame, text="切换主题", command=self.app.toggle_theme, **ThemeManager.style("secondary_action")).pack(side=LEFT, padx=5, fill=X, expand=True)

    def _build_status_bar(self):
        status_frame = ttk.LabelFrame(self.frame, text="检测状态", padding="10")
        status_frame.pack(fill=X, pady=5)
        status_frame.grid_columnconfigure(1, weight=1)

        self.status_label = ttk.Label(status_frame, textvariable=self.app.status_message, anchor=W)
        self.status_label.grid(row=4, column=0, columnspan=2, padx=5, pady=(10, 5), sticky=EW)

        self.progress_bar = ttk.Progressbar(status_frame, mode="determinate")
        self.progress_bar.grid(row=0, column=0, columnspan=4, padx=5, pady=5, sticky=EW)

        stats_inner = ttk.Frame(status_frame)
        stats_inner.grid(row=1, column=0, columnspan=4, sticky=E)
        for label_text, var in [("总数:", self.app.total_links), ("已检:", self.app.checked_links)]:
            ttk.Label(stats_inner, text=label_text).pack(side=LEFT, padx=(0, 2))
            ttk.Label(stats_inner, textvariable=var).pack(side=LEFT, padx=(0, 10))
        ttk.Label(stats_inner, text="有效:").pack(side=LEFT, padx=(0, 2))
        ttk.Label(stats_inner, textvariable=self.app.valid_links, foreground="green").pack(side=LEFT, padx=(0, 10))
        ttk.Label(stats_inner, text="无效:").pack(side=LEFT, padx=(0, 2))
        ttk.Label(stats_inner, textvariable=self.app.invalid_links, foreground="red").pack(side=LEFT)

        self.thread_status_label = ttk.Label(stats_inner, text="", foreground="gray")
        self.thread_status_label.pack(side=LEFT, padx=(10, 0))

        self.export_path_label = ttk.Label(status_frame, text="", **ThemeManager.style("link"), cursor="hand2")
        self.export_path_label.grid(row=3, column=0, columnspan=4, padx=5, pady=(10, 5), sticky=W)
        self.export_path_label.bind("<Button-1>", self.app.open_export_folder)

    def _build_search_bar(self):
        search_frame = ttk.Frame(self.frame)
        search_frame.pack(fill=X, pady=(0, 5))
        ttk.Label(search_frame, text="搜索:").pack(side=LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.apply_search_filter())
        ttk.Entry(search_frame, textvariable=self.search_var).pack(side=LEFT, fill=X, expand=True, padx=(0, 5))
        self.clear_search_btn = ttk.Button(search_frame, text="清除", command=self.clear_search, state=DISABLED, width=8)
        self.clear_search_btn.pack(side=LEFT)

    def _build_result_table(self):
        result_frame = ttk.LabelFrame(self.frame, text="检测结果 (支持Ctrl/Shift多选, 右键可复制)", padding="10")
        result_frame.pack(fill=BOTH, expand=True, pady=5)

        self.notebook = ttk.Notebook(result_frame)
        self.notebook.pack(fill=BOTH, expand=True)

        for name, text in [("all", "全部"), ("valid", "有效源"), ("invalid", "无效源")]:
            self._create_result_tab(name, text)

        result_bottom = ttk.Frame(result_frame)
        result_bottom.pack(fill=X, pady=(5, 0))

        from iptv_check.app.widgets.pagination import PaginationWidget
        for tab_name in ["all", "valid", "invalid"]:
            pagination = PaginationWidget(result_bottom, items_per_page=PAGES_PER_VIEW, on_page_change=lambda page, t=tab_name: self._on_page_change(page, t))
            self.pagination_widgets[tab_name] = pagination
            pagination.frame.pack_forget()

        self.pagination_widgets["all"].frame.pack(fill=X)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def _create_result_tab(self, name, text):
        tab = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(tab, text=text)
        tree = ttk.Treeview(tab, columns=RESULT_COLUMNS, show="headings", height=15, selectmode="extended")
        setattr(self, f"tree_{name}", tree)
        tree.bind("<Button-3>", lambda event, t=tree: self._show_context_menu(event, t))
        tree.bind("<Control-a>", lambda event, t=tree: self._select_all_items(t))
        tree.bind("<Control-A>", lambda event, t=tree: self._select_all_items(t))
        tree.bind("<ButtonRelease-1>", lambda event, t=tree, t_name=name: self._on_tree_click(event, t, t_name))

        for col in RESULT_COLUMNS:
            tree.heading(col, text=col, command=lambda _col=col, _tree_name=name: self._sort_column(getattr(self, f"tree_{_tree_name}"), _col, _tree_name))

        widths = {"原始序号": 60, "来源文件": 90, "频道名称": 130, "URL": 300, "状态": 60, "延迟(ms)": 80, "速度(KB/s)": 90, "信息": 130, "播放": 50}
        anchors = {"原始序号": CENTER, "状态": CENTER, "延迟(ms)": CENTER, "速度(KB/s)": CENTER, "播放": CENTER}
        for col in RESULT_COLUMNS:
            tree.column(col, width=widths.get(col, 100), anchor=anchors.get(col, W))

        vsb = ttk.Scrollbar(tab, orient=VERTICAL, command=tree.yview)
        hsb = ttk.Scrollbar(tab, orient=HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=RIGHT, fill=Y)
        hsb.pack(side=BOTTOM, fill=X)
        tree.pack(fill=BOTH, expand=True)
        tree.tag_configure("valid", foreground="green")
        tree.tag_configure("invalid", foreground="red")

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
                filtered = [item for item in self.all_items_data[tab_name] if not query or any(query in str(v).lower() for v in item["values"])]
                for item in filtered[start_idx:end_idx]:
                    tree.insert("", END, values=item["values"], tags=(item["tag"],))
                pagination.set_total_items(len(filtered))

    def insert_result(self, result: CheckResult):
        values = result.to_tree_values()
        play_icon = "▶"
        values_with_play = values + (play_icon,)
        item_data = {"values": values_with_play, "tag": result.tag}
        tab_name = "valid" if result.is_valid else "invalid"
        self.all_items_data["all"].append(item_data)
        self.all_items_data[tab_name].append(item_data)
        if tab_name == self.current_active_tab or self.current_active_tab == "all":
            tree = getattr(self, f"tree_{self.current_active_tab}")
            tree.insert("", END, values=values_with_play, tags=(result.tag,))
        for tab_name_update in ["all", "valid", "invalid"]:
            if tab_name_update in self.pagination_widgets:
                self.pagination_widgets[tab_name_update].set_total_items(len(self.all_items_data[tab_name_update]))

    def reset(self):
        self.app.checked_links.set(0)
        self.app.valid_links.set(0)
        self.app.invalid_links.set(0)
        self.progress_bar["value"] = 0
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

    def toggle_controls(self, is_checking: bool):
        state = DISABLED if is_checking else NORMAL
        for widget in [self.start_button, self.browse_button, self.browse_export_dir_button, self.timeout_connect_spinbox, self.timeout_read_spinbox, self.threads_spinbox]:
            widget.config(state=state)
        self.stop_button.config(state=NORMAL if is_checking else DISABLED)

    def _on_tab_change(self, event=None):
        tab_names = ["all", "valid", "invalid"]
        idx = self.notebook.index(self.notebook.select())
        new_tab = tab_names[idx] if idx < len(tab_names) else "all"
        if new_tab != self.current_active_tab:
            if self.current_active_tab in self.pagination_widgets:
                self.pagination_widgets[self.current_active_tab].frame.pack_forget()
            if new_tab in self.pagination_widgets:
                self.pagination_widgets[new_tab].frame.pack(fill=X)
            self.current_active_tab = new_tab

    def _on_page_change(self, page, tab_name):
        self._refresh_current_page()

    def _refresh_current_page(self):
        tab_name = self.current_active_tab
        tree = getattr(self, f"tree_{tab_name}")
        pagination = self.pagination_widgets.get(tab_name)
        if not pagination:
            return
        tree.delete(*tree.get_children())
        start_idx, end_idx = pagination.get_page_range()
        for item in self.all_items_data.get(tab_name, [])[start_idx:end_idx]:
            tree.insert("", END, values=item["values"], tags=(item["tag"],))

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
                        self.app.play_url(channel_url, channel_name)

    def _select_all_items(self, tree):
        tree.selection_set(tree.get_children())
        return "break"

    def _show_context_menu(self, event, tree):
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
        context_menu.add_command(label="▶ 播放此频道", command=lambda: self.app.play_channel(tree))
        context_menu.add_separator()
        context_menu.add_command(label="复制 URL", command=lambda: self._copy_cell(tree, "URL"))
        context_menu.add_command(label="复制 频道名称", command=lambda: self._copy_cell(tree, "频道名称"))
        context_menu.add_separator()
        context_menu.add_command(label="复制 整行数据", command=lambda: self._copy_cell(tree, None))
        context_menu.add_separator()
        context_menu.add_command(label="⚡ 智能优选（同频道选最快源）", command=self.app.smart_select_optimize)
        context_menu.post(event.x_root, event.y_root)

    def _copy_cell(self, tree, column_name):
        selected_items = tree.selection()
        if not selected_items:
            return
        item_id = selected_items[0]
        all_values = tree.item(item_id, "values")
        if column_name is None:
            text = ", ".join(map(str, all_values))
        else:
            try:
                col_index = tree["columns"].index(column_name)
                text = str(all_values[col_index])
            except (ValueError, IndexError):
                return
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(text)

    def _sort_column(self, tv, col, tree_name):
        sort_info = self.sort_state[tree_name]
        reverse = not sort_info["rev"] if col == sort_info["col"] else False
        sort_info["col"] = col
        sort_info["rev"] = reverse
        items = [(tv.set(k, col), k) for k in tv.get_children("")]
        def safe_float(s):
            try:
                return float(s)
            except (ValueError, TypeError):
                return -1
        if col in ("原始序号", "延迟(ms)", "速度(KB/s)"):
            items.sort(key=lambda t: safe_float(t[0]), reverse=reverse)
        else:
            items.sort(key=lambda t: str(t[0]).lower(), reverse=reverse)
        for index, (val, k) in enumerate(items):
            tv.move(k, "", index)
