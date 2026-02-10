import math
import random
import time
from datetime import date
from pathlib import Path
from tkinter import BOTH, Canvas, Tk, messagebox

from base.Core import Card, Core, DUMMY_PLAYER, GameConfig, encodeStack
from base.Interface import Interface
from modern_ui.adapter import CoreAdapter
from modern_ui.card_face import CardFaceRenderer
from modern_ui.entities import CollectCard, DragState, MovingCard, Particle, VictoryCard
from modern_ui.game_store import SLOT_COUNT, has_saved_game, list_slot_status, load_game, save_game
from modern_ui.settings_store import load_settings, save_settings
from modern_ui.stats_store import load_stats, record_game_lost, record_game_started, record_game_won, save_stats
from modern_ui.ui_config import (
    ANIM_DURATION,
    CARD_HEIGHT_RATIO,
    CARD_STYLE_ORDER,
    CARD_WIDTH_RATIO,
    DIFFICULTY_ORDER,
    DIFFICULTY_TO_SUITS,
    FONT_SCALE_FACTOR,
    FONT_SCALE_ORDER,
    FPS_MS,
    GAME,
    MENU,
    SETTINGS,
    STATS,
    STACK_GAP_RATIO,
    TEXTURED_STYLE_ASSETS,
    THEMES,
    THEME_ORDER,
    TOP_MARGIN_RATIO,
    VISIBLE_STEP_RATIO,
)

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

if Image is not None:
    try:
        RESAMPLE = Image.Resampling.LANCZOS
    except Exception:
        RESAMPLE = Image.LANCZOS
    try:
        ROTATE_RESAMPLE = Image.Resampling.BICUBIC
    except Exception:
        ROTATE_RESAMPLE = Image.BICUBIC
else:
    RESAMPLE = None
    ROTATE_RESAMPLE = None


class ModernTkInterface(Interface):
    def __init__(self, width=1200, height=760):
        super().__init__()
        self.width = width
        self.height = height
        self.root = None
        self.canvas = None
        self.stage = MENU

        self.vm = None
        self.message = ""

        self.difficulty = "Medium"
        self.card_style = "Classic"
        self.theme_name = "Forest"
        self.font_scale = "Normal"
        self.daily_mode = False
        self.test_mode = False
        self.current_seed = None
        self.save_slot = 1

        self.anim_queue = []
        self.anim_cards = []
        self.anim_start = 0.0
        self.anim_duration = ANIM_DURATION

        self.drag = None
        self.hover_drop_stack = None
        self.hover_drop_valid = False
        self.pending_move_anim = None

        self.particles = []
        self.collect_cards = []
        self.victory_cards = []
        self.fx_rng = random.Random()
        self.last_win_firework = 0.0
        self.last_drag_spark = 0.0

        self.active_buttons = []
        self.can_continue = False
        self.slot_status = []
        self.stats = load_stats()
        self.current_game_started_at = None
        self.current_game_actions = 0
        self.current_game_recorded = False
        self.victory_started_at = 0.0
        self.victory_anim_duration = 2.8
        self.victory_anim_active = False
        self.victory_panel_visible = False
        self.victory_summary = {}
        self.card_renderer = CardFaceRenderer()
        self.style_back_images = {}
        self.pil_back_source = None
        self.front_images = {}
        self.pil_front_sources = {}
        self.runtime_tk_images = []
        self.rotated_sprite_cache = {}
        self.needs_redraw = True
        self.cached_card_px = None
        self.load_persisted_settings()

    def run(self):
        self.root = Tk()
        self.root.title("Spider Card Modern")
        self.root.resizable(True, True)
        self.canvas = Canvas(self.root, width=self.width, height=self.height, highlightthickness=0, bd=0)
        self.canvas.pack(expand=1, fill=BOTH)

        self.root.bind("<Configure>", self.on_resize)
        self.root.bind("<Button-1>", self.on_press)
        self.root.bind("<Button-2>", self.on_right_click)
        self.root.bind("<Button-3>", self.on_right_click)
        self.root.bind("<B1-Motion>", self.on_drag)
        self.root.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Key>", self.on_key)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_style_assets()

        self.open_menu()
        self.tick()
        self.root.mainloop()

    @property
    def theme(self):
        return THEMES[self.theme_name]

    def load_persisted_settings(self):
        settings = load_settings()
        self.difficulty = settings["difficulty"]
        self.card_style = settings["card_style"]
        self.theme_name = settings["theme_name"]
        self.font_scale = settings["font_scale"]
        self.save_slot = int(settings["save_slot"])

    def persist_settings(self):
        save_settings(
            {
                "difficulty": self.difficulty,
                "card_style": self.card_style,
                "theme_name": self.theme_name,
                "font_scale": self.font_scale,
                "save_slot": str(self.save_slot),
            }
        )

    def load_style_images(self):
        self.style_back_images = {}
        self.pil_back_source = None
        self.rotated_sprite_cache.clear()
        if Image is None or ImageTk is None:
            return
        cw, ch = self.card_pixel_size()
        style_asset = TEXTURED_STYLE_ASSETS.get(self.card_style)
        if style_asset is None:
            return
        back_path = Path(__file__).with_name("assets").joinpath("card_backs", style_asset["back_file"])
        if back_path.exists():
            try:
                base = Image.open(back_path).convert("RGBA")
                self.pil_back_source = base
                img = base.resize((cw, ch), RESAMPLE)
                self.style_back_images[self.card_style] = ImageTk.PhotoImage(img)
            except Exception:
                pass

    def load_front_images(self):
        self.front_images = {}
        self.pil_front_sources = {}
        self.rotated_sprite_cache.clear()
        style_asset = TEXTURED_STYLE_ASSETS.get(self.card_style)
        if style_asset is None:
            return
        front_dir = Path(__file__).with_name("assets").joinpath("card_fronts", style_asset["front_dir"])
        if Image is None or ImageTk is None:
            return
        cw, ch = self.card_pixel_size()
        for suit in range(4):
            for num in range(13):
                path = front_dir / f"s{suit}_n{num}.png"
                if not path.exists():
                    continue
                try:
                    base = Image.open(path).convert("RGBA")
                    self.pil_front_sources[(suit, num)] = base
                    img = base.resize((cw, ch), RESAMPLE)
                    self.front_images[(suit, num)] = ImageTk.PhotoImage(img)
                except Exception:
                    continue

    def refresh_style_assets(self):
        self.cached_card_px = self.card_pixel_size()
        self.rotated_sprite_cache.clear()
        self.load_style_images()
        if self.card_style in TEXTURED_STYLE_ASSETS:
            self.load_front_images()
        else:
            self.front_images = {}
            self.pil_front_sources = {}
        self.needs_redraw = True

    def request_redraw(self):
        self.needs_redraw = True

    def fs(self, base):
        factor = FONT_SCALE_FACTOR[self.font_scale]
        return max(8, int(base * factor))

    def on_close(self):
        if not messagebox.askyesno("Exit", "Exit the game now?"):
            return
        if self.stage == GAME and self.core is not None and self.vm is not None:
            self.save_current_game()
        self.persist_settings()
        self.root.destroy()

    def confirm_overwrite_saved_game(self, mode_label):
        if not has_saved_game(self.save_slot):
            return True
        return messagebox.askyesno(
            "Overwrite Saved Game",
            f"Starting {mode_label} will overwrite saved slot {self.save_slot}. Continue?",
        )

    def cycle_value(self, order, current):
        idx = order.index(current)
        return order[(idx + 1) % len(order)]

    def open_menu(self):
        self.stage = MENU
        self.drag = None
        self.anim_cards.clear()
        self.anim_queue.clear()
        self.active_buttons = []
        self.slot_status = list_slot_status()
        self.can_continue = has_saved_game(self.save_slot)
        self.message = "Start new game, continue saved game, daily challenge, or open settings."
        self.request_redraw()

    def open_stats(self):
        self.stage = STATS
        self.active_buttons = []
        self.message = "Statistics overview."
        self.request_redraw()

    def open_settings(self):
        self.stage = SETTINGS
        self.active_buttons = []
        self.message = "Configure difficulty, card style, and theme."
        self.request_redraw()

    def cycle_save_slot(self):
        self.save_slot += 1
        if self.save_slot > SLOT_COUNT:
            self.save_slot = 1
        self.persist_settings()
        self.slot_status = list_slot_status()
        self.can_continue = has_saved_game(self.save_slot)
        self.request_redraw()

    def begin_game_tracking(self):
        if self.test_mode:
            self.current_game_started_at = None
            self.current_game_actions = 0
            self.current_game_recorded = True
            return
        self.current_game_started_at = time.time()
        self.current_game_actions = 0
        self.current_game_recorded = False
        self.stats = record_game_started(self.stats, self.difficulty)
        save_stats(self.stats)

    def reset_victory_state(self):
        self.victory_started_at = 0.0
        self.victory_anim_active = False
        self.victory_panel_visible = False
        self.victory_summary = {}
        self.victory_cards.clear()

    def mark_game_won_if_needed(self):
        if self.test_mode or self.current_game_recorded:
            return
        if self.current_game_started_at is None:
            return
        duration = time.time() - self.current_game_started_at
        self.stats = record_game_won(self.stats, self.difficulty, duration, self.current_game_actions)
        save_stats(self.stats)
        self.current_game_recorded = True

    def mark_game_lost_if_needed(self):
        if self.test_mode or self.current_game_recorded:
            return
        if self.current_game_started_at is None:
            return
        self.stats = record_game_lost(self.stats, self.difficulty)
        save_stats(self.stats)
        self.current_game_recorded = True

    def build_config(self, daily=False):
        cfg = GameConfig()
        cfg.suits = DIFFICULTY_TO_SUITS[self.difficulty]
        if daily:
            today = date.today()
            base_seed = int(today.strftime("%Y%m%d"))
            cfg.seed = base_seed * 10 + cfg.suits
            self.current_seed = cfg.seed
            self.daily_mode = True
        else:
            self.current_seed = None
            self.daily_mode = False
        return cfg

    def start_new_game(self, daily=False):
        if self.stage == GAME:
            self.mark_game_lost_if_needed()
        core = Core()
        core.registerInterface(self)
        core.registerPlayer(DUMMY_PLAYER)
        core.startGame(self.build_config(daily))
        self.vm = CoreAdapter.snapshot(core)
        self.test_mode = False

        self.stage = GAME
        self.drag = None
        self.hover_drop_stack = None
        self.hover_drop_valid = False
        self.pending_move_anim = None

        self.anim_queue.clear()
        self.anim_cards.clear()
        self.particles.clear()
        self.collect_cards.clear()
        self.reset_victory_state()

        mode = "Daily Challenge" if self.daily_mode else "Normal"
        self.message = f"{mode} started ({self.difficulty}). Drag cards to move."
        self.begin_game_tracking()
        self.save_current_game()
        self.request_redraw()

    def continue_game(self):
        core = load_game(self.save_slot)
        if core is None:
            self.can_continue = False
            self.message = f"No valid saved game in slot {self.save_slot}."
            self.request_redraw()
            return
        core.registerInterface(self)
        core.registerPlayer(DUMMY_PLAYER)
        core.resumeGame()
        self.vm = CoreAdapter.snapshot(core)
        self.stage = GAME
        self.drag = None
        self.hover_drop_stack = None
        self.hover_drop_valid = False
        self.pending_move_anim = None
        self.anim_queue.clear()
        self.anim_cards.clear()
        self.particles.clear()
        self.collect_cards.clear()
        self.reset_victory_state()
        self.test_mode = False
        self.daily_mode = False
        self.current_seed = None
        self.current_game_started_at = time.time()
        self.current_game_actions = 0
        self.current_game_recorded = False
        self.message = f"Continued saved game from slot {self.save_slot}."
        self.request_redraw()

    def save_current_game(self):
        if self.core is None:
            return
        if self.test_mode:
            return
        save_game(self.core, self.save_slot)

    @staticmethod
    def visible_card(suit, num):
        card = Card.fromSuitAndNum(suit, num)
        card.hidden = False
        return card

    def build_test_stacks(self):
        suit = 0  # Spade
        stack0 = [self.visible_card(suit, n) for n in range(12, 0, -1)]  # K..2
        stack1 = [self.visible_card(suit, 0)]  # A, move this to stack0 to finish one full pile
        stack2 = []
        stack3 = []
        stack4 = []
        stack5 = []
        stack6 = []
        stack7 = []
        stack8 = []
        stack9 = []
        return [stack0, stack1, stack2, stack3, stack4, stack5, stack6, stack7, stack8, stack9]

    def start_test_game(self):
        stacks = self.build_test_stacks()
        lines = ["0", "False", encodeStack([])]
        lines.extend(encodeStack(stack) for stack in stacks)
        core = Core()
        core.loadGameFromLines(lines)
        core.registerInterface(self)
        core.registerPlayer(DUMMY_PLAYER)
        core.resumeGame()
        self.vm = CoreAdapter.snapshot(core)

        self.stage = GAME
        self.drag = None
        self.hover_drop_stack = None
        self.hover_drop_valid = False
        self.pending_move_anim = None
        self.anim_queue.clear()
        self.anim_cards.clear()
        self.particles.clear()
        self.collect_cards.clear()
        self.reset_victory_state()
        self.test_mode = True
        self.daily_mode = False
        self.current_seed = None
        self.current_game_started_at = None
        self.current_game_actions = 0
        self.current_game_recorded = True
        self.message = "Test duel: move A♠ from stack 1 onto stack 0 to win in one move."
        self.request_redraw()

    def onStart(self):
        self.vm = CoreAdapter.snapshot(self.core)
        self.request_redraw()

    def onWin(self):
        self.vm = CoreAdapter.snapshot(self.core)
        duration = 0.0
        if self.current_game_started_at is not None:
            duration = max(0.0, time.time() - self.current_game_started_at)
        self.victory_summary = {
            "moves": int(self.current_game_actions),
            "duration_sec": duration,
            "difficulty": self.difficulty,
            "mode": "Daily" if self.daily_mode else ("Test" if self.test_mode else "Normal"),
        }
        self.fx_rng.seed(time.time_ns())
        self.victory_started_at = time.time()
        self.victory_anim_active = True
        self.victory_panel_visible = False
        self.message = "Victory animation..."
        self.mark_game_won_if_needed()
        self.spawn_firework_burst(self.width * 0.5, self.height * 0.3, 34)
        self.spawn_firework_burst(self.width * 0.35, self.height * 0.26, 28)
        self.spawn_firework_burst(self.width * 0.65, self.height * 0.26, 28)
        self.request_redraw()

    def onEvent(self, event):
        self.vm = CoreAdapter.snapshot(self.core)
        self.anim_queue.append(CoreAdapter.event_to_animation(event))
        self.save_current_game()
        self.request_redraw()
        super().onEvent(event)

    def onUndoEvent(self, event):
        self.vm = CoreAdapter.snapshot(self.core)
        self.anim_cards.clear()
        self.anim_queue.clear()
        self.drag = None
        self.message = "Undo applied."
        self.save_current_game()
        self.request_redraw()
        super().onUndoEvent(event)

    def notifyRedraw(self):
        self.request_redraw()

    def on_resize(self, event):
        if event.widget != self.root:
            return
        old_card_px = self.cached_card_px
        self.width = event.width
        self.height = event.height
        new_card_px = self.card_pixel_size()
        if old_card_px != new_card_px:
            self.refresh_style_assets()
        self.request_redraw()

    def on_key(self, event):
        key = event.keysym.lower()
        if key == "m":
            self.open_menu()
            return

        if self.stage == MENU:
            if key in ("n", "return"):
                if not self.confirm_overwrite_saved_game("a new game"):
                    return
                self.start_new_game(daily=False)
            elif key == "t":
                self.start_test_game()
            elif key == "c":
                self.continue_game()
            elif key == "d":
                if not self.confirm_overwrite_saved_game("a daily challenge"):
                    return
                self.start_new_game(daily=True)
            elif key == "s":
                self.open_settings()
            elif key == "p":
                self.open_stats()
            elif key == "l":
                self.cycle_save_slot()
            self.request_redraw()
            return

        if self.stage == SETTINGS:
            if key == "escape":
                self.open_menu()
            elif key == "1":
                self.difficulty = "Easy"
                self.persist_settings()
            elif key == "2":
                self.difficulty = "Medium"
                self.persist_settings()
            elif key == "4":
                self.difficulty = "Hard"
                self.persist_settings()
            elif key == "c":
                self.card_style = self.cycle_value(CARD_STYLE_ORDER, self.card_style)
                self.refresh_style_assets()
                self.persist_settings()
            elif key == "t":
                self.theme_name = self.cycle_value(THEME_ORDER, self.theme_name)
                self.persist_settings()
            elif key == "f":
                self.font_scale = self.cycle_value(FONT_SCALE_ORDER, self.font_scale)
                self.persist_settings()
            elif key == "l":
                self.cycle_save_slot()
            self.request_redraw()
            return

        if self.stage == STATS:
            if key in ("escape", "p"):
                self.open_menu()
            else:
                self.request_redraw()
            return

        if self.stage == GAME:
            if key == "n":
                if not self.confirm_overwrite_saved_game("a new game"):
                    return
                self.start_new_game(daily=False)
            elif key == "d":
                if not self.core.askDeal():
                    self.message = "No cards left in base."
                else:
                    self.current_game_actions += 1
            elif key == "u":
                if not self.core.askUndo():
                    self.message = "Cannot undo."
            elif key == "r":
                if not self.core.askRedo():
                    self.message = "Cannot redo."
            elif key == "s":
                self.open_settings()
            elif key == "h":
                self.message = self.build_hint_message()
            elif key == "p":
                self.open_stats()
            self.request_redraw()

    def on_press(self, event):
        if self.stage in (MENU, SETTINGS, STATS):
            self.on_page_click(event.x, event.y)
            return

        if self.vm is None or self.anim_cards:
            return
        if self.victory_anim_active or self.victory_panel_visible:
            return

        if self.is_point_in_deck(event.x, event.y):
            if not self.core.askDeal():
                self.message = "No cards left in base."
            else:
                self.message = "Dealt from deck."
                self.current_game_actions += 1
            self.request_redraw()
            return

        hit = self.find_stack_and_index(event.x, event.y)
        if hit is None:
            return
        stack_idx, card_idx = hit
        if not self.core.isValidSequence((stack_idx, card_idx)):
            self.message = "This sequence cannot be moved."
            self.request_redraw()
            return

        src_x, src_y = self.card_position(stack_idx, card_idx)
        stack_cards = list(self.vm.stacks[stack_idx].cards[card_idx:])
        self.drag = DragState(
            src_stack=stack_idx,
            src_idx=card_idx,
            cards=stack_cards,
            anchor_x=event.x - src_x,
            anchor_y=event.y - src_y,
            x=src_x,
            y=src_y,
        )
        self.hover_drop_stack = None
        self.hover_drop_valid = False
        self.message = f"Dragging {len(stack_cards)} card(s)..."
        self.spawn_spark_shower(src_x, src_y, 8)
        self.request_redraw()

    def on_right_click(self, event):
        if self.stage != GAME:
            return
        if self.drag is not None:
            self.drag = None
            self.hover_drop_stack = None
            self.hover_drop_valid = False
            self.request_redraw()
        if not self.core.askUndo():
            self.message = "Cannot undo."
            self.request_redraw()

    def on_drag(self, event):
        if self.stage != GAME or self.drag is None:
            return

        target_stack = self.find_drop_stack(event.x)
        self.hover_drop_stack = target_stack
        self.hover_drop_valid = self.can_drop_to(target_stack)

        target_x = event.x - self.drag.anchor_x
        if self.hover_drop_valid and target_stack is not None:
            sx, _ = self.stack_origin(target_stack)
            target_x = sx

        self.drag.x = target_x
        self.drag.y = event.y - self.drag.anchor_y
        self.request_redraw()

        now = time.time()
        if now - self.last_drag_spark > 0.04:
            self.last_drag_spark = now
            self.spawn_spark_shower(
                self.drag.x + self.card_size()[0] * 0.5,
                self.drag.y + self.card_size()[1] * 0.35,
                2,
                speed=(0.2, 1.2),
                ttl=(0.18, 0.35),
            )

    def on_release(self, event):
        if self.stage != GAME or self.drag is None:
            return

        released_drag = self.drag
        drop_stack = self.hover_drop_stack if self.hover_drop_stack is not None else self.find_drop_stack(event.x)
        src = (released_drag.src_stack, released_drag.src_idx)
        move_count = len(released_drag.cards)
        release_x = released_drag.x
        release_y = released_drag.y

        self.drag = None
        self.hover_drop_stack = None
        self.hover_drop_valid = False

        if drop_stack is None:
            self.message = "Move canceled."
            self.request_redraw()
            return

        self.pending_move_anim = {
            "src": src,
            "dest_stack": drop_stack,
            "count": move_count,
            "release_x": release_x,
            "release_y": release_y,
        }

        if not self.core.askMove(src, drop_stack):
            self.pending_move_anim = None
            self.message = "Move rejected by rules."
            sx, sy = self.stack_origin(drop_stack)
            self.spawn_spark_shower(sx + self.card_size()[0] * 0.5, sy + 20, 10)
        else:
            self.current_game_actions += 1
            sx, sy = self.stack_origin(drop_stack)
            self.spawn_spark_shower(sx + self.card_size()[0] * 0.5, sy + 20, 8)
        self.request_redraw()

    def on_page_click(self, x, y):
        for button in self.active_buttons:
            x1, y1, x2, y2 = button["rect"]
            if x1 <= x <= x2 and y1 <= y <= y2:
                if not button.get("enabled", True):
                    return
                action = button["action"]
                if action == "new":
                    if not self.confirm_overwrite_saved_game("a new game"):
                        return
                    self.start_new_game(daily=False)
                elif action == "continue":
                    self.continue_game()
                elif action == "daily":
                    if not self.confirm_overwrite_saved_game("a daily challenge"):
                        return
                    self.start_new_game(daily=True)
                elif action == "settings":
                    self.open_settings()
                elif action == "stats":
                    self.open_stats()
                elif action == "save_slot":
                    self.cycle_save_slot()
                elif action == "difficulty":
                    self.difficulty = self.cycle_value(DIFFICULTY_ORDER, self.difficulty)
                    self.persist_settings()
                elif action == "card_style":
                    self.card_style = self.cycle_value(CARD_STYLE_ORDER, self.card_style)
                    self.refresh_style_assets()
                    self.persist_settings()
                elif action == "theme":
                    self.theme_name = self.cycle_value(THEME_ORDER, self.theme_name)
                    self.persist_settings()
                elif action == "font_scale":
                    self.font_scale = self.cycle_value(FONT_SCALE_ORDER, self.font_scale)
                    self.persist_settings()
                elif action == "back_menu":
                    self.open_menu()
                self.request_redraw()
                return

    def tick(self):
        self.consume_animation_queue()
        self.update_effects()
        if self.stage == GAME and self.vm and self.vm.game_ended and self.victory_anim_active:
            now = time.time()
            if now - self.last_win_firework > 0.18:
                self.last_win_firework = now
                x = random.uniform(self.width * 0.18, self.width * 0.82)
                y = random.uniform(self.height * 0.12, self.height * 0.50)
                self.spawn_firework_burst(x, y, 18)
                self.spawn_victory_cards_burst(10)
            if now - self.victory_started_at >= self.victory_anim_duration:
                self.victory_anim_active = False
                self.victory_panel_visible = True
                self.message = "Victory summary ready. Press N for new game or M for menu."
                self.request_redraw()

        has_active_fx = bool(
            self.anim_cards
            or self.particles
            or self.collect_cards
            or self.victory_cards
            or self.victory_anim_active
        )
        if self.needs_redraw or has_active_fx:
            self.draw()
            self.needs_redraw = False
        self.root.after(FPS_MS, self.tick)

    def format_stats_line(self, title, bucket):
        started = int(bucket["games_started"])
        won = int(bucket["games_won"])
        win_rate = (won / started * 100.0) if started > 0 else 0.0
        avg_actions = (bucket["total_actions"] / won) if won > 0 else 0.0
        avg_duration = (bucket["total_duration_sec"] / won) if won > 0 else 0.0
        return (
            f"{title}: played {started}, won {won}, win {win_rate:.1f}% | "
            f"avg moves {avg_actions:.1f}, avg time {avg_duration:.1f}s | "
            f"streak {int(bucket['current_streak'])} (best {int(bucket['best_streak'])})"
        )

    def build_hint_candidates(self, limit=3):
        if self.core is None or self.vm is None:
            return []
        candidates = []
        stacks = self.core.stacks
        for s_idx, stack in enumerate(stacks):
            for idx in range(len(stack)):
                src = (s_idx, idx)
                if not self.core.isValidSequence(src):
                    continue
                moved_len = len(stack) - idx
                src_card = stack[idx]
                reveal_bonus = 40 if idx > 0 and stack[idx - 1].hidden else 0
                for d_idx in range(len(stacks)):
                    if d_idx == s_idx:
                        continue
                    if not self.core.canMove(src, d_idx):
                        continue
                    dest_stack = stacks[d_idx]
                    score = 30 + moved_len * 2 + reveal_bonus
                    tags = []
                    if reveal_bonus > 0:
                        tags.append("reveals hidden")
                    if len(dest_stack) == 0:
                        score -= 8
                        tags.append("uses empty column")
                    else:
                        top = dest_stack[-1]
                        if top.suit == src_card.suit:
                            score += 5
                            tags.append("same-suit link")
                    risk = "low"
                    if "uses empty column" in tags and moved_len <= 2:
                        risk = "medium"
                    if "uses empty column" in tags and moved_len == 1 and reveal_bonus == 0:
                        risk = "high"
                    candidates.append(
                        {
                            "src": src,
                            "dest": d_idx,
                            "moved_len": moved_len,
                            "tags": tags,
                            "risk": risk,
                            "score": score,
                        }
                    )
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:limit]

    def build_hint_message(self):
        items = self.build_hint_candidates(limit=3)
        if not items:
            return "Hint+: no legal moves available."
        parts = []
        for i, it in enumerate(items, start=1):
            src_stack, src_idx = it["src"]
            tag_text = ", ".join(it["tags"]) if it["tags"] else "neutral"
            parts.append(
                f"{i}) S{src_stack}:{src_idx} -> S{it['dest']} | "
                f"{it['moved_len']} card(s), risk {it['risk']}, {tag_text}"
            )
        return "Hint+: " + " ; ".join(parts)

    def consume_animation_queue(self):
        now = time.time()
        if self.anim_cards:
            end_time = self.anim_start + self.anim_duration + max(c.delay for c in self.anim_cards)
            if now >= end_time:
                self.anim_cards.clear()
                self.request_redraw()
            return

        if not self.anim_queue:
            return

        evt = self.anim_queue.pop(0)
        self.anim_cards = self.build_anim_cards(evt)
        if self.anim_cards:
            self.anim_start = now
            self.request_redraw()

        if evt.type == "COMPLETE_SUIT":
            stack_idx = evt.payload["stack"]
            suit = evt.payload.get("suit", 0)
            self.spawn_collect_animation(stack_idx, suit)
            sx, sy = self.stack_origin(stack_idx)
            cw, _ = self.card_size()
            self.spawn_firework_burst(sx + cw * 0.5, sy + 20, 24)
            self.request_redraw()

    def build_anim_cards(self, animation_event):
        if self.vm is None:
            return []
        cards = []
        stacks = self.vm.stacks

        if animation_event.type == "MOVE":
            src_stack, src_idx = animation_event.payload["src"]
            dest_stack, dest_start_idx = animation_event.payload["dest"]
            moved = len(stacks[dest_stack].cards) - dest_start_idx

            override = self.pending_move_anim
            use_override = (
                override is not None
                and override["src"] == (src_stack, src_idx)
                and override["dest_stack"] == dest_stack
                and override["count"] == moved
            )

            for i in range(max(0, moved)):
                card = stacks[dest_stack].cards[dest_start_idx + i]
                if use_override:
                    sx = override["release_x"]
                    sy = override["release_y"] + self.visible_step() * i
                else:
                    sx, sy = self.card_position(src_stack, src_idx + i)
                ex, ey = self.card_position(dest_stack, dest_start_idx + i)
                cards.append(
                    MovingCard(
                        card=card,
                        start_x=sx,
                        start_y=sy,
                        end_x=ex,
                        end_y=ey,
                        suppress_stack=dest_stack,
                        suppress_idx=dest_start_idx + i,
                        delay=0.0,
                    )
                )
            self.pending_move_anim = None

        elif animation_event.type == "DEAL":
            draw_count = animation_event.payload["draw_count"]
            stack_count = len(stacks)
            for i in range(draw_count):
                stack_idx = i % stack_count
                card_idx = len(stacks[stack_idx].cards) - 1
                if card_idx < 0:
                    continue
                card = stacks[stack_idx].cards[card_idx]
                sx, sy = self.deck_position()
                ex, ey = self.card_position(stack_idx, card_idx)
                cards.append(
                    MovingCard(
                        card=card,
                        start_x=sx,
                        start_y=sy,
                        end_x=ex,
                        end_y=ey,
                        suppress_stack=stack_idx,
                        suppress_idx=card_idx,
                        delay=i * 0.015,
                    )
                )

        return cards

    def update_effects(self):
        now = time.time()
        alive = []
        for p in self.particles:
            age = now - p.born
            if age > p.ttl:
                continue
            p.x += p.vx
            p.y += p.vy
            p.vy += 0.06
            p.vx *= 0.985
            p.vy *= 0.985
            alive.append(p)
        self.particles = alive

        alive_collect = []
        for cc in self.collect_cards:
            if now - cc.born <= cc.duration:
                alive_collect.append(cc)
        self.collect_cards = alive_collect

        alive_victory_cards = []
        for vc in self.victory_cards:
            age = now - vc.born
            if age > vc.ttl:
                continue
            vc.x += vc.vx
            vc.y += vc.vy
            vc.vy += 0.22
            vc.vx *= 0.992
            vc.vy *= 0.992
            vc.angle += vc.va
            vc.tilt += vc.vtilt
            alive_victory_cards.append(vc)
        self.victory_cards = alive_victory_cards

    def draw(self):
        if self.canvas is None:
            return
        c = self.canvas
        c.delete("all")
        self.runtime_tk_images = []
        self.draw_background(c)

        if self.stage == MENU:
            self.draw_menu(c)
            return
        if self.stage == SETTINGS:
            self.draw_settings(c)
            return
        if self.stage == STATS:
            self.draw_stats(c)
            return
        if self.vm is None:
            return

        suppressed = {(a.suppress_stack, a.suppress_idx) for a in self.anim_cards}
        if self.drag is not None:
            for i in range(len(self.drag.cards)):
                suppressed.add((self.drag.src_stack, self.drag.src_idx + i))

        for s_idx, stack in enumerate(self.vm.stacks):
            self.draw_stack(c, s_idx, stack.cards, suppressed)

        self.draw_base_and_hud(c)
        self.draw_active_cards(c)
        self.draw_collect_cards(c)
        self.draw_drag_cards(c)
        self.draw_particles(c)
        if self.victory_anim_active or self.victory_panel_visible:
            self.draw_victory_overlay(c)
        self.draw_victory_cards(c)

    def draw_background(self, c):
        theme = self.theme
        c.create_rectangle(0, 0, self.width, self.height, fill=theme["bg_base"], width=0)
        band_h = max(10, self.height // 18)
        for i in range(0, self.height + band_h, band_h):
            color = theme["bg_band_a"] if (i // band_h) % 2 == 0 else theme["bg_band_b"]
            c.create_rectangle(0, i, self.width, i + band_h, fill=color, width=0)

    def draw_menu(self, c):
        theme = self.theme
        self.active_buttons = []

        c.create_text(self.width * 0.5, self.height * 0.2, text="Spider Card Modern", fill=theme["hud_text"], font=f"Helvetica {self.fs(48)} bold")
        c.create_text(
            self.width * 0.5,
            self.height * 0.2 + 52,
            text="Animated Spider Solitaire with customizable visuals",
            fill=theme["hud_subtext"],
            font=f"Helvetica {self.fs(16)}",
        )

        bw = min(420, int(self.width * 0.42))
        bh = 58
        start_y = int(self.height * 0.42)
        gap = 18
        button_defs = [
            ("Start New Game", "new", "#0f766e"),
            ("Continue Game", "continue", "#0d9488"),
            ("Daily Challenge", "daily", "#1d4ed8"),
            (f"Save Slot: {self.save_slot}", "save_slot", "#334155"),
            ("Statistics", "stats", "#0ea5e9"),
            ("Game Settings", "settings", "#7c3aed"),
        ]

        for i, (label, action, fill) in enumerate(button_defs):
            x1 = (self.width - bw) / 2
            y1 = start_y + i * (bh + gap)
            x2 = x1 + bw
            y2 = y1 + bh
            enabled = not (action == "continue" and not self.can_continue)
            self.active_buttons.append({"action": action, "rect": (x1, y1, x2, y2), "enabled": enabled})
            button_fill = fill if enabled else "#475569"
            text_fill = "#f8fafc" if enabled else "#cbd5e1"
            c.create_rectangle(x1, y1, x2, y2, fill=button_fill, outline="#f8fafc", width=2)
            c.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=label, fill=text_fill, font=f"Helvetica {self.fs(16)} bold")

        slot_lines = []
        for row in self.slot_status:
            state = "Saved" if row["exists"] else "Empty"
            marker = " <" if row["slot"] == self.save_slot else ""
            slot_lines.append(f"Slot {row['slot']}: {state}{marker}")
        c.create_text(
            self.width * 0.5,
            start_y - self.fs(30),
            text=" | ".join(slot_lines),
            fill=theme["hud_subtext"],
            font=f"Helvetica {self.fs(12)}",
        )

        c.create_text(
            self.width * 0.5,
            self.height - 34,
            text="Keys: N new game, C continue, D daily, L slot, P stats, S settings",
            fill=theme["hud_subtext"],
            font=f"Helvetica {self.fs(13)}",
        )

    def draw_settings(self, c):
        theme = self.theme
        self.active_buttons = []

        c.create_text(self.width * 0.5, self.height * 0.16, text="Game Settings", fill=theme["hud_text"], font=f"Helvetica {self.fs(42)} bold")
        c.create_text(
            self.width * 0.5,
            self.height * 0.16 + 46,
            text="Difficulty, card style, and board theme",
            fill=theme["hud_subtext"],
            font=f"Helvetica {self.fs(15)}",
        )

        bw = min(560, int(self.width * 0.54))
        bh = 64
        start_y = int(self.height * 0.34)
        gap = 20
        settings_defs = [
            (f"Difficulty: {self.difficulty}", "difficulty", "#0f766e"),
            (f"Card Style: {self.card_style}", "card_style", "#4338ca"),
            (f"Theme: {self.theme_name}", "theme", "#9a3412"),
            (f"Font Scale: {self.font_scale}", "font_scale", "#0f766e"),
            (f"Save Slot: {self.save_slot}", "save_slot", "#334155"),
            ("Back To Menu", "back_menu", "#374151"),
        ]

        for i, (label, action, fill) in enumerate(settings_defs):
            x1 = (self.width - bw) / 2
            y1 = start_y + i * (bh + gap)
            x2 = x1 + bw
            y2 = y1 + bh
            self.active_buttons.append({"action": action, "rect": (x1, y1, x2, y2)})
            c.create_rectangle(x1, y1, x2, y2, fill=fill, outline="#f8fafc", width=2)
            c.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=label, fill="#f8fafc", font=f"Helvetica {self.fs(17)} bold")

        # Style preview cards on the right side in a vertical stack.
        cw, ch = self.card_size()
        px = self.width - cw - 28
        py = max(self.height * 0.26, start_y)
        gap_y = ch * 0.18
        self.draw_card(c, px, py, False, 0, 0, False)
        self.draw_card(c, px, py + ch + gap_y, False, 1, 11, False)
        self.draw_card(c, px, py + (ch + gap_y) * 2, True, 2, 6, False)

        c.create_text(
            self.width * 0.5,
            self.height - 26,
            text="Keys: 1/2/4 diff, C style, T theme, F font, L slot, Esc/M menu",
            fill=theme["hud_subtext"],
            font=f"Helvetica {self.fs(12)}",
        )

    def draw_stats(self, c):
        theme = self.theme
        self.active_buttons = []
        c.create_text(self.width * 0.5, self.height * 0.14, text="Statistics", fill=theme["hud_text"], font=f"Helvetica {self.fs(42)} bold")
        c.create_text(
            self.width * 0.5,
            self.height * 0.14 + 42,
            text="Overall and per-difficulty performance",
            fill=theme["hud_subtext"],
            font=f"Helvetica {self.fs(15)}",
        )

        lines = [self.format_stats_line("Overall", self.stats["overall"])]
        for d in DIFFICULTY_ORDER:
            lines.append(self.format_stats_line(d, self.stats["by_difficulty"][d]))

        y = self.height * 0.30
        for line in lines:
            c.create_text(40, y, anchor="nw", text=line, fill=theme["hud_text"], font=f"Helvetica {self.fs(12)}")
            y += self.fs(26)

        bw = min(360, int(self.width * 0.35))
        bh = 58
        x1 = (self.width - bw) / 2
        y1 = self.height * 0.78
        x2 = x1 + bw
        y2 = y1 + bh
        self.active_buttons.append({"action": "back_menu", "rect": (x1, y1, x2, y2)})
        c.create_rectangle(x1, y1, x2, y2, fill="#374151", outline="#f8fafc", width=2)
        c.create_text((x1 + x2) / 2, (y1 + y2) / 2, text="Back To Menu", fill="#f8fafc", font=f"Helvetica {self.fs(16)} bold")

        c.create_text(
            self.width * 0.5,
            self.height - 24,
            text="Key: P or Esc to return menu",
            fill=theme["hud_subtext"],
            font=f"Helvetica {self.fs(12)}",
        )

    def draw_base_and_hud(self, c):
        theme = self.theme
        deck_x, deck_y = self.deck_position()
        cw, ch = self.card_size()

        c.create_rectangle(
            deck_x,
            deck_y,
            deck_x + cw,
            deck_y + ch,
            fill=theme["deck_fill"],
            outline=theme["deck_outline"],
            width=2,
        )
        c.create_text(deck_x + cw / 2, deck_y + ch / 2, text=str(self.vm.base_count), fill=theme["hud_text"], font=f"Helvetica {self.fs(14)} bold")

        c.create_text(16, 16, anchor="nw", text=f"Finished: {self.vm.finished_count}", fill=theme["hud_text"], font=f"Helvetica {self.fs(16)} bold")
        mode = "Daily" if self.daily_mode else "Normal"
        seed_info = f" | seed {self.current_seed}" if self.current_seed is not None else ""
        c.create_text(
            16,
            42,
            anchor="nw",
            text=(
                f"Mode: {mode} | Difficulty: {self.difficulty} | Style: {self.card_style} | "
                f"Theme: {self.theme_name} | Font: {self.font_scale} | Slot: {self.save_slot}{seed_info}"
            ),
            fill=theme["hud_subtext"],
            font=f"Helvetica {self.fs(12)}",
        )
        c.create_text(16, self.height - 20, anchor="sw", text=self.message, fill=theme["hud_subtext"], font=f"Helvetica {self.fs(12)}")

    def draw_stack(self, c, stack_idx, cards, suppressed):
        theme = self.theme
        sx, sy = self.stack_origin(stack_idx)
        cw, ch = self.card_size()

        outline = theme["slot_outline"]
        width = 1
        if self.drag is not None and self.hover_drop_stack == stack_idx:
            outline = theme["slot_valid"] if self.hover_drop_valid else theme["slot_invalid"]
            width = 3

        c.create_rectangle(sx, sy, sx + cw, sy + ch, outline=outline, width=width, dash=(4, 2))

        for idx, card in enumerate(cards):
            if (stack_idx, idx) in suppressed:
                continue
            x, y = self.card_position(stack_idx, idx)
            self.draw_card(c, x, y, card.hidden, card.suit, card.num, selected=False)

    def draw_active_cards(self, c):
        if not self.anim_cards:
            return
        elapsed = time.time() - self.anim_start
        for card in self.anim_cards:
            t = (elapsed - card.delay) / self.anim_duration
            if t < 0.0:
                continue
            t = min(1.0, t)
            eased = 1 - (1 - t) * (1 - t)
            x = card.start_x + (card.end_x - card.start_x) * eased
            y = card.start_y + (card.end_y - card.start_y) * eased
            self.draw_card(c, x, y, card.card.hidden, card.card.suit, card.card.num, selected=False)

    def draw_drag_cards(self, c):
        if self.drag is None:
            return
        step = self.visible_step()
        cw, ch = self.card_size()
        for i, card in enumerate(self.drag.cards):
            x = self.drag.x
            y = self.drag.y + i * step
            c.create_rectangle(x + 5, y + 5, x + cw + 5, y + ch + 5, fill="#000000", outline="")
            self.draw_card(c, x, y, card.hidden, card.suit, card.num, selected=True)

    def draw_particles(self, c):
        now = time.time()
        for p in self.particles:
            t = (now - p.born) / p.ttl
            alpha = max(0.0, 1.0 - t)
            r = p.size * alpha
            tx = p.x - p.vx * 1.5
            ty = p.y - p.vy * 1.5
            c.create_oval(tx - r * 0.6, ty - r * 0.6, tx + r * 0.6, ty + r * 0.6, fill="#ffffff", width=0)
            c.create_oval(p.x - r, p.y - r, p.x + r, p.y + r, fill=p.color, width=0)

    def draw_rotated_card_sprite(self, c, cx, cy, w, h, angle_deg, suit, num, tilt_deg=0.0):
        # Pseudo-3D: tilt compresses width like a card flipping in depth.
        depth_scale = max(0.16, abs(math.cos(math.radians(tilt_deg))))
        w3d = w * depth_scale

        # ArtDeck: render true textured rotation and auto flip front/back by tilt.
        if (
            self.card_style in TEXTURED_STYLE_ASSETS
            and Image is not None
            and ImageTk is not None
            and self.pil_back_source is not None
        ):
            show_front = math.cos(math.radians(tilt_deg)) >= 0
            src = self.pil_front_sources.get((suit, num)) if show_front else self.pil_back_source
            if src is not None:
                tw = max(2, int(w3d))
                th = max(2, int(h))
                angle_q = int(round(angle_deg / 6.0) * 6)
                shade_q = int(round((1.0 - depth_scale) * 8))
                cache_key = (self.card_style, show_front, suit, num, tw, th, angle_q, shade_q)
                tkimg = self.rotated_sprite_cache.get(cache_key)
                if tkimg is None:
                    img = src.resize((tw, th), RESAMPLE)
                    shade = int(80 * (shade_q / 8.0))
                    if shade > 0:
                        overlay = Image.new("RGBA", img.size, (0, 0, 0, shade))
                        img = Image.alpha_composite(img, overlay)
                    rot = img.rotate(-angle_q, resample=ROTATE_RESAMPLE, expand=True)
                    tkimg = ImageTk.PhotoImage(rot)
                    self.rotated_sprite_cache[cache_key] = tkimg
                    if len(self.rotated_sprite_cache) > 1200:
                        self.rotated_sprite_cache.clear()
                c.create_image(cx, cy, image=tkimg)
                return

        rad = math.radians(angle_deg)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        hw = w3d * 0.5
        hh = h * 0.5
        corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        pts = []
        for px, py in corners:
            rx = cx + px * cos_a - py * sin_a
            ry = cy + px * sin_a + py * cos_a
            pts.extend((rx, ry))
        theme = self.theme
        # Keep victory cards visually aligned with current card style.
        if self.card_style == "ArtDeck":
            base_r, base_g, base_b = (248, 240, 224)
            border = "#6b4f2a"
            accent = "#cfb27c"
        elif self.card_style == "Minimal":
            base_r, base_g, base_b = (245, 247, 252)
            border = theme["card_border"]
            accent = theme["deck_outline"]
        elif self.card_style == "Neo":
            base_r, base_g, base_b = (240, 245, 255)
            border = theme["card_border"]
            accent = theme["deck_fill"]
        else:
            base_r, base_g, base_b = (247, 232, 188)
            border = theme["card_border"]
            accent = theme["deck_outline"]

        light = 0.78 + 0.28 * depth_scale
        rr = max(0, min(255, int(base_r * light)))
        gg = max(0, min(255, int(base_g * light)))
        bb = max(0, min(255, int(base_b * light)))
        face = f"#{rr:02x}{gg:02x}{bb:02x}"

        c.create_polygon(*pts, fill=face, outline=border, width=1)
        suit_text = ["♠", "♥", "♣", "♦"][suit]
        rank_text = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"][num]
        text_color = "#dc2626" if suit in (1, 3) else "#111827"
        if self.card_style == "Neo":
            c.create_text(cx, cy - h * 0.07, text=rank_text, fill=text_color, font=f"Helvetica {self.fs(10)} bold")
            c.create_text(cx, cy + h * 0.10, text=suit_text * 2, fill=text_color, font=f"Helvetica {self.fs(9)}")
            c.create_line(cx - w3d * 0.30, cy + h * 0.01, cx + w3d * 0.30, cy + h * 0.01, fill=accent, width=2)
        elif self.card_style == "Minimal":
            c.create_text(cx, cy - h * 0.02, text=rank_text, fill=text_color, font=f"Helvetica {self.fs(11)} bold")
            c.create_text(cx, cy + h * 0.14, text=suit_text, fill=text_color, font=f"Helvetica {self.fs(9)}")
        else:
            c.create_text(cx, cy, text=f"{rank_text}{suit_text}", fill=text_color, font=f"Helvetica {self.fs(10)} bold")
            c.create_line(cx - w3d * 0.24, cy - h * 0.18, cx + w3d * 0.24, cy - h * 0.18, fill=accent, width=1)

    def draw_collect_cards(self, c):
        now = time.time()
        cw, ch = self.card_size()
        for cc in self.collect_cards:
            t = min(1.0, (now - cc.born) / cc.duration)
            t2 = 1 - (1 - t) * (1 - t)
            # arc path: rise a bit then sink to collector
            mx = (cc.start_x + cc.end_x) * 0.5
            my = min(cc.start_y, cc.end_y) - ch * 0.35
            x = (1 - t2) * (1 - t2) * cc.start_x + 2 * (1 - t2) * t2 * mx + t2 * t2 * cc.end_x
            y = (1 - t2) * (1 - t2) * cc.start_y + 2 * (1 - t2) * t2 * my + t2 * t2 * cc.end_y
            angle = cc.angle0 + (cc.angle1 - cc.angle0) * t2
            tilt = -55 + 110 * t2
            self.draw_rotated_card_sprite(
                c,
                x + cw * 0.5,
                y + ch * 0.5,
                cw * 0.92,
                ch * 0.92,
                angle,
                cc.suit,
                cc.num,
                tilt_deg=tilt,
            )

    def draw_victory_cards(self, c):
        cw, ch = self.card_size()
        for vc in self.victory_cards:
            self.draw_rotated_card_sprite(
                c,
                vc.x,
                vc.y,
                cw * vc.scale,
                ch * vc.scale,
                vc.angle,
                vc.suit,
                vc.num,
                tilt_deg=vc.tilt,
            )

    def draw_victory_overlay(self, c):
        title_size = self.fs(52)
        subtitle_size = self.fs(16)
        if self.victory_anim_active:
            t = min(1.0, (time.time() - self.victory_started_at) / self.victory_anim_duration)
            pulse = 1.0 + 0.08 * math.sin(time.time() * 10)
            size = max(18, int(title_size * (0.85 + 0.15 * t) * pulse))
            c.create_text(
                self.width * 0.5 + 2,
                self.height * 0.42 + 2,
                text="VICTORY!",
                fill="#1f2937",
                font=f"Helvetica {size} bold",
            )
            c.create_text(
                self.width * 0.5,
                self.height * 0.42,
                text="VICTORY!",
                fill="#fde68a",
                font=f"Helvetica {size} bold",
            )
            c.create_text(
                self.width * 0.5,
                self.height * 0.52,
                text="Calculating settlement...",
                fill="#dbeafe",
                font=f"Helvetica {subtitle_size}",
            )
            return

        # Post-animation settlement panel
        pw = min(self.width * 0.72, 760)
        ph = min(self.height * 0.56, 420)
        x1 = (self.width - pw) / 2
        y1 = (self.height - ph) / 2
        x2 = x1 + pw
        y2 = y1 + ph
        c.create_rectangle(x1, y1, x2, y2, fill="#111827", outline="#f8fafc", width=2)
        c.create_text((x1 + x2) / 2, y1 + 44, text="Victory Settlement", fill="#fde68a", font=f"Helvetica {self.fs(34)} bold")

        moves = self.victory_summary.get("moves", 0)
        duration_sec = self.victory_summary.get("duration_sec", 0.0)
        mode = self.victory_summary.get("mode", "Normal")
        diff = self.victory_summary.get("difficulty", self.difficulty)

        lines = [
            f"Mode: {mode}",
            f"Difficulty: {diff}",
            f"Moves Used: {moves}",
            f"Time Used: {duration_sec:.1f}s",
        ]
        yy = y1 + 108
        for line in lines:
            c.create_text(x1 + 40, yy, anchor="nw", text=line, fill="#e5e7eb", font=f"Helvetica {self.fs(18)}")
            yy += self.fs(34)

        c.create_text(
            (x1 + x2) / 2,
            y2 - 34,
            text="Press N for a new game or M to return menu",
            fill="#93c5fd",
            font=f"Helvetica {self.fs(14)}",
        )

    def collect_target_position(self, i):
        cw, ch = self.card_size()
        col = i % 5
        row = i // 5
        x = self.width * 0.5 - cw * 1.2 + col * cw * 0.42
        y = self.height - ch * 0.55 + row * ch * 0.08
        return x, y

    def spawn_collect_animation(self, stack_idx, suit):
        if self.vm is None or stack_idx < 0 or stack_idx >= len(self.vm.stacks):
            return
        now = time.time()
        remain = len(self.vm.stacks[stack_idx].cards)
        for i in range(13):
            sx, sy = self.card_position(stack_idx, remain + i)
            ex, ey = self.collect_target_position(i)
            self.collect_cards.append(
                CollectCard(
                    suit=suit,
                    num=12 - i,
                    start_x=sx,
                    start_y=sy,
                    end_x=ex,
                    end_y=ey,
                    born=now,
                    duration=0.42 + i * 0.017,
                    angle0=self.fx_rng.uniform(-22, 22),
                    angle1=self.fx_rng.uniform(-6, 6),
                )
            )

    def spawn_victory_cards_burst(self, count):
        now = time.time()
        for _ in range(count):
            # Wider launch window + stronger velocities for a larger explosion area.
            x = self.width * 0.5 + self.fx_rng.uniform(-self.width * 0.42, self.width * 0.42)
            y = self.height + self.fx_rng.uniform(10, 130)
            self.victory_cards.append(
                VictoryCard(
                    x=x,
                    y=y,
                    vx=self.fx_rng.uniform(-12.5, 12.5),
                    vy=self.fx_rng.uniform(-18.0, -7.5),
                    angle=self.fx_rng.uniform(0, 360),
                    va=self.fx_rng.uniform(-14.0, 14.0),
                    born=now,
                    ttl=self.fx_rng.uniform(1.9, 3.3),
                    suit=self.fx_rng.randint(0, 3),
                    num=self.fx_rng.randint(0, 12),
                    scale=self.fx_rng.uniform(0.68, 1.18),
                    tilt=self.fx_rng.uniform(0, 360),
                    vtilt=self.fx_rng.uniform(-20.0, 20.0),
                )
            )

    def draw_card(self, c, x, y, hidden, suit, num, selected):
        cw, ch = self.card_size()
        self.card_renderer.draw_card(
            canvas=c,
            x=x,
            y=y,
            hidden=hidden,
            suit=suit,
            num=num,
            selected=selected,
            cw=cw,
            ch=ch,
            theme=self.theme,
            card_style=self.card_style,
            font_scale=FONT_SCALE_FACTOR[self.font_scale],
            back_image=self.style_back_images.get(self.card_style),
            front_image=self.front_images.get((suit, num)),
        )

    def find_stack_and_index(self, x, y):
        if self.vm is None:
            return None
        for s_idx, stack in enumerate(self.vm.stacks):
            sx, sy = self.stack_origin(s_idx)
            cw, ch = self.card_size()
            if not (sx <= x <= sx + cw):
                continue
            if not stack.cards:
                if sy <= y <= sy + ch:
                    return s_idx, 0
                continue
            step = self.visible_step()
            max_y = sy + ch + step * (len(stack.cards) - 1)
            if y < sy or y > max_y:
                continue
            idx = int((y - sy) // step)
            idx = max(0, min(idx, len(stack.cards) - 1))
            return s_idx, idx
        return None

    def find_drop_stack(self, x):
        if self.vm is None:
            return None
        for s_idx in range(len(self.vm.stacks)):
            sx, _ = self.stack_origin(s_idx)
            cw, _ = self.card_size()
            if sx <= x <= sx + cw:
                return s_idx
        return None

    def can_drop_to(self, stack_idx):
        if self.drag is None or stack_idx is None:
            return False
        src = (self.drag.src_stack, self.drag.src_idx)
        return self.core.canMove(src, stack_idx)

    def is_point_in_deck(self, x, y):
        dx, dy = self.deck_position()
        cw, ch = self.card_size()
        return dx <= x <= dx + cw and dy <= y <= dy + ch

    def spawn_firework_burst(self, x, y, count):
        now = time.time()
        colors = self.theme["particle"]
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(1.8, 4.6)
            self.particles.append(
                Particle(
                    x=x,
                    y=y,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed - 0.8,
                    born=now,
                    ttl=random.uniform(0.45, 0.9),
                    size=random.uniform(2.2, 4.4),
                    color=random.choice(colors),
                )
            )

    def spawn_spark_shower(self, x, y, count, speed=(0.8, 2.6), ttl=(0.25, 0.5)):
        now = time.time()
        colors = self.theme["particle"]
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            mag = random.uniform(speed[0], speed[1])
            self.particles.append(
                Particle(
                    x=x + random.uniform(-6, 6),
                    y=y + random.uniform(-6, 6),
                    vx=math.cos(angle) * mag,
                    vy=math.sin(angle) * mag - 0.2,
                    born=now,
                    ttl=random.uniform(ttl[0], ttl[1]),
                    size=random.uniform(1.2, 3.4),
                    color=random.choice(colors),
                )
            )

    def card_size(self):
        return self.width * CARD_WIDTH_RATIO, self.height * CARD_HEIGHT_RATIO

    def card_pixel_size(self):
        return max(1, int(self.width * CARD_WIDTH_RATIO)), max(1, int(self.height * CARD_HEIGHT_RATIO))

    def visible_step(self):
        return self.height * VISIBLE_STEP_RATIO

    def stack_origin(self, stack_idx):
        stack_count = len(self.vm.stacks)
        cw, _ = self.card_size()
        gap = self.width * STACK_GAP_RATIO
        total_w = stack_count * cw + (stack_count - 1) * gap
        start_x = (self.width - total_w) / 2
        x = start_x + stack_idx * (cw + gap)
        y = self.height * TOP_MARGIN_RATIO
        return x, y

    def card_position(self, stack_idx, card_idx):
        x, y = self.stack_origin(stack_idx)
        return x, y + self.visible_step() * card_idx

    def deck_position(self):
        cw, _ = self.card_size()
        x = self.width - cw - 24
        y = 20
        return x, y
