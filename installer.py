#!/usr/bin/env python3
"""
sudo apt update
sudo apt install -y python3-opencv

Installer helper for the PIN Inspection Raspberry Pi deployment.

Default usage on Raspberry Pi:
    python installer.py

Install OS packages too:
    python installer.py --install-system

Then run:
    ./run_pi.sh
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
DEFAULT_VENV = Path.home() / ".venv"
REQUIREMENTS = APP_DIR / "requirements.txt"
RUN_SCRIPT = APP_DIR / "run_pi.sh"

APT_PACKAGES = [
    "python3-pip",
    "python3-venv",
    "python3-tk",
    "python3-pil",
    "python3-pil.imagetk",
    "python3-opencv",
    "libcamera-tools",
]

OPTIONAL_PIP_PACKAGES = {"zxing-cpp"}


def log(message: str) -> None:
    print(f"[INSTALL] {message}", flush=True)


def warn(message: str) -> None:
    print(f"[WARN] {message}", flush=True)


def run(command: list[str], *, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    log("$ " + " ".join(command))
    return subprocess.run(command, cwd=APP_DIR, check=check, env=env)


def is_linux() -> bool:
    return platform.system().lower() == "linux"


def is_raspberry_pi_like() -> bool:
    machine = platform.machine().lower()
    if "arm" in machine or "aarch" in machine:
        return True

    model_path = Path("/proc/device-tree/model")
    try:
        return "raspberry pi" in model_path.read_text(errors="ignore").lower()
    except OSError:
        return False


def python_in_venv(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def ensure_system_site_packages(venv_dir: Path) -> None:
    config_path = venv_dir / "pyvenv.cfg"
    if not config_path.is_file():
        warn(f"Cannot find venv config: {config_path}")
        return

    lines = config_path.read_text(encoding="utf-8").splitlines()
    next_lines: list[str] = []
    found = False
    changed = False
    for line in lines:
        if line.lower().startswith("include-system-site-packages"):
            found = True
            if line.strip().lower() != "include-system-site-packages = true":
                next_lines.append("include-system-site-packages = true")
                changed = True
            else:
                next_lines.append(line)
            continue
        next_lines.append(line)

    if not found:
        next_lines.append("include-system-site-packages = true")
        changed = True

    if changed:
        config_path.write_text("\n".join(next_lines) + "\n", encoding="utf-8", newline="\n")
        log("Enabled system site packages in existing venv so apt packages such as python3-opencv are visible.")


def create_venv(venv_dir: Path, *, system_site_packages: bool) -> Path:
    if not venv_dir.exists():
        command = [sys.executable, "-m", "venv"]
        if system_site_packages:
            command.append("--system-site-packages")
        command.append(str(venv_dir))
        run(command)
    else:
        log(f"Virtual environment already exists: {venv_dir}")
        if system_site_packages:
            ensure_system_site_packages(venv_dir)

    python_path = python_in_venv(venv_dir)
    if not python_path.exists():
        raise RuntimeError(f"Cannot find venv Python: {python_path}")
    return python_path


def install_system_packages() -> None:
    if not is_linux():
        warn("--install-system is only supported on Linux.")
        return
    if shutil.which("apt-get") is None:
        warn("apt-get not found. Skipping system package install.")
        return

    sudo = ["sudo"] if os.geteuid() != 0 and shutil.which("sudo") else []
    run(sudo + ["apt-get", "update"])
    run(sudo + ["apt-get", "install", "-y"] + APT_PACKAGES)


def read_requirements() -> list[str]:
    if not REQUIREMENTS.is_file():
        raise FileNotFoundError(f"Missing requirements file: {REQUIREMENTS}")

    packages: list[str] = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        packages.append(item)
    return packages


def install_python_packages(
    python_path: Path,
    *,
    skip_opencv_pip: bool,
    continue_optional: bool,
) -> None:
    run([str(python_path), "-m", "pip", "install", "--upgrade", "pip"])

    packages = read_requirements()
    if skip_opencv_pip:
        packages = [pkg for pkg in packages if pkg.split("==", 1)[0].lower() != "opencv-python"]
        warn("Skipping pip opencv-python. Raspberry Pi should use apt package python3-opencv.")

    for package in packages:
        result = run([str(python_path), "-m", "pip", "install", package], check=False)
        if result.returncode == 0:
            continue

        package_name = package.split("==", 1)[0].lower()
        if continue_optional and package_name in OPTIONAL_PIP_PACKAGES:
            warn(f"Optional package failed and was skipped: {package}")
            warn("QR fallback still works with OpenCV, but Data Matrix may require zxing-cpp.")
            continue

        raise RuntimeError(f"pip install failed: {package}")


def write_run_script(python_path: Path) -> None:
    script = f"""#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export PIN_SYSTEM_MODE=rasp
"{python_path}" main.py
"""
    RUN_SCRIPT.write_text(script, encoding="utf-8", newline="\n")

    mode = RUN_SCRIPT.stat().st_mode
    RUN_SCRIPT.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    log(f"Created launcher: {RUN_SCRIPT}")


def create_desktop_autostart() -> None:
    if not is_linux():
        warn("--create-autostart is only supported on Linux.")
        return

    autostart_dir = Path.home() / ".config" / "autostart"
    autostart_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = autostart_dir / "pin-inspection.desktop"
    desktop_file.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                "Name=PIN Inspection",
                f"Exec={RUN_SCRIPT}",
                f"Path={APP_DIR}",
                "Terminal=false",
                "X-GNOME-Autostart-enabled=true",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    log(f"Created desktop autostart entry: {desktop_file}")


def check_runtime(python_path: Path) -> None:
    checks = [
        ("tkinter", "import tkinter"),
        ("cv2", "import cv2"),
        ("numpy", "import numpy"),
        ("PIL", "from PIL import Image, ImageTk"),
    ]
    for name, code in checks:
        result = run([str(python_path), "-c", code], check=False)
        if result.returncode == 0:
            log(f"Python check OK: {name}")
        else:
            warn(f"Python check failed: {name}")

    camera_command = shutil.which("rpicam-still") or shutil.which("libcamera-still")
    if camera_command:
        log(f"Camera command found: {camera_command}")
    elif is_linux():
        warn("No rpicam-still/libcamera-still found. Install libcamera-tools on Raspberry Pi.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install PIN Inspection dependencies and Pi launcher.")
    parser.add_argument("--venv", default=str(DEFAULT_VENV), help="Virtual environment directory.")
    parser.add_argument("--install-system", action="store_true", help="Install apt packages on Linux/Raspberry Pi.")
    parser.add_argument("--no-venv", action="store_true", help="Install Python packages into the current interpreter.")
    parser.add_argument(
        "--include-opencv-pip",
        action="store_true",
        help="Install opencv-python from pip even on Raspberry Pi.",
    )
    parser.add_argument(
        "--strict-optional",
        action="store_true",
        help="Fail if optional packages such as zxing-cpp cannot be installed.",
    )
    parser.add_argument(
        "--create-autostart",
        action="store_true",
        help="Create a desktop autostart entry for Raspberry Pi desktop login.",
    )
    parser.add_argument("--skip-pip", action="store_true", help="Skip pip package installation.")
    parser.add_argument("--skip-checks", action="store_true", help="Skip runtime import/camera checks.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    venv_dir = Path(args.venv).resolve()
    pi_like = is_raspberry_pi_like()

    log(f"App directory: {APP_DIR}")
    log(f"Platform: {platform.platform()} machine={platform.machine()}")
    log(f"Raspberry Pi-like platform: {pi_like}")

    if args.install_system:
        install_system_packages()

    if args.no_venv:
        python_path = Path(sys.executable)
        log(f"Using current Python: {python_path}")
    else:
        old_project_venv = APP_DIR / ".venv"
        if old_project_venv.exists() and venv_dir != old_project_venv:
            warn(f"Project-local venv exists but will not be used: {old_project_venv}")
            warn(f"Using home venv instead: {venv_dir}")
        python_path = create_venv(venv_dir, system_site_packages=pi_like)

    if not args.skip_pip:
        install_python_packages(
            python_path,
            skip_opencv_pip=pi_like and not args.include_opencv_pip,
            continue_optional=not args.strict_optional,
        )

    write_run_script(python_path)

    if args.create_autostart:
        create_desktop_autostart()

    if not args.skip_checks:
        check_runtime(python_path)

    log("Done.")
    log("Run on Raspberry Pi with: ./run_pi.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
