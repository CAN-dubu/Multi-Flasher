import threading
import time
import platform
import serial.tools.list_ports

_root = None
_ui = None
_flash_worker = None
_usb_hint_event = threading.Event()

def init(root, ui_module, flash_worker_module):
    global _root, _ui, _flash_worker
    _root = root
    _ui = ui_module
    _flash_worker = flash_worker_module

def get_esp_ports():
    try:
        return [p for p in serial.tools.list_ports.comports() if p.vid in [0x10C4, 0x303A]]
    except:
        return []

def on_usb_change():
    _usb_hint_event.set()

def monitor_ports():
    last_ports = {p.device for p in get_esp_ports()}

    while True:
        got_hint = _usb_hint_event.wait(timeout=1.0)

        if got_hint:
            _usb_hint_event.clear()
            time.sleep(0.05)

        try:
            current_ports = get_esp_ports()
            current_set = {p.device for p in current_ports}
        except:
            continue

        # 새 포트 감지
        new_ports = current_set - last_ports - set(_ui.port_frames.keys())
        for port_name in new_ports:
            _handle_new_port(port_name, current_ports)

        # 제거된 포트 감지
        _handle_removed_ports(current_set)

        last_ports = current_set


def _handle_new_port(port_name, current_ports):
    port_info = next((p for p in current_ports if p.device == port_name), None)
    port_type = ""
    if port_info:
        if port_info.vid == 0x10C4:
            port_type = " [CP2102]"
        elif port_info.vid == 0x303A:
            port_type = " [Native USB]"
    _root.after(0, lambda p=port_name, pt=port_type: _ui.create_port_gui(p, pt))
    _root.after(0, _ui.update_subtitle)
    threading.Thread(target=_flash_worker.flash_device, args=(port_name, port_type), daemon=True).start()


def _handle_removed_ports(current_set):
    removed = set(_ui.port_frames.keys()) - current_set
    if not removed:
        return
    for port in removed:
        frame = _ui.port_frames.pop(port, None)
        if frame:
            _root.after(0, lambda f=frame: f.destroy())
        _ui.port_logs.pop(port, None)
        _ui.port_labels.pop(port, None)
        _ui.port_status_labels.pop(port, None)
        _ui.port_status_bars.pop(port, None)
        _ui.port_log_widgets.pop(port, None)
        _ui.port_accent_lines.pop(port, None)
    _root.after(0, _ui.adjust_window_size)
    _root.after(0, _ui.update_subtitle)
    _root.after(0, _ui.update_status_bar)


def usb_monitor_thread():
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        from ctypes import wintypes
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            LRESULT = ctypes.c_int64
            WPARAM_TYPE = ctypes.c_uint64
            LPARAM_TYPE = ctypes.c_int64
        else:
            LRESULT = ctypes.c_long
            WPARAM_TYPE = ctypes.c_uint
            LPARAM_TYPE = ctypes.c_long

        WM_DEVICECHANGE = 0x0219
        DBT_DEVNODES_CHANGED = 0x0007

        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM_TYPE, LPARAM_TYPE)

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT), ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON),
            ]

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM_TYPE, LPARAM_TYPE]
        user32.DefWindowProcW.restype = LRESULT
        user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
        user32.RegisterClassExW.restype = wintypes.ATOM
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = wintypes.BOOL
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        def wnd_proc(hwnd, msg, wparam, lparam):
            try:
                if msg == WM_DEVICECHANGE and wparam == DBT_DEVNODES_CHANGED:
                    _root.after_idle(on_usb_change)
            except Exception as e:
                print(f"[ERROR] wnd_proc: {e}")
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        wnd_proc_cb = WNDPROC(wnd_proc)
        hInstance = kernel32.GetModuleHandleW(None)
        class_name = "ESPFlasherUSBMonitor_" + str(int(time.time()))

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = wnd_proc_cb
        wc.hInstance = hInstance
        wc.lpszClassName = class_name

        atom = user32.RegisterClassExW(ctypes.byref(wc))
        if not atom:
            return

        hwnd = user32.CreateWindowExW(
            0, class_name, "ESP Flasher USB Monitor", 0x00CF0000,
            0, 0, 1, 1, None, None, hInstance, None
        )
        if not hwnd:
            return

        user32.ShowWindow(hwnd, 0)
        print(f"[INFO] USB monitor started (hwnd={hwnd})")

        msg_struct = wintypes.MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg_struct), None, 0, 0)
            if ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg_struct))
            user32.DispatchMessageW(ctypes.byref(msg_struct))

    except Exception as e:
        print(f"[ERROR] usb_monitor_thread: {e}")
        import traceback
        traceback.print_exc()

def start_usb_monitor():
    if platform.system() == "Windows":
        threading.Thread(target=usb_monitor_thread, daemon=True).start()
        print("[INFO] USB device monitor started")
