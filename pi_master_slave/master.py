"""
master_app.py  —  รันบน MASTER Raspberry Pi
Features:
  - Capture 4 images (master cam0/1 + slave cam0/1) พร้อมกัน
  - คลิกที่ภาพ → popup viewer พร้อม zoom in/out, drag, close
  - Save All พร้อม messagebox แจ้งผล
  - Settings dialog: ตั้ง save path (รองรับ network path //server/share/...)
  - Error messagebox ทุก operation
"""

import io
import os
import time
import base64
import threading
import logging
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageTk

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  [%(levelname)s]  %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_SLAVE_IP  = "192.168.1.100"
SLAVE_PORT        = 5000
REQUEST_TIMEOUT   = 20
DEFAULT_SAVE_DIR  = str(Path.home() / "Pictures" / "captures")

# ── Theme ─────────────────────────────────────────────────────────────────────
BG      = "#16161c"
BG2     = "#1f1f27"
BG3     = "#28283a"
ACCENT  = "#5b9cf6"
SUCCESS = "#4caf7d"
DANGER  = "#e05c5c"
WARNING = "#e0a04a"
TXT     = "#e2e2f0"
TXT_DIM = "#6b6b88"
GRID_BG = "#0e0e14"


# ── Camera detection ──────────────────────────────────────────────────────────
def detect_local_cameras() -> list:
    try:
        from picamera2 import Picamera2
        cams = Picamera2.global_camera_info()
        indices = [c["Num"] for c in cams]
        log.info("master picamera2 detected: %s", indices)
        return indices
    except ImportError:
        pass
    except Exception as e:
        log.warning("master picamera2 detect: %s", e)

    try:
        import subprocess
        out = subprocess.check_output(
            ["libcamera-hello", "--list-cameras"],
            stderr=subprocess.STDOUT, timeout=5).decode()
        indices = []
        for line in out.splitlines():
            s = line.strip()
            if s and s[0].isdigit() and ":" in s:
                try:
                    indices.append(int(s.split(":")[0].strip()))
                except ValueError:
                    pass
        log.info("master libcamera detected: %s", indices)
        return indices
    except Exception as e:
        log.warning("master libcamera detect: %s", e)

    indices = [i for i in range(2) if Path(f"/dev/video{i}").exists()]
    log.info("master v4l2 detected: %s", indices)
    return indices


def master_take_photo(cam_index: int, path: Path) -> None:
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
        return
    except ImportError:
        pass
    except Exception as e:
        log.warning("master picamera2 cam%d: %s", cam_index, e)

    ret = os.system(
        f"libcamera-still --nopreview --timeout 1000 "
        f"--camera {cam_index} --output {path} 2>/dev/null")
    if ret == 0:
        return

    device = f"/dev/video{cam_index}"
    ret = os.system(
        f"fswebcam -d {device} -r 1920x1080 --no-banner {path} 2>/dev/null")
    if ret != 0:
        raise RuntimeError(f"master กล้อง {cam_index} ถ่ายไม่ได้")


# ═════════════════════════════════════════════════════════════════════════════
# Image Viewer Popup — zoom + drag + close
# ═════════════════════════════════════════════════════════════════════════════
class ImageViewer(tk.Toplevel):
    """Popup window แสดงภาพพร้อม zoom/drag — เปิดด้วยคลิกที่ panel"""

    MIN_ZOOM = 0.1
    MAX_ZOOM = 8.0

    def __init__(self, parent, pil_img: Image.Image, title: str):
        super().__init__(parent)
        self.title(f"🔍  {title}")
        self.configure(bg=BG)
        self.geometry("900x700")
        self.minsize(400, 300)

        self._orig        = pil_img
        self._zoom        = 1.0
        self._offset      = [0, 0]
        self._drag_start  = None
        self._resize_job  = None
        # cache resized image — ไม่ resize ซ้ำถ้า zoom ยังเท่าเดิม
        self._cache_zoom  = -1.0
        self._cache_img   = None

        self._build_ui()
        self._fit_to_window()   # zoom to fit on open
        # delay grab_set จนกว่า window จะ render และ viewable
        self.after(100, self._safe_grab)

    def _build_ui(self):
        # Toolbar
        bar = tk.Frame(self, bg=BG2, height=40)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        def tb_btn(text, cmd, color=BG3):
            b = tk.Button(bar, text=text, command=cmd,
                          bg=color, fg=TXT, font=("Courier", 10, "bold"),
                          relief="flat", cursor="hand2", padx=10)
            b.pack(side="left", padx=2, pady=4)
            return b

        tb_btn("🔍+  Zoom In",  self._zoom_in,  BG3)
        tb_btn("🔍−  Zoom Out", self._zoom_out, BG3)
        tb_btn("⊡  Fit",       self._fit_to_window, BG3)
        tb_btn("1:1  Actual",  self._actual_size, BG3)

        self._zoom_lbl = tk.Label(bar, text="100%", font=("Courier", 9),
                                   fg=TXT_DIM, bg=BG2)
        self._zoom_lbl.pack(side="left", padx=10)

        tk.Button(bar, text="✕  Close", command=self.destroy,
                  bg=DANGER, fg="#fff", font=("Courier", 10, "bold"),
                  relief="flat", cursor="hand2", padx=10
                  ).pack(side="right", padx=6, pady=4)

        # Canvas
        self._canvas = tk.Canvas(self, bg=GRID_BG, cursor="fleur",
                                  highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)

        # Bindings
        self._canvas.bind("<ButtonPress-1>",   self._on_drag_start)
        self._canvas.bind("<B1-Motion>",       self._on_drag)
        self._canvas.bind("<MouseWheel>",      self._on_scroll)
        self._canvas.bind("<Button-4>",        self._on_scroll)
        self._canvas.bind("<Button-5>",        self._on_scroll)
        self._canvas.bind("<Double-Button-1>", lambda _: self._fit_to_window())
        self.bind("<Configure>", self._on_configure)
        self.bind("<Escape>", lambda _: self.destroy())

    def _on_configure(self, event):
        """debounce resize — filter child events, รอ 200ms แล้วค่อย redraw"""
        if event.widget is not self:
            return
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._cache_img = None   # window size เปลี่ยน → bust cache
        self._resize_job = self.after(200, lambda: self._redraw(final=True))

    def _safe_grab(self):
        """grab_set ปลอดภัย — รอให้ window viewable ก่อน"""
        try:
            self.grab_set()
        except Exception:
            pass   # ถ้ายังไม่พร้อมก็ข้ามไป — ไม่ crash

    # ── Zoom helpers ──────────────────────────────────────────────────────────
    def _zoom_in(self):  self._apply_zoom(self._zoom * 1.25)
    def _zoom_out(self): self._apply_zoom(self._zoom * 0.8)
    def _actual_size(self):
        self._zoom = 1.0
        self._offset = [0, 0]
        self._cache_img = None   # force re-render
        self._redraw(final=True)

    def _fit_to_window(self):
        cw = self._canvas.winfo_width()  or 800
        ch = self._canvas.winfo_height() or 600
        scale = min(cw / self._orig.width, ch / self._orig.height) * 0.97
        self._zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, scale))
        self._offset = [0, 0]
        self._cache_img = None
        self._redraw(final=True)

    def _apply_zoom(self, new_zoom: float):
        """fast render ทันที แล้วตาม LANCZOS หลัง 300ms"""
        self._zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, new_zoom))
        self._cache_img = None   # zoom เปลี่ยน → bust cache
        self._redraw(final=False)
        # schedule คุณภาพสูงหลังหยุด zoom
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(300, lambda: self._redraw(final=True))

    def _on_scroll(self, event):
        if hasattr(event, "delta") and event.delta:
            factor = 1.1 if event.delta > 0 else 0.9
        else:
            factor = 1.1 if event.num == 4 else 0.9
        self._apply_zoom(self._zoom * factor)

    # ── Pan ───────────────────────────────────────────────────────────────────
    def _on_drag_start(self, event):
        self._drag_start = (event.x, event.y)

    def _on_drag(self, event):
        if self._drag_start is None:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        self._offset[0] += dx
        self._offset[1] += dy
        self._drag_start = (event.x, event.y)
        # pan ไม่ต้อง resize เลย — แค่ move image บน canvas โดยตรง
        self._canvas.move("all", dx, dy)
        # อัปเดต zoom label position เท่านั้น (ไม่ redraw)

    # ── Render ────────────────────────────────────────────────────────────────
    def _redraw(self, final: bool = False):
        """
        Render ภาพบน canvas
        final=False → ใช้ BILINEAR (เร็ว) ระหว่าง drag/scroll
        final=True  → ใช้ LANCZOS (คม) หลัง settle
        """
        self._resize_job = None
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 2 or ch < 2:
            return

        new_w = max(1, int(self._orig.width  * self._zoom))
        new_h = max(1, int(self._orig.height * self._zoom))

        # resize ใหม่เฉพาะตอน zoom เปลี่ยน — ถ้าแค่ pan ให้ใช้ cache
        if self._cache_img is None or abs(self._cache_zoom - self._zoom) > 1e-6:
            resample = Image.LANCZOS if final else Image.BILINEAR
            self._cache_img  = self._orig.resize((new_w, new_h), resample)
            self._cache_zoom = self._zoom

        tk_img = ImageTk.PhotoImage(self._cache_img)
        cx = cw // 2 + self._offset[0]
        cy = ch // 2 + self._offset[1]

        self._canvas.delete("all")
        self._canvas.create_image(cx, cy, anchor="center", image=tk_img)
        self._canvas.image = tk_img

        pct = int(self._zoom * 100)
        self._zoom_lbl.config(text=f"{pct}%  ({new_w}×{new_h}px)")


# ═════════════════════════════════════════════════════════════════════════════
# Settings Dialog
# ═════════════════════════════════════════════════════════════════════════════
class SettingsDialog(tk.Toplevel):
    """Dialog ตั้งค่า save path — รองรับ local path และ network path"""

    def __init__(self, parent, current_path: str):
        super().__init__(parent)
        self.title("⚙  Settings — Save Path")
        self.configure(bg=BG2)
        self.resizable(True, False)
        self.geometry("560x220")
        self.grab_set()

        self.result: str | None = None   # ถ้า None = cancelled
        self._path_var = tk.StringVar(value=current_path)

        self._build()

    def _build(self):
        pad = dict(padx=20, pady=8)

        tk.Label(self, text="Save Path Configuration",
                 font=("Courier", 13, "bold"), fg=ACCENT, bg=BG2
                 ).pack(anchor="w", **pad)

        tk.Label(self,
                 text="ใส่ path ที่ต้องการบันทึก (local หรือ network share)\n"
                      "ตัวอย่าง:  /home/pi/captures\n"
                      "            //10.17.44.233/sharedfolder/captures",
                 font=("Courier", 9), fg=TXT_DIM, bg=BG2, justify="left"
                 ).pack(anchor="w", padx=20)

        # Path entry row
        row = tk.Frame(self, bg=BG2)
        row.pack(fill="x", padx=20, pady=6)

        self._entry = tk.Entry(row, textvariable=self._path_var,
                               font=("Courier", 11),
                               bg=BG3, fg=TXT, insertbackground=TXT,
                               relief="flat", bd=6)
        self._entry.pack(side="left", fill="x", expand=True)

        tk.Button(row, text="Browse…", command=self._browse,
                  bg=BG3, fg=TXT, font=("Courier", 9, "bold"),
                  relief="flat", cursor="hand2", padx=8, pady=4
                  ).pack(side="left", padx=(6, 0))

        # Buttons
        btn_row = tk.Frame(self, bg=BG2)
        btn_row.pack(fill="x", padx=20, pady=(4, 16))

        tk.Button(btn_row, text="✓  Save", command=self._on_save,
                  bg=SUCCESS, fg="#fff", font=("Courier", 11, "bold"),
                  relief="flat", cursor="hand2", padx=16, pady=6
                  ).pack(side="left", padx=(0, 8))

        tk.Button(btn_row, text="✕  Cancel", command=self.destroy,
                  bg=DANGER, fg="#fff", font=("Courier", 11, "bold"),
                  relief="flat", cursor="hand2", padx=16, pady=6
                  ).pack(side="left")

        self.bind("<Return>", lambda _: self._on_save())
        self.bind("<Escape>", lambda _: self.destroy())

    def _browse(self):
        """เปิด folder picker — ใช้สำหรับ local path"""
        chosen = filedialog.askdirectory(
            title="เลือก folder บันทึกภาพ",
            initialdir=self._path_var.get() or str(Path.home()))
        if chosen:
            self._path_var.set(chosen)

    def _on_save(self):
        p = self._path_var.get().strip()
        if not p:
            messagebox.showwarning("ไม่ได้ใส่ path", "กรุณาใส่ path ก่อน", parent=self)
            return
        self.result = p
        self.destroy()


# ═════════════════════════════════════════════════════════════════════════════
# Image Panel — click to open viewer
# ═════════════════════════════════════════════════════════════════════════════
class ImagePanel(tk.Frame):
    def __init__(self, parent, label: str, header_color: str = ACCENT,
                 on_click=None, **kw):
        super().__init__(parent, bg=GRID_BG, **kw)
        self._pil: Image.Image | None = None
        self._label = label
        self._on_click = on_click   # callback(pil_img, label)

        header = tk.Frame(self, bg=BG2, height=28)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text=label, font=("Courier", 9, "bold"),
                 fg=header_color, bg=BG2).pack(side="left", padx=10)
        self._size_lbl = tk.Label(header, text="", font=("Courier", 8),
                                   fg=TXT_DIM, bg=BG2)
        self._size_lbl.pack(side="right", padx=10)

        self._img_lbl = tk.Label(self, bg=GRID_BG, text="— รอภาพ —",
                                  fg=TXT_DIM, font=("Courier", 10),
                                  cursor="hand2")
        self._img_lbl.pack(fill="both", expand=True)

        self._img_lbl.bind("<Button-1>", self._clicked)
        self._resize_job = None                          # debounce timer id
        self._last_wh    = (0, 0)                        # track last rendered size
        self.bind("<Configure>", self._on_configure)

    # ── debounced resize ──────────────────────────────────────────────────────
    def _on_configure(self, event):
        """
        ป้องกัน lag:
        1. กรอง event ที่มาจาก child widget (bubble-up) — ใช้เฉพาะ event ของตัวเอง
        2. debounce 150ms — render เฉพาะตอน resize หยุดแล้ว
        """
        if event.widget is not self:
            return
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(150, self._refresh)

    def set_image(self, pil_img: Image.Image):
        self._pil = pil_img
        self._last_wh = (0, 0)   # force re-render
        self._size_lbl.config(text=f"{pil_img.width}×{pil_img.height}  🔍")
        self._img_lbl.config(cursor="hand2")
        self._refresh()

    def set_loading(self):
        self._pil = None
        self._size_lbl.config(text="")
        self._img_lbl.config(image="", text="กำลังถ่าย …", fg=WARNING, cursor="")
        self._img_lbl.image = None

    def set_no_camera(self):
        self._pil = None
        self._size_lbl.config(text="")
        self._img_lbl.config(image="", text="⚠ ไม่พบกล้อง", fg=TXT_DIM, cursor="")
        self._img_lbl.image = None

    def set_error(self, msg: str):
        self._pil = None
        self._size_lbl.config(text="")
        self._img_lbl.config(image="", text=f"✗ Error\n{msg[:60]}", fg=DANGER, cursor="")
        self._img_lbl.image = None

    def _clicked(self, _event):
        if self._pil and self._on_click:
            self._on_click(self._pil, self._label)

    def _refresh(self):
        self._resize_job = None
        if self._pil is None:
            return
        w = self._img_lbl.winfo_width()
        h = self._img_lbl.winfo_height()
        if w < 10 or h < 10:
            return
        # ข้ามถ้าขนาดไม่เปลี่ยนเลย (เช่น configure event จาก scroll)
        if (w, h) == self._last_wh:
            return
        self._last_wh = (w, h)
        # ใช้ BILINEAR สำหรับ thumbnail ใน grid — เร็วกว่า LANCZOS มาก
        # LANCZOS จะใช้เฉพาะตอนเปิด viewer popup เท่านั้น
        img = self._pil.copy()
        img.thumbnail((w, h), Image.BILINEAR)
        tk_img = ImageTk.PhotoImage(img)
        self._img_lbl.config(image=tk_img, text="")
        self._img_lbl.image = tk_img


# ═════════════════════════════════════════════════════════════════════════════
# Main Application
# ═════════════════════════════════════════════════════════════════════════════
class MasterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Pi Capture — Master (4 Cameras)")
        self.configure(bg=BG)
        self.geometry("1100x700")
        self.minsize(800, 560)

        self._slave_ip   = tk.StringVar(value=DEFAULT_SLAVE_IP)
        self._status_msg = tk.StringVar(value="พร้อมใช้งาน")
        self._save_path  = DEFAULT_SAVE_DIR   # str — อาจเป็น network path
        self._busy       = False
        self._images: dict = {}

        self._build_ui()
        self._schedule_clock()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        ttk.Style(self).theme_use("clam")

        # Top bar
        topbar = tk.Frame(self, bg=BG2, height=52)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        tk.Label(topbar, text="Pi Capture  ·  4 Cameras",
                 font=("Courier", 16, "bold"), fg=ACCENT, bg=BG2
                 ).pack(side="left", padx=20, pady=8)
        self._clock = tk.Label(topbar, text="", font=("Courier", 10),
                                fg=TXT_DIM, bg=BG2)
        self._clock.pack(side="right", padx=20)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        self._build_sidebar(body)
        self._build_grid(body)

        bar = tk.Frame(self, bg=BG2, height=26)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, textvariable=self._status_msg,
                 font=("Courier", 9), fg=TXT_DIM, bg=BG2, anchor="w"
                 ).pack(side="left", padx=12)

    def _build_sidebar(self, parent):
        sb = tk.Frame(parent, bg=BG2, width=230)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        def section(text):
            tk.Label(sb, text=text, font=("Courier", 8, "bold"),
                     fg=TXT_DIM, bg=BG2).pack(anchor="w", padx=16, pady=(16, 3))
        def sep():
            ttk.Separator(sb).pack(fill="x", padx=16, pady=8)

        # ── Connection ──
        section("SLAVE CONNECTION")
        tk.Label(sb, text="IP Address", font=("Courier", 9), fg=TXT, bg=BG2
                 ).pack(anchor="w", padx=16)
        ttk.Entry(sb, textvariable=self._slave_ip,
                  font=("Courier", 11)).pack(fill="x", padx=16, pady=(2, 4))
        self._ping_btn = self._mk_btn(sb, "Ping Slave", self._on_ping, ACCENT)
        self._ping_btn.pack(fill="x", padx=16, pady=2)
        self._conn_dot = tk.Label(sb, text="● offline", font=("Courier", 9),
                                   fg=DANGER, bg=BG2)
        self._conn_dot.pack(anchor="w", padx=16, pady=2)

        sep()

        # ── Capture ──
        section("CAPTURE")
        self._cap_btn = self._mk_btn(
            sb, "📷  Capture All (4 Cams)", self._on_capture,
            SUCCESS, font=("Courier", 11, "bold"))
        self._cap_btn.pack(fill="x", padx=16, pady=4)

        sep()

        # ── Save ──
        section("SAVE")
        self._save_btn = self._mk_btn(sb, "💾  Save All Images",
                                       self._on_save_all, WARNING, state="disabled")
        self._save_btn.pack(fill="x", padx=16, pady=4)

        # Save path display
        path_row = tk.Frame(sb, bg=BG2)
        path_row.pack(fill="x", padx=16, pady=(0, 2))
        self._path_lbl = tk.Label(path_row,
                                   text=self._short_path(self._save_path),
                                   font=("Courier", 7), fg=TXT_DIM, bg=BG2,
                                   anchor="w", wraplength=180, justify="left")
        self._path_lbl.pack(side="left", fill="x", expand=True)

        self._mk_btn(sb, "⚙  Settings", self._on_settings, BG3,
                     font=("Courier", 9, "bold")
                     ).pack(fill="x", padx=16, pady=2)

        sep()
        self._progress = ttk.Progressbar(sb, mode="indeterminate")
        self._progress.pack(fill="x", padx=16, pady=4)

        # ── Legend ──
        sep()
        for tag, color in [("Master Cam 0", "#5b9cf6"), ("Master Cam 1", "#9b6cf6"),
                            ("Slave  Cam 0", "#4caf7d"), ("Slave  Cam 1", "#4ccfaf")]:
            r = tk.Frame(sb, bg=BG2)
            r.pack(fill="x", padx=16, pady=1)
            tk.Label(r, text="■", fg=color, bg=BG2, font=("Courier", 10)).pack(side="left")
            tk.Label(r, text=f"  {tag}", fg=TXT_DIM, bg=BG2, font=("Courier", 8)).pack(side="left")

        sep()
        self._cam_status_lbl = tk.Label(sb, text="กด Ping เพื่อดูสถานะกล้อง",
                                         font=("Courier", 8), fg=TXT_DIM, bg=BG2,
                                         justify="left", wraplength=195)
        self._cam_status_lbl.pack(anchor="w", padx=16)

    def _build_grid(self, parent):
        grid = tk.Frame(parent, bg=GRID_BG)
        grid.pack(side="left", fill="both", expand=True, padx=2, pady=2)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.rowconfigure(0, weight=1)
        grid.rowconfigure(1, weight=1)

        self._panel_meta = {
            "master_0": (0, 0, "Master — Cam 0", "#5b9cf6"),
            "master_1": (0, 1, "Master — Cam 1", "#9b6cf6"),
            "slave_0":  (1, 0, "Slave  — Cam 0", "#4caf7d"),
            "slave_1":  (1, 1, "Slave  — Cam 1", "#4ccfaf"),
        }
        self._panels: dict[str, ImagePanel] = {}
        for key, (row, col, lbl, color) in self._panel_meta.items():
            panel = ImagePanel(grid, lbl, header_color=color,
                               on_click=self._open_viewer)
            panel.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)
            panel.set_no_camera()
            self._panels[key] = panel

    def _mk_btn(self, parent, text, cmd, color,
                state="normal", font=("Courier", 10, "bold")):
        return tk.Button(parent, text=text, command=cmd,
                         bg=color, fg="#fff", activebackground=BG3,
                         font=font, relief="flat", cursor="hand2",
                         state=state, pady=7)

    # ── Image Viewer ──────────────────────────────────────────────────────────
    def _open_viewer(self, pil_img: Image.Image, label: str):
        ImageViewer(self, pil_img, label)

    # ── Ping ──────────────────────────────────────────────────────────────────
    def _on_ping(self):
        ip = self._slave_ip.get().strip()
        self._set_status(f"กำลัง ping {ip} …")
        threading.Thread(target=self._do_ping, args=(ip,), daemon=True).start()

    def _do_ping(self, ip):
        try:
            r = requests.get(f"http://{ip}:{SLAVE_PORT}/ping", timeout=5)
            ok = r.status_code == 200
            slave_cams = r.json().get("cameras", "?") if ok else 0
        except Exception:
            ok = False
            slave_cams = 0

        master_cams = detect_local_cameras()
        self.after(0, self._conn_dot.config,
                   {"text": "● online", "fg": SUCCESS} if ok
                   else {"text": "● offline", "fg": DANGER})
        cam_info = (f"Master: {len(master_cams)} กล้อง {master_cams}\n"
                    f"Slave:  {slave_cams} กล้อง")
        self.after(0, self._cam_status_lbl.config, {"text": cam_info})
        self.after(0, self._set_status,
                   f"Slave {ip} {'ออนไลน์ ✓' if ok else 'ไม่ตอบสนอง ✗'}  |  "
                   f"{cam_info.replace(chr(10), '  ')}")

    # ── Capture ───────────────────────────────────────────────────────────────
    def _on_capture(self):
        if self._busy:
            return
        self._set_busy(True)
        for p in self._panels.values():
            p.set_loading()
        self._set_status("กำลัง detect กล้องและถ่ายรูป …")
        threading.Thread(target=self._do_capture_all, daemon=True).start()

    def _do_capture_all(self):
        ip = self._slave_ip.get().strip()
        master_cams = detect_local_cameras()

        for idx in range(2):
            if idx not in master_cams:
                self.after(0, self._panels[f"master_{idx}"].set_no_camera)

        results: dict = {}
        errors:  dict = {}

        def capture_master_cam(idx):
            key  = f"master_{idx}"
            ts   = int(time.time() * 1000)
            path = Path(f"/tmp/master_cam{idx}_{ts}.jpg")
            try:
                master_take_photo(idx, path)
                results[key] = Image.open(path).copy()
                path.unlink(missing_ok=True)
            except Exception as e:
                errors[key] = str(e)

        def capture_slave():
            try:
                r = requests.post(f"http://{ip}:{SLAVE_PORT}/capture",
                                  timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text}")
                data = r.json()
                for idx in range(2):
                    key = f"slave_{idx}"
                    b64key = f"cam{idx}"
                    if b64key in data:
                        results[key] = Image.open(
                            io.BytesIO(base64.b64decode(data[b64key]))).copy()
                    else:
                        self.after(0, self._panels[key].set_no_camera)
                if data.get("errors"):
                    log.warning("Slave partial errors: %s", data["errors"])
                requests.delete(f"http://{ip}:{SLAVE_PORT}/images", timeout=5)
            except Exception as e:
                log.error("Slave capture error: %s", e)
                err_msg = str(e)
                errors["slave_0"] = err_msg
                errors["slave_1"] = err_msg
                self.after(0, self._panels["slave_0"].set_error, err_msg)
                self.after(0, self._panels["slave_1"].set_error, err_msg)

        threads = [threading.Thread(target=capture_master_cam, args=(i,))
                   for i in master_cams]
        threads.append(threading.Thread(target=capture_slave))
        for t in threads: t.start()
        for t in threads: t.join()

        for key, img in results.items():
            self._images[key] = img
            self.after(0, self._panels[key].set_image, img)

        # Error messagebox ถ้ามี error และไม่ได้รับภาพเลย
        fatal_errors = {k: v for k, v in errors.items() if k not in results}
        if fatal_errors:
            err_text = "\n".join(f"• {k}: {v}" for k, v in fatal_errors.items())
            self.after(0, messagebox.showerror,
                       "Capture มีปัญหา",
                       f"กล้องบางตัวถ่ายไม่ได้:\n\n{err_text}")

        ok = len(results)
        self.after(0, self._set_status,
                   f"ได้รับ {ok} ภาพ  |  master: {master_cams}  |  "
                   f"slave: {[k for k in results if k.startswith('slave')]}")
        self.after(0, self._set_busy, False)
        if ok > 0:
            self.after(0, self._save_btn.config, {"state": "normal"})

    # ── Save ──────────────────────────────────────────────────────────────────
    def _on_save_all(self):
        """บันทึกทุกภาพไปที่ save_path — แสดง messagebox เมื่อเสร็จหรือ error"""
        save_dir = Path(self._save_path)
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror(
                "สร้าง folder ไม่ได้",
                f"ไม่สามารถสร้าง folder ที่:\n{save_dir}\n\nError: {e}\n\n"
                "ตรวจสอบ:\n• Network path ถูกต้องและเชื่อมต่ออยู่\n"
                "• มี permission เขียนไฟล์")
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved, failed = [], []

        for key, img in self._images.items():
            if img is None:
                continue
            fname = save_dir / f"{ts}_{key}.jpg"
            try:
                img.save(str(fname), "JPEG", quality=95)
                saved.append(fname.name)
                log.info("Saved: %s", fname)
            except Exception as e:
                failed.append(f"{fname.name}: {e}")
                log.error("Save failed %s: %s", fname, e)

        if not saved and not failed:
            messagebox.showinfo("ไม่มีภาพ", "ยังไม่มีภาพที่จะบันทึก\nกด Capture ก่อน")
            return

        if failed:
            msg = ""
            if saved:
                msg += f"บันทึกสำเร็จ {len(saved)} ภาพ:\n" + "\n".join(f"  ✓ {s}" for s in saved)
                msg += "\n\n"
            msg += f"บันทึกไม่สำเร็จ {len(failed)} ภาพ:\n" + "\n".join(f"  ✗ {f}" for f in failed)
            messagebox.showwarning("บันทึกบางส่วนสำเร็จ", msg)
        else:
            msg = (f"บันทึกสำเร็จ {len(saved)} ภาพ\n\n"
                   + "\n".join(f"  ✓ {s}" for s in saved)
                   + f"\n\nไปที่:\n{save_dir}")
            messagebox.showinfo("บันทึกสำเร็จ ✓", msg)

        self._set_status(f"บันทึกแล้ว {len(saved)} ภาพ → {save_dir}")

    # ── Settings ──────────────────────────────────────────────────────────────
    def _on_settings(self):
        dlg = SettingsDialog(self, self._save_path)
        self.wait_window(dlg)
        if dlg.result is not None:
            self._save_path = dlg.result
            self._path_lbl.config(text=self._short_path(self._save_path))
            self._set_status(f"Save path ตั้งค่าแล้ว: {self._save_path}")

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _short_path(self, path: str) -> str:
        """ตัดให้สั้นสำหรับแสดงใน sidebar"""
        if len(path) <= 30:
            return path
        return "…" + path[-28:]

    def _set_busy(self, busy: bool):
        self._busy = busy
        self._cap_btn.config(state="disabled" if busy else "normal")
        self._progress.start(10) if busy else self._progress.stop()

    def _set_status(self, msg: str):
        self._status_msg.set(msg)
        log.info(msg)

    def _schedule_clock(self):
        self._clock.config(text=datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.after(1000, self._schedule_clock)


if __name__ == "__main__":
    MasterApp().mainloop()