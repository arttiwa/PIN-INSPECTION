import tkinter as tk

from pages.base_page import BasePage
from pages.config import load_config


class HomePage(BasePage):
    def __init__(self, parent, app):
        super().__init__(
            parent,
            app,
            "Dashboard",
            "Choose a workflow, check current configuration, then start inspection.",
        )
        self.body.rowconfigure(0, weight=0)
        self.summary = tk.Frame(self.body, bg="#ffffff")
        self.summary.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        self.summary.columnconfigure((0, 1, 2), weight=1)

    def refresh(self):
        for child in self.summary.winfo_children():
            child.destroy()

        config = load_config()
        cameras = config.get("cameras", {})
        camera_count = len(cameras)
        pin_count = sum(len(cam.get("expected_pin_holes", [])) for cam in cameras.values())
        qr_count = sum(1 for cam in cameras.values() if cam.get("read_qr"))

        self._metric(0, "Configured Cameras", str(camera_count))
        self._metric(1, "Expected Pin Holes", str(pin_count))
        self._metric(2, "QR/Data Matrix", f"{qr_count} camera(s)")

    def _metric(self, column, label, value):
        frame = tk.Frame(
            self.summary,
            bg="#f9fafb",
            padx=18,
            pady=16,
            highlightbackground="#e5e7eb",
            highlightthickness=1,
        )
        frame.grid(row=0, column=column, sticky="ew", padx=6)
        tk.Label(
            frame,
            text=value,
            bg="#f9fafb",
            fg="#111827",
            font=("Helvetica", 22, "bold"),
        ).pack(anchor="w")
        tk.Label(
            frame,
            text=label,
            bg="#f9fafb",
            fg="#4b5563",
            font=("Helvetica", 10, "bold"),
        ).pack(anchor="w")
