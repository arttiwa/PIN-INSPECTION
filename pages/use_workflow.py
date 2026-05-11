import threading
import tkinter as tk
from pathlib import Path

import cv2
from PIL import Image, ImageTk

from pages.config import APP_DIR, load_config
from pages.inspection_logic import inspect_image_with_pin_conditions
from pages.widgets import primary_button
from pin_inspection_app import (
    CAMERA_SOURCES,
    RASP_TEST_IMAGES,
    SYSTEM_MODE,
    WINDOW_TEST_IMAGES,
    draw_code_results,
    save_result_image,
)
from read_qr_code import read_codes_from_image


class UseWorkflow(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg="#ffffff")
        self._has_loaded = False
        self.panels = {}
        self.action_buttons = []
        self.status_var = tk.StringVar(value="Ready.")
        self.pending_panels = 0
        self._build_layout()

    def refresh(self):
        if not self._has_loaded:
            self._has_loaded = True
            self.status_var.set("Click Run Inspection to inspect cam0 and cam1.")

    def _build_layout(self):
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        toolbar = tk.Frame(self, bg="#ffffff")
        toolbar.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        toolbar.columnconfigure(2, weight=1)

        run_button = primary_button(toolbar, "Run Inspection", self.run_all)
        run_button.configure(
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
        )
        run_button.grid(row=0, column=0, sticky="w")
        self.action_buttons.append(run_button)

        tk.Label(
            toolbar,
            textvariable=self.status_var,
            bg="#ffffff",
            fg="#4b5563",
            font=("Helvetica", 11),
        ).grid(row=0, column=2, sticky="e")

        content = tk.Frame(self, bg="#ffffff")
        content.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)

        for column, camera_name in enumerate(("cam0", "cam1")):
            panel = CameraResultPanel(content, camera_name, self._panel_finished)
            panel.grid(row=0, column=column, sticky="nsew", padx=(0, 10) if column == 0 else (10, 0))
            self.panels[camera_name] = panel

    def run_all(self):
        if any(panel.is_busy for panel in self.panels.values()):
            return
        self.status_var.set("Running inspection for cam0 and cam1...")
        self.pending_panels = len(self.panels)
        for button in self.action_buttons:
            button.configure(state="disabled")
        for panel in self.panels.values():
            panel.run_inspection()

    def _panel_finished(self):
        self.pending_panels = max(0, self.pending_panels - 1)
        if self.pending_panels > 0:
            return
        for button in self.action_buttons:
            button.configure(state="normal")
        self.status_var.set("Inspection finished.")


class CameraResultPanel(tk.Frame):
    def __init__(self, parent, camera_name, on_finished):
        super().__init__(parent, bg="#ffffff", highlightbackground="#e5e7eb", highlightthickness=1)
        self.camera_name = camera_name
        self.on_finished = on_finished
        self.image = None
        self.photo = None
        self.scale = 1.0
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.pan_screen_x = 0
        self.pan_screen_y = 0
        self._drag_start = None
        self._alert = None
        self._alert_job = None
        self.is_busy = False
        self.status_var = tk.StringVar(value="Waiting.")

        self._build_layout()

    def _build_layout(self):
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        header = tk.Frame(self, bg="#ffffff")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=12)
        header.columnconfigure(1, weight=1)

        tk.Label(
            header,
            text=self.camera_name,
            bg="#ffffff",
            fg="#111827",
            font=("Helvetica", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")

        tk.Label(
            header,
            textvariable=self.status_var,
            bg="#ffffff",
            fg="#4b5563",
            font=("Helvetica", 10),
        ).grid(row=0, column=1, sticky="e")

        self.canvas = tk.Canvas(
            self,
            bg="#f3f4f6",
            highlightbackground="#e5e7eb",
            highlightthickness=1,
            cursor="fleur",
        )
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.canvas.bind("<Configure>", lambda _event: self.render())
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag_view)
        self.canvas.bind("<ButtonRelease-1>", self._end_drag)

    def run_inspection(self):
        config = load_config()
        camera_config = config.get("cameras", {}).get(self.camera_name)
        if not camera_config:
            self.show_alert(f"No setup config for {self.camera_name}.", "warning")
            self.on_finished()
            return

        image = self._read_test_image()
        if image is None:
            image = self._capture_image()
        if image is None:
            self.show_alert(f"Cannot load image for {self.camera_name}.", "error")
            self.on_finished()
            return

        self._set_busy(True, "Running...")
        threading.Thread(
            target=self._inspection_worker,
            args=(image, camera_config),
            daemon=True,
        ).start()

    def _inspection_worker(self, image, camera_config):
        try:
            result_image, _results, pin_passed = inspect_image_with_pin_conditions(image, camera_config)
            code_text = ""
            if camera_config.get("read_qr"):
                codes = read_codes_from_image(image)
                result_image = draw_code_results(result_image, codes)
                code_text = codes[0]["data"] if codes else "NOT FOUND"

            status = "PASS" if pin_passed else "FAIL"
            cv2.putText(
                result_image,
                f"{self.camera_name} {status} {code_text}",
                (20, 120),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 200, 0) if pin_passed else (0, 0, 220),
                3,
            )
            output_path = save_result_image(self.camera_name, result_image, "result")
            self.after(0, lambda: self._inspection_done(result_image, status, code_text, output_path, None))
        except Exception as exc:
            self.after(0, lambda error=exc: self._inspection_done(None, "FAIL", "", "", error))

    def _inspection_done(self, result_image, status, code_text, output_path, error):
        self._set_busy(False)
        if error is not None:
            self.show_alert(f"Inspection failed: {error}", "error")
            self.on_finished()
            return

        self.image = result_image
        self._reset_view()
        self.status_var.set(f"Pin {status}. Code: {code_text or '-'}")
        if code_text == "NOT FOUND":
            self.show_alert("No QR/Data Matrix found.", "warning")
        elif status != "PASS":
            self.show_alert("Pin inspection failed.", "error")
        else:
            self.show_alert(f"Saved: {Path(output_path).name}", "info")
        self.render()
        self.on_finished()

    def _read_test_image(self):
        images = RASP_TEST_IMAGES if SYSTEM_MODE == "rasp" else WINDOW_TEST_IMAGES
        test_path = images.get(self.camera_name, "")
        if not test_path:
            return None
        normalized = test_path.replace("\\", "/")
        path = Path(normalized)
        if not path.is_absolute():
            path = APP_DIR / path
        return cv2.imread(str(path))

    def _capture_image(self):
        source = CAMERA_SOURCES.get(self.camera_name)
        if source is None:
            return None
        cap = cv2.VideoCapture(source)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            return None
        return frame

    def render(self):
        self.canvas.delete("all")
        if self.image is None:
            self.canvas.create_text(
                max(1, self.canvas.winfo_width() // 2),
                max(1, self.canvas.winfo_height() // 2),
                text="No result yet",
                fill="#6b7280",
                font=("Helvetica", 14, "bold"),
            )
            self._draw_loading_overlay()
            self._draw_alert_overlay()
            return

        canvas_w = max(1, self.canvas.winfo_width())
        canvas_h = max(1, self.canvas.winfo_height())
        image_h, image_w = self.image.shape[:2]
        self.scale = min(canvas_w / image_w, canvas_h / image_h) * self.zoom
        render_w = max(1, int(image_w * self.scale))
        render_h = max(1, int(image_h * self.scale))
        self.offset_x = (canvas_w - render_w) // 2 + int(self.pan_screen_x)
        self.offset_y = (canvas_h - render_h) // 2 + int(self.pan_screen_y)

        display = cv2.resize(self.image, (render_w, render_h), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.canvas.create_image(self.offset_x, self.offset_y, image=self.photo, anchor="nw")
        self._draw_loading_overlay()
        self._draw_alert_overlay()

    def _set_busy(self, busy, message=None):
        self.is_busy = busy
        if message:
            self.status_var.set(message)
        self.render()
        self.update_idletasks()

    def _reset_view(self):
        self.zoom = 1.0
        self.pan_screen_x = 0
        self.pan_screen_y = 0

    def _on_mousewheel(self, event):
        if self.image is None:
            return
        if event.num == 4 or getattr(event, "delta", 0) > 0:
            self.zoom = min(8.0, self.zoom * 1.2)
        else:
            self.zoom = max(1.0, self.zoom / 1.2)
        self.render()

    def _start_drag(self, event):
        if self.is_busy:
            return
        self._drag_start = (event.x, event.y, self.pan_screen_x, self.pan_screen_y)

    def _drag_view(self, event):
        if self._drag_start is None:
            return
        start_x, start_y, start_pan_x, start_pan_y = self._drag_start
        self.pan_screen_x = start_pan_x + event.x - start_x
        self.pan_screen_y = start_pan_y + event.y - start_y
        self.render()

    def _end_drag(self, _event):
        self._drag_start = None

    def show_alert(self, message, level="warning"):
        self._alert = (message, level)
        self.status_var.set(message)
        if self._alert_job:
            self.after_cancel(self._alert_job)
        self._alert_job = self.after(4500, self.clear_alert)
        self.render()

    def clear_alert(self):
        self._alert = None
        self._alert_job = None
        self.render()

    def _draw_loading_overlay(self):
        if not self.is_busy:
            return
        canvas_w = max(1, self.canvas.winfo_width())
        canvas_h = max(1, self.canvas.winfo_height())
        box_w = min(280, canvas_w - 30)
        box_h = 82
        x1 = (canvas_w - box_w) // 2
        y1 = (canvas_h - box_h) // 2
        self.canvas.create_rectangle(x1, y1, x1 + box_w, y1 + box_h, fill="#ffffff", outline="#d1d5db", width=2)
        self.canvas.create_text(canvas_w // 2, y1 + 30, text="Please wait", fill="#111827", font=("Helvetica", 15, "bold"))
        self.canvas.create_text(canvas_w // 2, y1 + 56, text=self.status_var.get(), fill="#4b5563", font=("Helvetica", 10))

    def _draw_alert_overlay(self):
        if not self._alert or self.is_busy:
            return
        message, level = self._alert
        colors = {
            "error": ("#fef2f2", "#b91c1c", "#fecaca"),
            "warning": ("#fffbeb", "#92400e", "#fde68a"),
            "info": ("#eff6ff", "#1d4ed8", "#bfdbfe"),
        }
        fill, text_color, outline = colors.get(level, colors["warning"])
        canvas_w = max(1, self.canvas.winfo_width())
        box_w = min(380, canvas_w - 30)
        box_h = 56
        x1 = (canvas_w - box_w) // 2
        y1 = 16
        self.canvas.create_rectangle(x1, y1, x1 + box_w, y1 + box_h, fill=fill, outline=outline, width=2)
        self.canvas.create_text(
            x1 + 16,
            y1 + box_h // 2,
            text=message,
            fill=text_color,
            anchor="w",
            font=("Helvetica", 11, "bold"),
            width=box_w - 32,
        )
