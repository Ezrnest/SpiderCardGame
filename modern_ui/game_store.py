from pathlib import Path

from base.Core import Core, loadGameFromFile, saveGameToFile

SLOT_COUNT = 3
SAVE_PREFIX = "savegame_slot"
SAVE_SUFFIX = ".txt"


def _slot_path(slot: int) -> Path:
    return Path(__file__).with_name(f"{SAVE_PREFIX}{slot}{SAVE_SUFFIX}")


def _valid_slot(slot: int) -> int:
    try:
        slot_int = int(slot)
    except Exception:
        slot_int = 1
    if slot_int < 1:
        slot_int = 1
    if slot_int > SLOT_COUNT:
        slot_int = SLOT_COUNT
    return slot_int


def has_saved_game(slot: int = 1) -> bool:
    path = _slot_path(_valid_slot(slot))
    return path.exists() and path.is_file()


def save_game(core: Core, slot: int = 1) -> bool:
    path = _slot_path(_valid_slot(slot))
    try:
        saveGameToFile(core, str(path))
        return True
    except Exception:
        return False


def load_game(slot: int = 1) -> Core | None:
    path = _slot_path(_valid_slot(slot))
    if not path.exists() or not path.is_file():
        return None
    try:
        return loadGameFromFile(str(path))
    except Exception:
        return None


def list_slot_status() -> list[dict]:
    rows = []
    for slot in range(1, SLOT_COUNT + 1):
        path = _slot_path(slot)
        exists = path.exists() and path.is_file()
        rows.append({"slot": slot, "exists": exists, "path": str(path.name)})
    return rows
