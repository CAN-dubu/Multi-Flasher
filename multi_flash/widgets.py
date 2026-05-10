import tkinter as tk

import constants as theme


class DropdownRegistry:
    def __init__(self):
        self._dropdowns = []

    def add(self, dropdown):
        self._dropdowns.append(dropdown)

    def remove(self, dropdown):
        if dropdown in self._dropdowns:
            self._dropdowns.remove(dropdown)

    def close_others(self, current):
        for dropdown in list(self._dropdowns):
            if dropdown is current:
                continue
            try:
                dropdown.close()
            except tk.TclError:
                self.remove(dropdown)

    def close_all(self):
        for dropdown in list(self._dropdowns):
            try:
                dropdown.close()
            except tk.TclError:
                self.remove(dropdown)

    def refresh_all(self):
        for dropdown in list(self._dropdowns):
            try:
                dropdown.refresh_theme()
            except tk.TclError:
                self.remove(dropdown)


class ThemedDropdown:
    """Custom dropdown whose drawing reads live values from constants.THEMES."""

    def __init__(self, parent, values, callback, default_value=None, width=220, registry=None):
        self.parent = parent
        self.values = list(values)
        self.callback = callback
        self.width = width
        self.default_value = default_value if default_value in self.values else (self.values[0] if self.values else "")
        self.current_value = tk.StringVar(value=self.default_value)
        self.popup = None
        self.selected_index = self.values.index(self.default_value) if self.default_value in self.values else 0
        self.registry = registry
        if self.registry:
            self.registry.add(self)

        self.button = tk.Frame(parent, bg=theme.DROPDOWN_BG, cursor="hand2", relief="flat", bd=0)
        self.button.pack(side=tk.LEFT)

        self.canvas = tk.Canvas(
            self.button,
            width=self.width,
            height=32,
            bg=theme.DROPDOWN_BG,
            highlightthickness=0,
            insertborderwidth=0,
            relief="flat",
        )
        self.canvas.pack()

        self.border = self.canvas.create_rectangle(
            0, 0, self.width - 1, 31, outline=theme.DROPDOWN_BORDER, width=1, fill=theme.DROPDOWN_BG
        )

        self.label = tk.Label(
            self.canvas,
            text=self.default_value,
            bg=theme.DROPDOWN_BG,
            fg=theme.DROPDOWN_TEXT,
            font=("Segoe UI", 12, "bold"),
            anchor="w",
            padx=12,
        )
        self.label_window = self.canvas.create_window(
            4, 2, window=self.label, width=self.width - 32, height=28, anchor="nw"
        )

        self.arrow = tk.Label(
            self.canvas,
            text="v",
            bg=theme.DROPDOWN_BG,
            fg=theme.ACCENT,
            font=("Segoe UI", 9, "bold"),
            anchor="e",
        )
        self.arrow_window = self.canvas.create_window(
            self.width - 18, 8, window=self.arrow, width=12, height=16, anchor="nw"
        )

        self.button.bind("<Button-1>", lambda _event: self._toggle_popup())
        self.label.bind("<Button-1>", lambda _event: self._toggle_popup())
        self.canvas.bind("<Button-1>", lambda _event: self._toggle_popup())

    def refresh_theme(self):
        self._close_popup()
        self.button.configure(bg=theme.DROPDOWN_BG)
        self.canvas.configure(bg=theme.DROPDOWN_BG)
        self.canvas.itemconfigure(self.border, outline=theme.DROPDOWN_BORDER, fill=theme.DROPDOWN_BG)
        self.canvas.tag_lower(self.border)
        self.label.configure(bg=theme.DROPDOWN_BG, fg=theme.DROPDOWN_TEXT)
        self.arrow.configure(bg=theme.DROPDOWN_BG, fg=theme.ACCENT)

    def _toggle_popup(self):
        if self.popup:
            self._close_popup()
        else:
            self._open_popup()

    def _open_popup(self):
        if not self.values:
            return
        if self.registry:
            self.registry.close_others(self)

        self.popup = tk.Toplevel(self.button)
        self.popup.overrideredirect(True)
        self.popup.configure(bg=theme.DROPDOWN_POPUP_BORDER)

        x = self.button.winfo_rootx()
        y = self.button.winfo_rooty() + self.button.winfo_height() + 2
        height = min(len(self.values) * 36, 220)
        self.popup.geometry(f"{self.width}x{height}+{x}+{y}")

        frame = tk.Frame(self.popup, bg=theme.DROPDOWN_POPUP_BORDER, relief="flat", bd=0)
        frame.pack(fill="both", expand=True, padx=1, pady=1)

        border_frame = tk.Frame(frame, bg=theme.DROPDOWN_POPUP_BORDER, relief="flat", bd=0)
        border_frame.pack(fill="both", expand=True, padx=1, pady=1)

        list_frame = tk.Frame(border_frame, bg=theme.DROPDOWN_POPUP_BG, relief="flat", bd=0)
        list_frame.pack(fill="both", expand=True)

        for index, value in enumerate(self.values):
            self._add_popup_item(list_frame, index, value)

        self.popup.bind("<FocusOut>", lambda _event: self._close_popup())
        self.popup.bind("<Button-1>", lambda _event: "break")

    def _add_popup_item(self, list_frame, index, value):
        is_selected = index == self.selected_index
        item_bg = theme.DROPDOWN_SELECTED_BG if is_selected else theme.DROPDOWN_POPUP_BG
        item_fg = theme.ACCENT if is_selected else theme.DROPDOWN_TEXT

        item_frame = tk.Frame(list_frame, bg=item_bg, cursor="hand2", relief="flat", bd=0)
        item_frame.pack(fill="x", padx=0, pady=0)

        accent_bar = tk.Frame(item_frame, bg=theme.ACCENT if is_selected else theme.DROPDOWN_POPUP_BG, width=3, height=32)
        accent_bar.pack(side="left", fill="y")

        item_label = tk.Label(
            item_frame,
            text=f"   {value}",
            bg=item_bg,
            fg=item_fg,
            font=("Segoe UI", 12, "bold" if is_selected else "normal"),
            anchor="w",
            padx=16,
        )
        item_label.pack(side="left", fill="both", expand=True, pady=0)

        def on_enter(_event):
            item_frame.config(bg=theme.DROPDOWN_HOVER_BG)
            item_label.config(bg=theme.DROPDOWN_HOVER_BG, fg=theme.ACCENT)
            accent_bar.config(bg=theme.ACCENT)

        def on_leave(_event):
            bg = theme.DROPDOWN_SELECTED_BG if is_selected else theme.DROPDOWN_POPUP_BG
            item_frame.config(bg=bg)
            item_label.config(bg=bg, fg=theme.ACCENT if is_selected else theme.DROPDOWN_TEXT)
            accent_bar.config(bg=theme.ACCENT if is_selected else theme.DROPDOWN_POPUP_BG)

        def on_click(_event):
            self._select(index)

        item_frame.bind("<Button-1>", on_click)
        item_label.bind("<Button-1>", on_click)
        item_frame.bind("<Enter>", on_enter)
        item_label.bind("<Enter>", on_enter)
        item_frame.bind("<Leave>", on_leave)
        item_label.bind("<Leave>", on_leave)

    def _close_popup(self):
        if self.popup:
            self.popup.destroy()
            self.popup = None

    def close(self):
        self._close_popup()

    def _select(self, index):
        if index < 0 or index >= len(self.values):
            return
        self.selected_index = index
        value = self.values[index]
        self.current_value.set(value)
        self.label.config(text=value)
        self._close_popup()
        self.callback(value)

    def get(self):
        return self.current_value.get()

    def set(self, value, notify=False):
        if value not in self.values:
            return
        self.selected_index = self.values.index(value)
        self.current_value.set(value)
        self.label.config(text=value)
        if notify:
            self.callback(value)

    def set_values(self, values, default_value=None, notify=False):
        self._close_popup()
        self.values = list(values)
        value = default_value if default_value in self.values else (self.values[0] if self.values else "")
        self.selected_index = self.values.index(value) if value in self.values else 0
        self.current_value.set(value)
        self.label.config(text=value)
        if notify and value:
            self.callback(value)
