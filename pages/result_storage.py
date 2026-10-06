import json
from datetime import datetime, timedelta
from pathlib import Path

import cv2

from pages.config import APP_DIR


RESULT_DIR = APP_DIR / "result"
RESULT_RETENTION_DAYS = 15
RESULT_MAX_BYTES = 1024 * 1024 * 1024


def _safe_write_image(path, image):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image):
        raise OSError(f"Cannot write image: {path}")


def _result_to_dict(result):
    actual_position = list(result.actual_position) if result.actual_position else None
    return {
        "pin_id": int(result.hole_id),
        "status": "PASS" if result.detected else "FAIL",
        "brightness": round(float(result.brightness), 2) if result.actual_position else None,
        "accepted_range": [result.brightness_min, result.brightness_max],
        "failure_reason": result.failure_reason or None,
        "expected_position": list(result.expected_position),
        "actual_position": actual_position,
        "actual_radius": int(result.actual_radius),
        "distance_from_expected": (
            round(float(result.distance_from_expected), 2)
            if result.actual_position
            else None
        ),
    }


def save_inspection_record(camera_name, run_id, raw_image, result_image, results, status, qr_text):
    now = datetime.now()
    session_dir = RESULT_DIR / f"session_{now:%Y-%m-%d}"
    record_name = f"{run_id}_{camera_name}"
    raw_path = session_dir / f"{record_name}_raw.jpg"
    result_path = session_dir / f"{record_name}_result.jpg"
    metadata_path = session_dir / f"{record_name}.json"

    record_paths = (raw_path, result_path, metadata_path)
    try:
        _safe_write_image(raw_path, raw_image)
        _safe_write_image(result_path, result_image)

        metadata = {
            "run_id": run_id,
            "captured_at": now.isoformat(timespec="milliseconds"),
            "camera": camera_name,
            "status": status,
            "qr": qr_text or None,
            "raw_image": raw_path.name,
            "result_image": result_path.name,
            "pins": [_result_to_dict(result) for result in results],
        }
        with metadata_path.open("w", encoding="utf-8") as file:
            json.dump(metadata, file, indent=2, ensure_ascii=True)
    except Exception:
        for path in record_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    cleanup_result_storage(now)
    return str(result_path)


def _record_key(path):
    stem = path.stem
    for suffix in ("_raw", "_result"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return path.parent, stem


def _result_groups():
    groups = {}
    if not RESULT_DIR.exists():
        return groups

    for path in RESULT_DIR.rglob("*"):
        if path.is_file():
            groups.setdefault(_record_key(path), []).append(path)
    return groups


def _group_modified_at(paths):
    return min(path.stat().st_mtime for path in paths if path.exists())


def _group_size(paths):
    return sum(path.stat().st_size for path in paths if path.exists())


def _delete_group(paths):
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            print(f"[RESULT WARN] Cannot delete {path}: {exc}", flush=True)


def _remove_empty_session_dirs():
    if not RESULT_DIR.exists():
        return
    for path in sorted(RESULT_DIR.iterdir(), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass


def cleanup_result_storage(now=None):
    now = now or datetime.now()
    cutoff_timestamp = (now - timedelta(days=RESULT_RETENTION_DAYS)).timestamp()
    groups = _result_groups()

    for _key, paths in sorted(groups.items(), key=lambda item: _group_modified_at(item[1])):
        if _group_modified_at(paths) < cutoff_timestamp:
            print(f"[RESULT] Delete expired record: {paths[0].parent / _key[1]}", flush=True)
            _delete_group(paths)

    groups = _result_groups()
    ordered_groups = sorted(groups.values(), key=_group_modified_at)
    total_size = sum(_group_size(paths) for paths in ordered_groups)
    for paths in ordered_groups:
        if total_size <= RESULT_MAX_BYTES:
            break
        group_size = _group_size(paths)
        print(f"[RESULT] Delete oldest record to keep 1 GB limit: {paths[0]}", flush=True)
        _delete_group(paths)
        total_size -= group_size

    _remove_empty_session_dirs()
