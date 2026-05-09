import json
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "inspection_settings.json"
PIN_APP_PATH = APP_DIR / "pin_inspection_app.py"


def load_config():
    if not CONFIG_PATH.is_file():
        return {"cameras": {}}
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return {"cameras": {}}


def save_config(config):
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        json.dump(config, file, indent=2)
