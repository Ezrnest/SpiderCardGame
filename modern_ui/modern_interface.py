import math
import random
import time
from dataclasses import dataclass
from datetime import date
from tkinter import BOTH, Canvas, Tk

from base.Core import Core, DUMMY_PLAYER, GameConfig
from base.Interface import Interface
from modern_ui.adapter import CoreAdapter
from modern_ui.view_model import CardView

MENU = 1
GAME = 2

CARD_COLOR = "#f7e8bc"
BACK_COLOR = "#1b4332"
DECK_COLOR = "#2d6a4f"
TEXT_COLOR = "#f1f5f9"
HIDDEN_COLOR = "#334155"
STACK_GAP_RATIO = 0.015
TOP_MARGIN_RATIO = 0.16
CARD_WIDTH_RATIO = 0.08
CARD_HEIGHT_RATIO = 0.17
VISIBLE_STEP_RATIO = 0.05
ANIM_DURATION = 0.22
FPS_MS = 16

SUITS = "SHCD"
NUMS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
DIFFICULTY_TO_SUITS = {"Easy": 1, "Medium": 2, "Hard": 4}
DIFFICULTY_ORDER = ("Easy", "Medium", "Hard")


@dataclass
class MovingCard:
    card: CardView
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    suppress_stack: int
    suppress_idx: int
    delay: float


@dataclass
class DragState:
    src_stack: int
    src_idx: int
    cards: list
    anchor_x: float
    anchor_y: float
    x: float
    y: float


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    born: float
    ttl: float
    size: float
    color: str


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
        self.daily_mode = False
        self.current_seed = None

        self.anim_queue = []
        self.anim_cards = []
        self.anim_start = 0.0
        self.anim_duration = ANIM_DURATION

        self.drag = None
        self.hover_drop_stack = None
        self.hover_drop_valid = False
        self.pending_move_anim = None
        self.particles = []
        self.last_win_firework = 0.0
        self.last_drag_spark = 0.0
        self.menu_buttons = []

    def run(self):
        self.root = Tk()
        self.root.title("Spider Card Modern")
        self.root.resizable(True, True)
        self.canvas = Canvas(self.root, width=self.width, height=self.height, highlightthickness=0, bd=0)
        self.canvas.pack(expand=1, fill=BOTH)

        self.root.bind("<Configure>", self.on_resize)
        self.root.bind("<Button-1>", self.on_press)
        self.root.bind("<B1-Motion>", self.on_drag)
        self.root.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Key>", self.on_key)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

        self.open_menu()
        self.tick()
        self.root.mainloop()

    def open_menu(self):
        self.stage = MENU
        self.drag = None
        self.anim_cards.clear()
        self.anim_queue.clear()
        self.message = "Select difficulty, start a new game, or play daily challenge."

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
        core = Core()
        core.registerInterface(self)
        core.registerPlayer(DUMMY_PLAYER)
        core.startGame(self.build_config(daily))
        self.vm = CoreAdapter.snapshot(core)
        self.stage = GAME
        self.drag = None
        self.anim_queue.clear()
        self.anim_cards.clear()
        self.particles.clear()
        mode = "Daily Challenge" if self.daily_mode else "Normal"
        self.message = f"{mode} started ({self.difficulty}). Drag cards to move."

    def onStart(self):
        self.vm = CoreAdapter.snapshot(self.core)

    def onWin(self):
        self.vm = CoreAdapter.snapshot(self.core)
        self.message = "You win! Press N for a new game or M for menu."
        self.spawn_firework_burst(self.width * 0.5, self.height * 0.3, "#22d3ee", 34)
        self.spawn_firework_burst(self.width * 0.35, self.height * 0.26, "#f59e0b", 28)
        self.spawn_firework_burst(self.width * 0.65, self.height * 0.26, "#f472b6", 28)

    def onEvent(self, event):
        self.vm = CoreAdapter.snapshot(self.core)
        self.anim_queue.append(CoreAdapter.event_to_animation(event))
        super().onEvent(event)

    def onUndoEvent(self, event):
        self.vm = CoreAdapter.snapshot(self.core)
        self.anim_cards.clear()
        self.anim_queue.clear()
        self.drag = None
        self.message = "Undo applied."
        super().onUndoEvent(event)

    def notifyRedraw(self):
        self.draw()

    def on_resize(self, event):
        if event.widget != self.root:
            return
        self.width = event.width
        self.height = event.height
        self.draw()

    def on_key(self, event):
        key = event.keysym.lower()
        if key == "m":
            self.open_menu()
        if self.stage == MENU:
            if key in ("n", "return"):
                self.start_new_game(daily=False)
            elif key == "d":
                self.start_new_game(daily=True)
            elif key in ("1", "2", "4"):
                target = {"1": "Easy", "2": "Medium", "4": "Hard"}[key]
                self.difficulty = target
            return

        if key == "n":
            self.start_new_game(daily=False)
        elif key == "d":
            if not self.core.askDeal():
                self.message = "No cards left in base."
        elif key == "u":
            if not self.core.askUndo():
                self.message = "Cannot undo."
        elif key == "r":
            if not self.core.askRedo():
                self.message = "Cannot redo."

    def on_press(self, event):
        if self.stage == MENU:
            self.on_menu_click(event.x, event.y)
            return
        if self.vm is None or self.anim_cards:
            return
        if self.is_point_in_deck(event.x, event.y):
            if not self.core.askDeal():
                self.message = "No cards left in base."
            else:
                self.message = "Dealt from deck."
            return
        hit = self.find_stack_and_index(event.x, event.y)
        if hit is None:
            return
        stack_idx, card_idx = hit
        if not self.core.isValidSequence((stack_idx, card_idx)):
            self.message = "This sequence cannot be moved."
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
        self.spawn_spark_shower(src_x, src_y, "#fde047", 8)

    def on_drag(self, event):
        if self.drag is None:
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
        now = time.time()
        if now - self.last_drag_spark > 0.04:
            self.last_drag_spark = now
            self.spawn_spark_shower(
                self.drag.x + self.card_size()[0] * 0.5,
                self.drag.y + self.card_size()[1] * 0.35,
                "#93c5fd",
                2,
                speed=(0.2, 1.2),
                ttl=(0.18, 0.35),
            )

    def on_release(self, event):
        if self.drag is None:
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
            self.spawn_spark_shower(sx + self.card_size()[0] * 0.5, sy + 20, "#ef4444", 10)
        else:
            sx, sy = self.stack_origin(drop_stack)
            self.spawn_spark_shower(sx + self.card_size()[0] * 0.5, sy + 20, "#86efac", 8)

    def on_menu_click(self, x, y):
        for button in self.menu_buttons:
            x1, y1, x2, y2 = button["rect"]
            if x1 <= x <= x2 and y1 <= y <= y2:
                action = button["action"]
                if action == "new":
                    self.start_new_game(daily=False)
                elif action == "daily":
                    self.start_new_game(daily=True)
                elif action == "difficulty":
                    idx = DIFFICULTY_ORDER.index(self.difficulty)
                    self.difficulty = DIFFICULTY_ORDER[(idx + 1) % len(DIFFICULTY_ORDER)]
                return

    def tick(self):
        self.consume_animation_queue()
        self.update_effects()
        if self.stage == GAME and self.vm and self.vm.game_ended:
            now = time.time()
            if now - self.last_win_firework > 0.5:
                self.last_win_firework = now
                x = random.uniform(self.width * 0.2, self.width * 0.8)
                y = random.uniform(self.height * 0.16, self.height * 0.45)
                color = random.choice(["#fde047", "#22d3ee", "#f472b6", "#a3e635"])
                self.spawn_firework_burst(x, y, color, 16)
        self.draw()
        self.root.after(FPS_MS, self.tick)

    def consume_animation_queue(self):
        now = time.time()
        if self.anim_cards:
            end_time = self.anim_start + self.anim_duration + max(c.delay for c in self.anim_cards)
            if now >= end_time:
                self.anim_cards.clear()
            return

        if not self.anim_queue:
            return

        evt = self.anim_queue.pop(0)
        self.anim_cards = self.build_anim_cards(evt)
        if self.anim_cards:
            self.anim_start = now
        if evt.type == "REVEAL":
            pass
        elif evt.type == "COMPLETE_SUIT":
            stack_idx = evt.payload["stack"]
            sx, sy = self.stack_origin(stack_idx)
            cw, _ = self.card_size()
            self.spawn_firework_burst(sx + cw * 0.5, sy + 20, "#f59e0b", 24)
        elif evt.type == "MOVE":
            pass

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
        alive_particles = []
        for p in self.particles:
            age = now - p.born
            if age > p.ttl:
                continue
            p.x += p.vx
            p.y += p.vy
            p.vy += 0.06
            p.vx *= 0.985
            p.vy *= 0.985
            alive_particles.append(p)
        self.particles = alive_particles

    def draw(self):
        if self.canvas is None:
            return
        c = self.canvas
        c.delete("all")
        self.draw_background(c)
        if self.stage == MENU:
            self.draw_menu(c)
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
        self.draw_drag_cards(c)
        self.draw_particles(c)

    def draw_background(self, c):
        c.create_rectangle(0, 0, self.width, self.height, fill=BACK_COLOR, width=0)
        band_h = max(10, self.height // 20)
        for i in range(0, self.height + band_h, band_h):
            alpha_shift = 12 * math.sin(i / max(1, band_h))
            tone = int(58 + alpha_shift)
            tone = max(40, min(90, tone))
            color = f"#{tone:02x}{(tone + 24):02x}{(tone + 8):02x}"
            c.create_rectangle(0, i, self.width, i + band_h, fill=color, width=0)

    def draw_menu(self, c):
        title_y = self.height * 0.2
        c.create_text(
            self.width * 0.5,
            title_y,
            text="Spider Card Modern",
            fill="#fef08a",
            font="Helvetica 48 bold",
        )
        c.create_text(
            self.width * 0.5,
            title_y + 52,
            text="Drag-and-drop, animated effects, and challenge modes",
            fill="#d1fae5",
            font="Helvetica 16",
        )

        bw = min(420, int(self.width * 0.42))
        bh = 58
        start_y = int(self.height * 0.4)
        gap = 20
        self.menu_buttons = [
            {"label": f"Difficulty: {self.difficulty} (click to switch)", "action": "difficulty"},
            {"label": "Start New Game", "action": "new"},
            {"label": "Daily Challenge", "action": "daily"},
        ]
        for i, button in enumerate(self.menu_buttons):
            x1 = (self.width - bw) / 2
            y1 = start_y + i * (bh + gap)
            x2 = x1 + bw
            y2 = y1 + bh
            button["rect"] = (x1, y1, x2, y2)
            fill = "#0f766e" if button["action"] != "difficulty" else "#1d4ed8"
            c.create_rectangle(x1, y1, x2, y2, fill=fill, outline="#f8fafc", width=2)
            c.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=button["label"], fill="#f8fafc", font="Helvetica 16 bold")

        c.create_text(
            self.width * 0.5,
            self.height - 40,
            text="Keys: 1/2/4 set difficulty, N start game, D daily challenge",
            fill="#bbf7d0",
            font="Helvetica 13",
        )

    def draw_base_and_hud(self, c):
        deck_x, deck_y = self.deck_position()
        cw, ch = self.card_size()
        c.create_rectangle(deck_x, deck_y, deck_x + cw, deck_y + ch, fill=DECK_COLOR, outline="#a7f3d0", width=2)
        c.create_text(deck_x + cw / 2, deck_y + ch / 2, text=str(self.vm.base_count), fill=TEXT_COLOR, font="Helvetica 14 bold")
        c.create_text(16, 16, anchor="nw", text=f"Finished: {self.vm.finished_count}", fill=TEXT_COLOR, font="Helvetica 16 bold")
        mode = "Daily" if self.daily_mode else "Normal"
        seed_info = f" | seed {self.current_seed}" if self.current_seed is not None else ""
        c.create_text(
            16,
            42,
            anchor="nw",
            text=f"Mode: {mode} | Difficulty: {self.difficulty}{seed_info}",
            fill="#d1fae5",
            font="Helvetica 12",
        )
        c.create_text(
            16,
            self.height - 20,
            anchor="sw",
            text=self.message,
            fill="#d8e3db",
            font="Helvetica 12",
        )

    def draw_stack(self, c, stack_idx, cards, suppressed):
        sx, sy = self.stack_origin(stack_idx)
        cw, ch = self.card_size()
        outline = "#99f6e4"
        width = 1
        if self.drag is not None and self.hover_drop_stack == stack_idx:
            if self.hover_drop_valid:
                outline = "#4ade80"
                width = 3
            else:
                outline = "#ef4444"
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
        for i, card in enumerate(self.drag.cards):
            x = self.drag.x
            y = self.drag.y + i * step
            c.create_rectangle(
                x + 5,
                y + 5,
                x + self.card_size()[0] + 5,
                y + self.card_size()[1] + 5,
                fill="#000000",
                outline="",
            )
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

    def draw_card(self, c, x, y, hidden, suit, num, selected):
        cw, ch = self.card_size()
        fill = HIDDEN_COLOR if hidden else CARD_COLOR
        outline = "#fde047" if selected else "#0f172a"
        width = 3 if selected else 1
        c.create_rectangle(x, y, x + cw, y + ch, fill=fill, outline=outline, width=width)
        if hidden:
            c.create_text(x + cw / 2, y + ch / 2, text="###", fill="#e5e7eb", font="Helvetica 12 bold")
            return
        text = f"{SUITS[suit]}{NUMS[num]}"
        color = "#ef4444" if suit in (1, 3) else "#111827"
        c.create_text(x + 8, y + 8, anchor="nw", text=text, fill=color, font="Helvetica 12 bold")

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

    def spawn_firework_burst(self, x, y, color, count):
        now = time.time()
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
                    color=random.choice([color, "#f8fafc", "#fde68a", "#bfdbfe"]),
                )
            )

    def spawn_spark_shower(self, x, y, color, count, speed=(0.8, 2.6), ttl=(0.25, 0.5)):
        now = time.time()
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
                    color=random.choice([color, "#ffffff", "#e2e8f0"]),
                )
            )

    def card_size(self):
        return self.width * CARD_WIDTH_RATIO, self.height * CARD_HEIGHT_RATIO

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
