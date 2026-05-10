import ctypes
import sys

import constants as app_constants


def apply_windows_titlebar_theme(window, theme_name=None):
    if sys.platform != "win32" or window is None:
        return
    try:
        window.update_idletasks()
        use_dark = ctypes.c_int(1 if (theme_name or app_constants.CURRENT_THEME) == app_constants.THEME_DARK else 0)
        hwnds = [window.winfo_id()]
        parent_hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if parent_hwnd and parent_hwnd not in hwnds:
            hwnds.append(parent_hwnd)
        for hwnd in hwnds:
            for attribute in (20, 19):
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd),
                    ctypes.c_uint(attribute),
                    ctypes.byref(use_dark),
                    ctypes.sizeof(use_dark),
                )
                if result == 0:
                    break
    except:
        pass


def retint_tk_child(widget, old_theme, new_theme):
    color_map = {
        old_value.lower(): new_theme[key]
        for key, old_value in old_theme.items()
        if isinstance(old_value, str) and isinstance(new_theme.get(key), str)
    }
    for option in (
        "fg_color",
        "bg_color",
        "border_color",
        "button_color",
        "button_hover_color",
        "text_color",
        "bg",
        "fg",
    ):
        try:
            current = widget.cget(option)
            if isinstance(current, str):
                replacement = color_map.get(current.lower())
                if replacement:
                    widget.configure(**{option: replacement})
        except:
            pass
    try:
        for child in widget.winfo_children():
            retint_tk_child(child, old_theme, new_theme)
    except:
        pass
