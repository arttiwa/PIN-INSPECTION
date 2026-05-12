import socket
import tkinter as tk

from pages.config import load_config, save_config
from pages.widgets import primary_button, secondary_button, success_button


DEFAULT_REMOTE_IO = {
    "enabled": False,
    "host": "192.168.1.10",
    "port": 502,
    "unit_id": 1,
    "timeout_ms": 1000,
    "di0_address": 0,
    "do_pass_address": 16,
    "do_fail_address": 17,
}


class NetworkConfigDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Remote I/O Connection")
        self.configure(bg="#ffffff")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.resizable(False, False)

        self.status_var = tk.StringVar(value="Configure Modbus TCP/IP Remote I/O.")
        self.enabled_var = tk.BooleanVar()
        self.vars = {}

        self._load_values()
        self._build_layout()
        self._center(parent)

    def _load_values(self):
        config = load_config()
        remote_io = dict(DEFAULT_REMOTE_IO)
        remote_io.update(config.get("remote_io", {}))

        self.enabled_var.set(bool(remote_io["enabled"]))
        for key, value in remote_io.items():
            if key == "enabled":
                continue
            self.vars[key] = tk.StringVar(value=str(value))

    def _build_layout(self):
        root = tk.Frame(self, bg="#ffffff", padx=24, pady=22)
        root.grid(row=0, column=0, sticky="nsew")

        tk.Label(
            root,
            text="Remote I/O Connection",
            bg="#ffffff",
            fg="#111827",
            font=("Helvetica", 18, "bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w")

        tk.Label(
            root,
            text="Modbus TCP/IP: DI0 uses Function 2, DO16/DO17 use Function 5.",
            bg="#ffffff",
            fg="#6b7280",
            font=("Helvetica", 11),
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 18))

        tk.Checkbutton(
            root,
            text="Enable Remote I/O",
            variable=self.enabled_var,
            bg="#ffffff",
            fg="#111827",
            activebackground="#ffffff",
            activeforeground="#111827",
            selectcolor="#ffffff",
            font=("Helvetica", 11, "bold"),
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(0, 14))

        fields = (
            ("host", "IP Address", 18),
            ("port", "Port", 8),
            ("unit_id", "Unit ID", 8),
            ("timeout_ms", "Timeout (ms)", 8),
            ("di0_address", "DI0 Address", 8),
            ("do_pass_address", "DO Pass Address", 8),
            ("do_fail_address", "DO Fail Address", 8),
        )

        for index, (key, label, width) in enumerate(fields, start=3):
            tk.Label(
                root,
                text=label,
                bg="#ffffff",
                fg="#374151",
                font=("Helvetica", 11, "bold"),
            ).grid(row=index, column=0, sticky="w", pady=7, padx=(0, 12))

            entry = tk.Entry(
                root,
                textvariable=self.vars[key],
                width=width,
                bg="#ffffff",
                fg="#111827",
                relief="solid",
                bd=1,
                justify="center" if key != "host" else "left",
                font=("Helvetica", 12),
            )
            entry.grid(row=index, column=1, sticky="w", pady=7)

            hint = self._hint_for(key)
            tk.Label(
                root,
                text=hint,
                bg="#ffffff",
                fg="#6b7280",
                font=("Helvetica", 10),
            ).grid(row=index, column=2, columnspan=2, sticky="w", pady=7, padx=(14, 0))

        tk.Label(
            root,
            textvariable=self.status_var,
            bg="#ffffff",
            fg="#4b5563",
            font=("Helvetica", 11),
        ).grid(row=10, column=0, columnspan=4, sticky="w", pady=(16, 0))

        buttons = tk.Frame(root, bg="#ffffff")
        buttons.grid(row=11, column=0, columnspan=4, sticky="e", pady=(20, 0))
        secondary_button(buttons, "Cancel", self.destroy).grid(row=0, column=0, padx=(0, 8))
        primary_button(buttons, "Test TCP", self.test_connection).grid(row=0, column=1, padx=(0, 8))
        success_button(buttons, "Save", self.save).grid(row=0, column=2)

    def _hint_for(self, key):
        hints = {
            "host": "Remote I/O device IP",
            "port": "Default Modbus TCP is 502",
            "unit_id": "Slave/unit id",
            "timeout_ms": "TCP connection timeout",
            "di0_address": "Read input with Function 2",
            "do_pass_address": "Write coil with Function 5",
            "do_fail_address": "Write coil with Function 5",
        }
        return hints.get(key, "")

    def _values(self):
        values = {"enabled": bool(self.enabled_var.get())}
        values["host"] = self.vars["host"].get().strip()
        if not values["host"]:
            raise ValueError("IP Address is required.")

        for key in (
            "port",
            "unit_id",
            "timeout_ms",
            "di0_address",
            "do_pass_address",
            "do_fail_address",
        ):
            values[key] = int(self.vars[key].get())

        values["port"] = max(1, min(65535, values["port"]))
        values["unit_id"] = max(0, min(255, values["unit_id"]))
        values["timeout_ms"] = max(100, values["timeout_ms"])
        values["di0_address"] = max(0, values["di0_address"])
        values["do_pass_address"] = max(0, values["do_pass_address"])
        values["do_fail_address"] = max(0, values["do_fail_address"])
        return values

    def save(self):
        try:
            values = self._values()
        except ValueError as exc:
            self.status_var.set(str(exc))
            return

        config = load_config()
        config.setdefault("version", 1)
        config["remote_io"] = values
        save_config(config)
        self.status_var.set("Saved Remote I/O connection.")
        self.after(350, self.destroy)

    def test_connection(self):
        try:
            values = self._values()
        except ValueError as exc:
            self.status_var.set(str(exc))
            return

        timeout = values["timeout_ms"] / 1000
        try:
            with socket.create_connection((values["host"], values["port"]), timeout=timeout):
                self.status_var.set("TCP connection OK.")
        except OSError as exc:
            self.status_var.set(f"TCP connection failed: {exc}")

    def _center(self, parent):
        self.update_idletasks()
        parent_root = parent.winfo_toplevel()
        x = parent_root.winfo_rootx() + (parent_root.winfo_width() - self.winfo_width()) // 2
        y = parent_root.winfo_rooty() + (parent_root.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
