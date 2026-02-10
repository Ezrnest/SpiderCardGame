import unittest

from base.Core import CallDeal, CardMove, Core, FreeStack, RevealTop
from modern_ui.adapter import CoreAdapter


class ModernAdapterTestCase(unittest.TestCase):
    def test_snapshot_empty_core(self):
        core = Core()
        core.base = []
        core.stacks = [[], []]
        core.finishedCount = 0
        core.gameEnded = False

        vm = CoreAdapter.snapshot(core)
        self.assertEqual(0, vm.base_count)
        self.assertEqual(2, len(vm.stacks))
        self.assertFalse(vm.game_ended)

    def test_event_mapping(self):
        move_evt = CoreAdapter.event_to_animation(CardMove((0, 1), (2, 4)))
        deal_evt = CoreAdapter.event_to_animation(CallDeal(10))
        reveal_evt = CoreAdapter.event_to_animation(RevealTop(3))
        free_evt = CoreAdapter.event_to_animation(FreeStack(1, 2))

        self.assertEqual("MOVE", move_evt.type)
        self.assertEqual("DEAL", deal_evt.type)
        self.assertEqual("REVEAL", reveal_evt.type)
        self.assertEqual("COMPLETE_SUIT", free_evt.type)


if __name__ == "__main__":
    unittest.main()

