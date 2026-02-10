from dataclasses import dataclass


@dataclass(frozen=True)
class CardView:
    id: int
    suit: int
    num: int
    hidden: bool


@dataclass(frozen=True)
class StackView:
    cards: tuple[CardView, ...]


@dataclass(frozen=True)
class GameViewModel:
    base_count: int
    finished_count: int
    game_ended: bool
    stacks: tuple[StackView, ...]


@dataclass(frozen=True)
class AnimationEvent:
    type: str
    payload: dict

