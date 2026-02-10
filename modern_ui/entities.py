from dataclasses import dataclass

from modern_ui.view_model import CardView


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


@dataclass
class CollectCard:
    suit: int
    num: int
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    born: float
    duration: float
    angle0: float
    angle1: float


@dataclass
class VictoryCard:
    x: float
    y: float
    vx: float
    vy: float
    angle: float
    va: float
    born: float
    ttl: float
    suit: int
    num: int
    scale: float
    tilt: float
    vtilt: float
