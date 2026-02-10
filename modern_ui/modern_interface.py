import time
from dataclasses import dataclass
from tkinter import BOTH, Canvas, Tk

from base.Core import Core, DUMMY_PLAYER
from base.Interface import Interface
from modern_ui.adapter import CoreAdapter

CARD_COLOR = "#f7e8bc"
BACK_COLOR = "#274c2b"
DECK_COLOR = "#2f4f2f"
TEXT_COLOR = "#f1f5f9"
HIDDEN_COLOR = "#1f2937"
STACK_GAP_RATIO = 0.015
TOP_MARGIN_RATIO = 0.15
CARD_WIDTH_RATIO = 0.08
CARD_HEIGHT_RATIO = 0.17
VISIBLE_STEP_RATIO = 0.05
ANIM_DURATION = 0.22
FPS_MS = 16

SUITS = "SHCD"
NUMS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")


@dataclass
class MovingCard:
    card_id: int
    suit: int
    num: int
    hidden: bool
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    suppress_stack: int
    suppress_idx: int


class ModernTkInterface(Interface):
    def __init__(self, width=1200, height=760):
        super().__init__()
        self.width = width
        self.height = height
        self.root = None
        self.canvas = None
        self.vm = None
        self.selection = None
        self.message = "N: New  D: Deal  U: Undo  R: Redo"
        self.anim_queue = []
        self.anim_cards = []
        self.anim_start = 0.0
        self.anim_duration = ANIM_DURATION
        self.flash_until = 0.0
        self.flash_stack = None

    def run(self):
        self.root = Tk()
        self.root.title("Spider Card Modern")
        self.root.resizable(True, True)
        self.canvas = Canvas(self.root, width=self.width, height=self.height, highlightthickness=0, bd=0)
        self.canvas.pack(expand=1, fill=BOTH)

        self.root.bind("<Configure>", self.on_resize)
        self.root.bind("<Button-1>", self.on_click)
        self.root.bind("<Key>", self.on_key)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

        self.start_new_game()
        self.tick()
        self.root.mainloop()

    def start_new_game(self):
        core = Core()
        core.registerInterface(self)
        core.registerPlayer(DUMMY_PLAYER)
        core.startGame()
        self.vm = CoreAdapter.snapshot(core)
        self.selection = None
        self.anim_queue.clear()
        self.anim_cards.clear()
        self.message = "Game started. Click a sequence then click destination stack."

    def onStart(self):
        self.vm = CoreAdapter.snapshot(self.core)

    def onWin(self):
        self.message = "You win! Press N for a new game."
        self.vm = CoreAdapter.snapshot(self.core)

    def onEvent(self, event):
        self.vm = CoreAdapter.snapshot(self.core)
        self.anim_queue.append(CoreAdapter.event_to_animation(event))
        super().onEvent(event)

    def onUndoEvent(self, event):
        self.vm = CoreAdapter.snapshot(self.core)
        self.anim_cards.clear()
        self.anim_queue.clear()
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
        if key == "n":
            self.start_new_game()
        elif key == "d":
            if not self.core.askDeal():
                self.message = "No cards left in base."
        elif key == "u":
            if not self.core.askUndo():
                self.message = "Cannot undo."
        elif key == "r":
            if not self.core.askRedo():
                self.message = "Cannot redo."

    def on_click(self, event):
        if self.vm is None or self.anim_cards:
            return
        hit = self.find_stack_and_index(event.x, event.y)
        if hit is None:
            self.selection = None
            self.message = "Selection cleared."
            return
        stack_idx, card_idx = hit
        if self.selection is None:
            if self.core.isValidSequence((stack_idx, card_idx)):
                self.selection = (stack_idx, card_idx)
                self.message = f"Selected stack {stack_idx}, card index {card_idx}. Choose destination."
            else:
                self.message = "Invalid source sequence."
            return
        src = self.selection
        self.selection = None
        ok = self.core.askMove(src, stack_idx)
        if not ok:
            self.message = "Move rejected by rules."

    def tick(self):
        self.consume_animation_queue()
        self.draw()
        self.root.after(FPS_MS, self.tick)

    def consume_animation_queue(self):
        now = time.time()
        if self.anim_cards:
            if now - self.anim_start >= self.anim_duration:
                self.anim_cards.clear()
            return

        if not self.anim_queue:
            return

        evt = self.anim_queue.pop(0)
        self.anim_cards = self.build_anim_cards(evt)
        if self.anim_cards:
            self.anim_start = now
        if evt.type == "REVEAL":
            self.flash_until = now + 0.18
            self.flash_stack = evt.payload["stack"]
        if evt.type == "COMPLETE_SUIT":
            self.flash_until = now + 0.35
            self.flash_stack = evt.payload["stack"]

    def build_anim_cards(self, animation_event):
        if self.vm is None:
            return []
        cards = []
        stacks = self.vm.stacks
        if animation_event.type == "MOVE":
            src_stack, src_idx = animation_event.payload["src"]
            dest_stack, dest_start_idx = animation_event.payload["dest"]
            moved = len(stacks[dest_stack].cards) - dest_start_idx
            for i in range(max(0, moved)):
                card = stacks[dest_stack].cards[dest_start_idx + i]
                sx, sy = self.card_position(src_stack, src_idx + i)
                ex, ey = self.card_position(dest_stack, dest_start_idx + i)
                cards.append(
                    MovingCard(card.id, card.suit, card.num, card.hidden, sx, sy, ex, ey, dest_stack, dest_start_idx + i)
                )
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
                cards.append(MovingCard(card.id, card.suit, card.num, card.hidden, sx, sy, ex, ey, stack_idx, card_idx))
        return cards

    def draw(self):
        if self.canvas is None:
            return
        c = self.canvas
        c.delete("all")
        self.draw_background(c)
        if self.vm is None:
            return

        suppressed = {(a.suppress_stack, a.suppress_idx) for a in self.anim_cards}
        for s_idx, stack in enumerate(self.vm.stacks):
            self.draw_stack(c, s_idx, stack.cards, suppressed)
        self.draw_base_and_hud(c)
        self.draw_active_cards(c)

    def draw_background(self, c):
        c.create_rectangle(0, 0, self.width, self.height, fill=BACK_COLOR, width=0)
        band_h = max(8, self.height // 24)
        for i in range(0, self.height, band_h * 2):
            c.create_rectangle(0, i, self.width, i + band_h, fill="#2d5a34", width=0)

    def draw_base_and_hud(self, c):
        deck_x, deck_y = self.deck_position()
        cw, ch = self.card_size()
        c.create_rectangle(deck_x, deck_y, deck_x + cw, deck_y + ch, fill=DECK_COLOR, outline="#88a67a", width=2)
        c.create_text(deck_x + cw / 2, deck_y + ch / 2, text=str(self.vm.base_count), fill=TEXT_COLOR, font="Helvetica 14 bold")
        c.create_text(16, 16, anchor="nw", text=f"Finished: {self.vm.finished_count}", fill=TEXT_COLOR, font="Helvetica 16 bold")
        c.create_text(16, self.height - 20, anchor="sw", text=self.message, fill="#d8e3db", font="Helvetica 12")

    def draw_stack(self, c, stack_idx, cards, suppressed):
        sx, sy = self.stack_origin(stack_idx)
        cw, ch = self.card_size()
        now = time.time()
        flashing = self.flash_stack == stack_idx and now <= self.flash_until
        if flashing:
            c.create_rectangle(sx - 4, sy - 4, sx + cw + 4, sy + ch + 4, outline="#facc15", width=3)
        c.create_rectangle(sx, sy, sx + cw, sy + ch, outline="#6b8f71", width=1, dash=(4, 2))

        for idx, card in enumerate(cards):
            if (stack_idx, idx) in suppressed:
                continue
            x, y = self.card_position(stack_idx, idx)
            selected = self.selection == (stack_idx, idx)
            self.draw_card(c, x, y, card.hidden, card.suit, card.num, selected=selected)

    def draw_active_cards(self, c):
        if not self.anim_cards:
            return
        t = min(1.0, (time.time() - self.anim_start) / self.anim_duration)
        eased = 1 - (1 - t) * (1 - t)
        for card in self.anim_cards:
            x = card.start_x + (card.end_x - card.start_x) * eased
            y = card.start_y + (card.end_y - card.start_y) * eased
            self.draw_card(c, x, y, card.hidden, card.suit, card.num, selected=False)

    def draw_card(self, c, x, y, hidden, suit, num, selected):
        cw, ch = self.card_size()
        fill = HIDDEN_COLOR if hidden else CARD_COLOR
        outline = "#f59e0b" if selected else "#1f2937"
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

