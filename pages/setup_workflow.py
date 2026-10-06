import tkinter as tk
import threading
from pathlib import Path

import cv2
from PIL import Image, ImageTk

from ck_pin import get_circle_brightness
from pages.config import APP_DIR, load_config, save_config
from pages.inspection_logic import inspect_image_with_pin_conditions
from pages.widgets import primary_button, secondary_button, success_button
from pin_inspection_app import (
    CAMERA_SOURCES,
    DEFAULT_CIRCLE_FILTER,
    DEFAULT_INSPECTION,
    RASP_TEST_IMAGES,
    SYSTEM_MODE,
    WINDOW_TEST_IMAGES,
    capture_image,
    detect_circles,
    draw_code_results,
)
from read_qr_code import read_codes_from_image


class SetupWorkflow(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg="#ffffff")
        self.image = None
        self.display_image = None
        self.result_image = None
        self.photo = None
        self.circles = []
        self.selected_ids = []
        self.circle_conditions = {}
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.zoom = 1.0
        self.pan_screen_x = 0
        self.pan_screen_y = 0
        self._drag_start = None
        self._drag_moved = False
        self._has_loaded = False
        self._busy = False
        self._alert = None
        self._alert_job = None
        self._render_job = None
        self._render_cache_key = None
        self.view_mode = "setup"

        self.camera_var = tk.StringVar(value=next(iter(CAMERA_SOURCES), "cam0"))
        self.empty_message = "No image for now. Please click Recapture for the setup image."
        self.read_qr_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready.")
        self.setting_vars = {
            key: tk.StringVar(value=str(value))
            for key, value in DEFAULT_CIRCLE_FILTER.items()
        }
        self.inspection_vars = {
            key: tk.StringVar(value=str(value))
            for key, value in DEFAULT_INSPECTION.items()
        }

        self._build_layout()

    def refresh(self):
        if not self._has_loaded:
            self._has_loaded = True
            self.load_camera_image()

    def _build_layout(self):
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        controls = tk.Frame(self, bg="#ffffff")
        controls.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 12))
        controls.columnconfigure(0, weight=1)

        settings_row = tk.Frame(controls, bg="#ffffff")
        settings_row.grid(row=0, column=0, sticky="ew")

        tk.Label(
            settings_row,
            text="Camera",
            bg="#ffffff",
            fg="#374151",
            font=("Helvetica", 11, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        camera_group = tk.Frame(settings_row, bg="#ffffff")
        camera_group.grid(row=0, column=1, sticky="w", padx=(0, 16))
        self.camera_buttons = []
        for column, camera_name in enumerate(CAMERA_SOURCES):
            button = tk.Radiobutton(
                camera_group,
                text=camera_name.upper(),
                variable=self.camera_var,
                value=camera_name,
                command=self.load_camera_image,
                indicatoron=False,
                bg="#f3f4f6",
                fg="#374151",
                activebackground="#dbeafe",
                activeforeground="#1d4ed8",
                selectcolor="#bfdbfe",
                relief="flat",
                bd=0,
                padx=14,
                pady=8,
                font=("Helvetica", 11, "bold"),
            )
            button.grid(row=0, column=column, padx=(0, 4))
            self.camera_buttons.append(button)

        for index, (key, label) in enumerate(
            (
                ("min_radius", "Min R"),
                ("max_radius", "Max R"),
                ("param2", "Strict"),
                ("min_dist", "Distance"),
            ),
            start=2,
        ):
            tk.Label(
                settings_row,
                text=label,
                bg="#ffffff",
                fg="#374151",
                font=("Helvetica", 10, "bold"),
            ).grid(row=0, column=index * 2 - 2, sticky="e", padx=(0, 6))
            entry = tk.Entry(
                settings_row,
                textvariable=self.setting_vars[key],
                width=6,
                bg="#ffffff",
                fg="#111827",
                relief="solid",
                bd=1,
                justify="center",
                font=("Helvetica", 11),
            )
            entry.grid(row=0, column=index * 2 - 1, sticky="w", padx=(0, 12))

        qr_checkbox = tk.Checkbutton(
            settings_row,
            text="Read QR/Data Matrix",
            variable=self.read_qr_var,
            onvalue=True,
            offvalue=False,
            bg="#ffffff",
            fg="#111827",
            activebackground="#ffffff",
            activeforeground="#111827",
            selectcolor="#ffffff",
            font=("Helvetica", 10),
            padx=4,
            pady=6,
        )
        qr_checkbox.grid(row=0, column=10, sticky="w", padx=(4, 0))
        self.qr_buttons = [qr_checkbox]

        actions_row = tk.Frame(controls, bg="#ffffff")
        actions_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        actions_row.columnconfigure(4, weight=1)

        self.action_buttons = []
        self.recapture_button = secondary_button(actions_row, "1 Recapture", self.recapture_camera_image)
        self.recapture_button.grid(row=0, column=0, padx=(0, 8))
        self.action_buttons.append(self.recapture_button)

        self.process_button = primary_button(actions_row, "2 Process", self.process_circles)
        self.process_button.grid(row=0, column=1, padx=(0, 8))
        self.action_buttons.append(self.process_button)

        self.condition_button = primary_button(actions_row, "3 Pin Conditions", self.open_condition_popup)
        self.condition_button.grid(row=0, column=2, padx=(0, 8))
        self.action_buttons.append(self.condition_button)

        self.clear_button = secondary_button(actions_row, "Clear", self.clear_selection)
        self.clear_button.grid(row=0, column=3, padx=(0, 12))
        self.action_buttons.append(self.clear_button)

        tk.Label(
            actions_row,
            textvariable=self.status_var,
            bg="#ffffff",
            fg="#4b5563",
            font=("Helvetica", 10),
            anchor="e",
        ).grid(row=0, column=4, sticky="ew", padx=(0, 12))

        self.save_button = success_button(actions_row, "4 Save Setup", self.save_setup)
        self.save_button.grid(row=0, column=5, sticky="e")
        self.action_buttons.append(self.save_button)

        self.canvas = tk.Canvas(
            self,
            bg="#f3f4f6",
            highlightbackground="#e5e7eb",
            highlightthickness=1,
            cursor="crosshair",
        )
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 16))
        self.canvas.bind("<Configure>", lambda _event: self.schedule_render(80))
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag_view)
        self.canvas.bind("<ButtonRelease-1>", self._end_left_drag)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
        self.canvas.bind("<ButtonPress-2>", self._start_drag)
        self.canvas.bind("<B2-Motion>", self._drag_view)
        self.canvas.bind("<ButtonRelease-2>", self._end_drag)
        self.canvas.bind("<ButtonPress-3>", self._start_drag)
        self.canvas.bind("<B3-Motion>", self._drag_view)
        self.canvas.bind("<ButtonRelease-3>", self._end_drag)

    def load_camera_image(self):
        self._load_camera_image(force_capture=False)

    def recapture_camera_image(self):
        self._load_camera_image(force_capture=True)

    def _load_camera_image(self, force_capture=False):
        if self._busy:
            return

        camera_name = self.camera_var.get()
        self.apply_camera_setup(camera_name)
        image = None
        if force_capture:
            image = capture_image(camera_name, use_test_image=False)
        else:
            image = self._read_test_image(camera_name)

        if image is None:
            self.image = None
            self.result_image = None
            self.view_mode = "setup"
            self._invalidate_render_cache()
            self._reset_view()
            self.circles = []
            self.selected_ids = self._configured_selected_ids(camera_name)
            if force_capture:
                self.show_alert(f"Cannot capture for {camera_name}.", "error")
                self.status_var.set(f"Cannot capture for {camera_name}.")
            else:
                self.status_var.set(self.empty_message)
            self.render()
            return

        self.image = image
        self.result_image = None
        self.view_mode = "setup"
        self._invalidate_render_cache()
        self._reset_view()
        self.circles = []
        self.selected_ids = self._configured_selected_ids(camera_name)
        if force_capture:
            self.status_var.set(f"Captured new image for {camera_name}. Click Process to detect circles.")
        else:
            self.status_var.set(f"Loaded image for {camera_name}. Click Process to detect circles.")
        self.render()

    def apply_camera_setup(self, camera_name):
        camera_config = load_config().get("cameras", {}).get(camera_name)
        if not camera_config:
            for key, value in DEFAULT_CIRCLE_FILTER.items():
                self.setting_vars[key].set(str(value))
            for key, value in DEFAULT_INSPECTION.items():
                self.inspection_vars[key].set(str(value))
            self.read_qr_var.set(False)
            self.selected_ids = []
            self.circle_conditions = {}
            return

        for key, value in camera_config.get("circle_filter", DEFAULT_CIRCLE_FILTER).items():
            if key in self.setting_vars:
                self.setting_vars[key].set(str(value))
        for key, value in camera_config.get("inspection", DEFAULT_INSPECTION).items():
            if key in self.inspection_vars:
                self.inspection_vars[key].set(str(value))
        self.read_qr_var.set(bool(camera_config.get("read_qr", False)))
        self.selected_ids = self._configured_selected_ids(camera_name)
        self.circle_conditions = {}
        pin_conditions = camera_config.get("pin_conditions", [])
        for index, circle_id in enumerate(self.selected_ids):
            if index < len(pin_conditions):
                self.circle_conditions[int(circle_id)] = dict(pin_conditions[index])

    def _configured_selected_ids(self, camera_name):
        camera_config = load_config().get("cameras", {}).get(camera_name, {})
        return list(camera_config.get("selected_circle_ids", []))

    def _invalidate_render_cache(self):
        self._render_cache_key = None

    def schedule_render(self, delay=30):
        if self._render_job:
            self.after_cancel(self._render_job)
        self._render_job = self.after(delay, self._run_scheduled_render)

    def _run_scheduled_render(self):
        self._render_job = None
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

        image = cv2.imread(str(path))
        if image is None:
            self.show_alert(f"Cannot read test image: {path}", "error")
        return image

    def _settings(self):
        settings = {}
        try:
            for key, var in self.setting_vars.items():
                settings[key] = int(var.get())
        except ValueError:
            self.show_alert("Circle settings must be numbers.", "warning")
            return None

        settings["min_radius"] = max(1, settings["min_radius"])
        settings["max_radius"] = max(settings["min_radius"] + 1, settings["max_radius"])
        settings["min_dist"] = max(1, settings["min_dist"])
        settings["param1"] = max(1, settings["param1"])
        settings["param2"] = max(1, settings["param2"])
        for key, value in settings.items():
            self.setting_vars[key].set(str(value))
        return settings

    def _inspection_settings(self):
        settings = {}
        try:
            for key, var in self.inspection_vars.items():
                settings[key] = int(var.get())
        except ValueError:
            self.show_alert("Pin condition values must be numbers.", "warning")
            return None

        settings["search_radius"] = max(1, settings["search_radius"])
        settings["brightness_min"] = max(0, min(255, settings["brightness_min"]))
        settings["brightness_max"] = max(0, min(255, settings["brightness_max"]))
        if settings["brightness_min"] > settings["brightness_max"]:
            settings["brightness_min"], settings["brightness_max"] = (
                settings["brightness_max"],
                settings["brightness_min"],
            )
        for key, value in settings.items():
            self.inspection_vars[key].set(str(value))
        return settings

    def _normalize_condition(self, condition):
        settings = dict(DEFAULT_INSPECTION)
        settings.update(condition or {})
        settings["search_radius"] = max(1, int(settings["search_radius"]))
        settings["brightness_min"] = max(0, min(255, int(settings["brightness_min"])))
        settings["brightness_max"] = max(0, min(255, int(settings["brightness_max"])))
        if settings["brightness_min"] > settings["brightness_max"]:
            settings["brightness_min"], settings["brightness_max"] = (
                settings["brightness_max"],
                settings["brightness_min"],
            )
        return settings

    def _condition_for_circle(self, circle_id):
        return self._normalize_condition(
            self.circle_conditions.get(int(circle_id), self._inspection_settings() or DEFAULT_INSPECTION)
        )

    def _pin_conditions(self):
        return [self._condition_for_circle(circle_id) for circle_id in self.selected_ids]

    def open_condition_popup(self):
        if not self.selected_ids:
            self.show_alert("Please select at least 1 circle before setting pin conditions.", "warning")
            return
        if len(self.selected_ids) > 5:
            self.show_alert("Please select no more than 5 circles.", "warning")
            return

        popup = tk.Toplevel(self)
        popup.withdraw()
        popup.title("Pin Conditions")
        popup.configure(bg="#ffffff")
        popup.transient(self.winfo_toplevel())
        popup.resizable(False, False)

        frame = tk.Frame(popup, bg="#ffffff", padx=22, pady=20)
        frame.grid(row=0, column=0, sticky="nsew")

        tk.Label(
            frame,
            text="Pin Conditions Per Circle",
            bg="#ffffff",
            fg="#111827",
            font=("Helvetica", 16, "bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))

        tk.Label(
            frame,
            text="Set search radius and brightness range for each selected circle.",
            bg="#ffffff",
            fg="#6b7280",
            font=("Helvetica", 11),
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 18))

        headers = (
            "Circle",
            "Search Radius",
            "Brightness Min",
            "Brightness Max",
        )
        for column, label in enumerate(headers):
            tk.Label(
                frame,
                text=label,
                bg="#ffffff",
                fg="#374151",
                font=("Helvetica", 10, "bold"),
            ).grid(row=2, column=column, sticky="w", pady=(0, 8), padx=(0, 12))

        row_vars = {}
        brightness_vars = {}
        for row, circle_id in enumerate(self.selected_ids, start=3):
            condition = self._condition_for_circle(circle_id)
            row_vars[circle_id] = {
                key: tk.StringVar(value=str(condition[key]))
                for key in ("search_radius", "brightness_min", "brightness_max")
            }
            brightness_vars[circle_id] = tk.StringVar(value=f"#{circle_id}  AVG: Not tested")
            tk.Label(
                frame,
                textvariable=brightness_vars[circle_id],
                bg="#ffffff",
                fg="#111827",
                font=("Helvetica", 12, "bold"),
            ).grid(row=row, column=0, sticky="w", pady=6, padx=(0, 12))

            for column, key in enumerate(("search_radius", "brightness_min", "brightness_max"), start=1):
                tk.Entry(
                    frame,
                    textvariable=row_vars[circle_id][key],
                    width=12,
                    bg="#ffffff",
                    fg="#111827",
                    relief="solid",
                    bd=1,
                    justify="center",
                    font=("Helvetica", 12),
                ).grid(row=row, column=column, sticky="w", pady=6, padx=(0, 12))

        def brightness_done(values, error):
            if not popup.winfo_exists():
                return
            test_brightness_button.configure(state="normal", text="Test Brightness")
            if error is not None:
                self.show_alert(f"Brightness test failed: {error}", "error")
                return
            for circle_id, value in values.items():
                if circle_id in brightness_vars:
                    brightness_vars[circle_id].set(f"#{circle_id}  AVG: {value:.0f}")

        def brightness_worker(image, selected_circles):
            try:
                values = {
                    circle_id: get_circle_brightness(image, (circle[0], circle[1]), circle[2])
                    for circle_id, circle in selected_circles.items()
                }
                self.after(0, lambda: brightness_done(values, None))
            except Exception as exc:
                self.after(0, lambda error=exc: brightness_done({}, error))

        def test_brightness():
            if self.image is None:
                self.show_alert("No setup image available for brightness test.", "warning")
                return
            selected_circles = {
                circle_id: self.circles[circle_id]
                for circle_id in self.selected_ids
                if 0 <= circle_id < len(self.circles)
            }
            if len(selected_circles) != len(self.selected_ids):
                self.show_alert("Please run Process again before testing brightness.", "warning")
                return
            test_brightness_button.configure(state="disabled", text="Calculating...")
            threading.Thread(
                target=brightness_worker,
                args=(self.image.copy(), selected_circles),
                daemon=True,
            ).start()

        def apply_condition():
            try:
                next_conditions = {
                    int(circle_id): self._normalize_condition(
                        {key: var.get() for key, var in vars_by_key.items()}
                    )
                    for circle_id, vars_by_key in row_vars.items()
                }
            except ValueError:
                self.show_alert("Pin condition values must be numbers.", "warning")
                return

            self.circle_conditions.update(next_conditions)
            camera_name = self.camera_var.get()
            config = load_config()
            camera_config = config.get("cameras", {}).get(camera_name)
            saved_ids = list(camera_config.get("selected_circle_ids", [])) if camera_config else []
            if camera_config and saved_ids == list(self.selected_ids):
                camera_config["pin_conditions"] = [
                    self.circle_conditions.get(int(circle_id), self._condition_for_circle(circle_id))
                    for circle_id in camera_config.get("selected_circle_ids", self.selected_ids)
                ]
                save_config(config)
                self.status_var.set(f"Saved pin conditions for {camera_name}.")
            else:
                self.status_var.set(f"Pin conditions ready for {camera_name}. Click Save Setup to store them.")
            popup.destroy()

        buttons = tk.Frame(frame, bg="#ffffff")
        buttons.grid(row=3 + len(self.selected_ids), column=0, columnspan=4, sticky="e", pady=(18, 0))
        test_brightness_button = primary_button(buttons, "Test Brightness", test_brightness)
        test_brightness_button.grid(row=0, column=0, padx=(0, 18))
        secondary_button(buttons, "Cancel", popup.destroy).grid(row=0, column=1, padx=(0, 8))
        success_button(buttons, "Save", apply_condition).grid(row=0, column=2)
        popup.update_idletasks()
        parent_root = self.winfo_toplevel()
        x = parent_root.winfo_rootx() + (parent_root.winfo_width() - popup.winfo_width()) // 2
        y = parent_root.winfo_rooty() + (parent_root.winfo_height() - popup.winfo_height()) // 2
        popup.geometry(f"+{max(0, x)}+{max(0, y)}")
        popup.deiconify()
        popup.lift()
        popup.focus_force()
        popup.grab_set()

    def process_circles(self):
        if self._busy:
            return

        if self.image is None:
            self.load_camera_image()
            return

        settings = self._settings()
        if settings is None:
            return

        image = self.image.copy()
        self._set_busy(True, "Processing circles. Please wait...")
        threading.Thread(
            target=self._process_circles_worker,
            args=(image, settings),
            daemon=True,
        ).start()

    def _process_circles_worker(self, image, settings):
        try:
            circles = detect_circles(image, settings)
            self.after(0, lambda: self._process_circles_done(circles, None))
        except Exception as exc:
            self.after(0, lambda error=exc: self._process_circles_done([], error))

    def _process_circles_done(self, circles, error):
        self._set_busy(False)
        if error is not None:
            self.show_alert(f"Process failed: {error}", "error")
            return

        self.circles = circles
        if not circles:
            self.show_alert("No circles found. Try adjusting circle settings.", "warning")
        self.selected_ids = [idx for idx in self.selected_ids if idx < len(self.circles)]
        self.result_image = None
        self.view_mode = "setup"
        self._invalidate_render_cache()
        self.status_var.set(f"Found {len(self.circles)} circles. Selected {len(self.selected_ids)}.")
        self.render()

    def clear_selection(self):
        if self._busy:
            return

        self.selected_ids = []
        self.result_image = None
        self.view_mode = "setup"
        self._invalidate_render_cache()
        self.status_var.set(f"Found {len(self.circles)} circles. Selected 0.")
        self.render()

    def save_setup(self):
        if self._busy:
            return

        if len(self.selected_ids) < 1:
            self.show_alert("Please select at least 1 circle before saving.", "warning")
            return
        if len(self.selected_ids) > 5:
            self.show_alert("Please select no more than 5 circles.", "warning")
            return

        settings = self._settings()
        if settings is None:
            return
        inspection = self._inspection_settings()
        if inspection is None:
            return

        selected = [self.circles[idx] for idx in self.selected_ids]
        setup = {
            "circle_filter": settings,
            "selected_circle_ids": list(self.selected_ids),
            "expected_pin_holes": selected,
            "template_ref_pos": [selected[0][0], selected[0][1]],
            "inspection": inspection,
            "pin_conditions": self._pin_conditions(),
            "read_qr": bool(self.read_qr_var.get()),
        }

        config = load_config()
        config.setdefault("version", 1)
        config.setdefault("system_mode", SYSTEM_MODE)
        config.setdefault("cameras", {})
        config["cameras"][self.camera_var.get()] = setup
        save_config(config)

        self.status_var.set(f"Saved setup for {self.camera_var.get()}.")
        self.show_result_preview(setup)

    def show_result_preview(self, setup):
        if self.image is None:
            return

        image = self.image.copy()
        self._set_busy(True, "Generating result preview. Please wait...")
        threading.Thread(
            target=self._result_preview_worker,
            args=(image, setup),
            daemon=True,
        ).start()

    def _result_preview_worker(self, image, setup):
        try:
            result_image, _results, pin_passed = inspect_image_with_pin_conditions(image, setup)
            code_text = ""
            if setup.get("read_qr"):
                camera_name = self.camera_var.get()
                try:
                    codes = read_codes_from_image(image)
                except Exception as exc:
                    print(f"[QR ERROR] {camera_name}: {exc}")
                    codes = []
                result_image = draw_code_results(result_image, codes)
                code_text = codes[0]["data"] if codes else "NOT FOUND"
                if not codes:
                    print(f"[QR] {camera_name}: NOT FOUND")
            self.after(
                0,
                lambda: self._result_preview_done(
                    result_image,
                    pin_passed,
                    code_text,
                    bool(setup.get("read_qr")),
                    None,
                ),
            )
        except Exception as exc:
            self.after(
                0,
                lambda error=exc: self._result_preview_done(
                    None,
                    False,
                    "",
                    bool(setup.get("read_qr")),
                    error,
                ),
            )

    def _result_preview_done(self, result_image, pin_passed, code_text, read_qr, error):
        self._set_busy(False)
        if error is not None:
            self.show_alert(f"Result preview failed: {error}", "error")
            return

        self.result_image = result_image
        self.view_mode = "result"
        self._invalidate_render_cache()
        self._reset_view()

        pin_status = "PASS" if pin_passed else "FAIL"
        if read_qr:
            self.status_var.set(f"Saved. Pin {pin_status}. Code: {code_text}.")
            if code_text == "NOT FOUND":
                self.show_alert("No QR/Data Matrix found in image.", "warning")
        else:
            self.status_var.set(f"Saved. Pin {pin_status}. QR/Data Matrix skipped.")
        self.render()

    def on_canvas_click(self, event):
        if self._busy:
            return

        if self.view_mode == "result":
            self.status_var.set("Result preview is showing. Click Process to edit setup again.")
            self.show_alert("Result preview is showing. Click Process to edit setup again.", "warning")
            return
        if self.image is None or not self.circles:
            return

        original = self._screen_to_original(event.x, event.y)
        if original is None:
            return

        ox, oy = original
        nearest_id = min(
            range(len(self.circles)),
            key=lambda idx: (self.circles[idx][0] - ox) ** 2 + (self.circles[idx][1] - oy) ** 2,
        )
        cx, cy, radius = self.circles[nearest_id]
        if (cx - ox) ** 2 + (cy - oy) ** 2 > max(radius * 2, 40) ** 2:
            return

        if nearest_id in self.selected_ids:
            self.selected_ids.remove(nearest_id)
        else:
            if len(self.selected_ids) >= 5:
                self.show_alert("You can select up to 5 circles.", "warning")
                return
            self.selected_ids.append(nearest_id)
            self.circle_conditions.setdefault(nearest_id, self._condition_for_circle(nearest_id))

        self.status_var.set(f"Found {len(self.circles)} circles. Selected {len(self.selected_ids)}.")
        self._invalidate_render_cache()
        self.render()

    def _screen_to_original(self, sx, sy):
        if self.display_image is None:
            return None

        x = sx - self.offset_x
        y = sy - self.offset_y
        if x < 0 or y < 0 or x >= self.display_image.shape[1] or y >= self.display_image.shape[0]:
            return None
        return int(x / self.scale), int(y / self.scale)

    def render(self):
        if self.view_mode == "result" and self.result_image is not None:
            self._render_result()
            return

        if self.image is None:
            self.canvas.delete("all")
            self.canvas.create_text(
                max(1, self.canvas.winfo_width() // 2),
                max(1, self.canvas.winfo_height() // 2),
                text=self.empty_message,
                fill="#6b7280",
                font=("Helvetica", 14, "bold"),
                width=max(200, self.canvas.winfo_width() - 80),
                justify="center",
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

        cache_key = (
            "setup",
            id(self.image),
            render_w,
            render_h,
            round(self.zoom, 4),
            tuple(self.circles),
            tuple(self.selected_ids),
        )
        if cache_key != self._render_cache_key:
            display = cv2.resize(self.image, (render_w, render_h), interpolation=cv2.INTER_AREA)
            selected = set(self.selected_ids)
            for idx, (x, y, radius) in enumerate(self.circles):
                sx = int(x * self.scale)
                sy = int(y * self.scale)
                sr = max(3, int(radius * self.scale))
                color = (37, 99, 235) if idx not in selected else (22, 163, 74)
                thickness = 2 if idx not in selected else 4
                cv2.circle(display, (sx, sy), sr, color, thickness)
                cv2.circle(display, (sx, sy), 3, color, -1)
                cv2.putText(
                    display,
                    str(idx),
                    (sx + sr + 4, sy),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    color,
                    2,
                )

            self.display_image = display
            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            self.photo = ImageTk.PhotoImage(Image.fromarray(rgb))
            self._render_cache_key = cache_key

        self.canvas.delete("all")
        self.canvas.create_image(self.offset_x, self.offset_y, image=self.photo, anchor="nw")
        self.canvas.create_text(
            self.offset_x + 12,
            self.offset_y + 18,
            text=f"Found {len(self.circles)} / Selected {len(self.selected_ids)}",
            fill="#111827",
            anchor="w",
            font=("Helvetica", 12, "bold"),
        )
        self._draw_loading_overlay()
        self._draw_alert_overlay()

    def _render_result(self):
        canvas_w = max(1, self.canvas.winfo_width())
        canvas_h = max(1, self.canvas.winfo_height())
        image_h, image_w = self.result_image.shape[:2]
        self.scale = min(canvas_w / image_w, canvas_h / image_h) * self.zoom
        render_w = max(1, int(image_w * self.scale))
        render_h = max(1, int(image_h * self.scale))
        self.offset_x = (canvas_w - render_w) // 2 + int(self.pan_screen_x)
        self.offset_y = (canvas_h - render_h) // 2 + int(self.pan_screen_y)

        cache_key = (
            "result",
            id(self.result_image),
            render_w,
            render_h,
            round(self.zoom, 4),
        )
        if cache_key != self._render_cache_key:
            display = cv2.resize(self.result_image, (render_w, render_h), interpolation=cv2.INTER_AREA)
            self.display_image = display
            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            self.photo = ImageTk.PhotoImage(Image.fromarray(rgb))
            self._render_cache_key = cache_key

        self.canvas.delete("all")
        self.canvas.create_image(self.offset_x, self.offset_y, image=self.photo, anchor="nw")
        self.canvas.create_text(
            self.offset_x + 12,
            self.offset_y + 18,
            text="Result Preview",
            fill="#111827",
            anchor="w",
            font=("Helvetica", 12, "bold"),
        )
        self._draw_loading_overlay()
        self._draw_alert_overlay()

    def _set_busy(self, busy, message=None):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for button in self.action_buttons:
            button.configure(state=state)
        for button in self.camera_buttons + self.qr_buttons:
            button.configure(state=state)
        if message:
            self.status_var.set(message)
        self.schedule_render(20)
        self.update_idletasks()

    def _reset_view(self):
        self.zoom = 1.0
        self.pan_screen_x = 0
        self.pan_screen_y = 0

    def _on_mousewheel(self, event):
        if self.image is None and self.result_image is None:
            return
        old_zoom = self.zoom
        if event.num == 4 or getattr(event, "delta", 0) > 0:
            self.zoom = min(8.0, self.zoom * 1.2)
        else:
            self.zoom = max(1.0, self.zoom / 1.2)

        factor = self.zoom / old_zoom
        self.pan_screen_x = event.x - (event.x - self.pan_screen_x) * factor
        self.pan_screen_y = event.y - (event.y - self.pan_screen_y) * factor
        self.schedule_render(20)

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
        self.schedule_render(20)

    def _end_drag(self, _event):
        self._drag_start = None

    def _end_left_drag(self, event):
        was_click = not self._drag_moved
        self._end_drag(event)
        if was_click:
            self.on_canvas_click(event)

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
        x2 = x1 + box_w
        y2 = y1 + box_h
        self.canvas.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            fill="#ffffff",
            outline="#d1d5db",
            width=2,
        )
        self.canvas.create_text(
            canvas_w // 2,
            y1 + 32,
            text="Please wait",
            fill="#111827",
            font=("Helvetica", 16, "bold"),
        )
        self.canvas.create_text(
            canvas_w // 2,
            y1 + 58,
            text=self.status_var.get(),
            fill="#4b5563",
            font=("Helvetica", 11),
        )

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
        x2 = x1 + box_w
        y2 = y1 + box_h
        self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=2)
        self.canvas.create_text(
            x1 + 18,
            y1 + box_h // 2,
            text=message,
            fill=text_color,
            anchor="w",
            font=("Helvetica", 12, "bold"),
            width=box_w - 36,
        )
