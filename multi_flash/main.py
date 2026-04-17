import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import ensure_package
ensure_package("pyserial", "serial")
ensure_package("esptool")
ensure_package("customtkinter")

import tkinter as tk
import customtkinter as ctk
import threading
import platform

from constants import *
import ui
import usb_monitor
import flash_worker

# ===== 메인 윈도우 =====
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

root = ctk.CTk()
root.title("Higenis Multi Flasher")
root.configure(fg_color=MAIN_BG)
root.minsize(900, 400)

_resize_scheduled = False

header_frame = ctk.CTkFrame(root, fg_color=MAIN_BG, corner_radius=0)
header_frame.pack(fill=tk.X, padx=15, pady=(15, 5))

title_label = ctk.CTkLabel(header_frame, text="Higenis Multi Flasher",
                           font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
                           text_color=ACCENT)
title_label.pack(side=tk.LEFT)

subtitle = ctk.CTkLabel(header_frame, text="  No boards  ",
                        font=ctk.CTkFont(family="Segoe UI", size=11),
                        text_color="#aaaaaa", fg_color="#555577",
                        corner_radius=10, padx=12, pady=2)
subtitle.pack(side=tk.LEFT, padx=15)

# ===== 보드 선택 드롭다운 (우측 정렬) =====
board_select_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
board_select_frame.pack(side=tk.RIGHT, padx=(0, 4))

board_icon = ctk.CTkLabel(
    board_select_frame,
    text="⬡",
    font=ctk.CTkFont(size=16),
    text_color=ACCENT,
    fg_color="transparent"
)
board_icon.pack(side=tk.LEFT, padx=(0, 4))

board_label = ctk.CTkLabel(
    board_select_frame,
    text="Board",
    font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
    text_color=TEXT_MUTED
)
board_label.pack(side=tk.LEFT, padx=(0, 8))

class DarkDropdown:
    def __init__(self, parent, values, callback, default_value=None):
        self.parent = parent
        self.values = values
        self.callback = callback
        self.default_value = default_value or values[0] if values else ""
        self.current_value = tk.StringVar(value=self.default_value)
        self.popup = None
        self.selected_index = values.index(self.default_value) if self.default_value in values else 0

        self.button = tk.Frame(parent, bg=HEADER_BG, cursor="hand2", relief="flat", bd=0)
        self.button.pack(side=tk.LEFT)

        canvas = tk.Canvas(self.button, width=220, height=32, bg=HEADER_BG,
                           highlightthickness=0, insertborderwidth=0, relief="flat")
        canvas.pack()

        self.label = tk.Label(canvas, text=self.default_value, bg=HEADER_BG,
                              fg=TEXT_COLOR, font=("Segoe UI", 12, "bold"),
                              anchor="w", padx=12)
        canvas.create_window(4, 2, window=self.label, width=188, height=28, anchor="nw")

        self.arrow = tk.Label(canvas, text="▼", bg=HEADER_BG,
                              fg=ACCENT, font=("Segoe UI", 8), anchor="e")
        canvas.create_window(206, 8, window=self.arrow, width=12, height=16, anchor="nw")

        self.button.bind("<Button-1>", lambda e: self._toggle_popup())
        self.label.bind("<Button-1>", lambda e: self._toggle_popup())
        canvas.bind("<Button-1>", lambda e: self._toggle_popup())

    def _toggle_popup(self):
        if self.popup:
            self._close_popup()
        else:
            self._open_popup()

    def _open_popup(self):
        self.popup = tk.Toplevel(self.button)
        self.popup.overrideredirect(True)
        self.popup.configure(bg=CARD_BG)

        x = self.button.winfo_rootx()
        y = self.button.winfo_rooty() + self.button.winfo_height() + 2
        self.popup.geometry(f"220x{min(len(self.values) * 36, 200)}+{x}+{y}")

        frame = tk.Frame(self.popup, bg=CARD_BG, relief="flat", bd=0)
        frame.pack(fill="both", expand=True, padx=1, pady=1)

        border_frame = tk.Frame(frame, bg="#3a3a5c", relief="flat", bd=0)
        border_frame.pack(fill="both", expand=True, padx=1, pady=1)

        list_frame = tk.Frame(border_frame, bg=CARD_BG, relief="flat", bd=0)
        list_frame.pack(fill="both", expand=True)

        for i, value in enumerate(self.values):
            is_selected = (i == self.selected_index)

            item_frame = tk.Frame(list_frame, bg=CARD_BG, cursor="hand2", relief="flat", bd=0)
            item_frame.pack(fill="x", padx=0, pady=0)

            accent_bar = tk.Frame(item_frame, bg=ACCENT if is_selected else CARD_BG, width=3, height=32)
            accent_bar.pack(side="left", fill="y")

            item_label = tk.Label(item_frame, text=f"   {value}", bg=CARD_BG,
                                  fg=ACCENT if is_selected else TEXT_COLOR,
                                  font=("Segoe UI", 12), anchor="w", padx=16)
            item_label.pack(side="left", fill="both", expand=True, pady=0)

            def on_enter(e, idx=i, iframe=item_frame, iaccent=accent_bar, ilbl=item_label, was_selected=is_selected):
                iframe.config(bg="#2a2a4e")
                ilbl.config(bg="#2a2a4e")
                iaccent.config(bg=ACCENT)

            def on_leave(e, idx=i, iframe=item_frame, iaccent=accent_bar, ilbl=item_label, was_selected=is_selected):
                iframe.config(bg="#2a2a4e" if was_selected else CARD_BG)
                ilbl.config(bg="#2a2a4e" if was_selected else CARD_BG)
                ilbl.config(fg=ACCENT if was_selected else TEXT_COLOR)
                iaccent.config(bg=ACCENT if was_selected else CARD_BG)

            def on_click(e, idx=i):
                self._select(idx)

            item_frame.bind("<Button-1>", on_click)
            item_label.bind("<Button-1>", on_click)
            item_frame.bind("<Enter>", on_enter)
            item_label.bind("<Enter>", on_enter)
            item_frame.bind("<Leave>", on_leave)
            item_label.bind("<Leave>", on_leave)

        self.popup._list_frame = list_frame
        self.popup.bind("<FocusOut>", lambda e: self._close_popup())
        self.popup.bind("<Button-1>", lambda e: "break")

    def _close_popup(self):
        if self.popup:
            self.popup.destroy()
            self.popup = None

    def _select(self, index):
        self.selected_index = index
        value = self.values[index]
        self.current_value.set(value)
        self.label.config(text=value)
        self._close_popup()
        self.callback(value)

    def get(self):
        return self.current_value.get()

    def set(self, value):
        if value in self.values:
            self.selected_index = self.values.index(value)
            self.current_value.set(value)
            self.label.config(text=value)


def on_board_change(choice):
    flash_worker.set_board(choice)
    ui.queue_log("SYSTEM", f"[INFO] Board changed → {choice}")


board_dropdown = DarkDropdown(
    board_select_frame,
    values=list(BOARD_CONFIGS.keys()),
    callback=on_board_change,
    default_value=CURRENT_BOARD
)

header_sep = ctk.CTkFrame(root, fg_color="#333355", height=1, corner_radius=0)
header_sep.pack(fill=tk.X, padx=15, pady=(0, 8))
header_sep.pack_propagate(False)

card_container = ctk.CTkFrame(root, fg_color=MAIN_BG, corner_radius=0)
card_container.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

status_bar_sep = ctk.CTkFrame(root, fg_color="#333355", height=1, corner_radius=0)
status_bar_sep.pack(side=tk.BOTTOM, fill=tk.X)
status_bar_sep.pack_propagate(False)

status_bar_frame = ctk.CTkFrame(root, fg_color="#2d2d4a", height=STATUS_BAR_HEIGHT, corner_radius=0)
status_bar_frame.pack(side=tk.BOTTOM, fill=tk.X)
status_bar_frame.pack_propagate(False)

status_bar_label = ctk.CTkLabel(status_bar_frame,
                                text="Ready — No boards connected",
                                font=ctk.CTkFont(family="Segoe UI", size=11),
                                text_color="#e0e0e0", fg_color="transparent")
status_bar_label.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=15, pady=0)

# ===== 모듈 초기화 =====
ui.init(root, card_container, subtitle, status_bar_label)
flash_worker.init(root, ui.queue_log, ui.update_status)
usb_monitor.init(root, ui, flash_worker)

# ===== 시작 =====
usb_monitor.start_usb_monitor()
threading.Thread(target=usb_monitor.monitor_ports, daemon=True).start()
root.after(100, ui._flush_log_queue)
root.mainloop()
