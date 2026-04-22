import cv2
import os
import shutil
from tkinter import Tk, filedialog

# Create a hidden root window for file dialog
root = Tk()
root.withdraw()

# Select source directory
source_dir = filedialog.askdirectory(title="Select Source Directory")
if not source_dir:
    print("No source directory selected.")
    exit()

# Select destination directory
dest_dir = filedialog.askdirectory(title="Select Destination Directory")
if not dest_dir:
    print("No destination directory selected.")
    exit()

# Get all subdirectories with images
subfolder_counter = {}
file_counter = {}

for root_folder, subdirs, files in os.walk(source_dir):
    # Filter only image files
    image_files = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif'))]
    
    if image_files:
        # Get the immediate subfolder name
        relative_path = os.path.relpath(root_folder, source_dir)
        subfolder_name = relative_path.split(os.sep)[0]
        
        # Counter for this subfolder
        if subfolder_name not in subfolder_counter:
            subfolder_counter[subfolder_name] = 0
            file_counter[subfolder_name] = 0
        
        subfolder_counter[subfolder_name] += 1
        folder_id = subfolder_counter[subfolder_name]
        
        # Copy all images with renamed filenames
        for image_file in image_files:
            src_file = os.path.join(root_folder, image_file)
            
            # Get file extension
            file_ext = os.path.splitext(image_file)[1]
            
            # Create new filename
            file_counter[subfolder_name] += 1
            new_filename = f"{subfolder_name}{folder_id}_{file_counter[subfolder_name]}{file_ext}"
            dst_file = os.path.join(dest_dir, new_filename)
            
            shutil.copy2(src_file, dst_file)
            print(f"Copied: {image_file} → {new_filename}")

print("✓ All images copied and renamed successfully!")