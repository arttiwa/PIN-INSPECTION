# PIN Inspection - Deployment Checklist

Last reviewed: 2026-09-14

## Raspberry Pi Setup

- [ ] Run installer helper from the project folder.

```bash
python installer.py --install-system
```

By default, the installer creates the virtual environment at:

```text
/home/pi/.venv
```

If you want a different path, pass `--venv`, for example:

```bash
python installer.py --venv /home/pi/.env --install-system
```

If system packages are already installed:

```bash
python installer.py
```

- [ ] Install Python dependencies.

```bash
python -m pip install -r requirements.txt
```

- [ ] Install system packages needed by the Pi UI/camera stack.

```bash
sudo apt install -y python3-tk python3-pil.imagetk libcamera-tools
```

- [ ] Confirm one Pi camera command exists.

```bash
which rpicam-still || which libcamera-still
```

- [ ] Confirm cameras are visible.

```bash
rpicam-hello --list-cameras
```

## Launch

- [ ] Start in Raspberry Pi mode. If installed with `installer.py`, use:

```bash
./run_pi.sh
```

Manual equivalent:

```bash
PIN_SYSTEM_MODE=rasp python main.py
```

- [ ] Confirm app log prints:

```text
System mode: rasp
```

## Camera Setup

- [ ] Open Setup Mode.
- [ ] Select `cam0`.
- [ ] Click Recapture.
- [ ] Click Process.
- [ ] Select expected pin hole circles.
- [ ] Set Pin Conditions if needed.
- [ ] Disable QR/Data Matrix if the camera view has no code.
- [ ] Save Setup.
- [ ] Repeat for `cam1`.

## Manual Inspection Test

- [ ] Open Use Mode.
- [ ] Click Run Manual.
- [ ] Confirm `cam0` completes.
- [ ] Confirm `cam1` completes.
- [ ] Confirm saved images appear in:

```text
result/session_YYYY-MM-DD/
```

- [ ] Confirm each camera record contains raw image, result image, and JSON metadata.
- [ ] Confirm the result directory stays within the 1 GB / 15-day retention policy.

- [ ] Confirm expected PASS/FAIL behavior with good and bad parts.

## Remote I/O Test

- [ ] Open Configure TCP/IP.
- [ ] Confirm host, port, unit id, DI0, DO PASS, DO FAIL.
- [ ] Click Test TCP.
- [ ] Confirm DI0 trigger starts one inspection cycle.
- [ ] Confirm PASS writes DO PASS for 5 seconds.
- [ ] Confirm FAIL writes DO FAIL for 5 seconds.

## Production Readiness

- [ ] Manual run stable for at least 10 cycles.
- [ ] No unexpected `Killed` process exit.
- [ ] QR disabled on cameras that do not need code reading.
- [ ] Lighting and camera mounts fixed.
- [ ] `inspection_settings.json` backed up after final calibration.
- [ ] Operator knows to use Recapture in Setup Mode before processing.

## Troubleshooting Quick Reference

| Symptom | Likely Cause | Action |
|---|---|---|
| App tries to read `captures/P1-P- (14).jpg` on Pi | Running in window mode | Start with `PIN_SYSTEM_MODE=rasp python main.py`. |
| Camera capture fails | Missing camera tool or wrong index | Check `which rpicam-still`, `rpicam-hello --list-cameras`, and `CAMERA_SOURCES`. |
| Installer says `Python check failed: cv2` | Existing venv cannot see apt package `python3-opencv` | Run the latest `python installer.py --install-system`; it enables system site packages in the selected venv `pyvenv.cfg`. |
| `QR NOT FOUND` | No QR/Data Matrix in image | Disable QR option for that camera or ignore if QR is optional. |
| Process says `Killed` | Pi memory pressure | Disable QR, run sequentially, reduce image size/camera resolution if needed. |
| Remote I/O no response | IP/port/network wrong | Use Configure TCP/IP and Test TCP. |
| False pin fail | Lighting/threshold mismatch | Re-run Setup Mode and adjust brightness/search radius. |
