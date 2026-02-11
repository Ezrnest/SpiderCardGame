import configparser
from pathlib import Path

from modern_ui.ui_config import (
    CARD_STYLE_ORDER,
    DIFFICULTY_BUCKET_ORDER,
    FONT_SCALE_ORDER,
    LEGACY_DIFFICULTY_TO_PROFILE,
    SUIT_COUNT_ORDER,
    THEME_ORDER,
)

SETTINGS_PATH = Path(__file__).with_name("settings.ini")

DEFAULT_SETTINGS = {
    "suit_count": "2",
    "difficulty_bucket": "Medium",
    "card_style": "Classic",
    "theme_name": "Forest",
    "font_scale": "Normal",
    "save_slot": "1",
}


def _sanitize(settings):
    data = dict(DEFAULT_SETTINGS)
    data.update(settings)

    raw_suit = str(data.get("suit_count", DEFAULT_SETTINGS["suit_count"]))
    raw_bucket = str(data.get("difficulty_bucket", DEFAULT_SETTINGS["difficulty_bucket"]))
    legacy_difficulty = str(data.get("difficulty", "")).strip()
    if legacy_difficulty in LEGACY_DIFFICULTY_TO_PROFILE:
        legacy_suit, legacy_bucket = LEGACY_DIFFICULTY_TO_PROFILE[legacy_difficulty]
        if raw_suit in ("", "None"):
            raw_suit = str(legacy_suit)
        if raw_bucket in ("", "None"):
            raw_bucket = legacy_bucket

    try:
        suit_count = int(raw_suit)
    except Exception:
        suit_count = int(DEFAULT_SETTINGS["suit_count"])
    if suit_count not in SUIT_COUNT_ORDER:
        suit_count = int(DEFAULT_SETTINGS["suit_count"])
    data["suit_count"] = str(suit_count)

    if raw_bucket not in DIFFICULTY_BUCKET_ORDER:
        raw_bucket = DEFAULT_SETTINGS["difficulty_bucket"]
    data["difficulty_bucket"] = raw_bucket

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
        "suit_count": parser["ui"].get("suit_count", ""),
        "difficulty_bucket": parser["ui"].get("difficulty_bucket", ""),
        # Legacy field for migration from old builds.
        "difficulty": parser["ui"].get("difficulty", ""),
        "card_style": parser["ui"].get("card_style", DEFAULT_SETTINGS["card_style"]),
        "theme_name": parser["ui"].get("theme_name", DEFAULT_SETTINGS["theme_name"]),
        "font_scale": parser["ui"].get("font_scale", DEFAULT_SETTINGS["font_scale"]),
        "save_slot": parser["ui"].get("save_slot", DEFAULT_SETTINGS["save_slot"]),
    }
    data = _sanitize(raw)
    data.pop("difficulty", None)
    return data


def save_settings(settings):
    data = _sanitize(settings)
    data.pop("difficulty", None)
    parser = configparser.ConfigParser()
    parser["ui"] = data
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS_PATH.open("w", encoding="utf-8") as f:
        parser.write(f)
