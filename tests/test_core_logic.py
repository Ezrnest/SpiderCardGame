import unittest

from base.Core import Card, Core, DUMMY_PLAYER, GameConfig, encodeStack
from base.Interface import Interface


class TestInterface(Interface):
    def __init__(self):
        super().__init__()
        self.events = []
        self.undo_events = []
        self.started = False
        self.won = False

    def onStart(self):
        self.started = True

    def onEvent(self, event):
        self.events.append(event)
        super().onEvent(event)

    def onUndoEvent(self, event):
        self.undo_events.append(event)
        super().onUndoEvent(event)

    def onWin(self):
        self.won = True


def visible(suit, num):
    c = Card.fromSuitAndNum(suit, num)
    c.hidden = False
    return c


class CoreTestCase(unittest.TestCase):
    def make_running_core(self):
        core = Core()
        ui = TestInterface()
        core.registerInterface(ui)
        core.registerPlayer(DUMMY_PLAYER)
        core.startGame()
        return core, ui

    def make_loaded_core(self, stacks, base=None, finished=0, ended=False):
        lines = [str(finished), str(ended), encodeStack(base or [])]
        lines.extend(encodeStack(stack) for stack in stacks)
        core = Core()
        core.loadGameFromLines(lines)
        ui = TestInterface()
        core.registerInterface(ui)
        core.registerPlayer(DUMMY_PLAYER)
        core.resumeGame()
        return core, ui

    def test_start_game_deals_cards_and_reveals_tops(self):
        core, ui = self.make_running_core()
        self.assertTrue(ui.started)
        self.assertEqual(50, len(core.base))
        self.assertEqual(10, len(core.stacks))
        self.assertEqual(54, sum(len(s) for s in core.stacks))
        for stack in core.stacks:
            self.assertGreater(len(stack), 0)
            self.assertFalse(stack[-1].hidden)

    def test_ask_move_moves_sequence_when_rule_is_valid(self):
        stacks = [
            [visible(0, 4), visible(0, 3)],
            [visible(1, 5)],
            [],
        ]
        core, _ = self.make_loaded_core(stacks)
        ok = core.askMove((0, 0), 1)
        self.assertTrue(ok)
        self.assertEqual(0, len(core.stacks[0]))
        self.assertEqual([5, 4, 3], [c.num for c in core.stacks[1]])

    def test_undo_and_redo_deal_restore_state(self):
        core, _ = self.make_running_core()
        before_base = len(core.base)
        before_total = sum(len(s) for s in core.stacks)
        self.assertTrue(core.askDeal())
        self.assertEqual(before_base - 10, len(core.base))
        self.assertEqual(before_total + 10, sum(len(s) for s in core.stacks))
        self.assertTrue(core.askUndo())
        self.assertEqual(before_base, len(core.base))
        self.assertEqual(before_total, sum(len(s) for s in core.stacks))
        self.assertTrue(core.askRedo())
        self.assertEqual(before_base - 10, len(core.base))

    def test_free_stack_and_undo(self):
        full = []
        Card.extendStack(full, suit=2, hidden=False)
        stacks = [full, []]
        core, _ = self.make_loaded_core(stacks)
        suit = core.doFree(0, True)
        self.assertEqual(2, suit)
        self.assertEqual(1, core.finishedCount)
        self.assertEqual(0, len(core.stacks[0]))
        self.assertTrue(core.askUndo())
        self.assertEqual(0, core.finishedCount)
        self.assertEqual(13, len(core.stacks[0]))
        self.assertFalse(core.stacks[0][-1].hidden)

    def test_load_game_parses_false_game_ended(self):
        core = Core()
        core.loadGameFromLines(["0", "False", "empty", "empty"])
        self.assertFalse(core.gameEnded)

    def test_seeded_start_is_deterministic(self):
        config = GameConfig()
        config.seed = 20260210

        core1 = Core()
        ui1 = TestInterface()
        core1.registerInterface(ui1)
        core1.registerPlayer(DUMMY_PLAYER)
        core1.startGame(config)
        s1 = [encodeStack(s) for s in core1.stacks]
        b1 = encodeStack(core1.base)

        core2 = Core()
        ui2 = TestInterface()
        core2.registerInterface(ui2)
        core2.registerPlayer(DUMMY_PLAYER)
        core2.startGame(config)
        s2 = [encodeStack(s) for s in core2.stacks]
        b2 = encodeStack(core2.base)

        self.assertEqual(s1, s2)
        self.assertEqual(b1, b2)


if __name__ == "__main__":
    unittest.main()
