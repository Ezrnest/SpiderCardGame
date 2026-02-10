from pathlib import Path

from base.Core import Core, loadGameFromFile, saveGameToFile

SAVE_PATH = Path(__file__).with_name("savegame.txt")


def has_saved_game() -> bool:
    return SAVE_PATH.exists() and SAVE_PATH.is_file()


def save_game(core: Core) -> bool:
    try:
        saveGameToFile(core, str(SAVE_PATH))
        return True
    except Exception:
        return False


def load_game() -> Core | None:
    if not has_saved_game():
        return None
    try:
        return loadGameFromFile(str(SAVE_PATH))
    except Exception:
        return None

