import tkinter as tk


class ColorButton(tk.Frame):
    def __init__(
        self,
        parent,
        text,
        command,
        bg,
        fg,
        activebackground,
        activeforeground,
        disabledbackground="#e5e7eb",
        disabledforeground="#9ca3af",
    ):
        super().__init__(parent, bg=bg, cursor="hand2")
        self.command = command
        self.normal_bg = bg
        self.normal_fg = fg
        self.active_bg = activebackground
        self.active_fg = activeforeground
        self.disabled_bg = disabledbackground
        self.disabled_fg = disabledforeground
        self.state = "normal"

        self.label = tk.Label(
            self,
            text=text,
            bg=bg,
            fg=fg,
            padx=20,
            pady=11,
            font=("Helvetica", 12, "bold"),
            cursor="hand2",
        )
        self.label.pack(fill="both", expand=True)

        for widget in (self, self.label):
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)

        if "state" in kwargs:
            self.state = kwargs.pop("state")
        if "bg" in kwargs:
            self.normal_bg = kwargs.pop("bg")
        if "fg" in kwargs:
            self.normal_fg = kwargs.pop("fg")
        if "activebackground" in kwargs:
            self.active_bg = kwargs.pop("activebackground")
        if "activeforeground" in kwargs:
            self.active_fg = kwargs.pop("activeforeground")
        if "text" in kwargs:
            self.label.configure(text=kwargs.pop("text"))
        if "command" in kwargs:
            self.command = kwargs.pop("command")

        super().configure(**kwargs)
        self._apply_colors()

    config = configure

    def _apply_colors(self, hover=False):
        if self.state == "disabled":
            bg = self.disabled_bg
            fg = self.disabled_fg
            cursor = "arrow"
        elif hover:
            bg = self.active_bg
            fg = self.active_fg
            cursor = "hand2"
        else:
            bg = self.normal_bg
            fg = self.normal_fg
            cursor = "hand2"

        self.configure_base(bg=bg, cursor=cursor)
        self.label.configure(bg=bg, fg=fg, cursor=cursor)

    def configure_base(self, **kwargs):
        tk.Frame.configure(self, **kwargs)

    def _on_click(self, _event):
        if self.state != "disabled" and self.command:
            self.command()

    def _on_enter(self, _event):
        self._apply_colors(hover=True)

    def _on_leave(self, _event):
        self._apply_colors(hover=False)


def primary_button(parent, text, command):
    return ColorButton(
        parent,
        text=text,
        command=command,
        bg="#2563eb",
        fg="#ffffff",
        activebackground="#1d4ed8",
        activeforeground="#ffffff",
    )


def success_button(parent, text, command):
    return ColorButton(
        parent,
        text=text,
        command=command,
        bg="#16a34a",
        fg="#ffffff",
        activebackground="#15803d",
        activeforeground="#ffffff",
    )


def secondary_button(parent, text, command):
    return ColorButton(
        parent,
        text=text,
        command=command,
        bg="#d52424",
        fg="#ffffff",
        activebackground="#7f1d1d",
        activeforeground="#ffffff",
        disabledbackground="#f3f4f6",
        disabledforeground="#9ca3af",
    )
