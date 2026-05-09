import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Optional
import datetime

@dataclass
class PinResult:
    hole_id: int
    expected_position: Tuple[int, int]
    detected: bool
    actual_position: Optional[Tuple[int, int]] = None
    actual_radius: int = 0
    distance_from_expected: float = 0.0
    brightness: float = 0.0          # เพิ่ม field นี้
    
def find_all_circles(img, min_radius=15, max_radius=80):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT,
        dp=1, minDist=30,
        param1=60, param2=30,
        minRadius=min_radius, maxRadius=max_radius
    )
    if circles is None:
        return []
    return [(int(x), int(y), int(r)) for x, y, r in circles[0]]

    
    
    
def find_reference_hole(all_circles, template_ref_pos, search_radius=160):
    if not all_circles:
        print("[REF ERROR] ไม่มี circle เลยในภาพ")
        return None

    rx, ry = template_ref_pos
    print(f"\n[REF DEBUG] กำลังหา reference ที่ ({rx}, {ry})  search_radius={search_radius}")
    print(f"{'rank':>5}  {'circle pos':>16}  {'dist':>8}  {'in range?'}")
    print("-" * 50)

    # เรียงทุก circle ตามระยะห่างจาก template_ref_pos
    sorted_circles = sorted(
        all_circles,
        key=lambda c: np.sqrt((c[0] - rx)**2 + (c[1] - ry)**2)
    )

    for i, (cx, cy, cr) in enumerate(sorted_circles[:10]):  # แสดง 10 อันที่ใกล้สุด
        dist = np.sqrt((cx - rx)**2 + (cy - ry)**2)
        in_range = "YES <--" if dist <= search_radius else "no"
        print(f"{i+1:>5}  ({cx:5d}, {cy:5d}, r={cr:3d})  {dist:>8.1f}  {in_range}")

    # หาตัวที่ใกล้สุดและอยู่ใน range
    best = sorted_circles[0]
    best_dist = np.sqrt((best[0] - rx)**2 + (best[1] - ry)**2)

    print(f"\n[REF DEBUG] ที่ใกล้สุดคือ ({best[0]}, {best[1]}, r={best[2]})  dist={best_dist:.1f}")

    if best_dist > search_radius:
        print(f"[REF ERROR] ใกล้สุดยังห่าง {best_dist:.0f}px > search_radius {search_radius}px")
        print(f"[REF ERROR] template_ref_pos=({rx},{ry}) อาจผิด หรือภาพนี้ต่างจาก calibration มาก")
        return None

    print(f"[REF DEBUG] พบแล้ว!")
    return best

def find_circle_near(all_circles, expected_pos, search_radius=40):
    """
    หา circle ที่อยู่ใกล้ expected_pos มากที่สุด
    ถ้าไม่มีอะไรอยู่ในระยะ search_radius เลย = ไม่มี pin

    คืนค่า (circle, distance) หรือ (None, inf)
    """
    ex, ey = expected_pos
    best = None
    best_dist = float('inf')

    for (x, y, r) in all_circles:
        dist = np.sqrt((x - ex)**2 + (y - ey)**2)
        if dist < best_dist and dist <= search_radius:
            best_dist = dist
            best = (x, y, r)

    return best, best_dist if best else float('inf')
  



def get_circle_brightness(img, center, radius):
    """วัด mean brightness ภายใน circle"""
    x, y = center
    h, w = img.shape[:2]

    x1, y1 = max(0, x - radius), max(0, y - radius)
    x2, y2 = min(w, x + radius), min(h, y + radius)

    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0

    gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    # mask เฉพาะวงกลม
    mask = np.zeros(gray_roi.shape, dtype=np.uint8)
    cx_local = x - x1
    cy_local = y - y1
    cv2.circle(mask, (cx_local, cy_local), radius, 255, -1)

    return cv2.mean(gray_roi, mask=mask)[0]

def draw_results(img, results, ref_hole, offset):
    output = img.copy()
    dx, dy = offset

    if ref_hole:
        rx, ry, rr = ref_hole
        cv2.circle(output, (rx, ry), rr, (255, 200, 0), 3)
        cv2.putText(output, f"REF offset({dx:+d},{dy:+d})",
                    (rx + rr + 5, ry), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (255, 200, 0), 2)

    for r in results:
        ex, ey = r.expected_position

        if r.detected:
            ax, ay = r.actual_position
            cv2.drawMarker(output, (ex, ey), (150, 150, 150), cv2.MARKER_CROSS, 20, 1)
            cv2.circle(output, (ax, ay), r.actual_radius, (0, 200, 0), 5)  # 5 = thickness ,base 2
            cv2.circle(output, (ax, ay), 4, (0, 200, 0), -1)
            cv2.line(output, (ex, ey), (ax, ay), (0, 200, 0), 1)
            cv2.putText(output, f"#{r.hole_id} OK",
                        (ax + r.actual_radius + 3, ay),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 0), 1)
        else:
            # แยกสีตามสาเหตุ: แดง = no circle, ส้ม = circle เจอแต่ brightness ผิด
            if r.actual_position:
                # เจอ circle แต่ brightness ผิด (PCB หรือสว่างเกิน)
                color = (0, 140, 255)  # ส้ม
                ax, ay = r.actual_position
                cv2.circle(output, (ax, ay), r.actual_radius, color, 2)
                cv2.putText(output, f"#{r.hole_id} NO PIN",
                            (ax + r.actual_radius + 3, ay),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            else:
                # ไม่เจอ circle เลย
                color = (0, 0, 220)   # แดง
                cv2.drawMarker(output, (ex, ey), color,
                               cv2.MARKER_TILTED_CROSS, 30, 2)
                cv2.putText(output, f"#{r.hole_id} MISSING",
                            (ex + 18, ey + 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    missing = [r for r in results if not r.detected]
    summary = f"PASS {len(results)-len(missing)}/{len(results)}"
    if missing:
        summary += f"  FAIL: {[r.hole_id for r in missing]}"
    cv2.putText(output, summary, (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                (0, 200, 0) if not missing else (0, 0, 220), 2)

    return output




def inspect_sheet(image_path,
                  template_ref_pos,
                  expected_pin_holes,
                  search_radius=40,       # รัศมีค้นหารอบแต่ละ expected point
                  output_path="result.jpg",
                  brigh_min=150,
                  brigh_max=220):
    """
    template_ref_pos  : (x, y) ตำแหน่ง reference hole จาก calibration image
    expected_pin_holes: [(x, y, r), ...] จาก calibration image
    search_radius     : ระยะสูงสุดที่ยอมรับว่า "circle นี้คือ pin ที่ตำแหน่งนั้น"
    """
    img = cv2.imread(image_path)
    if img is None:
        print(f"ไม่พบไฟล์: {image_path}")
        return [], False

    h, w = img.shape[:2]
    print(f"[Image] {w}x{h}")

    # 1. หาทุก circle ในภาพ
    all_circles = find_all_circles(img)
    print(f"[Circles] detect ได้ {len(all_circles)} circles")

    # 2. หา reference hole แล้วคำนวณ offset
    ref_hole = find_reference_hole(all_circles, template_ref_pos)
    if ref_hole is None:
        print("[ERROR] หา reference hole ไม่เจอ")
        return [], False

    dx = ref_hole[0] - template_ref_pos[0]
    dy = ref_hole[1] - template_ref_pos[1]
    print(f"[Ref] detected=({ref_hole[0]},{ref_hole[1]})  offset=({dx:+d},{dy:+d})")

    # 3. เลื่อน expected positions ตาม offset
    adjusted_holes = [(x + dx, y + dy, r) for (x, y, r) in expected_pin_holes]

    # 4. สำหรับแต่ละ expected hole — หา circle จริงที่ใกล้ที่สุด

    print(f"\n{'ID':>4}  {'expected':>14}  {'actual':>14}  "
          f"{'dist':>6}  {'bright':>7}  status")
    print("-" * 72)

    results = []
    used_circles = set()

    for i, (ex, ey, er) in enumerate(adjusted_holes):

        available = [c for j, c in enumerate(all_circles)if j not in used_circles]
        found_circle, dist = find_circle_near(available, (ex, ey), search_radius)

        if found_circle:
            ax, ay, ar = found_circle

            # ตรวจ brightness
            brightness = get_circle_brightness(img, (ax, ay), ar)
            is_valid_hole = brigh_min <= brightness <= brigh_max

            if is_valid_hole:
                # brightness ปกติ = เป็นหลุมจริง = มี pin
                idx = all_circles.index(found_circle)
                used_circles.add(idx)

                results.append(PinResult(
                    hole_id=i,
                    expected_position=(ex, ey),
                    detected=True,
                    actual_position=(ax, ay),
                    actual_radius=ar,
                    distance_from_expected=dist
                ))
                print(f"{i:>4}  ({ex:5d},{ey:5d})  ({ax:5d},{ay:5d})  "
                      f"{dist:>6.1f}  {brightness:>7.1f}  OK")
            else:
                # brightness ผิดปกติ = เป็นพื้น PCB ไม่ใช่หลุม
                reason = "too dark (PCB)" if brightness < brigh_min \
                         else "too bright"
                results.append(PinResult(
                    hole_id=i,
                    expected_position=(ex, ey),
                    detected=False,
                    actual_position=(ax, ay),   # เก็บไว้ให้ draw_results วาดสีส้มได้
                    actual_radius=ar,
                    distance_from_expected=dist,
                    brightness=brightness
                ))
                print(f"{i:>4}  ({ex:5d},{ey:5d})  ({ax:5d},{ay:5d})  "
                      f"{dist:>6.1f}  {brightness:>7.1f}  NO PIN ({reason})")
        else:
            results.append(PinResult(
                hole_id=i,
                expected_position=(ex, ey),
                detected=False,
                distance_from_expected=float('inf')
            ))
            print(f"{i:>4}  ({ex:5d},{ey:5d})  {'---':>14}  "
                  f"{'inf':>6}  {'---':>7}  MISSING (no circle)")
            
    # 5. สรุป
    missing = [r for r in results if not r.detected]
    print(f"\n{'='*60}")
    print(f"ตรวจ {len(results)} หลุม  →  "
          f"OK: {len(results)-len(missing)}  MISSING: {len(missing)}")
    if missing:
        print(f"หลุมที่ไม่มี pin: {[r.hole_id for r in missing]}")
    print(f"{'='*60}")

    # 6. วาดผลลัพธ์
    output_img = draw_results(img, results, ref_hole, (dx, dy))
    cv2.imwrite(output_path, output_img)
    print(f"\nบันทึกภาพที่: {output_path}")

    return results, len(missing) == 0




# p5 = destination\test2\capture_cam1_7.jpg
MODEEE = "P1"
TYPEE = "P"
NUM = " (3)"

# global parameters (ปรับได้ตามแต่ละรุ่น)
date_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

BRIGHTNESS_MIN = 150
BRIGHTNESS_MAX = 220
TEMPLATE_REF_POS = (10, 10)
EXPECTED_PIN_HOLES = []
IMG_PATH = f"destination\\test1\\{MODEEE}-{TYPEE}-{NUM}.jpg"
OUTPUT_PATH = f"result_{MODEEE}_{TYPEE}_{date_time}.jpg"

if MODEEE == "P5":
    IMG_PATH = f"destination\\test2\\capture_cam1_7.jpg"
    OUTPUT_PATH = f"result_P5_P_{date_time}.jpg"





if MODEEE == "P1":
    # P1-P-NL1_1.jpg
    EXPECTED_PIN_HOLES = [
        (3580, 1467,  64),  # circle #70
        (3883, 1766,  49),  # circle #85
        (3481, 1783,  61),  # circle #89 * * *
        (3380, 2015,  62),  # circle #98
    ]
    TEMPLATE_REF_POS = (3481, 1783)
    
    BRIGHTNESS_MIN = 150
    BRIGHTNESS_MAX = 220
       
elif MODEEE == "P2":
    # P2-P-NL1_1.jpg
    EXPECTED_PIN_HOLES = [
        (3792,  602,  47),  # circle #14
        (3791,  996,  34),  # circle #33
        (3494, 1171,  63),  # circle #40
        (3719, 1275,  62),  # circle #45 ***
        (3039, 1651,  65),  # circle #53
    ]
    TEMPLATE_REF_POS = (3719, 1275)
    
    BRIGHTNESS_MIN = 150
    BRIGHTNESS_MAX = 225

elif MODEEE == "P3":
    # P3-P-NL1_1.jpg
    EXPECTED_PIN_HOLES = [
        (3407, 1387,  66),  # circle #46
        (2630, 1637,  48),  # circle #49
        (3309, 1708,  64),  # circle #51 * * *
        (3209, 1939,  79),  # circle #62
    ]
    TEMPLATE_REF_POS = (3309, 1708)
    
    BRIGHTNESS_MIN = 150
    BRIGHTNESS_MAX = 220

elif MODEEE == "P4":
    # P4-P-NL1_1.jpg
    EXPECTED_PIN_HOLES = [
        (1957,  907,  65),  # circle #21
        (3607,  870,  47),  # circle #19
        (3319, 1448,  65),  # circle #48
        (3548, 1547,  63),  # circle #52 * * *
        (2867, 1940,  66),  # circle #61
    ]
    TEMPLATE_REF_POS = (3548, 1547)
    
    BRIGHTNESS_MIN = 150
    BRIGHTNESS_MAX = 220

elif MODEEE == "P5":
    # P5-P-NL1_1.jpg
    EXPECTED_PIN_HOLES = [
        (2915,  494,  41),  # circle #8
        (2666, 1004,  62),  # circle #26
        (2872, 1082,  54),  # circle #28 ****
        (2288, 1433,  56),  # circle #35
    ]
    TEMPLATE_REF_POS = (2872, 1082)
    
    BRIGHTNESS_MIN = 150
    BRIGHTNESS_MAX = 220
    
# [Image] 4056x3040
# [Circles] detect ได้ 144 circles
# [ERROR] หา reference hole ไม่เจอ


if __name__ == "__main__":
    results, passed = inspect_sheet(
        image_path=IMG_PATH,
        template_ref_pos=TEMPLATE_REF_POS,
        expected_pin_holes=EXPECTED_PIN_HOLES,
        search_radius=50,    # ปรับถ้า circle จริงขยับเยอะ
        output_path=OUTPUT_PATH,
        brigh_min=BRIGHTNESS_MIN,
        brigh_max=BRIGHTNESS_MAX
    )






