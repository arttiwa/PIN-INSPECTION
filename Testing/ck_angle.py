import cv2
import numpy as np

def detect_skew_angle(image_path):
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Edge detection
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    # Detect lines using Hough Transform
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180,
        threshold=100,
        minLineLength=100,
        maxLineGap=10
    )

    if lines is None:
        return 0.0  # No lines found, assume no tilt

    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        angles.append(angle)

    # Filter to near-horizontal lines (between -45° and 45°)
    angles = [a for a in angles if -45 < a < 45]

    if not angles:
        return 0.0

    median_angle = np.median(angles)
    return median_angle

def describe_tilt(angle):
    threshold = 0.5  # degrees — ignore tiny wobbles

    if abs(angle) < threshold:
        return f"Image is straight (angle: {angle:.2f}°)"
    elif angle > 0:
        return f"Image is tilted CLOCKWISE by {angle:.2f}°"
    else:
        return f"Image is tilted COUNTER-CLOCKWISE by {abs(angle):.2f}°"

def deskew(image_path, output_path=None):
    img = cv2.imread(image_path)
    angle = detect_skew_angle(image_path)

    print(describe_tilt(angle))

    if abs(angle) < 0.5:
        print("No correction needed.")
        return img

    # Rotate image by the negative of the detected angle
    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)

    rotation_matrix = cv2.getRotationMatrix2D(center, -angle, scale=1.0)
    corrected = cv2.warpAffine(
        img, rotation_matrix, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE  # fill edges with nearby pixels
    )

    if output_path:
        cv2.imwrite(output_path, corrected)
        print(f"Saved corrected image to: {output_path}")

    return corrected

# Run everything
result = deskew("destination\P1-UP-NL1_3.jpg", output_path="destination/P1-P-NL1_1.jpg")

# Or just check the angle first
angle = detect_skew_angle("destination\P1-UP-NL1_3.jpg")
print(describe_tilt(angle))












