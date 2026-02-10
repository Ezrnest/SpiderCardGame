from base.Core import CallDeal, CardMove, Core, FreeStack, GameEvent, RevealTop
from modern_ui.view_model import AnimationEvent, CardView, GameViewModel, StackView


class CoreAdapter:
    """Bridges the legacy Core state/events to a renderer-friendly model."""

    @staticmethod
    def snapshot(core: Core) -> GameViewModel:
        stacks = []
        for stack in core.stacks:
            cards = tuple(
                CardView(id=card.id, suit=card.suit, num=card.num, hidden=card.hidden)
                for card in stack
            )
            stacks.append(StackView(cards=cards))
        return GameViewModel(
            base_count=len(core.base),
            finished_count=core.finishedCount,
            game_ended=core.gameEnded,
            stacks=tuple(stacks),
        )

    @staticmethod
    def event_to_animation(event: GameEvent) -> AnimationEvent:
        if isinstance(event, CardMove):
            return AnimationEvent(
                type="MOVE",
                payload={"src": event.src, "dest": event.dest},
            )
        if isinstance(event, CallDeal):
            return AnimationEvent(
                type="DEAL",
                payload={"draw_count": event.drawCount},
            )
        if isinstance(event, RevealTop):
            return AnimationEvent(
                type="REVEAL",
                payload={"stack": event.idx},
            )
        if isinstance(event, FreeStack):
            return AnimationEvent(
                type="COMPLETE_SUIT",
                payload={"stack": event.idx, "suit": event.suit},
            )
        return AnimationEvent(type="UNKNOWN", payload={"event": type(event).__name__})

