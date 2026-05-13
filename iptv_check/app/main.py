import os
import sys
import time
import json
import re
import csv
import hashlib
import threading
import queue
import webbrowser
import subprocess
import logging
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from ttkbootstrap.constants import *
from datetime import datetime

from iptv_check.config import APP_TITLE, get_asset_path
from iptv_check.app.theme import ThemeManager
from iptv_check.app.views.wizard_view import WizardView
from iptv_check.app.views.result_view import ResultView
from iptv_check.models.channel import Channel
from iptv_check.models.check_result import CheckResult
from iptv_check.models.source import OnlineSource
from iptv_check.models.settings import CheckConfig
from iptv_check.infra.network import HttpClient
from iptv_check.infra.cache import CacheManager
from iptv_check.infra.persistence import SettingsManager
from iptv_check.infra.state import StateStore, AppState
from iptv_check.infra.event_bus import Events
from iptv_check.infra.exporter import ExportEngine
from iptv_check.infra.m3u_server import M3UServer
from iptv_check.infra.player import PlayerService
from iptv_check.core.checker import CheckEngine
from iptv_check.core.isp_detector import ISPDetector
from iptv_check.core.parser import PlaylistParser
from iptv_check.core.converter import FormatConverter
from iptv_check.core.optimizer import SmartOptimizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class Application:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1300x850")

        icon_path = get_asset_path("icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except tk.TclError:
                pass

        self.http_client = HttpClient()
        self.cache = CacheManager(base_dir=os.path.dirname(os.path.abspath(__file__)))
        self.settings = SettingsManager(base_dir=os.path.dirname(os.path.abspath(__file__)))
        self.state = StateStore()
        self.check_engine = CheckEngine(self.http_client, self.cache, self.state)
        self.isp_detector = ISPDetector(self.http_client)
        self.export_engine = ExportEngine()
        self.m3u_server = M3UServer()
        self.player = PlayerService()
        self.player.set_http_client(self.http_client)

        self.file_paths = []
        self.local_isp = "未知"
        self.source_isp = set()
        self.online_sources = []
        self.is_running = False
        self.stop_requested = False

        self.file_path_display = tk.StringVar(value="未选择文件")
        self.export_dir_var = tk.StringVar()
        self.source_file_basename = tk.StringVar()
        self.timeout_connect = tk.IntVar(value=self.settings.get("timeout_connect", 3))
        self.timeout_read = tk.IntVar(value=self.settings.get("timeout_read", 8))
        self.max_threads = tk.IntVar(value=self.settings.get("max_threads", 30))
        self.run_speed_test = tk.BooleanVar(value=True)
        self.use_cache = tk.BooleanVar(value=True)
        self.status_message = tk.StringVar()
        self.total_links = tk.IntVar(value=0)
        self.checked_links = tk.IntVar(value=0)
        self.valid_links = tk.IntVar(value=0)
        self.invalid_links = tk.IntVar(value=0)
        self.dont_show_again_var = tk.BooleanVar(value=False)
        self.last_export_path = None

        self.wizard_view = None
        self.result_view = None
        self.results = []

        self._load_online_sources()
        self._bind_events()

        threading.Thread(target=self._detect_isp_async, daemon=True).start()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        if not self.settings.get("skip_wizard", False):
            self.show_wizard()
        else:
            self.show_results_view()

    def _load_online_sources(self):
        try:
            sources_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_sources.json")
            if os.path.exists(sources_file):
                with open(sources_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.online_sources = [OnlineSource.from_dict(s) for s in data.get("sources", [])]
                logger.info("加载了 %d 个在线直播源", len(self.online_sources))
        except Exception as e:
            logger.warning("加载本地源配置失败: %s", e)
            self.online_sources = []

    def _detect_isp_async(self):
        self.local_isp = self.isp_detector.detect_local_isp()
        self.root.after(0, self._update_isp_display)

    def _update_isp_display(self):
        if self.result_view and hasattr(self.result_view, "isp_label"):
            self.result_view.isp_label.config(text=f"🌐 当前网络: {self.local_isp}宽带", **ThemeManager.style("info_action"))

    def _bind_events(self):
        Events.isp_detected.connect(self._on_isp_detected)
        Events.channel_checked.connect(self._on_channel_checked)
        Events.check_completed.connect(self._on_check_completed)

    def _on_isp_detected(self, sender, **kwargs):
        self.local_isp = kwargs.get("isp", "未知")

    def _on_channel_checked(self, sender, **kwargs):
        result = kwargs.get("result")
        if result and self.result_view:
            self.root.after(0, lambda: self.result_view.insert_result(result))

    def _on_check_completed(self, sender, **kwargs):
        self.root.after(0, self._handle_check_complete)

    def _handle_check_complete(self):
        self.is_running = False
        if self.result_view:
            self.result_view.toggle_controls(False)
            self.result_view.export_button.config(state=NORMAL)
        self.cache.save()
        self.root.title(f"{APP_TITLE} - 检测完成")
        messagebox.showinfo("完成", f"检测完成！\n有效: {self.valid_links.get()}\n无效: {self.invalid_links.get()}")

    def show_wizard(self):
        if self.result_view:
            self.result_view.frame.pack_forget()
        if not self.wizard_view:
            self.wizard_view = WizardView(self.root, self)
            self.wizard_view.frame.pack(fill=BOTH, expand=True)
        else:
            self.wizard_view.frame.pack(fill=BOTH, expand=True)

    def show_results_view(self):
        if self.wizard_view:
            self.wizard_view.frame.pack_forget()
        if not self.result_view:
            self.result_view = ResultView(self.root, self)
            self.result_view.frame.pack(fill=BOTH, expand=True)
        else:
            self.result_view.frame.pack(fill=BOTH, expand=True)

    def browse_file(self):
        paths = filedialog.askopenfilenames(title="选择直播源文件(可多选)", filetypes=(("M3U/TXT", "*.m3u;*.txt"), ("All files", "*.*")))
        if paths:
            self.file_paths = list(paths)
            display_text = f"{len(paths)} 个文件" if len(paths) > 1 else os.path.basename(paths[0])
            self.file_path_display.set(display_text)
            directory = os.path.dirname(paths[0])
            basename = os.path.splitext(os.path.basename(paths[0]))[0]
            if len(paths) > 1:
                basename = "批量检测_" + datetime.now().strftime("%Y%m%d_%H%M%S")
            self.export_dir_var.set(directory)
            self.source_file_basename.set(basename)

    def browse_export_dir(self):
        directory = filedialog.askdirectory(title="选择导出位置")
        if directory:
            self.export_dir_var.set(directory)

    def start_checking(self):
        if not self.file_paths:
            messagebox.showwarning("提示", "请先选择至少一个源文件！")
            return
        channels = PlaylistParser.parse_files(self.file_paths)
        if not channels:
            messagebox.showwarning("提示", "未解析到任何链接！")
            return

        self.source_isp = ISPDetector.detect_source_isp(self.file_paths, channels, self.local_isp)
        self.is_running = True
        self.stop_requested = False

        if self.result_view:
            self.result_view.reset()
            self.result_view.toggle_controls(True)

        self.total_links.set(len(channels))
        if self.result_view:
            self.result_view.progress_bar["maximum"] = len(channels)

        config = CheckConfig(
            timeout_connect=self.timeout_connect.get(),
            timeout_read=self.timeout_read.get(),
            max_threads=self.max_threads.get(),
            run_speed_test=self.run_speed_test.get(),
            use_cache=self.use_cache.get(),
        )
        self.http_client.update_timeout(config.timeout_connect, config.timeout_read)

        self.check_engine.start(channels, config, on_result=self._on_result_ui, on_complete=None)

    def _on_result_ui(self, result: CheckResult):
        if self.stop_requested:
            return
        if self.result_view:
            self.root.after(0, lambda: self.result_view.insert_result(result))
            self.root.after(0, lambda: self.result_view.progress_bar.configure(value=self.checked_links.get()))

    def stop_checking(self):
        if not self.is_running:
            return
        self.stop_requested = True
        self.is_running = False
        self.check_engine.stop()
        if self.result_view:
            self.result_view.toggle_controls(False)
        self.root.title(f"{APP_TITLE} - 已由用户中断")

    def toggle_theme(self):
        ThemeManager.toggle(self.root.style)

    def play_url(self, url: str, name: str):
        self.player.play(url, name)
        self._set_status(f"正在播放: {name}", duration=3000)

    def play_channel(self, tree):
        selected = tree.selection()
        if not selected:
            return
        item_id = selected[0]
        values = tree.item(item_id, "values")
        if len(values) >= 4:
            name, url = values[2], values[3]
            if values[4] != "有效":
                if not messagebox.askyesno("警告", f"频道 [{name}] 检测为无效源，是否仍尝试播放？"):
                    return
            self.play_url(url, name)

    def show_online_sources_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("📡 在线直播源库")
        dialog.geometry("600x550")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="选择在线直播源（自动匹配您的宽带运营商）", font=ThemeManager.font("body")).pack(pady=(15, 5))
        ttk.Label(dialog, text=f"当前网络：{self.local_isp}宽带", foreground="gray").pack(pady=(0, 10))

        sources_frame = ttk.Frame(dialog)
        sources_frame.pack(fill=BOTH, expand=True, padx=15, pady=5)

        canvas = tk.Canvas(sources_frame)
        scrollbar = ttk.Scrollbar(sources_frame, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        source_vars = []
        categorized = {}
        for source in self.online_sources:
            if source.disabled:
                continue
            cat = source.category
            categorized.setdefault(cat, []).append(source)

        row = 0
        for category, sources in categorized.items():
            ttk.Label(scrollable, text=f"--- {category} ---", font=ThemeManager.font("small")).grid(row=row, column=0, columnspan=4, sticky=W, pady=(10, 2))
            row += 1
            for source in sources:
                var = tk.BooleanVar(value=False)
                source_vars.append({"var": var, "source": source})
                isp_match = source.is_isp_compatible(self.local_isp)
                state = "normal" if isp_match else "disabled"
                hint = f"[{source.protocol.upper()}]" + ("" if isp_match else " (可能不兼容)")
                ttk.Checkbutton(scrollable, text=source.name, variable=var, state=state).grid(row=row, column=0, columnspan=3, sticky=W, padx=5)
                ttk.Label(scrollable, text=hint, **ThemeManager.style("success_action") if isp_match else ThemeManager.style("warning_action"), font=ThemeManager.font("tiny")).grid(row=row, column=3, sticky=E, padx=5)
                row += 1

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=X, padx=15, pady=15)

        def download_and_check():
            selected = [item["source"] for item in source_vars if item["var"].get()]
            if not selected:
                messagebox.showwarning("提示", "请至少选择一个直播源！", parent=dialog)
                return
            dialog.destroy()
            self._download_and_check_sources(selected)

        ttk.Button(btn_frame, text="全选匹配", command=lambda: [item["var"].set(True) for item in source_vars if item["source"].is_isp_compatible(self.local_isp)], width=10).pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text="取消全选", command=lambda: [item["var"].set(False) for item in source_vars], width=10).pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text="一键检测选中源", command=download_and_check, **ThemeManager.style("success_action"), width=15).pack(side=RIGHT, padx=5)

    def _download_and_check_sources(self, selected_sources):
        all_channels = []
        url_seen = {}
        for source in selected_sources:
            self._set_status(f"正在下载: {source.name}...")
            try:
                url = source.url
                if source.mirror_url and self.local_isp not in source.isp:
                    url = source.mirror_url
                resp = self.http_client.get(url, timeout=(30, 30))
                if resp.status_code == 200:
                    channels = PlaylistParser.parse_m3u_content(resp.text, source.name)
                    for ch in channels:
                        if ch.url_key in url_seen:
                            existing = url_seen[ch.url_key]
                            for src in ch.sources:
                                if src not in existing.sources:
                                    existing.sources.append(src)
                        else:
                            url_seen[ch.url_key] = ch
                            all_channels.append(ch)
                    self._set_status(f"已下载: {source.name} ({len(channels)} 个频道)", duration=2000)
                else:
                    self._set_status(f"下载失败: {source.name}", error=True, duration=3000)
            except Exception as e:
                self._set_status(f"下载失败: {source.name} ({e})", error=True, duration=3000)

        if not all_channels:
            messagebox.showerror("错误", "未解析到任何直播源链接！")
            return

        for idx, ch in enumerate(all_channels, 1):
            ch.index = idx

        self.file_path_display.set(f"在线源库 ({len(selected_sources)} 个源)")
        self.source_file_basename.set("在线源库_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        self.source_isp = set()
        for src in selected_sources:
            self.source_isp.update(src.isp)

        config = CheckConfig(
            timeout_connect=self.timeout_connect.get(),
            timeout_read=self.timeout_read.get(),
            max_threads=self.max_threads.get(),
            run_speed_test=self.run_speed_test.get(),
            use_cache=self.use_cache.get(),
        )

        self.is_running = True
        self.stop_requested = False
        if self.result_view:
            self.result_view.reset()
            self.result_view.toggle_controls(True)
        self.total_links.set(len(all_channels))
        if self.result_view:
            self.result_view.progress_bar["maximum"] = len(all_channels)

        self.check_engine.start(all_channels, config, on_result=self._on_result_ui, on_complete=None)

    def show_converter_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("🔄 直播源格式转换")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="选择要转换的文件", font=ThemeManager.font("body")).pack(pady=(15, 5))
        file_frame = ttk.LabelFrame(dialog, text="输入文件")
        file_frame.pack(fill=X, padx=15, pady=5)
        input_file_var = tk.StringVar(value="未选择文件")
        input_files = []

        def browse_input():
            paths = filedialog.askopenfilenames(title="选择直播源文件", filetypes=(("M3U/TXT", "*.m3u;*.txt"), ("All files", "*.*")))
            if paths:
                input_files.clear()
                input_files.extend(paths)
                input_file_var.set(f"{len(paths)} 个文件" if len(paths) > 1 else os.path.basename(paths[0]))

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
            for path in input_files:
                try:
                    FormatConverter.convert_file(path, output_format.get())
                except Exception as e:
                    messagebox.showerror("转换失败", f"转换 {path} 时出错: {e}", parent=dialog)
                    return
            messagebox.showinfo("成功", f"成功转换 {len(input_files)} 个文件！", parent=dialog)
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=X, padx=15, pady=15)
        ttk.Button(btn_frame, text="开始转换", command=do_convert, **ThemeManager.style("success_action"), width=15).pack(side=LEFT, padx=5, fill=X, expand=True)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy, width=15).pack(side=LEFT, padx=5, fill=X, expand=True)

    def toggle_m3u_server(self):
        if self.m3u_server.is_running:
            self.m3u_server.stop()
            self._set_status("在线服务已停止", duration=2000)
        else:
            valid_results = [r for r in self._get_all_results() if r.is_valid]
            if self.m3u_server.start(valid_results):
                url = self.m3u_server.url
                self.root.clipboard_clear()
                self.root.clipboard_append(url)
                messagebox.showinfo("在线服务", f"服务已启动！\nURL: {url}\n（已复制到剪贴板）")
            else:
                messagebox.showwarning("提示", "没有有效的直播源！请先检测并获取有效源。")

    def _get_all_results(self) -> list:
        if not self.result_view:
            return []
        results = []
        for item_data in self.result_view.all_items_data.get("all", []):
            vals = item_data["values"]
            if len(vals) >= 8:
                ch = Channel(name=vals[2], url=vals[3], sources=[vals[1]], index=vals[0])
                r = CheckResult(channel=ch, is_valid=(vals[4] == "有效"), latency=float(vals[5]) if str(vals[5]) != "-" else -1, speed=vals[6], details=vals[7])
                results.append(r)
        return results

    def export_results(self):
        export_dir = self.export_dir_var.get().strip()
        base_name = self.source_file_basename.get().strip()
        if not export_dir or not base_name:
            messagebox.showerror("错误", "无法导出，请先选择一个源文件。")
            return

        all_results = self._get_all_results()
        valid_results = [r for r in all_results if r.is_valid]
        invalid_results = [r for r in all_results if not r.is_valid]

        export_dialog = tk.Toplevel(self.root)
        export_dialog.title("导出选项")
        export_dialog.geometry("420x520")
        export_dialog.transient(self.root)
        export_dialog.grab_set()

        ttk.Label(export_dialog, text="数据概览", font=ThemeManager.font("body")).pack(pady=(15, 5))
        ttk.Label(export_dialog, text=f"有效: {len(valid_results)}  无效: {len(invalid_results)}  总计: {len(all_results)}", foreground="gray").pack(pady=(0, 15))

        format_frame = ttk.LabelFrame(export_dialog, text="选择导出格式")
        format_frame.pack(fill=X, padx=15, pady=5)
        export_m3u = tk.BooleanVar(value=True)
        export_txt = tk.BooleanVar(value=True)
        export_csv = tk.BooleanVar(value=True)
        export_xlsx = tk.BooleanVar(value=True)
        ttk.Checkbutton(format_frame, text="M3U 播放列表", variable=export_m3u).pack(anchor=W, pady=2)
        ttk.Checkbutton(format_frame, text="TXT 无效源列表", variable=export_txt).pack(anchor=W, pady=2)
        ttk.Checkbutton(format_frame, text="CSV 完整明细", variable=export_csv).pack(anchor=W, pady=2)
        ttk.Checkbutton(format_frame, text="Excel 表格", variable=export_xlsx).pack(anchor=W, pady=2)

        def do_export():
            formats = []
            if export_m3u.get():
                formats.append("m3u")
            if export_txt.get():
                formats.append("txt")
            if export_csv.get():
                formats.append("csv")
            if export_xlsx.get():
                formats.append("xlsx")
            if not formats:
                messagebox.showwarning("提示", "请至少选择一种导出格式！", parent=export_dialog)
                return
            export_dialog.destroy()
            try:
                exported = self.export_engine.export_batch(formats, all_results, export_dir, base_name, local_isp=self.local_isp)
                self.last_export_path = export_dir
                if self.result_view:
                    self.result_view.export_path_label.config(text=f"导出位置: {export_dir}")
                messagebox.showinfo("导出成功", f"检测结果已导出到:\n{export_dir}\n共 {len(exported)} 个文件")
            except Exception as e:
                messagebox.showerror("导出失败", f"导出文件时出错: {e}")

        btn_frame = ttk.Frame(export_dialog)
        btn_frame.pack(fill=X, padx=15, pady=15)
        ttk.Button(btn_frame, text="确认导出", command=do_export, **ThemeManager.style("success_action"), width=12).pack(side=LEFT, padx=5, fill=X, expand=True)
        ttk.Button(btn_frame, text="取消", command=export_dialog.destroy, width=12).pack(side=LEFT, padx=5, fill=X, expand=True)

    def smart_select_optimize(self):
        all_results = self._get_all_results()
        optimized = SmartOptimizer.optimize(all_results)
        if not optimized:
            messagebox.showinfo("提示", "没有有效源可供优选！")
            return
        original_count = len([r for r in all_results if r.is_valid])
        optimized_count = len([r for r in optimized if r.is_valid])
        removed = original_count - optimized_count
        messagebox.showinfo("智能优选完成", f"原始有效源: {original_count} 个\n优选后: {optimized_count} 个\n去除重复: {removed} 个")

    def open_export_folder(self, event=None):
        if not self.last_export_path or not os.path.isdir(self.last_export_path):
            return
        try:
            if sys.platform == "win32":
                os.startfile(self.last_export_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", self.last_export_path])
            else:
                subprocess.run(["xdg-open", self.last_export_path])
        except Exception:
            pass

    def _set_status(self, message: str, error: bool = False, duration: int = 3000):
        self.status_message.set(message)
        if self.result_view and hasattr(self.result_view, "status_label"):
            self.result_view.status_label.config(**ThemeManager.style("danger_action") if error else ThemeManager.style("primary_action"))
        self.root.after(duration, lambda: self.status_message.set(""))

    def on_closing(self):
        if self.is_running and messagebox.askyesno("退出", "检测正在进行中，确定要退出吗？"):
            self.stop_checking()
        elif self.is_running:
            return
        self.m3u_server.stop()
        self.player.stop()
        self.cache.save()
        self.http_client.close()
        self.root.destroy()


def run():
    import ttkbootstrap as ttk_bs
    root = ttk_bs.Window(themename="litera")
    app = Application(root)
    root.mainloop()


if __name__ == "__main__":
    run()
