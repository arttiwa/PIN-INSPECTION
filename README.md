# PIN-INSPECTION

Python/OpenCV project for pin inspection, QR/Data Matrix reading, and Raspberry Pi camera capture.

Current release: **Version 2.0.0**

## Raspberry Pi Deployment

Extract the release ZIP, open a terminal in the extracted folder, and run:

```bash
python installer.py --install-system
```

The installer uses `/home/pi/.env` by default and creates these Desktop files:

```text
/home/pi/Desktop/run.sh
/home/pi/Desktop/test_cam_new.py
```

Start the application with:

```bash
~/Desktop/run.sh
```

The Desktop camera test is optional:

```bash
python ~/Desktop/test_cam_new.py
```

See `docs/DEPLOYMENT_CHECKLIST.md` before production use.

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
- `inspection_settings.json` contains machine-specific camera calibration and Remote I/O settings. Verify it on the target Pi before production use.
