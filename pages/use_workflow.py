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
        self.image = None
        self.photo = None
        self.scale = 1.0
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.pan_screen_x = 0
        self.pan_screen_y = 0
        self._drag_start = None
        self._drag_moved = False
        self._busy = False
        self._alert = None
        self._alert_job = None
        self._has_loaded = False

        config = load_config()
        cameras = list(config.get("cameras", {}).keys()) or list(CAMERA_SOURCES.keys())
        self.camera_var = tk.StringVar(value=cameras[0] if cameras else "cam0")
        self.status_var = tk.StringVar(value="Ready.")
        self.action_buttons = []

        self._build_layout(cameras)

    def refresh(self):
        if not self._has_loaded:
            self._has_loaded = True
            self.status_var.set("Choose a camera, then click Run Inspection.")

    def _build_layout(self, cameras):
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        toolbar = tk.Frame(self, bg="#ffffff")
        toolbar.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        toolbar.columnconfigure(5, weight=1)

        tk.Label(
            toolbar,
            text="Camera",
            bg="#ffffff",
            fg="#374151",
            font=("Helvetica", 11, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        menu_values = cameras or ["cam0"]
        camera_menu = tk.OptionMenu(toolbar, self.camera_var, *menu_values)
        camera_menu.configure(
            bg="#f9fafb",
            fg="#111827",
            activebackground="#eef2ff",
            activeforeground="#1d4ed8",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#d1d5db",
            font=("Helvetica", 11),
        )
        camera_menu.grid(row=0, column=1, sticky="w", padx=(0, 16))

        run_button = primary_button(toolbar, "Run Inspection", self.run_inspection)
        run_button.grid(row=0, column=2, sticky="w")
        self.action_buttons.append(run_button)

        tk.Label(
            toolbar,
            textvariable=self.status_var,
            bg="#ffffff",
            fg="#4b5563",
            font=("Helvetica", 11),
        ).grid(row=0, column=5, sticky="e")

        self.canvas = tk.Canvas(
            self,
            bg="#f3f4f6",
            highlightbackground="#e5e7eb",
            highlightthickness=1,
            cursor="fleur",
        )
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self.canvas.bind("<Configure>", lambda _event: self.render())
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag_view)
        self.canvas.bind("<ButtonRelease-1>", self._end_drag)

    def run_inspection(self):
        if self._busy:
            return
        camera_name = self.camera_var.get()
        config = load_config()
        camera_config = config.get("cameras", {}).get(camera_name)
        if not camera_config:
            self.show_alert(f"No setup config for {camera_name}.", "warning")
            return

        image = self._read_test_image(camera_name)
        if image is None:
            image = self._capture_image(camera_name)
        if image is None:
            self.show_alert(f"Cannot load image for {camera_name}.", "error")
            return

        self._set_busy(True, "Running inspection. Please wait...")
        threading.Thread(
            target=self._inspection_worker,
            args=(camera_name, image, camera_config),
            daemon=True,
        ).start()

    def _inspection_worker(self, camera_name, image, camera_config):
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
                f"{camera_name} {status} {code_text}",
                (20, 120),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 200, 0) if pin_passed else (0, 0, 220),
                3,
            )
            output_path = save_result_image(camera_name, result_image, "result")
            self.after(0, lambda: self._inspection_done(result_image, status, code_text, output_path, None))
        except Exception as exc:
            self.after(0, lambda error=exc: self._inspection_done(None, "FAIL", "", "", error))

    def _inspection_done(self, result_image, status, code_text, output_path, error):
        self._set_busy(False)
        if error is not None:
            self.show_alert(f"Inspection failed: {error}", "error")
            return

        self.image = result_image
        self._reset_view()
        self.status_var.set(f"Pin {status}. Code: {code_text or '-'}")
        if code_text == "NOT FOUND":
            self.show_alert("No QR/Data Matrix found in image.", "warning")
        elif status != "PASS":
            self.show_alert("Pin inspection failed. Check marked locations.", "error")
        else:
            self.show_alert(f"Result saved: {Path(output_path).name}", "info")
        self.render()

    def _read_test_image(self, camera_name):
        images = RASP_TEST_IMAGES if SYSTEM_MODE == "rasp" else WINDOW_TEST_IMAGES
        test_path = images.get(camera_name, "")
        if not test_path:
            return None
        normalized = test_path.replace("\\", "/")
        path = Path(normalized)
        if not path.is_absolute():
            path = APP_DIR / path
        return cv2.imread(str(path))

    def _capture_image(self, camera_name):
        source = CAMERA_SOURCES.get(camera_name)
        if source is None:
            return None
        cap = cv2.VideoCapture(source)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            return None
        return frame

    def render(self):
        if self.image is None:
            self.canvas.delete("all")
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
        self.canvas.delete("all")
        self.canvas.create_image(self.offset_x, self.offset_y, image=self.photo, anchor="nw")
        self._draw_loading_overlay()
        self._draw_alert_overlay()

    def _set_busy(self, busy, message=None):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for button in self.action_buttons:
            button.configure(state=state)
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
        if self._busy:
            return
        self._drag_start = (event.x, event.y, self.pan_screen_x, self.pan_screen_y)
        self._drag_moved = False

    def _drag_view(self, event):
        if self._drag_start is None:
            return
        start_x, start_y, start_pan_x, start_pan_y = self._drag_start
        if abs(event.x - start_x) > 3 or abs(event.y - start_y) > 3:
            self._drag_moved = True
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
        if not self._busy:
            return
        canvas_w = max(1, self.canvas.winfo_width())
        canvas_h = max(1, self.canvas.winfo_height())
        box_w = min(360, canvas_w - 40)
        box_h = 86
        x1 = (canvas_w - box_w) // 2
        y1 = (canvas_h - box_h) // 2
        self.canvas.create_rectangle(x1, y1, x1 + box_w, y1 + box_h, fill="#ffffff", outline="#d1d5db", width=2)
        self.canvas.create_text(canvas_w // 2, y1 + 32, text="Please wait", fill="#111827", font=("Helvetica", 16, "bold"))
        self.canvas.create_text(canvas_w // 2, y1 + 58, text=self.status_var.get(), fill="#4b5563", font=("Helvetica", 11))

    def _draw_alert_overlay(self):
        if not self._alert or self._busy:
            return
        message, level = self._alert
        colors = {
            "error": ("#fef2f2", "#b91c1c", "#fecaca"),
            "warning": ("#fffbeb", "#92400e", "#fde68a"),
            "info": ("#eff6ff", "#1d4ed8", "#bfdbfe"),
        }
        fill, text_color, outline = colors.get(level, colors["warning"])
        canvas_w = max(1, self.canvas.winfo_width())
        box_w = min(520, canvas_w - 40)
        box_h = 58
        x1 = (canvas_w - box_w) // 2
        y1 = 18
        self.canvas.create_rectangle(x1, y1, x1 + box_w, y1 + box_h, fill=fill, outline=outline, width=2)
        self.canvas.create_text(
            x1 + 18,
            y1 + box_h // 2,
            text=message,
            fill=text_color,
            anchor="w",
            font=("Helvetica", 12, "bold"),
            width=box_w - 36,
        )
