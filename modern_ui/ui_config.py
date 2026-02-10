MENU = 1
SETTINGS = 2
GAME = 3
STATS = 4

STACK_GAP_RATIO = 0.015
TOP_MARGIN_RATIO = 0.16
CARD_WIDTH_RATIO = 0.08
CARD_HEIGHT_RATIO = 0.17
VISIBLE_STEP_RATIO = 0.05
ANIM_DURATION = 0.22
FPS_MS = 16

NUMS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
DIFFICULTY_TO_SUITS = {"Easy": 1, "Medium": 2, "Hard": 4}
DIFFICULTY_ORDER = ("Easy", "Medium", "Hard")
CARD_STYLE_ORDER = ("Classic", "Minimal", "Neo", "ArtDeck", "NeoGrid", "VintageGold", "SakuraInk")
TEXTURED_STYLE_ASSETS = {
    "ArtDeck": {"front_dir": "artdeck", "back_file": "artdeck_back.png"},
    "NeoGrid": {"front_dir": "neogrid", "back_file": "neogrid_back.png"},
    "VintageGold": {"front_dir": "vintagegold", "back_file": "vintagegold_back.png"},
    "SakuraInk": {"front_dir": "sakuraink", "back_file": "sakuraink_back.png"},
}
THEME_ORDER = ("Forest", "Ocean", "Sunset")
FONT_SCALE_ORDER = ("Small", "Normal", "Large", "X-Large", "Huge")
FONT_SCALE_FACTOR = {
    "Small": 0.95,
    "Normal": 1.1,
    "Large": 1.25,
    "X-Large": 1.45,
    "Huge": 1.7,
}
SUIT_SYMBOLS = ("♠", "♥", "♣", "♦")

THEMES = {
    "Forest": {
        "bg_base": "#1b4332",
        "bg_band_a": "#315d49",
        "bg_band_b": "#244636",
        "hud_text": "#f1f5f9",
        "hud_subtext": "#d1fae5",
        "deck_fill": "#2d6a4f",
        "deck_outline": "#a7f3d0",
        "slot_outline": "#99f6e4",
        "slot_valid": "#4ade80",
        "slot_invalid": "#ef4444",
        "card_front": "#f7e8bc",
        "card_back": "#334155",
        "card_border": "#0f172a",
        "card_select": "#fde047",
        "particle": ["#f8fafc", "#fde68a", "#bfdbfe", "#86efac"],
    },
    "Ocean": {
        "bg_base": "#0b2545",
        "bg_band_a": "#1f4f73",
        "bg_band_b": "#123552",
        "hud_text": "#e0f2fe",
        "hud_subtext": "#bae6fd",
        "deck_fill": "#0369a1",
        "deck_outline": "#7dd3fc",
        "slot_outline": "#67e8f9",
        "slot_valid": "#22d3ee",
        "slot_invalid": "#fb7185",
        "card_front": "#f8fafc",
        "card_back": "#1e3a8a",
        "card_border": "#082f49",
        "card_select": "#38bdf8",
        "particle": ["#e0f2fe", "#67e8f9", "#93c5fd", "#f0abfc"],
    },
    "Sunset": {
        "bg_base": "#3f1d38",
        "bg_band_a": "#7c2d4f",
        "bg_band_b": "#5b2141",
        "hud_text": "#fff7ed",
        "hud_subtext": "#fed7aa",
        "deck_fill": "#b45309",
        "deck_outline": "#fcd34d",
        "slot_outline": "#fdba74",
        "slot_valid": "#f59e0b",
        "slot_invalid": "#ef4444",
        "card_front": "#fffbeb",
        "card_back": "#7c2d12",
        "card_border": "#431407",
        "card_select": "#fb7185",
        "particle": ["#fff7ed", "#fcd34d", "#fb7185", "#fdba74"],
    },
}
