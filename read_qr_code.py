import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import cv2


TARGET_FILE = os.environ.get("TARGET_FILE", r"captures\P1-P- (14).jpg")

try:
    import zxingcpp
except ImportError:
    zxingcpp = None


def _decode_with_detector(detector: cv2.QRCodeDetector, image) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    ok, decoded_info, points, _ = detector.detectAndDecodeMulti(image)
    if ok and points is not None:
        for value, qr_points in zip(decoded_info, points):
            if not value:
                continue
            results.append(
                {
                    "data": value,
                    "points": [[float(x), float(y)] for x, y in qr_points],
                }
            )

    if results:
        return results

    value, points, _ = detector.detectAndDecode(image)
    if value:
        result: Dict[str, Any] = {"data": value}
        if points is not None:
            result["points"] = [[float(x), float(y)] for x, y in points[0]]
        results.append(result)

    return results


def _decode_with_zxing(image) -> List[Dict[str, Any]]:
    if zxingcpp is None:
        return []

    results: List[Dict[str, Any]] = []
    for barcode in zxingcpp.read_barcodes(image):
        if not barcode.text:
            continue

        result: Dict[str, Any] = {
            "data": barcode.text,
            "format": str(barcode.format),
        }

        position = getattr(barcode, "position", None)
        if position is not None:
            result["position"] = str(position)
            result["points"] = [
                [float(position.top_left.x), float(position.top_left.y)],
                [float(position.top_right.x), float(position.top_right.y)],
                [float(position.bottom_right.x), float(position.bottom_right.y)],
                [float(position.bottom_left.x), float(position.bottom_left.y)],
            ]

        results.append(result)

    return results


def _preprocess_images(image) -> List[Any]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    blurred = cv2.GaussianBlur(clahe, (3, 3), 0)

    _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adaptive = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        5,
    )

    base_images = [
        image,
        gray,
        clahe,
        otsu,
        cv2.bitwise_not(otsu),
        adaptive,
        cv2.bitwise_not(adaptive),
    ]

    attempts = []
    for base in base_images:
        for angle in (0, 90, 180, 270):
            rotated = base
            if angle == 90:
                rotated = cv2.rotate(base, cv2.ROTATE_90_CLOCKWISE)
            elif angle == 180:
                rotated = cv2.rotate(base, cv2.ROTATE_180)
            elif angle == 270:
                rotated = cv2.rotate(base, cv2.ROTATE_90_COUNTERCLOCKWISE)

            for scale in (1.0, 1.5, 2.0, 3.0):
                if scale == 1.0:
                    attempts.append(rotated)
                else:
                    attempts.append(
                        cv2.resize(
                            rotated,
                            None,
                            fx=scale,
                            fy=scale,
                            interpolation=cv2.INTER_CUBIC,
                        )
                    )

    return attempts


def read_codes_from_image(image, debug: bool = False) -> List[Dict[str, Any]]:
    detector = cv2.QRCodeDetector()
    attempts = [image] + _preprocess_images(image)

    seen = set()
    found: List[Dict[str, Any]] = []
    for index, attempt in enumerate(attempts, start=1):
        for result in _decode_with_zxing(attempt):
            key = (result.get("format", ""), result["data"])
            if key in seen:
                continue
            seen.add(key)
            found.append(result)
            if debug:
                print(f"Found {result.get('format', 'barcode')} on attempt {index}")
        if found:
            return found

        for result in _decode_with_detector(detector, attempt):
            key = ("QR Code", result["data"])
            if key in seen:
                continue
            seen.add(key)
            result.setdefault("format", "QR Code")
            found.append(result)
            if debug:
                print(f"Found QR on attempt {index}")
        if found:
            return found

    return found


def read_qr_codes(image_path: str, debug: bool = False) -> List[Dict[str, Any]]:
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Image file not found: {path}")

    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"OpenCV could not read image: {path}")

    return read_codes_from_image(image, debug=debug)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find and read QR/Data Matrix code data from an image."
    )
    parser.add_argument(
        "image",
        nargs="?",
        default=TARGET_FILE,
        help="Image path. If omitted, the TARGET_FILE environment variable is used.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print which preprocessing attempt decoded the QR code.",
    )
    args = parser.parse_args()

    if not args.image:
        parser.error("provide an image path or set TARGET_FILE")

    try:
        results = read_qr_codes(args.image, debug=args.debug)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    if not results:
        if zxingcpp is None:
            print(
                "No QR code found. Install zxing-cpp for Data Matrix support: "
                "python -m pip install zxing-cpp"
            )
        else:
            print("No QR/Data Matrix code found.")
        return 2

    if len(results) == 1:
        print(results[0]["data"])
    else:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
