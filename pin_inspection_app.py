import argparse
import datetime
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from ck_pin import (
    PinResult,
    draw_results,
    find_circle_near,
    find_reference_hole,
    get_circle_brightness,
)
from read_qr_code import read_codes_from_image


# ===== User settings =====
# Change to "rasp" on Raspberry Pi if you want different defaults below.
SYSTEM_MODE = "window"
# SYSTEM_MODE = "rasp"

# Start mode when no command line argument is provided: "setup" or "use".
APP_MODE = "setup"

CONFIG_PATH = "inspection_settings.json"
OUTPUT_DIR = "inspection_output"

# Use two cameras by default. Change camera ids here when Pi/PC maps them differently.
CAMERA_SOURCES = {
    "cam0": 0,
    "cam1": 1,
}

# On Windows you can test without real cameras by setting paths here.
# Set a camera image to "" to capture from CAMERA_SOURCES instead.
WINDOW_TEST_IMAGES = {
    "cam0": r"captures/P1-P- (14).jpg",
    "cam1": r"captures/P2-P- (5).jpg",
}

# Raspberry Pi usually captures from real cameras.
RASP_TEST_IMAGES = {
    "cam0": "",
    "cam1": "",
}

CAPTURE_WIDTH = 4056
CAPTURE_HEIGHT = 3040
DISPLAY_MAX_WIDTH = 1280
DISPLAY_MAX_HEIGHT = 800
SETUP_PANEL_WIDTH = 360

DEFAULT_CIRCLE_FILTER = {
    "min_radius": 50,
    "max_radius": 150,
    "min_dist": 100,
    "param1": 60,
    "param2": 30,
}

DEFAULT_INSPECTION = {
    "search_radius": 50,
    "brightness_min": 150,
    "brightness_max": 220,
}


Circle = Tuple[int, int, int]


def ensure_output_dir() -> None:
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)


def load_config() -> Dict:
    path = Path(CONFIG_PATH)
    if not path.is_file():
        return {"version": 1, "system_mode": SYSTEM_MODE, "cameras": {}}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: Dict) -> None:
    with Path(CONFIG_PATH).open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"[SAVE] {CONFIG_PATH}")


def test_image_for(camera_name: str) -> str:
    images = RASP_TEST_IMAGES if SYSTEM_MODE == "rasp" else WINDOW_TEST_IMAGES
    return images.get(camera_name, "")


def capture_image(camera_name: str) -> Optional[np.ndarray]:
    test_path = test_image_for(camera_name)
    if test_path:
        img = cv2.imread(test_path)
        if img is None:
            print(f"[ERROR] Cannot read test image: {test_path}")
        return img

    source = CAMERA_SOURCES[camera_name]
    cap = cv2.VideoCapture(source)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)

    ok, frame = cap.read()
    cap.release()
    if not ok:
        print(f"[ERROR] Cannot capture from {camera_name} source={source}")
        return None
    return frame


def display_scale(img: np.ndarray) -> float:
    h, w = img.shape[:2]
    return min(DISPLAY_MAX_WIDTH / w, DISPLAY_MAX_HEIGHT / h, 1.0)


def resize_for_display(img: np.ndarray) -> Tuple[np.ndarray, float]:
    scale = display_scale(img)
    if scale >= 1.0:
        return img.copy(), 1.0
    return (
        cv2.resize(img, (int(img.shape[1] * scale), int(img.shape[0] * scale))),
        scale,
    )


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))


def detect_circles(img: np.ndarray, settings: Dict) -> List[Circle]:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=max(1, int(settings["min_dist"])),
        param1=int(settings["param1"]),
        param2=max(1, int(settings["param2"])),
        minRadius=max(1, int(settings["min_radius"])),
        maxRadius=max(1, int(settings["max_radius"])),
    )
    if circles is None:
        return []
    result = [(int(x), int(y), int(r)) for x, y, r in circles[0]]
    result.sort(key=lambda c: (c[1] // 30, c[0]))
    return result


def render_setup_view(
    img: np.ndarray,
    circles: List[Circle],
    selected_ids: List[int],
    settings: Dict,
    active_field: Optional[str],
    zoom: float,
    pan_x: float,
    pan_y: float,
) -> Tuple[np.ndarray, Dict, Dict[str, Tuple[int, int, int, int]]]:
    image_w = DISPLAY_MAX_WIDTH
    image_h = DISPLAY_MAX_HEIGHT
    panel_x = image_w
    canvas = np.full((image_h, image_w + SETUP_PANEL_WIDTH, 3), 35, dtype=np.uint8)

    h, w = img.shape[:2]
    fit_scale = min(image_w / w, image_h / h)
    scale = fit_scale * zoom
    view_w = min(w, image_w / scale)
    view_h = min(h, image_h / scale)
    pan_x = clamp(pan_x, 0, max(0, w - view_w))
    pan_y = clamp(pan_y, 0, max(0, h - view_h))

    x1 = int(pan_x)
    y1 = int(pan_y)
    x2 = min(w, int(pan_x + view_w))
    y2 = min(h, int(pan_y + view_h))
    crop = img[y1:y2, x1:x2]
    render_w = max(1, int((x2 - x1) * scale))
    render_h = max(1, int((y2 - y1) * scale))
    view = cv2.resize(crop, (render_w, render_h), interpolation=cv2.INTER_AREA)

    offset_x = (image_w - render_w) // 2
    offset_y = (image_h - render_h) // 2
    canvas[offset_y : offset_y + render_h, offset_x : offset_x + render_w] = view

    selected = set(selected_ids)
    for idx, (x, y, r) in enumerate(circles):
        if x < x1 - r or x > x2 + r or y < y1 - r or y > y2 + r:
            continue
        sx = int(offset_x + (x - x1) * scale)
        sy = int(offset_y + (y - y1) * scale)
        sr = max(2, int(r * scale))
        color = (0, 255, 0) if idx in selected else (0, 180, 255)
        thickness = 4 if idx in selected else 2
        cv2.circle(canvas, (sx, sy), sr, color, thickness)
        cv2.circle(canvas, (sx, sy), 3, color, -1)
        cv2.putText(
            canvas,
            str(idx),
            (sx + sr + 3, sy),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
        )

    cv2.rectangle(canvas, (panel_x, 0), (panel_x + SETUP_PANEL_WIDTH, image_h), (55, 55, 55), -1)
    cv2.putText(canvas, "Circle Setup", (panel_x + 18, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    cv2.putText(canvas, f"Found: {len(circles)}", (panel_x + 18, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (230, 230, 230), 2)
    cv2.putText(canvas, f"Selected: {len(selected_ids)}", (panel_x + 18, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (230, 230, 230), 2)
    cv2.putText(canvas, f"Zoom: {zoom:.2f}x", (panel_x + 18, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (230, 230, 230), 2)

    fields: Dict[str, Tuple[int, int, int, int]] = {}
    labels = [
        ("min_radius", "Min Radius"),
        ("max_radius", "Max Radius"),
        ("param2", "Circle Strict"),
        ("min_dist", "Min Distance"),
    ]
    y = 175
    for key, label in labels:
        cv2.putText(canvas, label, (panel_x + 18, y), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (230, 230, 230), 1)
        rect = (panel_x + 175, y - 24, panel_x + 330, y + 10)
        fields[key] = rect
        color = (255, 210, 80) if active_field == key else (210, 210, 210)
        cv2.rectangle(canvas, rect[:2], rect[2:], (245, 245, 245), -1)
        cv2.rectangle(canvas, rect[:2], rect[2:], color, 2)
        cv2.putText(canvas, str(settings[key]), (rect[0] + 10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (20, 20, 20), 2)
        y += 48

    buttons = {
        "process": (panel_x + 18, 390, panel_x + 160, 435),
        "save": (panel_x + 185, 390, panel_x + 330, 435),
        "clear": (panel_x + 18, 455, panel_x + 160, 500),
        "recapture": (panel_x + 185, 455, panel_x + 330, 500),
    }
    for name, rect in buttons.items():
        fill = (40, 120, 220) if name in ("process", "save") else (90, 90, 90)
        cv2.rectangle(canvas, rect[:2], rect[2:], fill, -1)
        cv2.rectangle(canvas, rect[:2], rect[2:], (220, 220, 220), 1)
        cv2.putText(canvas, name.upper(), (rect[0] + 16, rect[1] + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    help_lines = [
        "Click field, type number",
        "Process: button or p",
        "Save: button or s",
        "Clear: c",
        "Wheel: zoom",
        "Drag image: pan",
        "Click circle: select",
        "q: quit",
    ]
    y = 555
    for line in help_lines:
        cv2.putText(canvas, line, (panel_x + 18, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)
        y += 28

    view_state = {
        "scale": scale,
        "offset_x": offset_x,
        "offset_y": offset_y,
        "x1": x1,
        "y1": y1,
        "render_w": render_w,
        "render_h": render_h,
        "image_w": image_w,
        "image_h": image_h,
        "pan_x": pan_x,
        "pan_y": pan_y,
    }
    controls = {**fields, **buttons}
    return canvas, view_state, controls


def select_circles_ui(camera_name: str, img: np.ndarray) -> Optional[Dict]:
    window = f"setup {camera_name}"
    cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)

    settings = dict(DEFAULT_CIRCLE_FILTER)
    selected_ids: List[int] = []
    circles: List[Circle] = []
    active_field: Optional[str] = None
    zoom = 1.0
    pan_x = 0.0
    pan_y = 0.0
    view_state: Dict = {}
    controls: Dict[str, Tuple[int, int, int, int]] = {}
    drag_start: Optional[Tuple[int, int, float, float]] = None
    drag_moved = False

    def point_in_rect(px: int, py: int, rect: Tuple[int, int, int, int]) -> bool:
        return rect[0] <= px <= rect[2] and rect[1] <= py <= rect[3]

    def screen_to_original(px: int, py: int) -> Optional[Tuple[int, int]]:
        if not view_state:
            return None
        ox = px - view_state["offset_x"]
        oy = py - view_state["offset_y"]
        if ox < 0 or oy < 0 or ox >= view_state["render_w"] or oy >= view_state["render_h"]:
            return None
        return (
            int(view_state["x1"] + ox / view_state["scale"]),
            int(view_state["y1"] + oy / view_state["scale"]),
        )

    def select_nearest_circle(px: int, py: int) -> None:
        nonlocal selected_ids
        original = screen_to_original(px, py)
        if original is None or not circles:
            return
        ox, oy = original
        nearest_id = min(
            range(len(circles)),
            key=lambda i: (circles[i][0] - ox) ** 2 + (circles[i][1] - oy) ** 2,
        )
        cx, cy, cr = circles[nearest_id]
        if (cx - ox) ** 2 + (cy - oy) ** 2 <= max(cr * 2, 40) ** 2:
            if nearest_id in selected_ids:
                selected_ids.remove(nearest_id)
            else:
                selected_ids.append(nearest_id)

    def run_process() -> None:
        nonlocal circles, selected_ids
        settings["min_radius"] = max(1, int(settings["min_radius"]))
        settings["max_radius"] = max(settings["min_radius"] + 1, int(settings["max_radius"]))
        settings["param2"] = max(1, int(settings["param2"]))
        settings["min_dist"] = max(1, int(settings["min_dist"]))
        print(f"[PROCESS] {camera_name} circle settings: {settings}")
        circles = detect_circles(img, settings)
        selected_ids = [i for i in selected_ids if i < len(circles)]

    def on_mouse(event, x, y, flags, param) -> None:
        nonlocal active_field, zoom, pan_x, pan_y, drag_start, drag_moved

        if event == cv2.EVENT_MOUSEWHEEL:
            old_zoom = zoom
            zoom = clamp(zoom * (1.2 if flags > 0 else 1 / 1.2), 1.0, 8.0)
            original = screen_to_original(x, y)
            if original is not None and view_state:
                ox, oy = original
                pan_x = ox - (x - view_state["offset_x"]) / (view_state["scale"] * (zoom / old_zoom))
                pan_y = oy - (y - view_state["offset_y"]) / (view_state["scale"] * (zoom / old_zoom))
            return

        if event == cv2.EVENT_LBUTTONDOWN:
            for name, rect in controls.items():
                if point_in_rect(x, y, rect):
                    if name in settings:
                        active_field = name
                    elif name == "process":
                        run_process()
                    elif name == "clear":
                        selected_ids.clear()
                    elif name == "recapture":
                        param["action"] = "recapture"
                    elif name == "save":
                        param["action"] = "save"
                    return
            active_field = None
            drag_start = (x, y, pan_x, pan_y)
            drag_moved = False

        elif event == cv2.EVENT_MOUSEMOVE and drag_start is not None:
            sx, sy, start_pan_x, start_pan_y = drag_start
            dx = x - sx
            dy = y - sy
            if abs(dx) > 4 or abs(dy) > 4:
                drag_moved = True
                pan_x = start_pan_x - dx / view_state["scale"]
                pan_y = start_pan_y - dy / view_state["scale"]

        elif event == cv2.EVENT_LBUTTONUP and drag_start is not None:
            if not drag_moved:
                select_nearest_circle(x, y)
            drag_start = None

    mouse_state: Dict[str, str] = {}
    cv2.setMouseCallback(window, on_mouse, mouse_state)
    run_process()

    while True:
        display_img, view_state, controls = render_setup_view(
            img, circles, selected_ids, settings, active_field, zoom, pan_x, pan_y
        )
        pan_x = view_state["pan_x"]
        pan_y = view_state["pan_y"]
        cv2.imshow(window, display_img)

        if mouse_state.get("action") == "recapture":
            cv2.destroyWindow(window)
            return {"recapture": True}
        if mouse_state.get("action") == "save":
            key = ord("s")
            mouse_state.clear()
        else:
            key = cv2.waitKey(30) & 0xFF

        if key == ord("q"):
            cv2.destroyWindow(window)
            return None
        if key == ord("p"):
            run_process()
        if key == ord("c"):
            selected_ids = []
        if key == ord("r"):
            cv2.destroyWindow(window)
            return {"recapture": True}
        if active_field and key in (8, 127):
            value = str(settings[active_field])
            settings[active_field] = int(value[:-1] or "0")
        elif active_field and ord("0") <= key <= ord("9"):
            value = str(settings[active_field])
            if value == "0":
                value = ""
            settings[active_field] = int((value + chr(key))[:4])
        elif key in (13, 10):
            active_field = None
        if key == ord("s"):
            if len(selected_ids) < 3:
                print("[SETUP] Select at least 3 circles before saving.")
                continue
            selected = [circles[i] for i in selected_ids]
            cv2.destroyWindow(window)
            return {
                "circle_filter": settings,
                "selected_circle_ids": selected_ids,
                "expected_pin_holes": selected,
                "template_ref_pos": [selected[0][0], selected[0][1]],
                "inspection": dict(DEFAULT_INSPECTION),
            }


def inspect_image(img: np.ndarray, camera_config: Dict) -> Tuple[np.ndarray, List[PinResult], bool]:
    filter_settings = camera_config["circle_filter"]
    inspection = camera_config["inspection"]
    expected_pin_holes = [tuple(item) for item in camera_config["expected_pin_holes"]]
    template_ref_pos = tuple(camera_config["template_ref_pos"])

    all_circles = detect_circles(img, filter_settings)
    ref_hole = find_reference_hole(
        all_circles,
        template_ref_pos,
        search_radius=inspection["search_radius"] * 3,
    )
    if ref_hole is None:
        output = img.copy()
        cv2.putText(output, "FAIL: reference circle not found", (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 220), 3)
        return output, [], False

    dx = ref_hole[0] - template_ref_pos[0]
    dy = ref_hole[1] - template_ref_pos[1]
    adjusted_holes = [(x + dx, y + dy, r) for (x, y, r) in expected_pin_holes]

    results: List[PinResult] = []
    used_circles = set()
    for i, (ex, ey, _er) in enumerate(adjusted_holes):
        available = [c for j, c in enumerate(all_circles) if j not in used_circles]
        found_circle, dist = find_circle_near(
            available,
            (ex, ey),
            inspection["search_radius"],
        )
        if found_circle:
            ax, ay, ar = found_circle
            brightness = get_circle_brightness(img, (ax, ay), ar)
            detected = inspection["brightness_min"] <= brightness <= inspection["brightness_max"]
            if detected:
                used_circles.add(all_circles.index(found_circle))
            results.append(
                PinResult(
                    hole_id=i,
                    expected_position=(ex, ey),
                    detected=detected,
                    actual_position=(ax, ay),
                    actual_radius=ar,
                    distance_from_expected=dist,
                    brightness=brightness,
                )
            )
        else:
            results.append(
                PinResult(
                    hole_id=i,
                    expected_position=(ex, ey),
                    detected=False,
                    distance_from_expected=float("inf"),
                )
            )

    passed = all(r.detected for r in results)
    return draw_results(img, results, ref_hole, (dx, dy)), results, passed


def draw_code_results(img: np.ndarray, codes: List[Dict]) -> np.ndarray:
    output = img.copy()
    if not codes:
        cv2.putText(output, "CODE NOT FOUND", (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 220), 3)
        return output

    for code in codes:
        points = code.get("points")
        if points:
            pts = np.array(points, dtype=np.int32)
            cv2.polylines(output, [pts], True, (0, 0, 255), 4)
            x, y = pts[:, 0].min(), pts[:, 1].max()
        else:
            x, y = 20, 80
        label = f"{code.get('format', 'Code')}: {code['data']}"
        cv2.putText(output, label, (int(x), int(y) + 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 3)
    return output


def show_image(window: str, img: np.ndarray) -> int:
    display_img, _ = resize_for_display(img)
    cv2.imshow(window, display_img)
    return cv2.waitKey(0) & 0xFF


def ask_yes_no(window: str, img: np.ndarray, prompt: str) -> bool:
    output = img.copy()
    cv2.putText(output, prompt, (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 3)
    cv2.putText(output, "y=yes  n=no", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 3)
    while True:
        key = show_image(window, output)
        if key == ord("y"):
            return True
        if key == ord("n"):
            return False


def save_result_image(camera_name: str, img: np.ndarray, suffix: str) -> str:
    ensure_output_dir()
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(OUTPUT_DIR) / f"{camera_name}_{suffix}_{ts}.jpg"
    cv2.imwrite(str(path), img)
    return str(path)


def setup_camera(camera_name: str, config: Dict) -> None:
    while True:
        img = capture_image(camera_name)
        if img is None:
            return
        setup = select_circles_ui(camera_name, img)
        if setup is None:
            return
        if setup.get("recapture"):
            continue

        preview, _results, passed = inspect_image(img, setup)
        read_code = ask_yes_no(f"pin result {camera_name}", preview, "Read QR/Data Matrix for this camera?")
        setup["read_qr"] = read_code

        if read_code:
            while True:
                codes = read_codes_from_image(img)
                code_img = draw_code_results(img, codes)
                key = show_image(f"code result {camera_name}", code_img)
                if codes:
                    break
                if key == ord("r"):
                    img = capture_image(camera_name)
                    if img is None:
                        break
                elif key == ord("f"):
                    continue
                elif key == ord("n"):
                    break
                else:
                    break

        config["cameras"][camera_name] = setup
        save_config(config)
        save_result_image(camera_name, preview, "setup_pin")
        print(f"[SETUP] {camera_name} saved. pin_pass={passed}")
        return


def run_setup() -> None:
    config = load_config()
    config.setdefault("cameras", {})
    for camera_name in CAMERA_SOURCES:
        setup_camera(camera_name, config)
    cv2.destroyAllWindows()


def run_use() -> None:
    config = load_config()
    for camera_name, camera_config in config.get("cameras", {}).items():
        img = capture_image(camera_name)
        if img is None:
            continue

        result_img, _results, pin_passed = inspect_image(img, camera_config)
        code_text = ""
        if camera_config.get("read_qr"):
            codes = read_codes_from_image(img)
            result_img = draw_code_results(result_img, codes)
            code_text = codes[0]["data"] if codes else "NOT FOUND"

        status = "PASS" if pin_passed else "FAIL"
        cv2.putText(result_img, f"{camera_name} {status} {code_text}", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 0) if pin_passed else (0, 0, 220), 3)
        path = save_result_image(camera_name, result_img, "result")
        print(f"[RESULT] {camera_name}: pin={status} code={code_text} image={path}")
        show_image(f"result {camera_name}", result_img)
    cv2.destroyAllWindows()


def main() -> int:
    parser = argparse.ArgumentParser(description="Two-camera pin inspection setup/use app.")
    parser.add_argument("--mode", choices=["setup", "use"], default=APP_MODE)
    args = parser.parse_args()

    if args.mode == "setup":
        run_setup()
    else:
        run_use()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
