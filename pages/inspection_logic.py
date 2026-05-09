import cv2

from ck_pin import (
    PinResult,
    draw_results,
    find_circle_near,
    find_reference_hole,
    get_circle_brightness,
)
from pin_inspection_app import detect_circles


def condition_for_hole(camera_config, index):
    default = camera_config.get("inspection", {})
    conditions = camera_config.get("pin_conditions", [])
    if index < len(conditions):
        merged = dict(default)
        merged.update(conditions[index])
        return merged
    return default


def inspect_image_with_pin_conditions(img, camera_config):
    filter_settings = camera_config["circle_filter"]
    expected_pin_holes = [tuple(item) for item in camera_config["expected_pin_holes"]]
    template_ref_pos = tuple(camera_config["template_ref_pos"])
    default_inspection = camera_config["inspection"]

    all_circles = detect_circles(img, filter_settings)
    ref_hole = find_reference_hole(
        all_circles,
        template_ref_pos,
        search_radius=default_inspection["search_radius"] * 3,
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
    used_circles = set()
    for index, (ex, ey, _er) in enumerate(adjusted_holes):
        condition = condition_for_hole(camera_config, index)
        search_radius = int(condition["search_radius"])
        brightness_min = int(condition["brightness_min"])
        brightness_max = int(condition["brightness_max"])

        available = [circle for circle_index, circle in enumerate(all_circles) if circle_index not in used_circles]
        found_circle, dist = find_circle_near(available, (ex, ey), search_radius)
        if found_circle:
            ax, ay, ar = found_circle
            brightness = get_circle_brightness(img, (ax, ay), ar)
            detected = brightness_min <= brightness <= brightness_max
            if detected:
                used_circles.add(all_circles.index(found_circle))
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
