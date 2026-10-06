# PIN Inspection - Design Report

Last reviewed: 2026-09-14

## Executive Summary

The project is close to Raspberry Pi deployment readiness. The current application supports camera setup, production inspection, manual run, automatic DI0-triggered run, PASS/FAIL Remote I/O output, Pi-native camera capture, and result image retention.

The latest important deployment fixes are:

- Setup Mode no longer captures automatically on page entry when no image exists.
- Recapture explicitly performs a fresh Pi camera capture.
- Use Mode processes cameras sequentially to reduce Raspberry Pi memory pressure.
- QR/Data Matrix failures are handled without killing the application.
- QR preprocessing is memory-limited and lazy to reduce the chance of the OS killing the process.

## Last Check Results

Static Python compile check passed:

```powershell
python -m py_compile main.py pin_inspection_app.py read_qr_code.py ck_pin.py get_circles.py pages\app.py pages\setup_workflow.py pages\use_workflow.py pages\inspection_logic.py pages\runner.py pages\config.py pages\widgets.py pages\remote_io.py pages\network_config.py
```

No syntax errors were found in the checked runtime files.

## Current Product Behavior

### Setup Mode

- Opens without forcing camera capture.
- Shows a no-image message if no test image is configured or readable.
- Uses `Recapture` to capture from the active camera.
- Allows circle detection, circle selection, per-circle pin conditions, and QR/Data Matrix enablement.
- Saves calibration to `inspection_settings.json`.

### Use Mode

- Starts as the default page in `main.py`.
- Supports `Run Manual`.
- Supports `Auto Run DI0` when Remote I/O is enabled.
- Processes `cam0` then `cam1`.
- Saves raw images, annotated results, and JSON metadata to daily folders in `result/`.
- Keeps records for up to 15 days and limits total result storage to 1 GB.
- Sends PASS/FAIL output over Modbus TCP if enabled.

### Raspberry Pi Capture

- Uses `rpicam-still` when available.
- Falls back to `libcamera-still`.
- Avoids OpenCV/GStreamer capture in Pi mode.

## Key Findings

1. The active runtime mode is not taken from `inspection_settings.json`.

   The app uses `PIN_SYSTEM_MODE` or `SYSTEM_MODE` in `pin_inspection_app.py`. For Pi deployment, launch with:

   ```bash
   PIN_SYSTEM_MODE=rasp python main.py
   ```

2. The current saved config still says:

   ```json
   "system_mode": "window"
   ```

   This value is mainly metadata in the current code. It can confuse operators, so production notes should emphasize the launch command.

3. `cam0` currently has QR/Data Matrix enabled.

   If the actual camera view has no QR/Data Matrix, keep this disabled in Setup Mode. The app now handles `NOT FOUND`, but disabling QR will reduce run time and memory pressure.

4. Remote I/O is currently enabled.

   Current target:

   - Host: `192.168.11.45`
   - Port: `502`
   - DI0: `0`
   - DO PASS: `16`
   - DO FAIL: `17`

   This must be tested on the production network before enabling Auto Run.

5. Result output directory changed from older helper output to Use Mode `result/`.

   Production users should collect result images from:

   ```text
   result/
   ```

## Recommendations Before Deployment

1. Confirm Pi command:

   ```bash
   PIN_SYSTEM_MODE=rasp python main.py
   ```

2. Confirm Pi camera tools:

   ```bash
   which rpicam-still || which libcamera-still
   ```

3. Check camera indices:

   ```bash
   rpicam-hello --list-cameras
   ```

   If needed, update:

   ```python
   CAMERA_SOURCES = {
       "cam0": 0,
       "cam1": 1,
   }
   ```

4. Re-run Setup Mode on the production machine.

   Production lighting, lens position, focus, and camera orientation can change circle positions and brightness thresholds.

5. Disable QR/Data Matrix on cameras that do not need it.

   In Setup Mode, uncheck:

   ```text
   Read QR/Data Matrix for this camera
   ```

6. Test Remote I/O.

   Open Configure TCP/IP, verify the IP/port, and use Test TCP before using Auto Run DI0.

7. Run at least 10 manual inspections before switching to Auto Run.

   Confirm result image output, PASS/FAIL status, and Remote I/O behavior.

## Deployment Readiness

Status: Ready for controlled Raspberry Pi trial after hardware validation.

Required hardware checks:

- Pi can open the Tkinter UI.
- Both cameras capture with `rpicam-still` or `libcamera-still`.
- Camera order matches `cam0` and `cam1`.
- Remote I/O device is reachable from the Pi.
- DI0 trigger and DO PASS/FAIL addresses are correct.

Recommended first production run:

1. Start app with `PIN_SYSTEM_MODE=rasp python main.py`.
2. Open Setup Mode.
3. Select `cam0`, click Recapture, Process, select pin holes, set QR option, Save Setup.
4. Select `cam1`, click Recapture, Process, select pin holes, set QR option, Save Setup.
5. Open Use Mode.
6. Run Manual.
7. Review both result panels and saved images in `result/`.
8. Test Auto Run DI0 only after manual mode is stable.

## Appendix: Important Files

| File | Purpose |
|---|---|
| `main.py` | Main UI entry point. |
| `pin_inspection_app.py` | Capture backend, core OpenCV helpers, CLI flow. |
| `pages/setup_workflow.py` | Setup/calibration UI behavior. |
| `pages/use_workflow.py` | Production run, Remote I/O, result save behavior. |
| `pages/remote_io.py` | Modbus TCP client. |
| `pages/network_config.py` | Remote I/O configuration dialog. |
| `read_qr_code.py` | QR/Data Matrix reader. |
| `inspection_settings.json` | Camera and Remote I/O configuration. |
