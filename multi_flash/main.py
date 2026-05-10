import os
import sys
import threading
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import ensure_package

ensure_package("pyserial", "serial")
ensure_package("esptool")
ensure_package("customtkinter")

import customtkinter as ctk

from app_state import all_boards, operations_for_board
import constants as app_constants
from constants import *
import flash_worker
import theme as theme_utils
import ui
import usb_monitor
from widgets import DropdownRegistry, ThemedDropdown


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_dropdown_registry = DropdownRegistry()
_selector_labels = []
_settings_window = None
_settings_dropdown = None


def _close_all_dropdowns():
    _dropdown_registry.close_all()

root = ctk.CTk()
root.title("Higenis Multi Flasher")
root.configure(fg_color=MAIN_BG)
root.geometry("1220x420")
root.minsize(1220, 420)
root.after(0, lambda: theme_utils.apply_windows_titlebar_theme(root))


header_frame = ctk.CTkFrame(root, fg_color=MAIN_BG, corner_radius=0)
header_frame.pack(fill=tk.X, padx=15, pady=(15, 5))

title_label = ctk.CTkLabel(
    header_frame,
    text="Higenis Multi Flasher",
    font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
    text_color=TITLE_COLOR,
)
title_label.pack(side=tk.LEFT)

subtitle = ctk.CTkLabel(
    header_frame,
    text="  No boards  ",
    font=ctk.CTkFont(family="Segoe UI", size=11),
    text_color=SUBTITLE_EMPTY_FG,
    fg_color=SUBTITLE_EMPTY_BG,
    corner_radius=10,
    padx=12,
    pady=2,
)
subtitle.pack(side=tk.LEFT, padx=15)

selector_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
selector_frame.pack(side=tk.RIGHT, padx=(0, 4))


def add_selector_label(text):
    label = ctk.CTkLabel(
        selector_frame,
        text=text,
        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        text_color=TEXT_MUTED,
    )
    label.pack(side=tk.LEFT, padx=(12, 6))
    _selector_labels.append(label)
    return label


def on_board_change(choice):
    ui.clear_all_cards()
    flash_worker.set_board(choice)
    current_operation = operation_dropdown.get()
    operation_values = operations_for_board(choice)
    next_operation = current_operation if current_operation in operation_values else operation_values[0]
    operation_dropdown.set_values(operation_values, next_operation, notify=False)
    flash_worker.set_operation_mode(next_operation)
    ui.queue_log("SYSTEM", f"[INFO] Board changed -> {choice}")
    usb_monitor.set_active_board(choice)


def on_operation_change(choice):
    ui.clear_all_cards()
    flash_worker.set_operation_mode(choice)
    ui.queue_log("SYSTEM", f"[INFO] Do changed -> {choice}")


def _theme_snapshot():
    return app_constants.get_theme_values(app_constants.CURRENT_THEME)


def apply_app_theme(choice):
    old_theme = _theme_snapshot()
    theme_values = app_constants.apply_theme(choice)
    globals().update(theme_values)
    flash_worker.__dict__.update(theme_values)
    usb_monitor.__dict__.update(theme_values)
    ui.apply_theme_colors(theme_values, old_theme)
    ctk.set_appearance_mode("light" if choice == THEME_WHITE else "dark")

    root.configure(fg_color=MAIN_BG)
    header_frame.configure(fg_color=MAIN_BG)
    title_label.configure(text_color=TITLE_COLOR)
    selector_frame.configure(fg_color="transparent")
    for label in _selector_labels:
        label.configure(text_color=TEXT_MUTED)
    _dropdown_registry.refresh_all()
    settings_button.configure(fg_color=BUTTON_BG, hover_color=BUTTON_HOVER, text_color=BUTTON_TEXT, border_color=BUTTON_BORDER, border_width=1)
    header_sep.configure(fg_color=SEPARATOR)
    card_container.configure(
        fg_color=MAIN_BG,
        scrollbar_button_color=MAIN_BG,
        scrollbar_button_hover_color=HEADER_BG,
    )
    status_bar_sep.configure(fg_color=SEPARATOR)
    status_bar_frame.configure(fg_color=STATUS_BAR_BG)
    status_bar_label.configure(text_color=STATUS_BAR_TEXT)
    theme_utils.apply_windows_titlebar_theme(root, choice)

    if _settings_window and _settings_window.winfo_exists():
        _settings_window.configure(bg=MAIN_BG)
        for child in _settings_window.winfo_children():
            theme_utils.retint_tk_child(child, old_theme, theme_values)
        theme_utils.apply_windows_titlebar_theme(_settings_window, choice)
        close_settings_window()


def open_settings_window():
    global _settings_window, _settings_dropdown
    if _settings_window and _settings_window.winfo_exists():
        _settings_window.lift()
        _settings_window.focus_force()
        return

    _settings_window = tk.Toplevel(root)
    _settings_window.title("Settings")
    _settings_window.configure(bg=MAIN_BG)
    _settings_window.resizable(False, False)
    _settings_window.transient(root)
    theme_utils.apply_windows_titlebar_theme(_settings_window)
    _settings_window.after(50, lambda window=_settings_window: theme_utils.apply_windows_titlebar_theme(window))

    width = 420
    height = 130
    x = root.winfo_rootx() + root.winfo_width() - width - 24
    y = root.winfo_rooty() + 76
    _settings_window.geometry(f"{width}x{height}+{x}+{y}")

    panel = ctk.CTkFrame(_settings_window, fg_color=CARD_BG, corner_radius=8, border_width=1, border_color=SEPARATOR)
    panel.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)

    title = ctk.CTkLabel(
        panel,
        text="Settings",
        font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        text_color=TEXT_COLOR,
    )
    title.pack(anchor=tk.W, padx=16, pady=(14, 6))

    row = ctk.CTkFrame(panel, fg_color="transparent")
    row.pack(fill=tk.X, padx=16, pady=(4, 14))

    color_label = ctk.CTkLabel(
        row,
        text="Color",
        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        text_color=TEXT_MUTED,
    )
    color_label.pack(side=tk.LEFT, padx=(0, 12))

    _settings_dropdown = ThemedDropdown(
        row,
        values=list(THEME_NAMES),
        callback=apply_app_theme,
        default_value=app_constants.CURRENT_THEME,
        width=220,
        registry=_dropdown_registry,
    )
    _settings_window.bind("<Configure>", close_dropdown_on_window_configure, add="+")
    _settings_window.protocol("WM_DELETE_WINDOW", close_settings_window)


def close_settings_window():
    global _settings_window, _settings_dropdown
    _dropdown_registry.remove(_settings_dropdown)
    if _settings_window and _settings_window.winfo_exists():
        _settings_window.destroy()
    _settings_window = None
    _settings_dropdown = None


add_selector_label("Board")
board_dropdown = ThemedDropdown(
    selector_frame,
    values=all_boards(),
    callback=on_board_change,
    default_value=CURRENT_BOARD,
    width=280,
    registry=_dropdown_registry,
)

do_label = add_selector_label("Do")
operation_dropdown = ThemedDropdown(
    selector_frame,
    values=operations_for_board(CURRENT_BOARD),
    callback=on_operation_change,
    default_value=OPERATION_FLASH,
    width=140,
    registry=_dropdown_registry,
)

settings_button = ctk.CTkButton(
    selector_frame,
    text="Config",
    width=78,
    height=32,
    corner_radius=8,
    fg_color=BUTTON_BG,
    hover_color=BUTTON_HOVER,
    text_color=BUTTON_TEXT,
    font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
    command=open_settings_window,
    border_color=BUTTON_BORDER,
    border_width=1,
)
settings_button.pack(side=tk.LEFT, padx=(12, 0))


def close_dropdown_on_window_configure(event):
    if event.widget is root or event.widget is _settings_window:
        _close_all_dropdowns()


root.bind("<Configure>", close_dropdown_on_window_configure, add="+")

header_sep = ctk.CTkFrame(root, fg_color=SEPARATOR, height=1, corner_radius=0)
header_sep.pack(fill=tk.X, padx=15, pady=(0, 8))
header_sep.pack_propagate(False)

card_container = ctk.CTkScrollableFrame(
    root,
    fg_color=MAIN_BG,
    scrollbar_button_color=MAIN_BG,
    scrollbar_button_hover_color=HEADER_BG,
)
card_container.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

status_bar_sep = ctk.CTkFrame(root, fg_color=SEPARATOR, height=1, corner_radius=0)
status_bar_sep.pack(side=tk.BOTTOM, fill=tk.X)
status_bar_sep.pack_propagate(False)

status_bar_frame = ctk.CTkFrame(root, fg_color=STATUS_BAR_BG, height=STATUS_BAR_HEIGHT, corner_radius=0)
status_bar_frame.pack(side=tk.BOTTOM, fill=tk.X)
status_bar_frame.pack_propagate(False)

status_bar_label = ctk.CTkLabel(
    status_bar_frame,
    text="Ready - No boards connected",
    font=ctk.CTkFont(family="Segoe UI", size=11),
    text_color=STATUS_BAR_TEXT,
    fg_color="transparent",
)
status_bar_label.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=15, pady=0)

ui.init(root, card_container, subtitle, status_bar_label)
flash_worker.init(root, ui.queue_log, ui.update_status)
usb_monitor.init(root, ui, flash_worker)

flash_worker.set_operation_mode(operation_dropdown.get())
usb_monitor.set_active_board(CURRENT_BOARD)

usb_monitor.start_usb_monitor()
threading.Thread(target=usb_monitor.monitor_ports, daemon=True).start()
root.after(100, ui._flush_log_queue)
root.mainloop()
