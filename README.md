# PIN-INSPECTION

Python/OpenCV project for pin inspection, QR/Data Matrix reading, and Raspberry Pi camera capture.

## Local Setup

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run the main app:

```bash
python main.py
python pin_inspection_app.py --mode setup
python pin_inspection_app.py --mode use
```

If `python main.py` fails with `No module named '_tkinter'` on Homebrew Python:

```bash
brew install python-tk@3.13
python main.py
```

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run the main app:

```powershell
python main.py
python pin_inspection_app.py --mode setup
python pin_inspection_app.py --mode use
```

## Notes

- `.venv/` is local only and should not be committed.
- `zxing-cpp` enables Data Matrix support. If it is unavailable, QR reading still falls back to OpenCV.
- Raspberry Pi camera support may also require system packages such as `picamera2`, `libcamera-tools`, `python3-tk`, and `python3-pil.imagetk`.
