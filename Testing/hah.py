import cv2
import os
from tkinter import Tk, filedialog

import numpy as np

# -----------------------------
# Select folder using tkinter
# -----------------------------
root = Tk()
root.withdraw()

screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()

folder_path = filedialog.askdirectory(title="Select a Folder with Images")

if not folder_path:
    print("No folder selected.")
    root.destroy()
    exit()

# -----------------------------
# Load image file list
# -----------------------------
image_files = [
    f for f in os.listdir(folder_path)
    if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".gif"))
]

if not image_files:
    print("No images found in the selected folder.")
    root.destroy()
    exit()

image_files.sort()
current_index = 0

# -----------------------------
# Create ONE window only
# -----------------------------
window_name = "Image Viewer"
new_width = int(screen_width * 0.9)
new_height = int(screen_height * 0.9)

cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
cv2.resizeWindow(window_name, new_width, new_height)

def resize_keep_ratio(image, max_width, max_height):
    h, w = image.shape[:2]

    # scale ratio (keep aspect)
    scale = min(max_width / w, max_height / h)

    new_w = int(w * scale)
    new_h = int(h * scale)

    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return resized

while True:
    image_path = os.path.join(folder_path, image_files[current_index])
    image = cv2.imread(image_path)

    if image is None:
        print(f"Error: Could not load {image_files[current_index]}")
        break

    resized = resize_keep_ratio(image, new_width, new_height)

    # create black canvas
    canvas = 255 * np.zeros((new_height, new_width, 3), dtype=np.uint8)

    h, w = resized.shape[:2]

    # center position
    y_offset = (new_height - h) // 2
    x_offset = (new_width - w) // 2

    canvas[y_offset:y_offset+h, x_offset:x_offset+w] = resized

    display_image = canvas.copy()

    info_text = f"{current_index + 1}/{len(image_files)} - {image_files[current_index]}"
    help_text = "A = Previous | D = Next | Q = Quit"

    # Draw text on image
    cv2.putText(
        display_image,
        info_text,
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2,
        cv2.LINE_AA
    )

    cv2.putText(
        display_image,
        help_text,
        (20, 80),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
        cv2.LINE_AA
    )

    cv2.imshow(window_name, display_image)

    print(f"Displaying: {image_files[current_index]} ({current_index + 1}/{len(image_files)})")
    print("Press 'A' for previous, 'D' for next, 'Q' to quit")

    key = cv2.waitKey(0) & 0xFF

    if key in (ord('q'), ord('Q')):
        print("Exiting...")
        break
    elif key in (ord('d'), ord('D')):
        current_index = (current_index + 1) % len(image_files)
    elif key in (ord('a'), ord('A')):
        current_index = (current_index - 1) % len(image_files)

cv2.destroyAllWindows()
root.destroy()