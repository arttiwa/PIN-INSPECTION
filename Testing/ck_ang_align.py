import cv2
import numpy as np

def detect_skew_angle(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180,
                             threshold=100, minLineLength=100, maxLineGap=10)
    if lines is None:
        return 0.0
    angles = [np.degrees(np.arctan2(l[0][3]-l[0][1], l[0][2]-l[0][0]))
              for l in lines]
    angles = [a for a in angles if -45 < a < 45]
    return float(np.median(angles)) if angles else 0.0


def deskew(img, angle):
    """Rotate image to fix tilt."""
    (h, w) = img.shape[:2]
    M = cv2.getRotationMatrix2D((w//2, h//2), -angle, 1.0)
    return cv2.warpAffine(img, M, (w, h),
                          flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)
    
    
def detect_alignment(img):
    """
    Finds the bounding box of the main content (e.g. a document or object)
    and measures how far it is offset from the image center.

    Returns:
        offset_x  — pixels shifted right (+) or left (-)
        offset_y  — pixels shifted down (+) or up (-)
        content_rect — (x, y, w, h) of the detected content region
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Threshold to separate content from background
    _, thresh = cv2.threshold(gray, 0, 255,
                               cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Find contours of content regions
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return 0, 0, None

    # Get bounding box that wraps ALL content
    x_min = min(cv2.boundingRect(c)[0] for c in contours)
    y_min = min(cv2.boundingRect(c)[1] for c in contours)
    x_max = max(cv2.boundingRect(c)[0] + cv2.boundingRect(c)[2] for c in contours)
    y_max = max(cv2.boundingRect(c)[1] + cv2.boundingRect(c)[3] for c in contours)

    content_cx = (x_min + x_max) / 2
    content_cy = (y_min + y_max) / 2

    img_h, img_w = img.shape[:2]
    img_cx = img_w / 2
    img_cy = img_h / 2

    offset_x = content_cx - img_cx   # + means content is too far right
    offset_y = content_cy - img_cy   # + means content is too far down

    return offset_x, offset_y, (x_min, y_min, x_max - x_min, y_max - y_min)


def describe_alignment(offset_x, offset_y, threshold=10):
    """Describe alignment issues in human-readable form."""
    issues = []

    if abs(offset_x) < threshold and abs(offset_y) < threshold:
        return "Content is well-centered."

    if offset_x > threshold:
        issues.append(f"shifted RIGHT by {offset_x:.0f}px")
    elif offset_x < -threshold:
        issues.append(f"shifted LEFT by {abs(offset_x):.0f}px")

    if offset_y > threshold:
        issues.append(f"shifted DOWN by {offset_y:.0f}px")
    elif offset_y < -threshold:
        issues.append(f"shifted UP by {abs(offset_y):.0f}px")

    return "Content is " + " and ".join(issues) + "."
    
    
def fix_alignment(img, offset_x, offset_y):
    """
    Shift image so content is centered.
    We move the image in the OPPOSITE direction of the offset.
    """
    if abs(offset_x) < 10 and abs(offset_y) < 10:
        return img  # Already centered, skip

    tx = -offset_x   # translate left/right
    ty = -offset_y   # translate up/down

    M = np.float32([[1, 0, tx],
                    [0, 1, ty]])

    img_h, img_w = img.shape[:2]
    return cv2.warpAffine(img, M, (img_w, img_h),borderMode=cv2.BORDER_REPLICATE)
    
    
    
def full_correction(image_path, output_path="corrected.jpg", angle_threshold=0.5, alignment_threshold=10):

    img = cv2.imread(image_path)

    # --- Step 1: Check and fix angle ---
    angle = detect_skew_angle(img)
    print(f"[Angle]  Detected: {angle:.2f}°")

    if abs(angle) > angle_threshold:
        print(f"[Angle]  Fixing tilt...")
        img = deskew(img, angle)
    else:
        print(f"[Angle]  OK — no rotation needed.")

    # --- Step 2: Check and fix alignment ---
    offset_x, offset_y, rect = detect_alignment(img)
    print(f"[Align]  {describe_alignment(offset_x, offset_y, alignment_threshold)}")
    print(f"[Align]  offset_x={offset_x:.1f}px, offset_y={offset_y:.1f}px")

    if abs(offset_x) > alignment_threshold or abs(offset_y) > alignment_threshold:
        print(f"[Align]  Fixing position...")
        img = fix_alignment(img, offset_x, offset_y)
    else:
        print(f"[Align]  OK — no translation needed.")

    cv2.imwrite(output_path, img)
    print(f"\nSaved to: {output_path}")
    return img


# Run it
full_correction("destination\P1-P-L1_1.jpg", "scan_fixed.jpg")
    
    
    
    
    
    