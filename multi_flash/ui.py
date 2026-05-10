import tkinter as tk
from tkinter.scrolledtext import ScrolledText
import customtkinter as ctk
import queue as _queue_module
import threading
import time

from constants import *
from flash_worker import is_stlink_board
_LOG_FLUSH_INTERVAL = 100  # defined in constants.py but not exported via *

# ===== ?꾩뿭 蹂??=====
port_logs = {}
port_frames = {}
port_labels = {}
port_status_labels = {}
port_status_bars = {}
port_log_widgets = {}
port_accent_lines = {}

detecting_frames = {}
detecting_progress_bars = {}

_resize_pending = False
_log_queue = _queue_module.Queue()

_root = None
_card_container = None
_subtitle_label = None
_status_bar_label = None
_theme_color_map = {}

_THEME_REPAINT_KEYS = {
    "MAIN_BG",
    "CARD_BG",
    "HEADER_BG",
    "LOG_BG",
    "TEXT_COLOR",
    "TEXT_MUTED",
    "PORT_COLOR",
    "SEPARATOR",
    "STATUS_BAR_BG",
    "STATUS_BAR_TEXT",
    "PROGRESS_BG",
    "DROPDOWN_BG",
    "DROPDOWN_BORDER",
    "DROPDOWN_POPUP_BG",
    "DROPDOWN_POPUP_BORDER",
    "DROPDOWN_TEXT",
    "DROPDOWN_SELECTED_BG",
    "DROPDOWN_HOVER_BG",
    "TITLE_COLOR",
    "BUTTON_BG",
    "BUTTON_TEXT",
    "BUTTON_HOVER",
    "BUTTON_BORDER",
    "STATUS_DONE_BADGE_BG",
    "STATUS_DONE_BADGE_FG",
    "BANNER_INFO_BG",
    "BANNER_INFO_BORDER",
    "BANNER_INFO_TEXT",
    "BANNER_WARN_BG",
    "BANNER_WARN_BORDER",
    "BANNER_WARN_TEXT",
    "BORDER_NEUTRAL",
    "BORDER_FAIL",
    "BORDER_DONE",
    "BORDER_DONE_ALT",
    "BORDER_UPLOAD",
    "BORDER_UART",
}

# USB pending cards (?щ윭 USB ?숈떆 ?몄떇 媛??
_usb_pending_cards = []

# ===== STLink ?щ’ UI =====
_stlink_banner = None
_stlink_detecting_card = None
_stlink_detecting_canvas = None
_stlink_detecting_arc = None
_stlink_detecting_job = None
_stlink_detecting_angle = 0
_stlink_jre_card = None
_stlink_jre_detail_label = None
_stlink_jre_status_label = None
_stlink_jre_accent_line = None
_stlink_jre_progress_frame = None
_stlink_jre_progress = None
stlink_slot_frames = {}
stlink_slot_labels = {}
stlink_slot_status_labels = {}
stlink_slot_progress_bars = {}
stlink_slot_progress_jobs = {}
stlink_slot_progress_values = {}
stlink_slot_progress_starts = {}
stlink_slot_progress_start_values = {}

_STLINK_UPDATE_PROGRESS_SECONDS = 10.5
_STLINK_JRE_PROGRESS_SECONDS = 1.2

def init(root, card_container, subtitle_label, status_bar_label):
    global _root, _card_container, _subtitle_label, _status_bar_label
    _root = root
    _card_container = card_container
    _subtitle_label = subtitle_label
    _status_bar_label = status_bar_label


def _normalize_color(color):
    return color.lower() if isinstance(color, str) and color.startswith("#") else color


def _theme_color(color):
    normalized = _normalize_color(color)
    return _theme_color_map.get(normalized, color)


def _theme_border_color(color):
    if isinstance(color, (tuple, list)):
        return type(color)(_theme_border_color(item) for item in color)
    normalized = _normalize_color(color)
    border_map = {
        "#333355": BORDER_NEUTRAL,
        "#2a2a3e": BORDER_NEUTRAL,
        "#3a3a5c": BORDER_NEUTRAL,
        "#7a2d2d": BORDER_FAIL,
        "#2d7a4a": BORDER_DONE,
        "#275f3a": BORDER_DONE_ALT,
        "#4ade80": BORDER_DONE,
        "#8b7a20": BORDER_UPLOAD,
        "#f59e0b": BORDER_UPLOAD,
        "#2d4a7a": BORDER_UART,
        "#6366f1": BORDER_UART,
        "#7aa2f7": BORDER_UART,
    }
    return border_map.get(normalized, _theme_color(color))


def _theme_status_colors(status_text, label_bg, label_fg):
    status = (status_text or "").upper()
    if any(token in status for token in ("DONE", " OK", "SUCCESS", "UPDATED")):
        return STATUS_DONE_BADGE_BG, STATUS_DONE_BADGE_FG
    return label_bg, label_fg


def _replace_color(value, color_map):
    if isinstance(value, str):
        return color_map.get(value.lower(), value)
    if isinstance(value, (tuple, list)):
        return type(value)(_replace_color(item, color_map) for item in value)
    return value


def _retint_widget_tree(widget, color_map):
    for option in (
        "fg_color",
        "bg_color",
        "border_color",
        "button_color",
        "button_hover_color",
        "scrollbar_button_color",
        "scrollbar_button_hover_color",
        "progress_color",
        "text_color",
    ):
        try:
            current = widget.cget(option)
            updated = _theme_border_color(current) if option == "border_color" else _replace_color(current, color_map)
            if updated != current:
                widget.configure(**{option: updated})
        except:
            pass

    for option in ("bg", "fg", "insertbackground", "highlightbackground", "highlightcolor"):
        try:
            current = widget.cget(option)
            updated = _replace_color(current, color_map)
            if updated != current:
                widget.configure(**{option: updated})
        except:
            pass

    try:
        for child in widget.winfo_children():
            _retint_widget_tree(child, color_map)
    except:
        pass


def _refresh_log_widget(text):
    try:
        text.configure(bg=LOG_BG, fg=TEXT_COLOR, insertbackground=TEXT_COLOR)
        text.tag_configure("info", foreground=TEXT_COLOR)
        text.tag_configure("warn", foreground=WARN_TEXT)
        text.tag_configure("error", foreground=ERROR_TEXT)
        text.tag_configure("success", foreground=SUCCESS_TEXT)
        text.tag_configure("done", foreground=TEXT_MUTED)
        text.tag_configure("default", foreground=LOG_DEFAULT)
        text.tag_configure("rx", foreground=RX_TEXT)
    except:
        pass


def apply_theme_colors(theme_values, old_theme_values=None):
    global _theme_color_map
    old_theme_values = old_theme_values or {}
    globals().update(theme_values)

    color_map = {}
    for key, old_value in old_theme_values.items():
        new_value = theme_values.get(key)
        if key in _THEME_REPAINT_KEYS and isinstance(old_value, str) and isinstance(new_value, str):
            color_map[old_value.lower()] = new_value

    try:
        for key, old_value in THEMES[THEME_DARK].items():
            new_value = theme_values.get(key)
            if key in _THEME_REPAINT_KEYS and isinstance(old_value, str) and isinstance(new_value, str):
                color_map[old_value.lower()] = new_value
    except:
        pass

    _theme_color_map = color_map
    if _root:
        try:
            _root.configure(fg_color=MAIN_BG)
        except:
            pass
        _retint_widget_tree(_root, color_map)
    if _stlink_detecting_canvas and _stlink_detecting_arc:
        try:
            _stlink_detecting_canvas.configure(bg=HEADER_BG)
            _stlink_detecting_canvas.itemconfigure(_stlink_detecting_arc, outline=WARN_TEXT)
        except:
            pass
    for text in list(port_logs.values()):
        _refresh_log_widget(text)
    update_subtitle()
    update_status_bar()


def clear_esp_cards():
    """Remove all ESP/serial cards from the current view."""
    for port, frame in list(port_frames.items()):
        try:
            frame.destroy()
        except:
            pass
        port_frames.pop(port, None)
        port_logs.pop(port, None)
        port_labels.pop(port, None)
        port_status_labels.pop(port, None)
        port_status_bars.pop(port, None)
        port_log_widgets.pop(port, None)
        port_accent_lines.pop(port, None)

    for port, frame in list(detecting_frames.items()):
        try:
            frame.destroy()
        except:
            pass
        detecting_frames.pop(port, None)
        detecting_progress_bars.pop(port, None)

    remove_all_usb_pending_cards()


def clear_all_cards():
    """Clear device cards when the selected workflow changes."""
    clear_esp_cards()
    clear_stlink_slots()
    hide_stlink_jre_card()
    update_subtitle()
    update_status_bar()
    _root.after(50, adjust_window_size)

# ===== 濡쒓렇 異쒕젰 =====
def queue_log(port, message):
    _log_queue.put((port, message))

def _write_log_to_widget(port, message):
    text_widget = port_logs.get(port)
    if text_widget:
        if "[FAIL]" in message or "[ERROR]" in message:
            tag = "error"
        elif "[SUCCESS]" in message or "[UPLOAD DONE]" in message or "[UART CHECK DONE]" in message:
            tag = "success"
        elif "[WARN]" in message:
            tag = "warn"
        elif "[INFO]" in message:
            tag = "info"
        elif "[DONE]" in message:
            tag = "done"
        else:
            tag = "default"
        text_widget.insert(tk.END, message + "\n", tag)
        text_widget.see(tk.END)

def _flush_log_queue():
    count = 0
    max_per_flush = 50
    while count < max_per_flush:
        try:
            port, message = _log_queue.get_nowait()
        except:
            break
        _write_log_to_widget(port, message)
        count += 1
    _root.after(_LOG_FLUSH_INTERVAL, _flush_log_queue)

# ===== ?곹깭 ?낅뜲?댄듃 =====
def update_status(port, status_text, label_bg, label_fg="#000000", border_color=None):
    border_color = _theme_border_color(border_color)
    label_bg, label_fg = _theme_status_colors(status_text, label_bg, label_fg)
    status_label = port_status_labels.get(port)
    outer = port_frames.get(port)
    accent_line = port_accent_lines.get(port)
    if status_label:
        try:
            status_label.configure(text=status_text, fg_color=label_bg, text_color=label_fg)
        except:
            pass
    if outer and border_color:
        try:
            outer.configure(border_color=border_color)
        except:
            pass
    if accent_line and border_color:
        try:
            accent_line.configure(fg_color=border_color)
        except:
            pass
    _root.after(0, update_status_bar)

# ===== USB Pending UI ?앹꽦 =====
def create_usb_pending_card():
    """USB 媛먯????먯쑝??COM ?ы듃 ?깅줉 ?湲곗쨷???곹깭 ?쒖떆. 移대뱶 frame??諛섑솚."""
    try:
        outer = ctk.CTkFrame(_card_container, fg_color=CARD_BG, corner_radius=12,
                             border_width=2, border_color=_theme_border_color("#f59e0b"))
        outer.pack(fill=tk.X, padx=12, pady=4)
        header = ctk.CTkFrame(outer, fg_color=HEADER_BG, corner_radius=8)
        header.pack(fill=tk.X, padx=8, pady=(8, 4))
        marker = ctk.CTkLabel(header, text="*", font=ctk.CTkFont(size=14),
                              text_color=WARN_TEXT, fg_color="transparent")
        marker.pack(side=tk.LEFT, padx=(8, 2), pady=6)
        port_label = ctk.CTkLabel(header, text="Waiting for COM port...",
                                  font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                                  text_color=PORT_COLOR)
        port_label.pack(side=tk.LEFT, padx=(0, 8), pady=6)
        type_label = ctk.CTkLabel(header, text="USB device detected",
                                  font=ctk.CTkFont(family="Segoe UI", size=10),
                                  text_color=TEXT_MUTED)
        type_label.pack(side=tk.LEFT)
        status_label = ctk.CTkLabel(header, text="USB DETECTED",
                                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                                    fg_color=STATUS_USB_PENDING_BG, text_color=STATUS_USB_PENDING_FG,
                                    corner_radius=6, padx=12, pady=4)
        status_label.pack(side=tk.RIGHT, padx=8, pady=6)
        progress_frame = ctk.CTkFrame(outer, fg_color=PROGRESS_BG, corner_radius=0)
        progress_frame.pack(fill=tk.X, padx=12, pady=(0, 8))
        progress_bar = ctk.CTkProgressBar(progress_frame, mode="indeterminate",
                                         progress_color=WARN_TEXT, fg_color=PROGRESS_BG)
        progress_bar.pack(fill=tk.X, padx=8, pady=8)
        progress_bar.start()
        _usb_pending_cards.append(outer)
        _root.after(0, update_status_bar)
        _root.after(50, adjust_window_size)
        return outer
    except Exception as e:
        print(f"[ERROR] create_usb_pending_card failed: {e}")
        return None

def remove_usb_pending_card(card):
    """?뱀젙 USB pending 移대뱶 ?쒓굅."""
    if card is None:
        return
    try:
        card.destroy()
    except:
        pass
    if card in _usb_pending_cards:
        _usb_pending_cards.remove(card)
    _root.after(0, update_status_bar)
    _root.after(50, adjust_window_size)

def remove_one_usb_pending_card():
    """USB pending 移대뱶 ?섎굹瑜??쒓굅 (FIFO)."""
    if _usb_pending_cards:
        card = _usb_pending_cards.pop(0)
        try:
            card.destroy()
        except:
            pass
        update_status_bar()
        _root.after(50, adjust_window_size)

def remove_all_usb_pending_cards():
    """紐⑤뱺 USB pending 移대뱶 ?쒓굅."""
    while _usb_pending_cards:
        card = _usb_pending_cards.pop(0)
        try:
            card.destroy()
        except:
            pass
    update_status_bar()
    _root.after(50, adjust_window_size)

# ===== STLink ?щ’ UI =====
def show_stlink_jre_card(status_text="CHECKING_JRE", message="Checking Java runtime...", label_bg="#6366f1", label_fg="#ffffff", border_color="#333355", spinning=True):
    """Show/update Java runtime preparation status for ST-LINK mode."""
    global _stlink_jre_card, _stlink_jre_detail_label, _stlink_jre_status_label, _stlink_jre_accent_line
    global _stlink_jre_progress_frame, _stlink_jre_progress
    border_color = _theme_border_color(border_color)
    label_bg, label_fg = _theme_status_colors(status_text, label_bg, label_fg)
    try:
        if _stlink_jre_card is None:
            outer = ctk.CTkFrame(_card_container, fg_color=CARD_BG, corner_radius=12,
                                 border_width=2, border_color=border_color)
            outer.pack(fill=tk.X, padx=12, pady=4)
            header = ctk.CTkFrame(outer, fg_color=HEADER_BG, corner_radius=8)
            header.pack(fill=tk.X, padx=8, pady=(8, 4))
            marker = ctk.CTkLabel(header, text="*", font=ctk.CTkFont(size=14),
                                  text_color=ACCENT, fg_color="transparent")
            marker.pack(side=tk.LEFT, padx=(10, 2), pady=8)
            title = ctk.CTkLabel(header, text="Java Runtime",
                                 font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                                 text_color=PORT_COLOR)
            title.pack(side=tk.LEFT, padx=(0, 8), pady=8)
            detail = ctk.CTkLabel(header, text=message,
                                  font=ctk.CTkFont(family="Segoe UI", size=10),
                                  text_color=TEXT_MUTED)
            detail.pack(side=tk.LEFT, pady=8)
            status = ctk.CTkLabel(header, text=status_text,
                                  font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                                  fg_color=label_bg, text_color=label_fg,
                                  corner_radius=6, padx=12, pady=4)
            status.pack(side=tk.RIGHT, padx=8, pady=6)
            accent_line = ctk.CTkFrame(outer, fg_color=border_color, height=2, corner_radius=0)
            accent_line.pack(fill=tk.X, padx=12, pady=(0, 0))
            accent_line.pack_propagate(False)
            progress_frame = ctk.CTkFrame(outer, fg_color=PROGRESS_BG, corner_radius=0)
            progress_frame.pack(fill=tk.X, padx=12, pady=(0, 8))
            progress = ctk.CTkProgressBar(progress_frame, mode="indeterminate",
                                          progress_color=label_bg, fg_color=PROGRESS_BG)
            progress.pack(fill=tk.X, padx=8, pady=8)
            _stlink_jre_card = outer
            _stlink_jre_detail_label = detail
            _stlink_jre_status_label = status
            _stlink_jre_accent_line = accent_line
            _stlink_jre_progress_frame = progress_frame
            _stlink_jre_progress = progress
        else:
            _stlink_jre_card.configure(border_color=border_color)
            _stlink_jre_detail_label.configure(text=message)
            _stlink_jre_status_label.configure(text=status_text, fg_color=label_bg, text_color=label_fg)
            if _stlink_jre_accent_line:
                _stlink_jre_accent_line.configure(fg_color=border_color)
            _stlink_jre_progress.configure(progress_color=label_bg)

        if spinning:
            if _stlink_jre_progress_frame and not _stlink_jre_progress_frame.winfo_ismapped():
                _stlink_jre_progress_frame.pack(fill=tk.X, padx=12, pady=(0, 8))
            _stlink_jre_progress.start()
        else:
            _stlink_jre_progress.stop()
            if _stlink_jre_progress_frame:
                _stlink_jre_progress_frame.pack_forget()
        _root.after(0, update_status_bar)
        _root.after(50, adjust_window_size)
    except Exception as e:
        print(f"[ERROR] show_stlink_jre_card failed: {e}")


def hide_stlink_jre_card():
    """Remove Java runtime preparation card."""
    global _stlink_jre_card, _stlink_jre_detail_label, _stlink_jre_status_label, _stlink_jre_accent_line
    global _stlink_jre_progress_frame, _stlink_jre_progress
    card = _stlink_jre_card
    progress = _stlink_jre_progress
    _stlink_jre_card = None
    _stlink_jre_detail_label = None
    _stlink_jre_status_label = None
    _stlink_jre_accent_line = None
    _stlink_jre_progress_frame = None
    _stlink_jre_progress = None
    if progress:
        try:
            progress.stop()
        except:
            pass
    if card:
        try:
            card.destroy()
        except:
            pass
    _root.after(0, update_status_bar)
    _root.after(50, adjust_window_size)
def show_stlink_banner(n):
    """ST-LINK 諛곕꼫: ?ㅼ쨷 ?μ튂 寃쎄퀬 ?먮뒗 ?⑥씪 ?μ튂 ?덈궡."""
    global _stlink_banner
    hide_stlink_banner()
    if n > 1:
        banner = ctk.CTkFrame(_card_container, fg_color=BANNER_WARN_BG, corner_radius=8,
                              border_width=1, border_color=BANNER_WARN_BORDER)
        banner.pack(fill=tk.X, padx=12, pady=(4, 0))
        icon = ctk.CTkLabel(banner, text="*", font=ctk.CTkFont(size=14),
                            text_color=BANNER_WARN_TEXT, fg_color="transparent")
        icon.pack(side=tk.LEFT, padx=(10, 4), pady=8)
        msg = f"{n} ST-LINKs detected - waiting for one safe update target."
    else:
        banner = ctk.CTkFrame(_card_container, fg_color=BANNER_INFO_BG, corner_radius=8,
                              border_width=1, border_color=BANNER_INFO_BORDER)
        banner.pack(fill=tk.X, padx=12, pady=(4, 0))
        icon = ctk.CTkLabel(banner, text="*", font=ctk.CTkFont(size=14),
                            text_color=BANNER_INFO_TEXT, fg_color="transparent")
        icon.pack(side=tk.LEFT, padx=(10, 4), pady=8)
        msg = "ST-LINK firmware update in progress."
    label = ctk.CTkLabel(banner, text=msg,
                         font=ctk.CTkFont(family="Segoe UI", size=11),
                         text_color=BANNER_INFO_TEXT if n <= 1 else BANNER_WARN_TEXT,
                         fg_color="transparent")
    label.pack(side=tk.LEFT, padx=(0, 10), pady=8)
    _stlink_banner = banner

def hide_stlink_banner():
    global _stlink_banner
    if _stlink_banner:
        try:
            _stlink_banner.destroy()
        except:
            pass
        _stlink_banner = None

def _animate_stlink_detecting():
    global _stlink_detecting_job, _stlink_detecting_angle
    if _stlink_detecting_card is None or _stlink_detecting_canvas is None or _stlink_detecting_arc is None:
        _stlink_detecting_job = None
        return
    try:
        _stlink_detecting_angle = (_stlink_detecting_angle + 24) % 360
        _stlink_detecting_canvas.itemconfigure(_stlink_detecting_arc, start=_stlink_detecting_angle)
        _stlink_detecting_job = _root.after(60, _animate_stlink_detecting)
    except:
        _stlink_detecting_job = None

def show_stlink_detecting_card(message="Scanning ST-LINK USB change..."):
    """Show a temporary ST-LINK USB-DETECT card while a rescan is pending."""
    global _stlink_detecting_card, _stlink_detecting_canvas, _stlink_detecting_arc
    global _stlink_detecting_angle
    if _stlink_detecting_card is not None:
        return _stlink_detecting_card
    try:
        outer = ctk.CTkFrame(_card_container, fg_color=CARD_BG, corner_radius=12,
                             border_width=2, border_color=_theme_border_color("#f59e0b"))
        outer.pack(fill=tk.X, padx=12, pady=4)
        header = ctk.CTkFrame(outer, fg_color=HEADER_BG, corner_radius=8)
        header.pack(fill=tk.X, padx=8, pady=8)

        spinner = tk.Canvas(header, width=24, height=24, bg=HEADER_BG,
                            highlightthickness=0, relief="flat")
        spinner.pack(side=tk.LEFT, padx=(8, 6), pady=6)
        arc = spinner.create_arc(4, 4, 20, 20, start=0, extent=270,
                                 style="arc", outline=WARN_TEXT, width=3)

        title = ctk.CTkLabel(header, text="ST-LINK USB detected",
                             font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                             text_color=PORT_COLOR)
        title.pack(side=tk.LEFT, padx=(0, 8), pady=6)
        detail = ctk.CTkLabel(header, text=message,
                              font=ctk.CTkFont(family="Segoe UI", size=10),
                              text_color=TEXT_MUTED)
        detail.pack(side=tk.LEFT)
        status_label = ctk.CTkLabel(header, text="USB-DETECT",
                                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                                    fg_color=STATUS_USB_PENDING_BG, text_color=STATUS_USB_PENDING_FG,
                                    corner_radius=6, padx=12, pady=4)
        status_label.pack(side=tk.RIGHT, padx=8, pady=6)

        _stlink_detecting_card = outer
        _stlink_detecting_canvas = spinner
        _stlink_detecting_arc = arc
        _stlink_detecting_angle = 0
        _animate_stlink_detecting()
        _root.after(0, update_status_bar)
        _root.after(50, adjust_window_size)
        return outer
    except Exception as e:
        print(f"[ERROR] show_stlink_detecting_card failed: {e}")
        return None

def hide_stlink_detecting_card():
    """Remove the temporary ST-LINK USB-DETECT card and stop its spinner."""
    global _stlink_detecting_card, _stlink_detecting_canvas, _stlink_detecting_arc
    global _stlink_detecting_job
    if _stlink_detecting_job:
        try:
            _root.after_cancel(_stlink_detecting_job)
        except:
            pass
        _stlink_detecting_job = None
    card = _stlink_detecting_card
    _stlink_detecting_card = None
    _stlink_detecting_canvas = None
    _stlink_detecting_arc = None
    if card:
        try:
            card.destroy()
        except:
            pass
    _root.after(0, update_status_bar)
    _root.after(50, adjust_window_size)

def create_stlink_slot(slot_num, model):
    """STLink ?щ’ 移대뱶 ?앹꽦."""
    try:
        outer = ctk.CTkFrame(_card_container, fg_color=CARD_BG, corner_radius=12,
                             border_width=2, border_color=BORDER_NEUTRAL)
        outer.pack(fill=tk.X, padx=12, pady=4)
        header = ctk.CTkFrame(outer, fg_color=HEADER_BG, corner_radius=8)
        header.pack(fill=tk.X, padx=8, pady=(8, 4))
        marker = ctk.CTkLabel(header, text="*", font=ctk.CTkFont(size=14),
                              text_color=IDLE_MARKER, fg_color="transparent")
        marker.pack(side=tk.LEFT, padx=(8, 2), pady=6)
        slot_label = ctk.CTkLabel(header, text=f"Slot #{slot_num} - {model}",
                                  font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                                  text_color=PORT_COLOR)
        slot_label.pack(side=tk.LEFT, padx=(0, 8), pady=6)
        status_label = ctk.CTkLabel(header, text="WAITING",
                                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                                    fg_color=STATUS_WAIT_BG, text_color=STATUS_WAIT_FG,
                                    corner_radius=6, padx=12, pady=4)
        status_label.pack(side=tk.RIGHT, padx=8, pady=6)
        accent_line = ctk.CTkFrame(outer, fg_color=SEPARATOR, height=2, corner_radius=0)
        accent_line.pack(fill=tk.X, padx=12, pady=(0, 0))
        accent_line.pack_propagate(False)
        progress_frame = ctk.CTkFrame(outer, fg_color=PROGRESS_BG, corner_radius=0)
        progress_bar = ctk.CTkProgressBar(progress_frame, mode="determinate",
                                          progress_color=ACCENT, fg_color=PROGRESS_BG)
        progress_bar.pack(fill=tk.X, padx=8, pady=6)
        progress_bar.set(0)
        log_frame = ctk.CTkFrame(outer, fg_color=LOG_BG, corner_radius=8)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        text = ScrolledText(log_frame, font=("Consolas", 9), bg=LOG_BG, fg=TEXT_COLOR,
                            insertbackground=TEXT_COLOR, relief=tk.FLAT, borderwidth=0,
                            wrap=tk.WORD, height=6)
        text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        text.tag_configure("info", foreground=TEXT_COLOR)
        text.tag_configure("warn", foreground=WARN_TEXT)
        text.tag_configure("error", foreground=ERROR_TEXT)
        text.tag_configure("success", foreground=SUCCESS_TEXT)
        text.tag_configure("done", foreground=TEXT_MUTED)
        text.tag_configure("default", foreground=LOG_DEFAULT)
        text.config(highlightthickness=0)
        key = f"STLINK-{slot_num}"
        port_logs[key] = text
        stlink_slot_frames[key] = outer
        stlink_slot_labels[key] = slot_label
        stlink_slot_status_labels[key] = status_label
        stlink_slot_progress_bars[key] = (progress_frame, progress_bar, log_frame)
        stlink_slot_progress_values[key] = 0.0
        port_accent_lines[key] = accent_line
        _write_log_to_widget(key, f"[INFO] {model} detected")
        _root.after(50, adjust_window_size)
        _root.after(0, update_status_bar)
        return key
    except Exception as e:
        print(f"[ERROR] create_stlink_slot failed: {e}")
        return None

def _cancel_stlink_progress_job(key):
    job = stlink_slot_progress_jobs.pop(key, None)
    if job:
        try:
            _root.after_cancel(job)
        except:
            pass

def _show_stlink_progress(key, color=None):
    progress_pair = stlink_slot_progress_bars.get(key)
    if not progress_pair:
        return None
    progress_frame, progress_bar, log_frame = progress_pair
    if color:
        progress_bar.configure(progress_color=color)
    if not progress_frame.winfo_ismapped():
        progress_frame.pack(fill=tk.X, padx=12, pady=(0, 4), before=log_frame)
    return progress_bar

def _animate_stlink_progress(key, target=0.95):
    progress_bar = _show_stlink_progress(key)
    if not progress_bar:
        return
    start_time = stlink_slot_progress_starts.get(key, time.monotonic())
    start_value = stlink_slot_progress_start_values.get(key, stlink_slot_progress_values.get(key, 0.0))
    duration = _STLINK_JRE_PROGRESS_SECONDS if target <= 0.12 else _STLINK_UPDATE_PROGRESS_SECONDS
    elapsed = max(0.0, time.monotonic() - start_time)
    ratio = min(1.0, elapsed / duration)
    existing = stlink_slot_progress_values.get(key, 0.0)
    current = max(existing, min(target, start_value + (target - start_value) * ratio))
    stlink_slot_progress_values[key] = current
    try:
        progress_bar.set(current)
    except:
        return
    stlink_slot_progress_jobs[key] = _root.after(120, lambda k=key: _animate_stlink_progress(k, target))

def _start_stlink_progress(key, color, target=0.95):
    color = _theme_color(color)
    progress_bar = _show_stlink_progress(key, color)
    if not progress_bar:
        return
    _cancel_stlink_progress_job(key)
    current = stlink_slot_progress_values.get(key, 0.0)
    if current <= 0:
        current = 0.02
        stlink_slot_progress_values[key] = current
        progress_bar.set(current)
    stlink_slot_progress_starts[key] = time.monotonic()
    stlink_slot_progress_start_values[key] = current
    _animate_stlink_progress(key, target)

def set_stlink_progress(slot_num, value, color=None, keep_visible=True):
    color = _theme_color(color)
    key = f"STLINK-{slot_num}"
    progress_bar = _show_stlink_progress(key, color)
    if not progress_bar:
        return
    value = max(0.0, min(1.0, float(value)))
    value = max(value, stlink_slot_progress_values.get(key, 0.0))
    stlink_slot_progress_values[key] = value
    try:
        progress_bar.set(value)
    except:
        pass
    if not keep_visible:
        progress_pair = stlink_slot_progress_bars.get(key)
        if progress_pair:
            progress_pair[0].pack_forget()
    elif key not in stlink_slot_progress_jobs and value < 1.0:
        target = 0.99 if value >= 0.95 else 0.95
        stlink_slot_progress_starts[key] = time.monotonic()
        stlink_slot_progress_start_values[key] = value
        _animate_stlink_progress(key, target)

def _finish_stlink_progress(key, color, value=1.0, keep_visible=True):
    color = _theme_color(color)
    _cancel_stlink_progress_job(key)
    progress_bar = _show_stlink_progress(key, color)
    if not progress_bar:
        return
    stlink_slot_progress_values[key] = value
    try:
        progress_bar.set(value)
    except:
        pass
    if not keep_visible:
        progress_pair = stlink_slot_progress_bars.get(key)
        if progress_pair:
            progress_pair[0].pack_forget()

def update_stlink_slot(slot_num, status_text, label_bg, label_fg="#000000", border_color=None):
    """STLink ?щ’ ?곹깭 ?낅뜲?댄듃."""
    border_color = _theme_border_color(border_color)
    label_bg, label_fg = _theme_status_colors(status_text, label_bg, label_fg)
    key = f"STLINK-{slot_num}"
    status_label = stlink_slot_status_labels.get(key)
    outer = stlink_slot_frames.get(key)
    accent_line = port_accent_lines.get(key)
    if status_label:
        try:
            status_label.configure(text=status_text, fg_color=label_bg, text_color=label_fg)
        except:
            pass
    if status_text == "CHECKING_JRE":
        _start_stlink_progress(key, label_bg, target=0.10)
    elif status_text == "UPDATING":
        _start_stlink_progress(key, label_bg, target=0.95)
    elif status_text in ("SUCCESS", "DONE", "UPDATED"):
        _finish_stlink_progress(key, label_bg, 1.0, keep_visible=True)
    else:
        _finish_stlink_progress(key, label_bg, stlink_slot_progress_values.get(key, 0.0), keep_visible=False)
    if outer and border_color:
        try:
            outer.configure(border_color=border_color)
        except:
            pass
    if accent_line and border_color:
        try:
            accent_line.configure(fg_color=border_color)
        except:
            pass
    _root.after(0, update_status_bar)

def clear_stlink_slots():
    """紐⑤뱺 STLink ?щ’ 移대뱶 ?쒓굅."""
    global _stlink_banner
    for key in list(stlink_slot_frames.keys()):
        frame = stlink_slot_frames.pop(key, None)
        if frame:
            try:
                frame.destroy()
            except:
                pass
        port_logs.pop(key, None)
        stlink_slot_labels.pop(key, None)
        stlink_slot_status_labels.pop(key, None)
        _cancel_stlink_progress_job(key)
        stlink_slot_progress_bars.pop(key, None)
        stlink_slot_progress_values.pop(key, None)
        stlink_slot_progress_starts.pop(key, None)
        stlink_slot_progress_start_values.pop(key, None)
        port_accent_lines.pop(key, None)
    stlink_slot_frames.clear()
    stlink_slot_labels.clear()
    stlink_slot_status_labels.clear()
    stlink_slot_progress_jobs.clear()
    stlink_slot_progress_bars.clear()
    stlink_slot_progress_values.clear()
    stlink_slot_progress_starts.clear()
    stlink_slot_progress_start_values.clear()
    hide_stlink_banner()
    hide_stlink_detecting_card()
    update_status_bar()
    _root.after(50, adjust_window_size)

def remove_stlink_slot(slot_num):
    """Remove one STLink slot card."""
    key = f"STLINK-{slot_num}"
    frame = stlink_slot_frames.pop(key, None)
    if frame:
        try:
            frame.destroy()
        except:
            pass
    port_logs.pop(key, None)
    stlink_slot_labels.pop(key, None)
    stlink_slot_status_labels.pop(key, None)
    _cancel_stlink_progress_job(key)
    stlink_slot_progress_bars.pop(key, None)
    stlink_slot_progress_values.pop(key, None)
    stlink_slot_progress_starts.pop(key, None)
    stlink_slot_progress_start_values.pop(key, None)
    port_accent_lines.pop(key, None)
    if not stlink_slot_frames:
        hide_stlink_banner()
    update_status_bar()
    _root.after(50, adjust_window_size)
def stlink_queue_log(slot_num, message):
    """STLink ?щ’ 濡쒓렇 異쒕젰."""
    key = f"STLINK-{slot_num}"
    _log_queue.put((key, message))

# ===== Detecting UI =====
def create_detecting_gui(port_name):
    try:
        outer = ctk.CTkFrame(_card_container, fg_color=CARD_BG, corner_radius=12,
                             border_width=2, border_color=_theme_border_color("#6366f1"))
        outer.pack(fill=tk.X, padx=12, pady=4)
        header = ctk.CTkFrame(outer, fg_color=HEADER_BG, corner_radius=8)
        header.pack(fill=tk.X, padx=8, pady=(8, 4))
        marker = ctk.CTkLabel(header, text="*", font=ctk.CTkFont(size=14),
                              text_color=WARN_TEXT, fg_color="transparent")
        marker.pack(side=tk.LEFT, padx=(8, 2), pady=6)
        port_label = ctk.CTkLabel(header, text=port_name,
                                  font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                                  text_color=PORT_COLOR)
        port_label.pack(side=tk.LEFT, padx=(0, 8), pady=6)
        type_label = ctk.CTkLabel(header, text="Identifying...",
                                  font=ctk.CTkFont(family="Segoe UI", size=10),
                                  text_color=TEXT_MUTED)
        type_label.pack(side=tk.LEFT)
        status_label = ctk.CTkLabel(header, text="DETECTING",
                                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                                    fg_color=STATUS_DETECTING_BG, text_color=STATUS_DETECTING_FG,
                                    corner_radius=6, padx=12, pady=4)
        status_label.pack(side=tk.RIGHT, padx=8, pady=6)
        progress_frame = ctk.CTkFrame(outer, fg_color=PROGRESS_BG, corner_radius=0)
        progress_frame.pack(fill=tk.X, padx=12, pady=(0, 8))
        progress_bar = ctk.CTkProgressBar(progress_frame, mode="indeterminate",
                                          progress_color=ACCENT, fg_color=PROGRESS_BG)
        progress_bar.pack(fill=tk.X, padx=8, pady=8)
        progress_bar.start()
        detecting_frames[port_name] = outer
        detecting_progress_bars[port_name] = progress_bar
        _root.after(0, update_status_bar)
        _root.after(50, adjust_window_size)
    except Exception as e:
        print(f"[ERROR] create_detecting_gui failed for {port_name}: {e}")

def remove_detecting_gui(port_name):
    frame = detecting_frames.pop(port_name, None)
    if frame:
        try:
            frame.destroy()
        except:
            pass
    detecting_progress_bars.pop(port_name, None)
    _root.after(0, update_status_bar)
    _root.after(50, adjust_window_size)

# ===== GUI ?앹꽦 =====
def create_port_gui(port, port_type):
    try:
        if port in detecting_frames:
            remove_detecting_gui(port)
        outer = ctk.CTkFrame(_card_container, fg_color=CARD_BG, corner_radius=12,
                             border_width=2, border_color=BORDER_NEUTRAL)
        outer.pack(fill=tk.X, padx=12, pady=4)
        header = ctk.CTkFrame(outer, fg_color=HEADER_BG, corner_radius=8)
        header.pack(fill=tk.X, padx=8, pady=(8, 4))
        marker_color = "#f97316" if "CP2102" in port_type else "#22c55e" if "CH343P" in port_type else "#3b82f6"
        marker = ctk.CTkLabel(header, text="*", font=ctk.CTkFont(size=14),
                              text_color=marker_color, fg_color="transparent")
        marker.pack(side=tk.LEFT, padx=(8, 2), pady=6)
        port_label = ctk.CTkLabel(header, text=port,
                                  font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                                  text_color=PORT_COLOR)
        port_label.pack(side=tk.LEFT, padx=(0, 8), pady=6)
        type_label = ctk.CTkLabel(header, text=port_type,
                                  font=ctk.CTkFont(family="Segoe UI", size=10),
                                  text_color=TEXT_MUTED)
        type_label.pack(side=tk.LEFT)
        status_label = ctk.CTkLabel(header, text="WAITING",
                                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                                    fg_color=STATUS_WAIT_BG, text_color=STATUS_WAIT_FG,
                                    corner_radius=6, padx=12, pady=4)
        status_label.pack(side=tk.RIGHT, padx=8, pady=6)
        accent_line = ctk.CTkFrame(outer, fg_color=SEPARATOR, height=2, corner_radius=0)
        accent_line.pack(fill=tk.X, padx=12, pady=(0, 0))
        accent_line.pack_propagate(False)
        port_accent_lines[port] = accent_line
        log_frame = ctk.CTkFrame(outer, fg_color=LOG_BG, corner_radius=8)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        text = ScrolledText(log_frame, font=("Consolas", 9), bg=LOG_BG, fg=TEXT_COLOR,
                            insertbackground=TEXT_COLOR, relief=tk.FLAT, borderwidth=0,
                            wrap=tk.WORD, height=6)
        text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        text.tag_configure("info", foreground=TEXT_COLOR)
        text.tag_configure("warn", foreground=WARN_TEXT)
        text.tag_configure("error", foreground=ERROR_TEXT)
        text.tag_configure("success", foreground=SUCCESS_TEXT)
        text.tag_configure("done", foreground=TEXT_MUTED)
        text.tag_configure("default", foreground=LOG_DEFAULT)
        text.tag_configure("rx", foreground=RX_TEXT)
        text.config(highlightthickness=0)
        port_logs[port] = text
        port_frames[port] = outer
        port_labels[port] = port_label
        port_status_labels[port] = status_label
        port_status_bars[port] = None
        port_log_widgets[port] = text
        _write_log_to_widget(port, f"[INFO] Board detected on {port}")
        _root.after(50, adjust_window_size)
        _root.after(0, update_status_bar)
    except Exception as e:
        print(f"[ERROR] create_port_gui failed for {port}: {e}")

def update_subtitle():
    from flash_worker import get_board
    if is_stlink_board():
        count = len(stlink_slot_frames)
    else:
        count = len(port_frames)
    if count == 0:
        _subtitle_label.configure(text="  No boards  ", fg_color=SUBTITLE_EMPTY_BG, text_color=SUBTITLE_EMPTY_FG)
    else:
        _subtitle_label.configure(text=f"  {count} board(s)  ", fg_color=ACCENT, text_color="#ffffff")

def adjust_window_size():
    """?붾컮?댁떛: ?щ윭 踰??몄텧?섏뼱???ㅼ젣 ?ㅽ뻾? 200ms ??1踰덈쭔."""
    global _resize_pending
    if _resize_pending:
        return
    _resize_pending = True
    _root.after(200, _do_adjust_window_size)

def _do_adjust_window_size():
    global _resize_pending
    _resize_pending = False

    count = len(port_frames)
    pending_count = len(_usb_pending_cards)
    stlink_count = len(stlink_slot_frames)
    stlink_detecting_count = 1 if _stlink_detecting_card else 0
    stlink_jre_count = 1 if _stlink_jre_card else 0

    if count == 0 and pending_count == 0 and stlink_count == 0 and stlink_detecting_count == 0 and stlink_jre_count == 0:
        _root.geometry("1220x420")
        return

    # ??踰덈쭔 update_idletasks() ?몄텧?댁꽌 ?뺥솗??heights ?뺣낫
    _root.update_idletasks()

    header_height = 70
    sep_height = 1
    card_padding = 8
    total_height = header_height + sep_height

    for port in port_frames:
        frame = port_frames[port]
        try:
            h = frame.winfo_reqheight()
            total_height += (h if h > 1 else 150) + card_padding
        except:
            total_height += 150 + card_padding

    for card in _usb_pending_cards:
        try:
            h = card.winfo_reqheight()
            total_height += (h if h > 1 else 100) + card_padding
        except:
            total_height += 100 + card_padding

    for key in stlink_slot_frames:
        frame = stlink_slot_frames[key]
        try:
            h = frame.winfo_reqheight()
            total_height += (h if h > 1 else 130) + card_padding
        except:
            total_height += 130 + card_padding

    if _stlink_banner:
        try:
            h = _stlink_banner.winfo_reqheight()
            total_height += (h if h > 1 else 40) + card_padding
        except:
            total_height += 40 + card_padding

    if _stlink_detecting_card:
        try:
            h = _stlink_detecting_card.winfo_reqheight()
            total_height += (h if h > 1 else 80) + card_padding
        except:
            total_height += 80 + card_padding

    if _stlink_jre_card:
        try:
            h = _stlink_jre_card.winfo_reqheight()
            total_height += (h if h > 1 else 90) + card_padding
        except:
            total_height += 90 + card_padding

    total_height += STATUS_BAR_HEIGHT + 10

    screen_height = _root.winfo_screenheight() - 100
    new_height = min(total_height, screen_height)
    new_height = max(new_height, 400)
    current_width = max(_root.winfo_width(), 1220)
    _root.geometry(f"{current_width}x{new_height}")

# ===== ?곹깭諛??낅뜲?댄듃 =====
def update_status_bar():
    if _status_bar_label is None:
        return
    working_count = 0
    success_count = 0
    error_count = 0
    waiting_count = 0
    for port, label in port_status_labels.items():
        try:
            text = label.cget("text")
            if "FLASHING" in text or "UART CHECK" in text or "DETECTING" in text or text.endswith(" WAIT"):
                working_count += 1
            elif "DONE" in text or text.endswith(" OK"):
                success_count += 1
            elif "FAIL" in text or "ERROR" in text or "PORT ERROR" in text or "UART FAIL" in text:
                error_count += 1
            elif "WAITING" in text or "TEST READY" in text:
                waiting_count += 1
        except:
            pass
    blocked_count = 0
    for key, label in stlink_slot_status_labels.items():
        try:
            text = label.cget("text")
            if any(state in text for state in ("CHECKING_JRE", "ISOLATING", "UPDATING")):
                working_count += 1
            elif any(state in text for state in ("SUCCESS", "DONE", "UPDATED")):
                success_count += 1
            elif any(state in text for state in ("FAIL", "ERROR", "JAR NOT FOUND", "NO TARGET")):
                error_count += 1
            elif "BLOCKED" in text:
                blocked_count += 1
            elif any(state in text for state in ("READY", "WAITING", "NEED_DFU")):
                waiting_count += 1
        except:
            pass

    working_count += len(detecting_frames)
    working_count += len(_usb_pending_cards)
    if _stlink_detecting_card:
        working_count += 1
    if success_count == 0 and working_count == 0 and error_count == 0 and waiting_count == 0 and blocked_count == 0:
        status_text = "Ready - No boards connected"
    else:
        parts = []
        if working_count > 0:
            parts.append(f"Working: {working_count}")
        if success_count > 0:
            parts.append(f"Success: {success_count}")
        if error_count > 0:
            parts.append(f"Error: {error_count}")
        if waiting_count > 0:
            parts.append(f"Waiting: {waiting_count}")
        if blocked_count > 0:
            parts.append(f"Blocked: {blocked_count}")
        status_text = "  |  ".join(parts)
    try:
        _status_bar_label.configure(text=status_text)
    except:
        pass


