import tkinter as tk
from tkinter import ttk
from ttkbootstrap.constants import *


class PaginationWidget:
    def __init__(self, parent_frame, items_per_page=50, on_page_change=None):
        self.items_per_page = items_per_page
        self.on_page_change = on_page_change
        self.current_page = 1
        self.total_pages = 1
        self.total_items = 0
        self.frame = ttk.Frame(parent_frame)
        self.frame.pack(fill=X, pady=(5, 0))
        self._build_ui()

    def _build_ui(self):
        from iptv_check.app.theme import ThemeManager

        left_frame = ttk.Frame(self.frame)
        left_frame.pack(side=LEFT)

        self.prev_btn = ttk.Button(
            left_frame, text="← 上一页", command=self._prev_page,
            width=10, state=DISABLED, **ThemeManager.style("secondary_outline")
        )
        self.prev_btn.pack(side=LEFT, padx=2)

        self.page_label = ttk.Label(
            left_frame, text="第 1 页 / 共 1 页",
            font=ThemeManager.font("small"), **ThemeManager.style("secondary_action")
        )
        self.page_label.pack(side=LEFT, padx=10)

        self.next_btn = ttk.Button(
            left_frame, text="下一页 →", command=self._next_page,
            width=10, state=DISABLED, **ThemeManager.style("secondary_outline")
        )
        self.next_btn.pack(side=LEFT, padx=2)

        right_frame = ttk.Frame(self.frame)
        right_frame.pack(side=RIGHT)

        ttk.Label(right_frame, text="跳转到:", font=ThemeManager.font("small")).pack(side=LEFT, padx=(0, 5))

        self.jump_var = tk.StringVar()
        self.jump_entry = ttk.Entry(right_frame, textvariable=self.jump_var, width=5)
        self.jump_entry.pack(side=LEFT, padx=2)
        self.jump_entry.bind("<Return>", lambda e: self._jump_to_page())

        ttk.Button(right_frame, text="跳转", command=self._jump_to_page, width=6, **ThemeManager.style("info_action")).pack(side=LEFT, padx=2)

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
        end_idx = min(start_idx + self.items_per_page, self.total_items)
        return start_idx, end_idx

    def set_total_items(self, total_items):
        self.total_items = total_items
        self.update_pagination(total_items)

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
