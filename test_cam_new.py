""" press p in cmd while in mode capture """

import subprocess
import shlex
import shutil
import time

def check_camera(cam_num, duration):
    if not shutil.which("rpicam-hello"):
        print("❌ ไม่พบ rpicam-hello")
        return

    print(f"🟡 เปิดกล้อง {cam_num} เป็นเวลา {duration} วินาที...")
    cmd = f"rpicam-hello --camera {cam_num} --timeout {duration*1000}"
    
    try:
        subprocess.run(shlex.split(cmd), check=True)
        print("✅ เสร็จสิ้นการทดสอบกล้อง")
    except subprocess.CalledProcessError:
        print("❌ เปิดกล้องไม่สำเร็จ")


def capture_images(cam_num, total_images):
    if not shutil.which("rpicam-still"):
        print("❌ ไม่พบ rpicam-still")
        return

    print(f"📸 เริ่มถ่าย {total_images} ภาพ จากกล้อง {cam_num}")

    for i in range(1, total_images + 1):
        filename = f"capture_cam{cam_num}_{i}.jpg"
        cmd = f"rpicam-still --camera {cam_num} -o {filename}"
        
        try:
            subprocess.run(shlex.split(cmd), check=True)
            print(f"✅ บันทึก: {filename}")
        except subprocess.CalledProcessError:
            print(f"❌ ถ่ายภาพที่ {i} ไม่สำเร็จ")

        time.sleep(0.5)  # หน่วง 1 วิ กันภาพซ้ำเร็วเกิน

    print("🎉 ถ่ายภาพครบแล้ว")


def main():
    while True:
        print("\n====== SELECT MODE ======")
        print("1: Check Camera")
        print("2: Capture Images")
        print("q: Quit")

        mode = input("เลือกโหมด: ").strip().lower()

        if mode == 'q':
            print("👋 ออกจากโปรแกรม")
            break

        elif mode == '1':
            try:
                cam_num = int(input("เลือกกล้อง (0 หรือ 1): "))
                duration = int(input("เปิดกล้องกี่วินาที?: "))

                if cam_num not in [0, 1]:
                    print("❌ เลือกได้แค่ 0 หรือ 1")
                    continue

                check_camera(cam_num, duration)

            except ValueError:
                print("❌ กรุณาใส่ตัวเลขเท่านั้น")

        elif mode == '2':
            try:
                cam_num = int(input("เลือกกล้อง (0 หรือ 1): "))
                total = int(input("จำนวนภาพที่ต้องการถ่าย: "))

                if cam_num not in [0, 1]:
                    print("❌ เลือกได้แค่ 0 หรือ 1")
                    continue

                capture_images(cam_num, total)

            except ValueError:
                print("❌ กรุณาใส่ตัวเลขเท่านั้น")

        else:
            print("❌ โหมดไม่ถูกต้อง")

if __name__ == "__main__":
    main()
