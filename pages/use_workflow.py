import threading
import tkinter as tk
import time
from datetime import datetime, timedelta
from pathlib import Path

import cv2
from PIL import Image, ImageTk

from pages.config import APP_DIR, load_config
from pages.inspection_logic import inspect_image_with_pin_conditions
from pages.remote_io import RemoteIOClient
from pages.widgets import primary_button
from pin_inspection_app import (
    CAMERA_SOURCES,
    RASP_TEST_IMAGES,
    SYSTEM_MODE,
    WINDOW_TEST_IMAGES,
    capture_image,
    draw_code_results,
)
from read_qr_code import read_codes_from_image


RESULT_DIR = APP_DIR / "result"
RESULT_RETENTION_DAYS = 7


def debug_log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[USE DEBUG {timestamp}] {message}", flush=True)


def save_result_image_to_result_folder(camera_name, image):
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    cleanup_old_result_images()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULT_DIR / f"{camera_name}_result_{timestamp}.jpg"
    cv2.imwrite(str(path), image)
    return str(path)


def cleanup_old_result_images():
    if not RESULT_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(days=RESULT_RETENTION_DAYS)
    for path in RESULT_DIR.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp"}:
            continue
        modified_at = datetime.fromtimestamp(path.stat().st_mtime)
        if modified_at < cutoff:
            debug_log(f"Delete old result image: {path}")
            path.unlink(missing_ok=True)


class UseWorkflow(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg="#ffffff")
        self._has_loaded = False
        self.panels = {}
        self.action_buttons = []
        self.status_var = tk.StringVar(value="Ready.")
        self.pending_panels = 0
        self.run_queue = []
        self.run_mode = None
        self.auto_enabled = False
        self.auto_reading = False
        self.last_di0 = False
        self.manual_button = None
        self.auto_button = None
        self.config_button = None
        self._build_layout()

    def refresh(self):
        if not self._has_loaded:
            self._has_loaded = True
            self.status_var.set("Manual run or Auto Run from Remote I/O DI0.")

    def _build_layout(self):
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        toolbar = tk.Frame(self, bg="#ffffff")
        toolbar.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        toolbar.columnconfigure(3, weight=1)

        self.manual_button = primary_button(toolbar, "Run Manual", self.run_manual)
        self.manual_button.configure(
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
        )
        self.manual_button.grid(row=0, column=0, sticky="w")

        self.auto_button = primary_button(toolbar, "Auto Run DI0", self.toggle_auto_mode)
        self.auto_button.configure(
            bg="#16a34a",
            fg="#ffffff",
            activebackground="#15803d",
            activeforeground="#ffffff",
        )
        self.auto_button.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.config_button = primary_button(toolbar, "Configure TCP/IP", self.network_config)
        self.config_button.configure(
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
        )
        self.config_button.grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.action_buttons.append(self.manual_button)
        self.action_buttons.append(self.auto_button)
        self.action_buttons.append(self.config_button)

        tk.Label(
            toolbar,
            textvariable=self.status_var,
            bg="#ffffff",
            fg="#4b5563",
            font=("Helvetica", 11),
        ).grid(row=0, column=3, sticky="e")

        content = tk.Frame(self, bg="#ffffff")
        content.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)

        for column, camera_name in enumerate(("cam0", "cam1")):
            panel = CameraResultPanel(content, camera_name, self._panel_finished)
            panel.grid(row=0, column=column, sticky="nsew", padx=(0, 10) if column == 0 else (10, 0))
            self.panels[camera_name] = panel

    def network_config(self):
        from pages.network_config import NetworkConfigDialog

        NetworkConfigDialog(self)

    def run_manual(self):
        if self.auto_enabled or self._is_running():
            debug_log("Manual run ignored because system is busy or auto mode is enabled.")
            return
        debug_log("Manual run requested.")
        self._start_run("manual")

    def toggle_auto_mode(self):
        if self.run_mode == "manual":
            debug_log("Auto mode ignored because manual run is active.")
            return
        if self.auto_enabled:
            self.auto_enabled = False
            self.last_di0 = False
            self.status_var.set("Auto Run canceled.")
            debug_log("Auto mode canceled by user.")
            self._apply_idle_buttons()
            return

        config = load_config().get("remote_io", {})
        if not config.get("enabled"):
            self.status_var.set("Please enable Remote I/O before Auto Run.")
            self._show_global_alert("Remote I/O is not enabled.", "warning")
            debug_log("Auto mode rejected because Remote I/O is disabled.")
            return

        self.auto_enabled = True
        self.last_di0 = False
        self.status_var.set("Auto Run is waiting for DI0.")
        debug_log(
            "Auto mode started. "
            f"host={config.get('host')} port={config.get('port')} di0={config.get('di0_address', 0)}"
        )
        self._apply_auto_buttons()
        self._poll_auto_input()

    def _poll_auto_input(self):
        if not self.auto_enabled:
            return
        if self._is_running() or self.auto_reading:
            self.after(300, self._poll_auto_input)
            return

        self.auto_reading = True
        config = load_config().get("remote_io", {})
        threading.Thread(target=self._read_auto_input_worker, args=(config,), daemon=True).start()

    def _read_auto_input_worker(self, config):
        try:
            value = RemoteIOClient(config).read_di(config.get("di0_address", 0))
            self.after(0, lambda: self._auto_input_done(value, None))
        except Exception as exc:
            self.after(0, lambda error=exc: self._auto_input_done(False, error))

    def _auto_input_done(self, value, error):
        self.auto_reading = False
        if not self.auto_enabled:
            return
        if error is not None:
            self.status_var.set(f"Auto Run DI0 read failed: {error}")
            debug_log(f"DI0 read error: {error}")
            self.after(1500, self._poll_auto_input)
            return

        rising_edge = value and not self.last_di0
        if value != self.last_di0:
            debug_log(f"DI0 changed: {self.last_di0} -> {value}")
        self.last_di0 = value
        if rising_edge:
            debug_log("DI0 rising edge detected. Auto run will start.")
            self._start_run("auto")
            return

        self.status_var.set("Auto Run is waiting for DI0.")
        self.after(300, self._poll_auto_input)

    def _start_run(self, mode):
        if any(panel.is_busy for panel in self.panels.values()):
            debug_log(f"{mode} run ignored because a panel is busy.")
            return
        self.run_mode = mode
        self.status_var.set("Running inspection for cam0 and cam1...")
        self.run_queue = list(self.panels.values())
        self.pending_panels = len(self.run_queue)
        debug_log(f"Inspection started. mode={mode} cameras={list(self.panels.keys())}")
        self._apply_running_buttons()
        self._run_next_panel()

    def _run_next_panel(self):
        if not self.run_queue:
            return
        panel = self.run_queue.pop(0)
        self.status_var.set(f"Running inspection for {panel.camera_name}...")
        debug_log(f"Start panel inspection: {panel.camera_name}")
        panel.run_inspection()

    def _panel_finished(self, panel):
        debug_log(
            f"Panel finished: {panel.camera_name} "
            f"status={panel.last_status} code={panel.last_code_text or '-'} "
            f"output={panel.last_output_path or '-'} error={panel.last_error or '-'}"
        )
        self.pending_panels = max(0, self.pending_panels - 1)
        if self.pending_panels > 0:
            self._run_next_panel()
            return

        passed = all(panel.last_status == "PASS" for panel in self.panels.values())
        debug_log(f"All panels finished. final_result={'PASS' if passed else 'FAIL'}")
        self.status_var.set("Inspection finished. Sending Remote I/O result...")
        self._send_final_result(passed)

    def _send_final_result(self, passed):
        config = load_config().get("remote_io", {})
        if not config.get("enabled"):
            debug_log("Remote I/O output skipped because it is disabled.")
            self._finish_run(passed, "Remote I/O disabled.")
            return

        debug_log(
            "Remote I/O output requested. "
            f"result={'PASS' if passed else 'FAIL'} "
            f"host={config.get('host')} port={config.get('port')} "
            f"do_pass={config.get('do_pass_address', 16)} do_fail={config.get('do_fail_address', 17)}"
        )
        threading.Thread(target=self._remote_result_worker, args=(config, passed), daemon=True).start()

    def _remote_result_worker(self, config, passed):
        try:
            client = RemoteIOClient(config)
            address = config.get("do_pass_address", 16) if passed else config.get("do_fail_address", 17)
            debug_log(f"Remote I/O write ON address={address}")
            client.write_do(address, True)
            time.sleep(5)
            debug_log(f"Remote I/O write OFF address={address}")
            client.write_do(address, False)
            self.after(0, lambda: self._finish_run(passed, None))
        except Exception as exc:
            debug_log(f"Remote I/O output error: {exc}")
            self.after(0, lambda error=exc: self._finish_run(passed, error))

    def _finish_run(self, passed, remote_error):
        if passed:
            message = "OK: both cameras found pins."
            level = "info"
        else:
            message = "FAIL: pin not found on one or both cameras."
            level = "error"

        if remote_error:
            message = f"{message} Remote I/O error: {remote_error}"
            level = "warning"

        self._show_global_alert(message, level)
        self.status_var.set(message)
        debug_log(f"Run finished. message={message}")
        self.run_mode = None
        if self.auto_enabled:
            self._apply_auto_buttons()
            self.after(300, self._poll_auto_input)
        else:
            self._apply_idle_buttons()

    def _is_running(self):
        return self.run_mode in ("manual", "auto") or any(panel.is_busy for panel in self.panels.values())

    def _apply_idle_buttons(self):
        self.manual_button.configure(state="normal")
        self.auto_button.configure(state="normal", text="Auto Run DI0")
        self.config_button.configure(state="normal")

    def _apply_auto_buttons(self):
        self.manual_button.configure(state="disabled")
        self.auto_button.configure(state="normal", text="Cancel Auto")
        self.config_button.configure(state="disabled")

    def _apply_running_buttons(self):
        self.manual_button.configure(state="disabled")
        self.config_button.configure(state="disabled")
        if self.run_mode == "auto":
            self.auto_button.configure(state="normal", text="Cancel Auto")
        else:
            self.auto_button.configure(state="disabled", text="Auto Run DI0")

    def _show_global_alert(self, message, level):
        for panel in self.panels.values():
            panel.show_alert(message, level)


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
        self.last_status = None
        self.last_code_text = ""
        self.last_output_path = ""
        self.last_error = None
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
        self.last_status = None
        self.last_code_text = ""
        self.last_output_path = ""
        self.last_error = None
        if not camera_config:
            self.last_status = "FAIL"
            self.last_error = f"No setup config for {self.camera_name}."
            debug_log(f"{self.camera_name}: missing setup config.")
            self.show_alert(f"No setup config for {self.camera_name}.", "warning")
            self.on_finished(self)
            return

        debug_log(
            f"{self.camera_name}: load setup. "
            f"selected_circles={len(camera_config.get('selected_circles', []))} "
            f"read_qr={bool(camera_config.get('read_qr'))}"
        )
        image = self._read_test_image()
        if image is None:
            debug_log(f"{self.camera_name}: test image not available, capture from camera.")
            image = capture_image(self.camera_name, use_test_image=False)
        else:
            debug_log(f"{self.camera_name}: loaded test image shape={image.shape}.")
        if image is None:
            self.last_status = "FAIL"
            self.last_error = f"Cannot load image for {self.camera_name}."
            debug_log(f"{self.camera_name}: cannot load/capture image.")
            self.show_alert(f"Cannot load image for {self.camera_name}.", "error")
            self.on_finished(self)
            return

        self._set_busy(True, "Running...")
        debug_log(f"{self.camera_name}: worker thread started.")
        threading.Thread(
            target=self._inspection_worker,
            args=(image, camera_config),
            daemon=True,
        ).start()

    def _inspection_worker(self, image, camera_config):
        try:
            debug_log(f"{self.camera_name}: pin inspection processing.")
            result_image, _results, pin_passed = inspect_image_with_pin_conditions(image, camera_config)
            debug_log(
                f"{self.camera_name}: pin inspection done. "
                f"detected={sum(1 for result in _results if result.detected)}/{len(_results)} "
                f"passed={pin_passed}"
            )
            code_text = ""
            if camera_config.get("read_qr"):
                try:
                    debug_log(f"{self.camera_name}: reading QR/Data Matrix.")
                    codes = read_codes_from_image(image)
                except Exception as exc:
                    print(f"[QR ERROR] {self.camera_name}: {exc}")
                    codes = []
                result_image = draw_code_results(result_image, codes)
                code_text = codes[0]["data"] if codes else "NOT FOUND"
                if not codes:
                    print(f"[QR] {self.camera_name}: NOT FOUND")
                debug_log(f"{self.camera_name}: QR/Data Matrix result={code_text}.")

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
            output_path = save_result_image_to_result_folder(self.camera_name, result_image)
            debug_log(f"{self.camera_name}: result image saved at {output_path}.")
            self.after(0, lambda: self._inspection_done(result_image, status, code_text, output_path, None))
        except Exception as exc:
            debug_log(f"{self.camera_name}: inspection error: {exc}")
            self.after(0, lambda error=exc: self._inspection_done(None, "FAIL", "", "", error))

    def _inspection_done(self, result_image, status, code_text, output_path, error):
        self._set_busy(False)
        if error is not None:
            self.last_status = "FAIL"
            self.last_error = str(error)
            self.show_alert(f"Inspection failed: {error}", "error")
            self.on_finished(self)
            return

        self.image = result_image
        self.last_status = status
        self.last_code_text = code_text
        self.last_output_path = output_path
        self._reset_view()
        self.status_var.set(f"Pin {status}. Code: {code_text or '-'}")
        if code_text == "NOT FOUND":
            self.show_alert("No QR/Data Matrix found.", "warning")
        elif status != "PASS":
            self.show_alert("Pin inspection failed.", "error")
        else:
            self.show_alert(f"Saved: {Path(output_path).name}", "info")
        self.render()
        self.on_finished(self)

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
