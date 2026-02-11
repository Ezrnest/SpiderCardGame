import math
import random
import threading
import time
from datetime import date
from pathlib import Path
from tkinter import BOTH, Canvas, Tk, messagebox, simpledialog

from base.Core import CallDeal, Card, CardMove, Core, DUMMY_PLAYER, FreeStack, GameConfig, encodeStack
from base.Interface import Interface
from modern_ui.adapter import CoreAdapter
from modern_ui.card_face import CardFaceRenderer
from modern_ui.entities import CollectCard, DragState, MovingCard, Particle, VictoryCard
from modern_ui.game_store import SLOT_COUNT, clear_game, has_saved_game, list_slot_status, load_game, save_game
from modern_ui.seed_pool_store import choose_seed_for_bucket
from modern_ui.settings_store import load_settings, save_settings
from modern_ui.sound_fx import SoundFxManager
from modern_ui.stats_store import load_stats, profile_key, record_game_lost, record_game_started, record_game_won, save_stats
from solver.analyzer import SearchLimits, SolverState, solve_state
from modern_ui.ui_config import (
    ANIM_DURATION,
    CARD_HEIGHT_RATIO,
    CARD_STYLE_ORDER,
    CARD_WIDTH_RATIO,
    DIFFICULTY_BUCKET_ORDER,
    FONT_SCALE_FACTOR,
    FONT_SCALE_ORDER,
    FPS_MS,
    GAME,
    MENU,
    SETTINGS,
    STATS,
    STACK_GAP_RATIO,
    TEXTURED_STYLE_ASSETS,
    SUIT_COUNT_ORDER,
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
    TEXTURED_DRAG_FULL_LIMIT = 5
    TEXTURED_DRAG_SHADOW_LIMIT = 1
    BUCKET_TEXT_ZH = {"Easy": "简单", "Medium": "中等", "Hard": "困难"}
    SEED_SOURCE_TEXT_ZH = {
        "random": "随机",
        "bucket": "题库",
        "daily": "每日",
        "manual": "手动",
        "replay": "重开",
        "loaded": "读档",
        "test": "测试",
    }
    STYLE_TEXT_ZH = {
        "Classic": "经典",
        "FourColorClassic": "四色经典",
        "Minimal": "极简",
        "Neo": "新锐",
        "ArtDeck": "艺术贴图",
        "NeoGrid": "霓虹网格",
        "VintageGold": "复古金",
        "SakuraInk": "樱墨",
    }
    THEME_TEXT_ZH = {"Forest": "森林", "Ocean": "海洋", "Sunset": "落日"}
    FONT_SCALE_TEXT_ZH = {
        "Small": "小",
        "Normal": "普通",
        "Large": "大",
        "X-Large": "超大",
        "Huge": "特大",
    }
    SHOW_TOP_LEFT_DETAIL = False
    AUTO_SOLVER_STEP_INTERVAL = 0.45

    def __init__(self, width=1200, height=760):
        super().__init__()
        self.width = width
        self.height = height
        self.root = None
        self.canvas = None
        self.stage = MENU

        self.vm = None
        self.message = ""

        self.suit_count = 2
        self.difficulty_bucket = "Medium"
        self.card_style = "Classic"
        self.theme_name = "Forest"
        self.font_scale = "Normal"
        self.daily_mode = False
        self.test_mode = False
        self.current_seed = None
        self.seed_source = "random"
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
        self.sound_fx = SoundFxManager()
        self.style_back_images = {}
        self.pil_back_source = None
        self.front_images = {}
        self.pil_front_sources = {}
        self.runtime_tk_images = []
        self.rotated_sprite_cache = {}
        self.needs_redraw = True
        self.cached_card_px = None
        self.solver_plan = []
        self.solver_mode = None
        self.solver_running = False
        self.solver_result = None
        self.solver_request_id = 0
        self.solver_next_step_at = 0.0
        self.load_persisted_settings()

    def run(self):
        self.root = Tk()
        self.root.title("蜘蛛纸牌")
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
        self.suit_count = int(settings["suit_count"])
        self.difficulty_bucket = settings["difficulty_bucket"]
        self.card_style = settings["card_style"]
        self.theme_name = settings["theme_name"]
        self.font_scale = settings["font_scale"]
        self.save_slot = int(settings["save_slot"])

    def persist_settings(self):
        save_settings(
            {
                "suit_count": str(self.suit_count),
                "difficulty_bucket": self.difficulty_bucket,
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

    def invalidate_solver_jobs(self):
        self.solver_request_id += 1
        self.solver_running = False
        self.solver_result = None
        self.solver_plan = []
        self.solver_mode = None
        self.solver_next_step_at = 0.0

    def fs(self, base):
        factor = FONT_SCALE_FACTOR[self.font_scale]
        return max(8, int(base * factor))

    def on_close(self):
        if not messagebox.askyesno("退出", "确定要退出游戏吗？"):
            return
        if self.stage == GAME and self.core is not None and self.vm is not None:
            self.save_current_game()
        self.persist_settings()
        self.root.destroy()

    def confirm_overwrite_saved_game(self, mode_label):
        if not has_saved_game(self.save_slot):
            return True
        return messagebox.askyesno(
            "覆盖存档",
            f"开始{mode_label}会覆盖存档槽 {self.save_slot}。是否继续？",
        )

    def cycle_value(self, order, current):
        idx = order.index(current)
        return order[(idx + 1) % len(order)]

    def current_profile_key(self):
        return profile_key(self.suit_count, self.difficulty_bucket)

    def current_profile_label(self):
        return f"{self.suit_count}花色 / {self.BUCKET_TEXT_ZH.get(self.difficulty_bucket, self.difficulty_bucket)}"

    def display_style_name(self):
        return self.STYLE_TEXT_ZH.get(self.card_style, self.card_style)

    def display_theme_name(self):
        return self.THEME_TEXT_ZH.get(self.theme_name, self.theme_name)

    def display_font_scale(self):
        return self.FONT_SCALE_TEXT_ZH.get(self.font_scale, self.font_scale)

    def pick_seed_from_bucket(self, suit_count: int, difficulty_bucket: str):
        seed = choose_seed_for_bucket(suit_count, difficulty_bucket)
        if seed is None:
            self.seed_source = "random"
            return None
        self.seed_source = "bucket"
        return int(seed)

    def open_menu(self):
        self.invalidate_solver_jobs()
        self.stage = MENU
        self.drag = None
        self.anim_cards.clear()
        self.anim_queue.clear()
        self.active_buttons = []
        self.slot_status = list_slot_status()
        self.can_continue = has_saved_game(self.save_slot)
        self.message = "开始新游戏、继续存档、每日挑战，或打开设置。"
        self.request_redraw()

    def open_stats(self):
        self.stage = STATS
        self.active_buttons = []
        self.message = "统计总览。"
        self.request_redraw()

    def open_settings(self):
        self.stage = SETTINGS
        self.active_buttons = []
        self.message = "配置花色数量、难度分级、卡面风格与主题。"
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
        self.stats = record_game_started(self.stats, self.suit_count, self.difficulty_bucket)
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
        self.stats = record_game_won(
            self.stats,
            self.suit_count,
            self.difficulty_bucket,
            duration,
            self.current_game_actions,
        )
        save_stats(self.stats)
        self.current_game_recorded = True

    def mark_game_lost_if_needed(self):
        if self.test_mode or self.current_game_recorded:
            return
        if self.current_game_started_at is None:
            return
        self.stats = record_game_lost(self.stats, self.suit_count, self.difficulty_bucket)
        save_stats(self.stats)
        self.current_game_recorded = True

    def build_config(self, daily=False):
        cfg = GameConfig()
        cfg.suits = self.suit_count
        if daily:
            today = date.today()
            base_seed = int(today.strftime("%Y%m%d"))
            bucket_idx = DIFFICULTY_BUCKET_ORDER.index(self.difficulty_bucket)
            cfg.seed = base_seed * 100 + cfg.suits * 10 + bucket_idx
            self.current_seed = cfg.seed
            self.daily_mode = True
            self.seed_source = "daily"
        else:
            picked_seed = self.pick_seed_from_bucket(cfg.suits, self.difficulty_bucket)
            cfg.seed = picked_seed
            self.current_seed = picked_seed
            self.daily_mode = False
        return cfg

    def start_new_game(self, daily=False):
        self.invalidate_solver_jobs()
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

        mode = "每日挑战" if self.daily_mode else "普通"
        profile = self.current_profile_label()
        if self.seed_source == "bucket":
            self.message = f"{mode}已开始（{profile}，题库种子 {self.current_seed}）。拖动卡牌移动。按 G 可同种子重开。"
        elif self.seed_source == "daily":
            self.message = f"{mode}已开始（{profile}，每日种子 {self.current_seed}）。拖动卡牌移动。按 G 可同种子重开。"
        else:
            self.message = f"{mode}已开始（{profile}，随机种子）。拖动卡牌移动。"
        self.begin_game_tracking()
        self.save_current_game()
        self.request_redraw()

    def start_seeded_game(self, seed: int):
        self.invalidate_solver_jobs()
        if self.stage == GAME:
            self.mark_game_lost_if_needed()
        core = Core()
        core.registerInterface(self)
        core.registerPlayer(DUMMY_PLAYER)
        cfg = GameConfig()
        cfg.suits = self.suit_count
        cfg.seed = int(seed)
        core.startGame(cfg)
        self.vm = CoreAdapter.snapshot(core)
        self.test_mode = False
        self.daily_mode = False
        self.current_seed = int(seed)
        self.seed_source = "manual"

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

        self.message = (
            f"种子对局已开始（{self.current_profile_label()}，手动种子 {self.current_seed}）。"
            "拖动卡牌移动。按 G 可同种子重开。"
        )
        self.begin_game_tracking()
        self.save_current_game()
        self.request_redraw()

    def prompt_and_start_seeded_game(self):
        if self.root is None:
            return
        raw = simpledialog.askstring("种子开局", "请输入整数种子：", parent=self.root)
        if raw is None:
            return
        value = raw.strip()
        if not value:
            self.message = "已取消种子输入。"
            self.request_redraw()
            return
        try:
            seed = int(value)
        except ValueError:
            messagebox.showerror("种子无效", "种子必须是整数。")
            self.message = "种子输入无效。"
            self.request_redraw()
            return
        self.start_seeded_game(seed)

    def restart_same_seed_game(self):
        if self.stage != GAME:
            return
        if self.current_seed is None:
            self.message = "当前对局没有可用种子，仅支持对有种子的对局进行同种子重开。"
            self.request_redraw()
            return

        self.mark_game_lost_if_needed()

        cfg = GameConfig()
        cfg.suits = self.suit_count
        cfg.seed = int(self.current_seed)

        core = Core()
        core.registerInterface(self)
        core.registerPlayer(DUMMY_PLAYER)
        core.startGame(cfg)
        self.vm = CoreAdapter.snapshot(core)
        self.test_mode = False
        self.daily_mode = False
        self.seed_source = "replay"

        self.drag = None
        self.hover_drop_stack = None
        self.hover_drop_valid = False
        self.pending_move_anim = None

        self.anim_queue.clear()
        self.anim_cards.clear()
        self.particles.clear()
        self.collect_cards.clear()
        self.reset_victory_state()

        self.message = (
            f"同种子重开（{self.current_profile_label()}，种子 {self.current_seed}）。拖动卡牌移动。"
        )
        self.begin_game_tracking()
        self.save_current_game()
        self.request_redraw()

    def continue_game(self):
        self.invalidate_solver_jobs()
        core = load_game(self.save_slot)
        if core is None:
            self.can_continue = False
            self.message = f"存档槽 {self.save_slot} 没有可用存档。"
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
        self.seed_source = "loaded"
        self.current_game_started_at = time.time()
        self.current_game_actions = 0
        self.current_game_recorded = False
        self.message = f"已从存档槽 {self.save_slot} 继续游戏。"
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
        self.invalidate_solver_jobs()
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
        self.seed_source = "test"
        self.current_game_started_at = None
        self.current_game_actions = 0
        self.current_game_recorded = True
        self.message = "测试对局：将 A♠ 从第 1 列移动到第 0 列即可获胜。"
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
            "suit_count": self.suit_count,
            "difficulty_bucket": self.difficulty_bucket,
            "profile": self.current_profile_label(),
            "mode": "每日" if self.daily_mode else ("测试" if self.test_mode else "普通"),
        }
        self.fx_rng.seed(time.time_ns())
        self.victory_started_at = time.time()
        self.victory_anim_active = True
        self.victory_panel_visible = False
        self.message = "胜利动画中..."
        self.mark_game_won_if_needed()
        self.sound_fx.play_victory()
        if not self.test_mode:
            clear_game(self.save_slot)
            self.slot_status = list_slot_status()
            self.can_continue = has_saved_game(self.save_slot)
        self.spawn_firework_burst(self.width * 0.5, self.height * 0.3, 34)
        self.spawn_firework_burst(self.width * 0.35, self.height * 0.26, 28)
        self.spawn_firework_burst(self.width * 0.65, self.height * 0.26, 28)
        self.request_redraw()

    def onEvent(self, event):
        self.vm = CoreAdapter.snapshot(self.core)
        self.anim_queue.append(CoreAdapter.event_to_animation(event))
        if isinstance(event, CardMove):
            self.sound_fx.play_move()
        elif isinstance(event, CallDeal):
            self.sound_fx.play_deal()
        elif isinstance(event, FreeStack):
            self.sound_fx.play_collect()
        self.save_current_game()
        self.request_redraw()
        super().onEvent(event)

    def onUndoEvent(self, event):
        self.vm = CoreAdapter.snapshot(self.core)
        self.anim_cards.clear()
        self.anim_queue.clear()
        self.drag = None
        self.message = "已撤销。"
        self.save_current_game()
        self.request_redraw()
        super().onUndoEvent(event)

    def notifyRedraw(self):
        self.request_redraw()

    def clear_solver_state(self):
        self.solver_mode = None
        self.solver_running = False
        self.solver_plan = []
        self.solver_result = None
        self.solver_next_step_at = 0.0

    def stop_solver(self):
        self.solver_request_id += 1
        self.clear_solver_state()
        self.message = "已停止求解器。"
        self.request_redraw()

    def _build_solver_state_from_core(self):
        if self.core is None:
            return None
        stacks = []
        hidden_prefix = []
        for stack in self.core.stacks:
            stacks.append(tuple(card.id for card in stack))
            hp = 0
            for card in stack:
                if card.hidden:
                    hp += 1
                else:
                    break
            hidden_prefix.append(hp)
        return SolverState(
            base=tuple(card.id for card in self.core.base),
            stacks=tuple(stacks),
            hidden_prefix=tuple(hidden_prefix),
            finished_count=int(self.core.finishedCount),
        )

    def _start_solver_job(self, mode: str):
        if self.stage != GAME or self.core is None or self.vm is None:
            self.message = "当前不在对局中，无法求解。"
            self.request_redraw()
            return
        if self.drag is not None:
            self.message = "拖动中无法启动求解，请先释放卡牌。"
            self.request_redraw()
            return
        if self.solver_running:
            self.message = "求解器正在运行中..."
            self.request_redraw()
            return

        state = self._build_solver_state_from_core()
        if state is None:
            self.message = "无法读取当前局面。"
            self.request_redraw()
            return

        self.solver_mode = mode
        self.solver_running = True
        self.solver_result = None
        self.solver_plan = []
        self.solver_request_id += 1
        request_id = self.solver_request_id

        self.message = "求解器运行中..."
        self.request_redraw()

        def worker():
            limits = SearchLimits(
                max_nodes=2_000_000 if mode == "auto" else 140_000,
                max_seconds=20.0 if mode == "auto" else 1.8,
                max_frontier=1_000_000 if mode == "auto" else 500_000,
            )
            result = solve_state(state, limits=limits)
            self.solver_result = (request_id, result)

        threading.Thread(target=worker, daemon=True).start()

    def play_one_heuristic_step(self):
        if self.stage != GAME or self.core is None or self.vm is None:
            self.message = "当前不在对局中，无法演示。"
            self.request_redraw()
            return
        if self.drag is not None or self.anim_cards:
            self.message = "请先结束当前拖动/动画。"
            self.request_redraw()
            return
        if self.victory_anim_active or self.victory_panel_visible:
            self.message = "结算阶段无法演示。"
            self.request_redraw()
            return

        hints = self.build_hint_candidates(limit=1)
        if hints:
            best = hints[0]
            ok = self.core.askMove(best["src"], best["dest"])
            if ok:
                self.current_game_actions += 1
                self.message = "已按启发式演示一步。"
            else:
                self.message = "启发式动作执行失败。"
            self.request_redraw()
            return

        if self.core.askDeal():
            self.current_game_actions += 1
            self.message = "无可移动作，已演示发牌一步。"
        else:
            self.message = "当前无可演示动作。"
        self.request_redraw()

    def _apply_solver_result_if_ready(self):
        if self.solver_result is None:
            return
        payload = self.solver_result
        self.solver_result = None
        request_id, result = payload
        if request_id != self.solver_request_id:
            return

        self.solver_running = False
        if result.status != "solved":
            self.solver_mode = None
            self.solver_plan = []
            if result.status == "proven_unsolvable":
                self.message = "求解完成：该局面无解。"
            else:
                self.message = "求解未找到可行解（达到搜索限制）。"
            self.request_redraw()
            return

        self.solver_plan = list(result.solution)
        if not self.solver_plan:
            self.solver_mode = None
            self.message = "当前局面已是终局。"
            self.request_redraw()
            return

        if self.solver_mode == "demo":
            self._play_one_solver_action()
        else:
            self.message = f"求解完成，准备自动执行 {len(self.solver_plan)} 步。"
            self.solver_next_step_at = time.time() + self.AUTO_SOLVER_STEP_INTERVAL
            self.request_redraw()

    def _play_one_solver_action(self):
        if not self.solver_plan:
            self.solver_mode = None
            self.message = "演示完成。"
            self.request_redraw()
            return
        action = self.solver_plan.pop(0)
        ok = False
        if action.kind == "DEAL":
            ok = self.core.askDeal()
            if not ok:
                self.message = "演示中断：当前不能发牌。"
        elif action.kind == "MOVE":
            ok = self.core.askMove((action.src_stack, action.src_idx), action.dest_stack)
            if not ok:
                self.message = "演示中断：动作与当前局面不一致。"
        if not ok:
            self.solver_mode = None
            self.solver_plan = []
            self.request_redraw()
            return
        self.current_game_actions += 1
        if self.solver_mode == "demo":
            self.solver_mode = None
            self.message = "已演示一步。"
        elif self.solver_mode == "auto":
            self.solver_next_step_at = time.time() + self.AUTO_SOLVER_STEP_INTERVAL
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
                if not self.confirm_overwrite_saved_game("新游戏"):
                    return
                self.start_new_game(daily=False)
            elif key == "i":
                if not self.confirm_overwrite_saved_game("种子对局"):
                    return
                self.prompt_and_start_seeded_game()
            elif key == "t":
                self.start_test_game()
            elif key == "c":
                self.continue_game()
            elif key == "d":
                if not self.confirm_overwrite_saved_game("每日挑战"):
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
                self.suit_count = 1
                self.persist_settings()
            elif key == "2":
                self.suit_count = 2
                self.persist_settings()
            elif key == "3":
                self.suit_count = 3
                self.persist_settings()
            elif key == "4":
                self.suit_count = 4
                self.persist_settings()
            elif key == "q":
                self.difficulty_bucket = "Easy"
                self.persist_settings()
            elif key == "w":
                self.difficulty_bucket = "Medium"
                self.persist_settings()
            elif key == "e":
                self.difficulty_bucket = "Hard"
                self.persist_settings()
            elif key == "b":
                self.difficulty_bucket = self.cycle_value(DIFFICULTY_BUCKET_ORDER, self.difficulty_bucket)
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
                if not self.confirm_overwrite_saved_game("新游戏"):
                    return
                self.start_new_game(daily=False)
            elif key == "g":
                self.restart_same_seed_game()
            elif key == "d":
                if not self.core.askDeal():
                    self.message = "底牌已发完。"
                else:
                    self.current_game_actions += 1
            elif key == "u":
                if not self.core.askUndo():
                    self.message = "无法撤销。"
            elif key == "r":
                if not self.core.askRedo():
                    self.message = "无法重做。"
            elif key == "s":
                self.open_settings()
            elif key == "h":
                self.message = self.build_hint_message()
            elif key == "a":
                self._start_solver_job("auto")
            elif key == "v":
                self.play_one_heuristic_step()
            elif key == "x":
                self.stop_solver()
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
                self.message = "底牌已发完。"
            else:
                self.message = "已发一轮牌。"
                self.current_game_actions += 1
            self.request_redraw()
            return

        hit = self.find_stack_and_index(event.x, event.y)
        if hit is None:
            return
        stack_idx, card_idx = hit
        if not self.core.isValidSequence((stack_idx, card_idx)):
            self.message = "该序列不可移动。"
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
        self.message = f"正在拖动 {len(stack_cards)} 张牌..."
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
            self.message = "无法撤销。"
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
        if self.card_style not in TEXTURED_STYLE_ASSETS and now - self.last_drag_spark > 0.04:
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
            self.message = "已取消移动。"
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
            self.message = "该移动不符合规则。"
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
                    if not self.confirm_overwrite_saved_game("新游戏"):
                        return
                    self.start_new_game(daily=False)
                elif action == "seed":
                    if not self.confirm_overwrite_saved_game("种子对局"):
                        return
                    self.prompt_and_start_seeded_game()
                elif action == "continue":
                    self.continue_game()
                elif action == "daily":
                    if not self.confirm_overwrite_saved_game("每日挑战"):
                        return
                    self.start_new_game(daily=True)
                elif action == "settings":
                    self.open_settings()
                elif action == "stats":
                    self.open_stats()
                elif action == "save_slot":
                    self.cycle_save_slot()
                elif action == "suit_count":
                    self.suit_count = self.cycle_value(SUIT_COUNT_ORDER, self.suit_count)
                    self.persist_settings()
                elif action == "difficulty_bucket":
                    self.difficulty_bucket = self.cycle_value(DIFFICULTY_BUCKET_ORDER, self.difficulty_bucket)
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
        self._apply_solver_result_if_ready()
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
                self.message = "胜利结算已就绪。按 N 开新局，或按 M 返回菜单。"
                self.request_redraw()

        can_auto_step = (
            self.solver_mode == "auto"
            and not self.solver_running
            and not self.anim_cards
            and not self.victory_anim_active
            and self.drag is None
            and self.stage == GAME
            and time.time() >= self.solver_next_step_at
        )
        did_auto_step = False
        if can_auto_step:
            if self.solver_plan:
                self._play_one_solver_action()
                did_auto_step = True
            else:
                self.solver_mode = None
                self.message = "自动求解演示完成。"
                self.request_redraw()
        if did_auto_step:
            # Important: consume move events in the same tick to avoid one-frame "teleport" flicker.
            self.consume_animation_queue()
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
            f"{title}：已玩 {started}，获胜 {won}，胜率 {win_rate:.1f}% | "
            f"平均步数 {avg_actions:.1f}，平均用时 {avg_duration:.1f} 秒 | "
            f"连胜 {int(bucket['current_streak'])}（最高 {int(bucket['best_streak'])}）"
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
                        tags.append("翻开暗牌")
                    if len(dest_stack) == 0:
                        score -= 8
                        tags.append("占用空列")
                    else:
                        top = dest_stack[-1]
                        if top.suit == src_card.suit:
                            score += 5
                            tags.append("同花衔接")
                    risk = "低"
                    if "占用空列" in tags and moved_len <= 2:
                        risk = "中"
                    if "占用空列" in tags and moved_len == 1 and reveal_bonus == 0:
                        risk = "高"
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
            return "提示+：当前无合法移动。"
        parts = []
        for i, it in enumerate(items, start=1):
            src_stack, src_idx = it["src"]
            tag_text = "，".join(it["tags"]) if it["tags"] else "中性"
            parts.append(
                f"{i}) 列{src_stack}:{src_idx} -> 列{it['dest']} | "
                f"{it['moved_len']} 张，风险 {it['risk']}，{tag_text}"
            )
        return "提示+：" + "；".join(parts)

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
                sx, sy = self.deck_spawn_position()
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

        c.create_text(self.width * 0.5, self.height * 0.2, text="蜘蛛纸牌", fill=theme["hud_text"], font=f"Helvetica {self.fs(48)} bold")
        c.create_text(
            self.width * 0.5,
            self.height * 0.2 + 52,
            text="经典的单人纸牌游戏，目标是将所有牌按花色排序收集起来",
            fill=theme["hud_subtext"],
            font=f"Helvetica {self.fs(16)}",
        )

        bh = 58
        row_gap = 18
        col_gap = 18
        start_y = int(self.height * 0.42)
        margin = 36
        usable_w = max(320, self.width - margin * 2)
        col_w3 = max(160, (usable_w - col_gap * 2) / 3)
        col_w2 = max(200, (usable_w - col_gap) / 2)
        row_top = start_y
        row_mid = row_top + bh + row_gap
        row_bot = row_mid + bh + row_gap
        row_x3 = (self.width - (col_w3 * 3 + col_gap * 2)) / 2
        row_x2 = (self.width - (col_w2 * 2 + col_gap)) / 2

        def draw_button(label, action, fill, x1, y1, w):
            x2 = x1 + w
            y2 = y1 + bh
            enabled = not (action == "continue" and not self.can_continue)
            self.active_buttons.append({"action": action, "rect": (x1, y1, x2, y2), "enabled": enabled})
            button_fill = fill if enabled else "#475569"
            text_fill = "#f8fafc" if enabled else "#cbd5e1"
            c.create_rectangle(x1, y1, x2, y2, fill=button_fill, outline="#f8fafc", width=2)
            c.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=label, fill=text_fill, font=f"Helvetica {self.fs(16)} bold")

        # Row 1: quick start actions.
        draw_button("开始新游戏", "new", "#0f766e", row_x3, row_top, col_w3)
        draw_button("输入种子开局", "seed", "#1f2937", row_x3 + col_w3 + col_gap, row_top, col_w3)
        draw_button("每日挑战", "daily", "#1d4ed8", row_x3 + (col_w3 + col_gap) * 2, row_top, col_w3)

        # Row 2: save/continue actions.
        draw_button("继续游戏", "continue", "#0d9488", row_x2, row_mid, col_w2)
        draw_button(f"存档槽：{self.save_slot}", "save_slot", "#334155", row_x2 + col_w2 + col_gap, row_mid, col_w2)

        # Row 3: information/settings actions.
        draw_button("统计信息", "stats", "#0ea5e9", row_x2, row_bot, col_w2)
        draw_button("游戏设置", "settings", "#7c3aed", row_x2 + col_w2 + col_gap, row_bot, col_w2)

        slot_lines = []
        for row in self.slot_status:
            state = "已保存" if row["exists"] else "空"
            marker = " <" if row["slot"] == self.save_slot else ""
            slot_lines.append(f"槽位 {row['slot']}：{state}{marker}")
        c.create_text(
            self.width * 0.5,
            row_top - self.fs(30),
            text=" | ".join(slot_lines),
            fill=theme["hud_subtext"],
            font=f"Helvetica {self.fs(12)}",
        )

        c.create_text(
            self.width * 0.5,
            self.height - 34,
            text="快捷键：N 新游戏，I 种子开局，C 继续，D 每日，L 切换槽位，P 统计，S 设置",
            fill=theme["hud_subtext"],
            font=f"Helvetica {self.fs(13)}",
        )

    def draw_settings(self, c):
        theme = self.theme
        self.active_buttons = []

        c.create_text(self.width * 0.5, self.height * 0.16, text="游戏设置", fill=theme["hud_text"], font=f"Helvetica {self.fs(42)} bold")
        c.create_text(
            self.width * 0.5,
            self.height * 0.16 + 46,
            text="配置花色数量、难度分级、卡面风格和主题",
            fill=theme["hud_subtext"],
            font=f"Helvetica {self.fs(15)}",
        )

        bw = min(430, int(self.width * 0.34))
        bh = 64
        start_y = int(self.height * 0.32)
        gap = 20
        col_gap = 20
        settings_defs = [
            (f"花色数量：{self.suit_count}", "suit_count", "#0f766e"),
            (f"难度分级：{self.BUCKET_TEXT_ZH.get(self.difficulty_bucket, self.difficulty_bucket)}", "difficulty_bucket", "#14532d"),
            (f"卡面风格：{self.display_style_name()}", "card_style", "#4338ca"),
            (f"主题：{self.display_theme_name()}", "theme", "#9a3412"),
            (f"字体大小：{self.display_font_scale()}", "font_scale", "#0f766e"),
            (f"存档槽：{self.save_slot}", "save_slot", "#334155"),
            ("返回菜单", "back_menu", "#374151"),
        ]

        for i, (label, action, fill) in enumerate(settings_defs):
            row = i // 2
            col = i % 2
            y1 = start_y + row * (bh + gap)
            if i == len(settings_defs) - 1 and len(settings_defs) % 2 == 1:
                # Keep the final "back" button centered when item count is odd.
                x1 = (self.width - bw) / 2
            else:
                total_w = bw * 2 + col_gap
                x1 = (self.width - total_w) / 2 + col * (bw + col_gap)
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
            text="快捷键：1/2/3/4 花色，Q/W/E 难度，B 切换难度，C 风格，T 主题，F 字体，L 槽位，Esc/M 菜单",
            fill=theme["hud_subtext"],
            font=f"Helvetica {self.fs(12)}",
        )

    def draw_stats(self, c):
        theme = self.theme
        self.active_buttons = []
        c.create_text(self.width * 0.5, self.height * 0.14, text="统计信息", fill=theme["hud_text"], font=f"Helvetica {self.fs(42)} bold")
        c.create_text(
            self.width * 0.5,
            self.height * 0.14 + 42,
            text="总计与各（花色数量、难度分级）表现",
            fill=theme["hud_subtext"],
            font=f"Helvetica {self.fs(15)}",
        )

        lines = [self.format_stats_line("总计", self.stats["overall"])]
        for suit_count in SUIT_COUNT_ORDER:
            for bucket_name in DIFFICULTY_BUCKET_ORDER:
                key = profile_key(suit_count, bucket_name)
                lines.append(
                    self.format_stats_line(
                        f"{suit_count}花色/{self.BUCKET_TEXT_ZH.get(bucket_name, bucket_name)}",
                        self.stats["by_profile"][key],
                    )
                )

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
        c.create_text((x1 + x2) / 2, (y1 + y2) / 2, text="返回菜单", fill="#f8fafc", font=f"Helvetica {self.fs(16)} bold")

        c.create_text(
            self.width * 0.5,
            self.height - 24,
            text="快捷键：P 或 Esc 返回菜单",
            fill=theme["hud_subtext"],
            font=f"Helvetica {self.fs(12)}",
        )

    def draw_base_and_hud(self, c):
        theme = self.theme
        deck_x, deck_y = self.deck_position()
        deck_w, deck_h = self.deck_size()

        c.create_rectangle(
            deck_x,
            deck_y,
            deck_x + deck_w,
            deck_y + deck_h,
            fill=theme["deck_fill"],
            outline=theme["deck_outline"],
            width=2,
        )
        c.create_text(
            deck_x + deck_w / 2,
            deck_y + deck_h / 2,
            text=str(self.vm.base_count),
            fill=theme["hud_text"],
            font=f"Helvetica {self.fs(14)} bold",
        )

        c.create_text(16, 16, anchor="nw", text=f"已完成：{self.vm.finished_count}", fill=theme["hud_text"], font=f"Helvetica {self.fs(16)} bold")
        mode = "每日" if self.daily_mode else "普通"
        profile = self.current_profile_label()
        seed_source_text = self.SEED_SOURCE_TEXT_ZH.get(self.seed_source, self.seed_source)
        seed_info = (
            f" | 种子 {self.current_seed}（{seed_source_text}）"
            if self.current_seed is not None
            else f" | 种子（{seed_source_text}）"
        )
        elapsed_sec = 0
        if self.current_game_started_at is not None:
            elapsed_sec = max(0, int(time.time() - self.current_game_started_at))
        elapsed_min = elapsed_sec // 60
        elapsed_remain = elapsed_sec % 60
        seed_text = str(self.current_seed) if self.current_seed is not None else "-"
        c.create_text(
            16,
            42,
            anchor="nw",
            text=f"步数：{self.current_game_actions}  用时：{elapsed_min:02d}:{elapsed_remain:02d}  种子：{seed_text}",
            fill=theme["hud_subtext"],
            font=f"Helvetica {self.fs(12)}",
        )
        if self.SHOW_TOP_LEFT_DETAIL:
            c.create_text(
                16,
                64,
                anchor="nw",
                text=(
                    f"模式：{mode} | 配置：{profile} | 风格：{self.display_style_name()} | "
                    f"主题：{self.display_theme_name()} | 字体：{self.display_font_scale()} | 槽位：{self.save_slot}{seed_info}"
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
        textured_drag = self.card_style in TEXTURED_STYLE_ASSETS
        card_count = len(self.drag.cards)
        full_limit = self.TEXTURED_DRAG_FULL_LIMIT if textured_drag else card_count
        shadow_limit = self.TEXTURED_DRAG_SHADOW_LIMIT if textured_drag else card_count

        for i, card in enumerate(self.drag.cards):
            x = self.drag.x
            y = self.drag.y + i * step
            if i < shadow_limit:
                c.create_rectangle(x + 5, y + 5, x + cw + 5, y + ch + 5, fill="#000000", outline="")
            if i < full_limit:
                self.draw_card(c, x, y, card.hidden, card.suit, card.num, selected=(i == 0))
            else:
                outline = self.theme["card_select"] if i == 0 else self.theme["card_border"]
                c.create_rectangle(x, y, x + cw, y + ch, fill=self.theme["card_front"], outline=outline, width=2 if i == 0 else 1)

        if textured_drag and card_count > full_limit:
            badge_x = self.drag.x + cw - 10
            badge_y = self.drag.y + min((full_limit - 1) * step, step * 2.0) + 16
            c.create_rectangle(badge_x - 52, badge_y - 14, badge_x + 10, badge_y + 14, fill="#111827", outline="#f8fafc", width=1)
            c.create_text(
                badge_x - 21,
                badge_y,
                text=f"+{card_count - full_limit}",
                fill="#f8fafc",
                font=f"Helvetica {self.fs(11)} bold",
            )

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
                text="胜利！",
                fill="#1f2937",
                font=f"Helvetica {size} bold",
            )
            c.create_text(
                self.width * 0.5,
                self.height * 0.42,
                text="胜利！",
                fill="#fde68a",
                font=f"Helvetica {size} bold",
            )
            c.create_text(
                self.width * 0.5,
                self.height * 0.52,
                text="正在结算...",
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
        c.create_text((x1 + x2) / 2, y1 + 44, text="胜利结算", fill="#fde68a", font=f"Helvetica {self.fs(34)} bold")

        moves = self.victory_summary.get("moves", 0)
        duration_sec = self.victory_summary.get("duration_sec", 0.0)
        mode = self.victory_summary.get("mode", "普通")
        profile = self.victory_summary.get("profile", self.current_profile_label())

        lines = [
            f"模式：{mode}",
            f"配置：{profile}",
            f"使用步数：{moves}",
            f"用时：{duration_sec:.1f} 秒",
        ]
        yy = y1 + 108
        for line in lines:
            c.create_text(x1 + 40, yy, anchor="nw", text=line, fill="#e5e7eb", font=f"Helvetica {self.fs(18)}")
            yy += self.fs(34)

        c.create_text(
            (x1 + x2) / 2,
            y2 - 34,
            text="按 N 开始新游戏，或按 M 返回菜单",
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
        dw, dh = self.deck_size()
        return dx <= x <= dx + dw and dy <= y <= dy + dh

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
        base_step = self.height * VISIBLE_STEP_RATIO
        if self.vm is None or not self.vm.stacks:
            return base_step

        max_cards = max(len(stack.cards) for stack in self.vm.stacks)
        if max_cards <= 1:
            return base_step

        sy = self.height * TOP_MARGIN_RATIO
        _, ch = self.card_size()
        # Keep a small bottom area for status text while fitting long piles on screen.
        max_span = self.height - sy - ch - 32
        if max_span <= 0:
            return max(6.0, base_step * 0.4)

        fit_step = max_span / (max_cards - 1)
        min_step = max(6.0, ch * 0.08)
        return max(min_step, min(base_step, fit_step))

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
        dw, _ = self.deck_size()
        x = self.width - dw - 24
        y = 20
        return x, y

    def deck_size(self):
        # Render the deal pile as a horizontal card slot to avoid overlap with stacks.
        cw, ch = self.card_size()
        return ch, cw

    def deck_spawn_position(self):
        dx, dy = self.deck_position()
        dw, dh = self.deck_size()
        cw, ch = self.card_size()
        # Emit dealing animation from the center of the horizontal deck slot.
        return dx + (dw - cw) * 0.5, dy + (dh - ch) * 0.5
