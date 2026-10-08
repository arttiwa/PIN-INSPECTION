# PIN Inspection Version 2 Release

Version: 2.0.0

Release date: 2026-10-06

## Install on Raspberry Pi

1. Extract `PIN-INSPECTION-v2.zip`.
2. Open a terminal in the extracted `PIN-INSPECTION-v2` folder.
3. Run `python installer.py --install-system`.
4. Start the app with `~/Desktop/run.sh`.

The default virtual environment is `/home/pi/.env`.

The installer creates `run.sh` on the current user's Desktop and copies
`test_cam_new.py` there for camera checks. The original camera test remains in
the application folder so the installer can be run again.

## Included

- Main Tkinter/OpenCV application and all `pages` modules.
- Raspberry Pi installer and camera test utility.
- App icon, Version file, requirements, and current inspection settings.
- Deployment and system design documents.
- Two sample images referenced by Window mode:
  - `captures/P1-P- (14).jpg`
  - `captures/P2-P- (5).jpg`

## Excluded

- Previous inspection results and generated test output.
- Python cache and virtual environment files.
- Git metadata and editor settings.
- Unused legacy `pi_master_slave`, `Testing`, and `get_circles` utilities.
- Sample captures not referenced by the current Window mode.

## Before Production

- Re-run Setup Mode after the cameras and lighting are mounted.
- Verify camera order for cam0 and cam1.
- Verify the Remote I/O IP address and Modbus DI/DO addresses.
- Run at least 10 manual inspection cycles before enabling Auto Run.
