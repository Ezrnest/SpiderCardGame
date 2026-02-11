import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modern_ui import seed_pool_store, settings_store, stats_store
from modern_ui.modern_interface import ModernTkInterface


class ModernUiSeedAndSettingsTestCase(unittest.TestCase):
    @staticmethod
    def _ui_settings():
        return {
            "suit_count": "2",
            "difficulty_bucket": "Medium",
            "card_style": "Classic",
            "theme_name": "Forest",
            "font_scale": "Normal",
            "save_slot": "1",
        }

    def test_settings_load_migrates_legacy_difficulty(self):
        with tempfile.TemporaryDirectory() as td:
            ini_path = Path(td) / "settings.ini"
            ini_path.write_text(
                "[ui]\n"
                "difficulty = Hard\n"
                "card_style = Classic\n"
                "theme_name = Forest\n"
                "font_scale = Normal\n"
                "save_slot = 1\n",
                encoding="utf-8",
            )
            with patch.object(settings_store, "SETTINGS_PATH", ini_path):
                data = settings_store.load_settings()
        self.assertEqual("4", data["suit_count"])
        self.assertEqual("Hard", data["difficulty_bucket"])

    def test_settings_save_writes_new_fields(self):
        with tempfile.TemporaryDirectory() as td:
            ini_path = Path(td) / "settings.ini"
            with patch.object(settings_store, "SETTINGS_PATH", ini_path):
                settings_store.save_settings(
                    {
                        "suit_count": "3",
                        "difficulty_bucket": "Medium",
                        "card_style": "Neo",
                        "theme_name": "Ocean",
                        "font_scale": "Large",
                        "save_slot": "2",
                        "difficulty": "Easy",
                    }
                )
            text = ini_path.read_text(encoding="utf-8")
        self.assertIn("suit_count = 3", text)
        self.assertIn("difficulty_bucket = Medium", text)
        self.assertNotIn("difficulty = ", text)

    def test_stats_migrate_legacy_by_difficulty(self):
        legacy = {
            "overall": {"games_started": 5},
            "by_difficulty": {
                "Easy": {"games_started": 1},
                "Medium": {"games_started": 3},
                "Hard": {"games_started": 1},
            },
        }
        data = stats_store._sanitize(legacy)
        self.assertEqual(5, data["overall"]["games_started"])
        self.assertEqual(1, data["by_profile"][stats_store.profile_key(1, "Easy")]["games_started"])
        self.assertEqual(3, data["by_profile"][stats_store.profile_key(2, "Medium")]["games_started"])
        self.assertEqual(1, data["by_profile"][stats_store.profile_key(4, "Hard")]["games_started"])

    def test_stats_record_updates_profile_bucket(self):
        stats = stats_store._default_stats()
        stats = stats_store.record_game_started(stats, 3, "Hard")
        stats = stats_store.record_game_won(stats, 3, "Hard", 12.5, 33)
        stats = stats_store.record_game_lost(stats, 3, "Hard")
        key = stats_store.profile_key(3, "Hard")
        bucket = stats["by_profile"][key]
        self.assertEqual(1, bucket["games_started"])
        self.assertEqual(1, bucket["games_won"])
        self.assertEqual(33, bucket["total_actions"])
        self.assertEqual(0, bucket["current_streak"])

    def test_seed_pool_load_and_pick(self):
        with tempfile.TemporaryDirectory() as td:
            pool_path = Path(td) / "seed_pool_2s.json"
            pool_path.write_text(
                '{"buckets":{"Easy":[11,"12","bad"],"Medium":[],"Hard":[21,22]}}',
                encoding="utf-8",
            )
            with patch.object(seed_pool_store, "seed_pool_path", return_value=pool_path):
                pools = seed_pool_store.load_seed_pool_buckets(2)
                picked = seed_pool_store.choose_seed_for_bucket(2, "Hard", rng=random.Random(1))
        self.assertEqual([11, 12], pools["Easy"])
        self.assertEqual([], pools["Medium"])
        self.assertIn(picked, {21, 22})

    def test_seed_pool_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            pool_path = Path(td) / "missing_seed_pool_4s.json"
            with patch.object(seed_pool_store, "seed_pool_path", return_value=pool_path), patch.object(
                seed_pool_store, "_legacy_seed_pool_path", return_value=pool_path
            ):
                picked = seed_pool_store.choose_seed_for_bucket(4, "Hard", rng=random.Random(1))
        self.assertIsNone(picked)

    def test_build_config_uses_bucket_seed_when_available(self):
        with patch("modern_ui.modern_interface.load_settings", return_value=self._ui_settings()):
            ui = ModernTkInterface()
        ui.suit_count = 3
        ui.difficulty_bucket = "Hard"
        with patch("modern_ui.modern_interface.choose_seed_for_bucket", return_value=987654):
            cfg = ui.build_config(daily=False)
        self.assertEqual(3, cfg.suits)
        self.assertEqual(987654, cfg.seed)
        self.assertEqual(987654, ui.current_seed)
        self.assertEqual("bucket", ui.seed_source)

    def test_build_config_falls_back_to_random_when_bucket_empty(self):
        with patch("modern_ui.modern_interface.load_settings", return_value=self._ui_settings()):
            ui = ModernTkInterface()
        ui.suit_count = 3
        ui.difficulty_bucket = "Hard"
        with patch("modern_ui.modern_interface.choose_seed_for_bucket", return_value=None):
            cfg = ui.build_config(daily=False)
        self.assertEqual(3, cfg.suits)
        self.assertIsNone(cfg.seed)
        self.assertIsNone(ui.current_seed)
        self.assertEqual("random", ui.seed_source)


if __name__ == "__main__":
    unittest.main()
