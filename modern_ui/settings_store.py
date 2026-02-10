import configparser
from pathlib import Path

from modern_ui.ui_config import CARD_STYLE_ORDER, DIFFICULTY_ORDER, FONT_SCALE_ORDER, THEME_ORDER

SETTINGS_PATH = Path(__file__).with_name("settings.ini")

DEFAULT_SETTINGS = {
    "difficulty": "Medium",
    "card_style": "Classic",
    "theme_name": "Forest",
    "font_scale": "Normal",
    "save_slot": "1",
}


def _sanitize(settings):
    data = dict(DEFAULT_SETTINGS)
    data.update(settings)
    if data["difficulty"] not in DIFFICULTY_ORDER:
        data["difficulty"] = DEFAULT_SETTINGS["difficulty"]
    if data["card_style"] not in CARD_STYLE_ORDER:
        data["card_style"] = DEFAULT_SETTINGS["card_style"]
    if data["theme_name"] not in THEME_ORDER:
        data["theme_name"] = DEFAULT_SETTINGS["theme_name"]
    if data["font_scale"] not in FONT_SCALE_ORDER:
        data["font_scale"] = DEFAULT_SETTINGS["font_scale"]
    try:
        slot = int(data["save_slot"])
    except Exception:
        slot = int(DEFAULT_SETTINGS["save_slot"])
    if slot < 1:
        slot = 1
    if slot > 3:
        slot = 3
    data["save_slot"] = str(slot)
    return data


def load_settings():
    parser = configparser.ConfigParser()
    if not SETTINGS_PATH.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        parser.read(SETTINGS_PATH, encoding="utf-8")
    except Exception:
        return dict(DEFAULT_SETTINGS)
    if "ui" not in parser:
        return dict(DEFAULT_SETTINGS)
    raw = {
        "difficulty": parser["ui"].get("difficulty", DEFAULT_SETTINGS["difficulty"]),
        "card_style": parser["ui"].get("card_style", DEFAULT_SETTINGS["card_style"]),
        "theme_name": parser["ui"].get("theme_name", DEFAULT_SETTINGS["theme_name"]),
        "font_scale": parser["ui"].get("font_scale", DEFAULT_SETTINGS["font_scale"]),
        "save_slot": parser["ui"].get("save_slot", DEFAULT_SETTINGS["save_slot"]),
    }
    return _sanitize(raw)


def save_settings(settings):
    data = _sanitize(settings)
    parser = configparser.ConfigParser()
    parser["ui"] = data
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS_PATH.open("w", encoding="utf-8") as f:
        parser.write(f)
