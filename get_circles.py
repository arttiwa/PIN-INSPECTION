import cv2
import numpy as np
import json

def detect_and_label_all_circles(image_path, output_path="circles_labeled.jpg"):
    """
    ตรวจหาทุก circle ในภาพ แสดงหมายเลข และ print ข้อมูลทั้งหมด
    ใช้สำหรับ calibration ครั้งแรก เพื่อหาตำแหน่ง pin holes
    """
    img = cv2.imread(image_path)
    if img is None:
        print(f"ไม่พบไฟล์: {image_path}")
        return []

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # blur นิดหน่อยเพื่อลด noise จากรูเล็กๆ บน sheet บางๆ
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # หา circles — ปรับ minRadius / maxRadius ตามขนาดจริงในภาพ
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=100,          # ระยะห่างขั้นต่ำระหว่าง circle (pixel)
        param1=60,           # Canny edge threshold
        param2=30,           # ยิ่งต่ำ = ยิ่งหาได้เยอะ (แต่อาจ false positive)
        minRadius=15,         # ขนาดเล็กสุด (pixel) — ปรับตามภาพ
        maxRadius=80         # ขนาดใหญ่สุด (pixel) — ปรับตามภาพ
    )

    if circles is None:
        print("ไม่พบ circle ใดๆ — ลองปรับ minRadius/maxRadius หรือ param2")
        return []

    # เรียงจากซ้ายบนไปขวาล่าง (อ่านง่ายขึ้น)
    circle_list = [(int(x), int(y), int(r)) for x, y, r in circles[0]]
    circle_list.sort(key=lambda c: (c[1] // 30, c[0]))  # เรียงตาม row แล้ว column

    output = img.copy()

    print("=" * 55)
    print(f"  พบทั้งหมด {len(circle_list)} circles")
    print("=" * 55)
    print(f"  {'ID':>3}  {'center_x':>9}  {'center_y':>9}  {'radius':>7}")
    print("-" * 55)

    for i, (x, y, r) in enumerate(circle_list):

        # สีสลับกัน เพื่อให้อ่านง่ายเมื่อ circles อยู่ใกล้กัน
        color = (0, 180, 255) if i % 2 == 0 else (255, 100, 0)

        if i == 83:  # ตัวอย่าง circle ที่ต้องการเน้น
            color = (0, 0, 0)  # สีเขียวสดใส
        
        # วาด circle
        cv2.circle(output, (x, y), r, color, 2)

        # วาด dot ตรงกลาง
        cv2.circle(output, (x, y), 3, color, -1)

        # วาดหมายเลข — ถ้า circle ใหญ่พอ วางไว้ตรงกลาง ถ้าเล็กวางไว้ด้านบน
        label = str(i)
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.45
        thickness = 1
        (tw, th), _ = cv2.getTextSize(label, font, font_scale, thickness)

        if r > 14:
            # วางตัวเลขตรงกลาง circle
            tx = x - tw // 2
            ty = y + th // 2
        else:
            # วางตัวเลขไว้เหนือ circle
            tx = x - tw // 2
            ty = y - r - 5

        # พื้นหลังสีขาวให้ตัวเลขอ่านง่าย
        cv2.rectangle(output,
                      (tx - 2, ty - th - 2),
                      (tx + tw + 2, ty + 2),
                      (255, 255, 255), -1)
        cv2.putText(output, label, (tx, ty),
                    font, font_scale, (0, 0, 0), thickness)

        print(f"  {i:>3}  {x:>9}  {y:>9}  {r:>7}")

    print("=" * 55)

    # print โค้ดที่ copy ไปใช้ได้เลย
    print("\n# --- copy โค้ดด้านล่างไปใส่ใน EXPECTED_PIN_HOLES ---\n")
    print("EXPECTED_PIN_HOLES = [")
    for i, (x, y, r) in enumerate(circle_list):
        print(f"    ({x:4d}, {y:4d}, {r:3d}),  # circle #{i}")
    print("]\n")

    # export เป็น JSON ด้วย เผื่อใช้ทีหลัง
    json_data = [{"id": i, "x": x, "y": y, "radius": r}
                 for i, (x, y, r) in enumerate(circle_list)]
    json_path = output_path.replace(".jpg", "_circles.json")
    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2)

    cv2.imwrite(output_path, output)
    print(f"บันทึกภาพที่: {output_path}")
    print(f"บันทึก JSON ที่: {json_path}")

    return circle_list


# ใช้งาน
circles = detect_and_label_all_circles("destination\P4-P-NL1_1.jpg", output_path="get_circles/circles_labeled_P4.jpg")