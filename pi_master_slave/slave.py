"""
slave_server.py  —  รันบน SLAVE Raspberry Pi
Auto-detect กล้องที่มีอยู่จริง (0, 1, หรือ 2 ตัว)
POST /capture  → ถ่ายรูปจากกล้องที่ detect ได้ทั้งหมด ส่งกลับ JSON + base64
GET  /cameras  → แสดงจำนวนกล้องที่ detect ได้
DELETE /images → ลบไฟล์ทั้งหมดที่ถ่ายไว้
GET  /ping     → health check
"""

import os
import time
import base64
import logging
import threading
from pathlib import Path
from flask import Flask, jsonify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(message)s",
)
log = logging.getLogger(__name__)

HOST     = "0.0.0.0"
PORT     = 5000
SAVE_DIR = Path("/tmp/captures")
SAVE_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
_last_files: list = []


# ── Camera detection ──────────────────────────────────────────────────────────
def detect_cameras() -> list[int]:
    """
    คืนค่า list ของ camera index ที่ใช้งานได้จริง เช่น [0], [0,1], []
    ลองใช้ picamera2 ก่อน ถ้าไม่มีให้ parse output ของ libcamera-hello
    """
    # วิธีที่ 1: picamera2
    try:
        from picamera2 import Picamera2
        cams = Picamera2.global_camera_info()   # คืน list of dict
        indices = [c["Num"] for c in cams]
        log.info("picamera2 detected cameras: %s", indices)
        return indices
    except ImportError:
        log.warning("picamera2 not available, trying libcamera …")
    except Exception as e:
        log.warning("picamera2 detect failed: %s", e)

    # วิธีที่ 2: libcamera-hello --list-cameras
    try:
        import subprocess
        out = subprocess.check_output(
            ["libcamera-hello", "--list-cameras"],
            stderr=subprocess.STDOUT, timeout=5
        ).decode()
        # ผลลัพธ์มีบรรทัดแบบ "0 : imx219 ..."
        indices = []
        for line in out.splitlines():
            stripped = line.strip()
            if stripped and stripped[0].isdigit() and ":" in stripped:
                try:
                    indices.append(int(stripped.split(":")[0].strip()))
                except ValueError:
                    pass
        log.info("libcamera detected cameras: %s", indices)
        return indices
    except Exception as e:
        log.warning("libcamera detect failed: %s", e)

    # วิธีที่ 3: ลอง /dev/video0, /dev/video1
    indices = []
    for i in range(2):
        if Path(f"/dev/video{i}").exists():
            indices.append(i)
    log.info("v4l2 detected cameras: %s", indices)
    return indices


# ── Photo capture ─────────────────────────────────────────────────────────────
def take_photo(cam_index: int, path: Path) -> None:
    """ถ่ายรูปจาก cam_index — ลอง picamera2 → libcamera-still → fswebcam"""
    try:
        from picamera2 import Picamera2
        cam = Picamera2(cam_index)
        cam.configure(cam.create_still_configuration(
            main={"size": (1920, 1080)}, buffer_count=1))
        cam.start()
        time.sleep(0.5)
        cam.capture_file(str(path))
        cam.stop()
        cam.close()
        log.info("cam%d → picamera2 OK", cam_index)
        return
    except ImportError:
        pass
    except Exception as e:
        log.warning("cam%d picamera2: %s", cam_index, e)

    ret = os.system(
        f"libcamera-still --nopreview --timeout 1000 "
        f"--camera {cam_index} --output {path} 2>/dev/null"
    )
    if ret == 0:
        log.info("cam%d → libcamera-still OK", cam_index)
        return

    device = f"/dev/video{cam_index}"
    ret = os.system(
        f"fswebcam -d {device} -r 1920x1080 --no-banner {path} 2>/dev/null"
    )
    if ret != 0:
        raise RuntimeError(f"cam{cam_index}: ถ่ายไม่ได้ด้วยทุก backend")
    log.info("cam%d → fswebcam OK", cam_index)


def _capture_worker(cam_index: int, results: dict, errors: dict) -> None:
    ts   = int(time.time() * 1000)
    path = SAVE_DIR / f"cam{cam_index}_{ts}.jpg"
    try:
        take_photo(cam_index, path)
        with open(path, "rb") as f:
            results[cam_index] = {"b64": base64.b64encode(f.read()).decode(),
                                   "path": str(path)}
    except Exception as e:
        errors[cam_index] = str(e)
        log.error("cam%d worker error: %s", cam_index, e)


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/cameras", methods=["GET"])
def list_cameras():
    """บอก master ว่าตอนนี้ slave มีกล้องกี่ตัว"""
    indices = detect_cameras()
    return jsonify({"count": len(indices), "indices": indices}), 200


@app.route("/capture", methods=["POST"])
def capture():
    """
    Detect กล้องก่อน แล้วถ่ายทุกตัวพร้อมกัน
    ส่งกลับ: { "count": N, "cam0": <b64>, "cam1": <b64> }
    ถ้าไม่มีกล้องเลย → 200 + { "count": 0 }  (ไม่ใช่ 500)
    """
    global _last_files

    available = detect_cameras()
    log.info("Capture requested — available cameras: %s", available)

    if not available:
        return jsonify({"count": 0, "message": "ไม่พบกล้องบน slave"}), 200

    results, errors = {}, {}
    threads = [
        threading.Thread(target=_capture_worker, args=(i, results, errors))
        for i in available
    ]
    for t in threads: t.start()
    for t in threads: t.join()

    if errors and not results:
        # ถ่ายไม่ได้เลยสักตัว
        return jsonify({"error": errors}), 500

    _last_files = [Path(results[i]["path"]) for i in results]

    payload = {"count": len(results)}
    for i, v in results.items():
        payload[f"cam{i}"] = v["b64"]
    if errors:
        payload["errors"] = errors   # แจ้ง master ว่ากล้องไหนพัง แต่ยังส่งรูปที่ได้
    return jsonify(payload), 200


@app.route("/images", methods=["DELETE"])
def delete_images():
    global _last_files
    deleted = []
    for p in _last_files:
        if p.exists():
            p.unlink()
            deleted.append(p.name)
    _last_files = []
    log.info("Deleted: %s", deleted)
    return jsonify({"deleted": deleted}), 200


@app.route("/ping", methods=["GET"])
def ping():
    cams = detect_cameras()
    return jsonify({"status": "ok", "cameras": len(cams), "indices": cams}), 200


if __name__ == "__main__":
    # แสดงผล detect ตอนเปิด server
    cams = detect_cameras()
    log.info("=" * 50)
    log.info("Slave server starting on %s:%d", HOST, PORT)
    log.info("Detected %d camera(s): %s", len(cams), cams)
    log.info("=" * 50)
    app.run(host=HOST, port=PORT, debug=False)