import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modern_ui import game_store


class GameStoreTestCase(unittest.TestCase):
    def test_clear_game_removes_existing_slot_file(self):
        with tempfile.TemporaryDirectory() as td:
            slot_path = Path(td) / "savegame_slot1.txt"
            slot_path.write_text("dummy", encoding="utf-8")
            with patch.object(game_store, "_slot_path", return_value=slot_path):
                self.assertTrue(game_store.has_saved_game(1))
                self.assertTrue(game_store.clear_game(1))
                self.assertFalse(game_store.has_saved_game(1))

    def test_clear_game_is_idempotent_for_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            slot_path = Path(td) / "savegame_slot1.txt"
            with patch.object(game_store, "_slot_path", return_value=slot_path):
                self.assertTrue(game_store.clear_game(1))
                self.assertFalse(game_store.has_saved_game(1))


if __name__ == "__main__":
    unittest.main()
