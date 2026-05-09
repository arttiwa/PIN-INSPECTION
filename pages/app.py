import tkinter as tk
from tkinter import messagebox

from pages.config import PIN_APP_PATH
from pages.home_page import HomePage
from pages.runner import ProcessRunner
from pages.setup_page import SetupPage
from pages.use_page import UsePage


class PinInspectionUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PIN Inspection")
        self.geometry("980x640")
        self.minsize(860, 560)
        self.configure(bg="#f7f8fa")

        self.runner = ProcessRunner(self.append_log, self.on_process_done)
        self.active_page = None

        self._build_shell()
        self.pages = {
            "home": HomePage(self.content, self),
            "setup": SetupPage(self.content, self),
            "use": UsePage(self.content, self),
        }
        self.show_page("home")
        self.after(120, self._poll_runner)

    def _build_shell(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        sidebar = tk.Frame(self, bg="#ffffff", width=210, highlightbackground="#e5e7eb", highlightthickness=1)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)

        tk.Label(
            sidebar,
            text="PIN Inspection",
            bg="#ffffff",
            fg="#111827",
            font=("Helvetica", 20, "bold"),
            justify="left",
        ).pack(anchor="w", padx=22, pady=(28, 10))

        tk.Label(
            sidebar,
            text="Inspection Control",
            bg="#ffffff",
            fg="#6b7280",
            font=("Helvetica", 11),
        ).pack(anchor="w", padx=22, pady=(0, 22))

        self.nav_buttons = {}
        for key, label in (
            ("home", "Dashboard"),
            ("setup", "Setup Mode"),
            ("use", "Use Mode"),
        ):
            button = tk.Button(
                sidebar,
                text=label,
                command=lambda page=key: self.show_page(page),
                anchor="w",
                padx=18,
                pady=12,
                relief="flat",
                bd=0,
                bg="#ffffff",
                fg="#374151",
                activebackground="#eef2ff",
                activeforeground="#1d4ed8",
                font=("Helvetica", 12, "bold"),
                cursor="hand2",
            )
            button.pack(fill="x", padx=12, pady=3)
            self.nav_buttons[key] = button

        tk.Label(
            sidebar,
            text="Setup runs inside this UI.\nUse mode may open result windows.",
            bg="#ffffff",
            fg="#6b7280",
            justify="left",
            font=("Helvetica", 10),
        ).pack(side="bottom", anchor="w", padx=22, pady=24)

        main = tk.Frame(self, bg="#f7f8fa")
        main.grid(row=0, column=1, sticky="nsew")
        main.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)

        self.content = tk.Frame(main, bg="#f7f8fa")
        self.content.grid(row=0, column=0, sticky="nsew", padx=32, pady=28)
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)

    def show_page(self, name):
        if self.active_page:
            self.active_page.grid_remove()
        self.active_page = self.pages[name]
        self.active_page.refresh()
        self.active_page.grid(row=0, column=0, sticky="nsew")

        for key, button in self.nav_buttons.items():
            selected = key == name
            button.configure(
                bg="#eef2ff" if selected else "#ffffff",
                fg="#1d4ed8" if selected else "#374151",
            )

    def run_mode(self, mode):
        if not PIN_APP_PATH.is_file():
            messagebox.showerror("Missing file", f"Cannot find {PIN_APP_PATH}")
            return
        self.runner.start(mode)

    def stop_current_task(self):
        self.runner.stop()

    def append_log(self, text):
        if not hasattr(self, "pages"):
            return
        for page in self.pages.values():
            page.append_log(text)

    def on_process_done(self, return_code):
        status = "finished" if return_code == 0 else f"exited with code {return_code}"
        self.append_log(f"\nTask {status}.\n")
        if self.active_page and hasattr(self.active_page, "process_finished"):
            self.active_page.process_finished(return_code)

    def _poll_runner(self):
        self.runner.poll()
        self.after(120, self._poll_runner)
