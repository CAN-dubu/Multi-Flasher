import tkinter as tk
from tkinter.scrolledtext import ScrolledText
import customtkinter as ctk
import queue as _queue_module
import threading

from constants import *
_LOG_FLUSH_INTERVAL = 100  # defined in constants.py but not exported via *

# ===== 전역 변수 =====
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

# USB pending cards (여러 USB 동시 인식 가능)
_usb_pending_cards = []

def init(root, card_container, subtitle_label, status_bar_label):
    global _root, _card_container, _subtitle_label, _status_bar_label
    _root = root
    _card_container = card_container
    _subtitle_label = subtitle_label
    _status_bar_label = status_bar_label

# ===== 로그 출력 =====
def queue_log(port, message):
    _log_queue.put((port, message))

def _write_log_to_widget(port, message):
    text_widget = port_logs.get(port)
    if text_widget:
        if "[FAIL]" in message or "[ERROR]" in message:
            tag = "error"
        elif "[SUCCESS]" in message or "[UPLOAD DONE]" in message or "[UART CHECK DONE]" in message or "[RX]" in message:
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

# ===== 상태 업데이트 =====
def update_status(port, status_text, label_bg, label_fg="#000000", border_color=None):
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

# ===== USB Pending UI 생성 =====
def create_usb_pending_card():
    """USB 감지는 됐으나 COM 포트 등록 대기중인 상태 표시. 카드 frame을 반환."""
    try:
        outer = ctk.CTkFrame(_card_container, fg_color=CARD_BG, corner_radius=12,
                             border_width=2, border_color="#f59e0b")
        outer.pack(fill=tk.X, padx=12, pady=4)
        header = ctk.CTkFrame(outer, fg_color=HEADER_BG, corner_radius=8)
        header.pack(fill=tk.X, padx=8, pady=(8, 4))
        marker = ctk.CTkLabel(header, text="●", font=ctk.CTkFont(size=14),
                              text_color="#fbbf24", fg_color="transparent")
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
        progress_frame = ctk.CTkFrame(outer, fg_color="#2a2a3e", corner_radius=0)
        progress_frame.pack(fill=tk.X, padx=12, pady=(0, 8))
        progress_bar = ctk.CTkProgressBar(progress_frame, mode="indeterminate",
                                         progress_color="#fbbf24", fg_color="#2a2a3e")
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
    """특정 USB pending 카드 제거."""
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
    """USB pending 카드 하나를 제거 (FIFO)."""
    if _usb_pending_cards:
        card = _usb_pending_cards.pop(0)
        try:
            card.destroy()
        except:
            pass
        update_status_bar()
        _root.after(50, adjust_window_size)

def remove_all_usb_pending_cards():
    """모든 USB pending 카드 제거."""
    while _usb_pending_cards:
        card = _usb_pending_cards.pop(0)
        try:
            card.destroy()
        except:
            pass
    update_status_bar()
    _root.after(50, adjust_window_size)

# ===== Detecting UI =====
def create_detecting_gui(port_name):
    try:
        outer = ctk.CTkFrame(_card_container, fg_color=CARD_BG, corner_radius=12,
                             border_width=2, border_color="#6366f1")
        outer.pack(fill=tk.X, padx=12, pady=4)
        header = ctk.CTkFrame(outer, fg_color=HEADER_BG, corner_radius=8)
        header.pack(fill=tk.X, padx=8, pady=(8, 4))
        marker = ctk.CTkLabel(header, text="●", font=ctk.CTkFont(size=14),
                              text_color="#fbbf24", fg_color="transparent")
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
        progress_frame = ctk.CTkFrame(outer, fg_color="#2a2a3e", corner_radius=0)
        progress_frame.pack(fill=tk.X, padx=12, pady=(0, 8))
        progress_bar = ctk.CTkProgressBar(progress_frame, mode="indeterminate",
                                          progress_color="#818cf8", fg_color="#2a2a3e")
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

# ===== GUI 생성 =====
def create_port_gui(port, port_type):
    try:
        if port in detecting_frames:
            remove_detecting_gui(port)
        outer = ctk.CTkFrame(_card_container, fg_color=CARD_BG, corner_radius=12,
                             border_width=2, border_color="#2a2a3e")
        outer.pack(fill=tk.X, padx=12, pady=4)
        header = ctk.CTkFrame(outer, fg_color=HEADER_BG, corner_radius=8)
        header.pack(fill=tk.X, padx=8, pady=(8, 4))
        marker_color = "#f97316" if "CP2102" in port_type else "#3b82f6"
        marker = ctk.CTkLabel(header, text="●", font=ctk.CTkFont(size=14),
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
        accent_line = ctk.CTkFrame(outer, fg_color="#333355", height=2, corner_radius=0)
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
        text.tag_configure("warn", foreground="#fbbf24")
        text.tag_configure("error", foreground="#f87171")
        text.tag_configure("success", foreground="#4ade80")
        text.tag_configure("done", foreground=TEXT_MUTED)
        text.tag_configure("default", foreground="#aaaaaa")
        text.tag_configure("rx", foreground="#4ade80")
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
    count = len(port_frames)
    if count == 0:
        _subtitle_label.configure(text="  No boards  ", fg_color="#555577", text_color="#aaaaaa")
    else:
        _subtitle_label.configure(text=f"  {count} board(s)  ", fg_color=ACCENT, text_color="#ffffff")

def adjust_window_size():
    """디바운싱: 여러 번 호출되어도 실제 실행은 200ms 후 1번만."""
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

    if count == 0 and pending_count == 0:
        _root.geometry("900x400")
        return

    # update_idletasks() 제거 — 이게 렉의 주범
    # 대신 winfo_reqheight()가 0을 반환할 수 있지만 다음 호출에서 보정됨

    header_height = 70
    card_padding = 8
    total_height = header_height

    for port in port_frames:
        frame = port_frames[port]
        h = frame.winfo_reqheight()
        if h > 1:
            total_height += h + card_padding
        else:
            total_height += 150 + card_padding  # 아직 렌더링 안 된 카드 기본값

    for card in _usb_pending_cards:
        try:
            h = card.winfo_reqheight()
            total_height += (h if h > 1 else 100) + card_padding
        except:
            pass

    total_height += STATUS_BAR_HEIGHT + 8

    screen_height = _root.winfo_screenheight() - 100
    new_height = min(total_height, screen_height)
    new_height = max(new_height, 400)
    current_width = max(_root.winfo_width(), 900)
    _root.geometry(f"{current_width}x{new_height}")

# ===== 상태바 업데이트 =====
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
            if "FLASHING" in text or "UART CHECK" in text or "DETECTING" in text:
                working_count += 1
            elif "DONE" in text:
                success_count += 1
            elif "FAIL" in text or "ERROR" in text or "PORT ERROR" in text or "UART FAIL" in text:
                error_count += 1
            elif "WAITING" in text:
                waiting_count += 1
        except:
            pass
    working_count += len(detecting_frames)
    working_count += len(_usb_pending_cards)
    if success_count == 0 and working_count == 0 and error_count == 0 and waiting_count == 0:
        status_text = "Ready — No boards connected"
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
        status_text = "  |  ".join(parts)
    try:
        _status_bar_label.configure(text=status_text)
    except:
        pass
