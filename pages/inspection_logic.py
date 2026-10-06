import cv2

from ck_pin import (
    PinResult,
    draw_results,
    find_circle_near,
    find_reference_hole,
    get_circle_brightness,
)
from pin_inspection_app import detect_circles


ROI_MARGIN = 25


def condition_for_hole(camera_config, index):
    default = camera_config.get("inspection", {})
    conditions = camera_config.get("pin_conditions", [])
    if index < len(conditions):
        merged = dict(default)
        merged.update(conditions[index])
        return merged
    return default


def _crop_bounds(img, center, radius):
    height, width = img.shape[:2]
    cx, cy = int(center[0]), int(center[1])
    radius = max(1, int(radius))
    x1 = max(0, cx - radius)
    y1 = max(0, cy - radius)
    x2 = min(width, cx + radius)
    y2 = min(height, cy + radius)
    return x1, y1, x2, y2


def _detect_circles_near(img, center, radius, settings):
    x1, y1, x2, y2 = _crop_bounds(img, center, radius)
    if x2 <= x1 or y2 <= y1:
        return []

    crop = img[y1:y2, x1:x2]
    circles = detect_circles(crop, settings)
    return [(x + x1, y + y1, r) for x, y, r in circles]


def inspect_image_with_pin_conditions(img, camera_config):
    filter_settings = camera_config["circle_filter"]
    expected_pin_holes = [tuple(item) for item in camera_config["expected_pin_holes"]]
    template_ref_pos = tuple(camera_config["template_ref_pos"])
    default_inspection = camera_config["inspection"]

    max_circle_radius = int(filter_settings.get("max_radius", 80))
    reference_search_radius = int(default_inspection["search_radius"]) * 3
    reference_roi_radius = reference_search_radius + max_circle_radius + ROI_MARGIN
    reference_circles = _detect_circles_near(
        img,
        template_ref_pos,
        reference_roi_radius,
        filter_settings,
    )
    ref_hole = find_reference_hole(
        reference_circles,
        template_ref_pos,
        search_radius=reference_search_radius,
    )
    if ref_hole is None:
        output = img.copy()
        cv2.putText(
            output,
            "FAIL: reference circle not found",
            (20, 45),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 220),
            3,
        )
        return output, [], False

    dx = ref_hole[0] - template_ref_pos[0]
    dy = ref_hole[1] - template_ref_pos[1]
    adjusted_holes = [(x + dx, y + dy, r) for (x, y, r) in expected_pin_holes]

    results = []
    used_positions = []
    for index, (ex, ey, _er) in enumerate(adjusted_holes):
        condition = condition_for_hole(camera_config, index)
        search_radius = int(condition["search_radius"])
        brightness_min = int(condition["brightness_min"])
        brightness_max = int(condition["brightness_max"])

        roi_radius = search_radius + max_circle_radius + ROI_MARGIN
        available = _detect_circles_near(img, (ex, ey), roi_radius, filter_settings)
        available = [
            circle
            for circle in available
            if all((circle[0] - ux) ** 2 + (circle[1] - uy) ** 2 > 9 for ux, uy in used_positions)
        ]
        found_circle, dist = find_circle_near(available, (ex, ey), search_radius)
        if found_circle:
            ax, ay, ar = found_circle
            brightness = get_circle_brightness(img, (ax, ay), ar)
            detected = brightness_min <= brightness <= brightness_max
            if detected:
                used_positions.append((ax, ay))
            results.append(
                PinResult(
                    hole_id=index,
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
                    hole_id=index,
                    expected_position=(ex, ey),
                    detected=False,
                    distance_from_expected=float("inf"),
                )
            )

    passed = all(result.detected for result in results)
    return draw_results(img, results, ref_hole, (dx, dy)), results, passed
