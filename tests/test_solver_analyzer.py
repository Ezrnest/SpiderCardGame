import unittest

from solver.analyzer import (
    Action,
    SearchLimits,
    SearchPolicy,
    SolverState,
    _canonical_state_key,
    _is_immediate_reverse,
    _iter_transitions,
    analyze_seed,
    analyze_state,
    solve_state,
)


def visible(suit, num):
    return suit * 13 + num


class SolverAnalyzerTestCase(unittest.TestCase):
    def test_solve_simple_one_move_position(self):
        full_run = tuple(visible(0, num) for num in range(12, -1, -1))
        state = SolverState(base=(), stacks=(full_run, tuple()), finished_count=0)

        result = solve_state(
            initial_state=state,
            limits=SearchLimits(max_nodes=5000, max_seconds=1.0, max_frontier=20000),
        )

        self.assertEqual("solved", result.status)
        self.assertEqual(1, len(result.solution))
        self.assertEqual("MOVE", result.solution[0].kind)
        self.assertTrue(all(len(stack) == 0 for stack in result.solution_states[-1].stacks))

    def test_analyze_state_reports_difficulty_for_solved_state(self):
        full_run = tuple(visible(0, num) for num in range(12, -1, -1))
        state = SolverState(base=(), stacks=(full_run, tuple()), finished_count=0)

        result = analyze_state(
            initial_state=state,
            suits=1,
            seed=123,
            limits=SearchLimits(max_nodes=5000, max_seconds=1.0, max_frontier=20000),
        )

        self.assertEqual("solved", result.status)
        self.assertTrue(result.solvable)
        self.assertIsNotNone(result.difficulty_score)
        self.assertIn("solution_len", result.metrics)

    def test_analyze_seed_returns_structured_result(self):
        result = analyze_seed(
            seed=20260210,
            suits=1,
            limits=SearchLimits(max_nodes=1500, max_seconds=0.1, max_frontier=5000),
        )

        self.assertIn(result.status, {"solved", "unknown", "proven_unsolvable"})
        self.assertIn("expanded_nodes", result.metrics)
        self.assertIn("elapsed_ms", result.metrics)
        self.assertIn("duplicate_states_skipped", result.metrics)

    def test_solver_skips_duplicate_states(self):
        stacks = (
            (visible(0, 7), visible(0, 6)),
            (visible(0, 8),),
            tuple(),
        )
        state = SolverState(base=(), stacks=stacks, finished_count=0)

        result = solve_state(
            initial_state=state,
            limits=SearchLimits(max_nodes=2000, max_seconds=1.0, max_frontier=20000),
        )

        self.assertLessEqual(result.unique_states, result.generated_nodes)
        self.assertGreater(result.duplicate_states_skipped, 0)

    def test_canonical_key_collapses_stack_permutations(self):
        state_a = SolverState(
            base=(visible(0, 1), visible(0, 2)),
            stacks=((visible(0, 7),), (visible(1, 7),), tuple()),
            finished_count=1,
        )
        state_b = SolverState(
            base=(visible(0, 1), visible(0, 2)),
            stacks=((visible(1, 7),), tuple(), (visible(0, 7),)),
            finished_count=1,
        )

        self.assertEqual(_canonical_state_key(state_a), _canonical_state_key(state_b))

    def test_policy_prefers_same_suit_destination(self):
        state = SolverState(
            base=(),
            stacks=(
                (visible(0, 7), visible(0, 6)),
                (visible(1, 8),),
                (visible(0, 8),),
            ),
            finished_count=0,
        )
        transitions = _iter_transitions(state)
        moves = [t for t in transitions if t.action.kind == "MOVE" and t.action.src_stack == 0 and t.action.src_idx == 0]
        self.assertTrue(moves)
        self.assertTrue(all(m.action.dest_stack == 2 for m in moves))

    def test_policy_does_not_split_same_suit_run(self):
        state = SolverState(
            base=(),
            stacks=(
                (visible(0, 9), visible(0, 8), visible(0, 7)),
                (visible(1, 10),),
                (visible(0, 10),),
            ),
            finished_count=0,
        )
        transitions = _iter_transitions(state)
        self.assertFalse(any(t.action.kind == "MOVE" and t.action.src_stack == 0 and t.action.src_idx == 1 for t in transitions))

    def test_policy_defers_deal_when_moves_exist(self):
        state = SolverState(
            base=(visible(0, 1),),
            stacks=(
                (visible(0, 7),),
                (visible(1, 8),),
                tuple(),
            ),
            finished_count=0,
        )
        transitions = _iter_transitions(state)
        self.assertFalse(any(t.action.kind == "DEAL" for t in transitions))

    def test_policy_allows_deal_when_stuck(self):
        state = SolverState(
            base=(visible(0, 1), visible(0, 2), visible(0, 3)),
            stacks=(
                (visible(0, 4),),
                (visible(1, 4),),
                (visible(2, 4),),
            ),
            finished_count=0,
        )
        transitions = _iter_transitions(state)
        self.assertTrue(any(t.action.kind == "DEAL" for t in transitions))

    def test_tabu_immediate_reverse_is_detected(self):
        state = SolverState(
            base=(),
            stacks=(
                (visible(0, 8),),
                (visible(0, 7), visible(0, 6)),
                tuple(),
            ),
            finished_count=0,
        )
        last_action = Action(kind="MOVE", src_stack=0, src_idx=1, dest_stack=1, moved_len=2)
        self.assertTrue(_is_immediate_reverse(state, last_action, 1, 0, 0, 2))

    def test_macro_chain_applies_follow_up(self):
        state = SolverState(
            base=(),
            stacks=(
                (visible(0, 9), visible(0, 8)),
                (visible(0, 10),),
                (visible(0, 11),),
            ),
            finished_count=0,
        )
        policy = SearchPolicy(
            lock_same_suit_runs=True,
            require_same_suit_destination_when_available=True,
            avoid_empty_for_short_moves=True,
            defer_deal_until_no_moves=True,
            limit_empty_destinations_per_move=True,
            macro_chain_enabled=True,
            macro_max_steps=4,
            macro_empty_restore_enabled=False,
            taboo_immediate_reverse=True,
        )
        transitions = _iter_transitions(state, policy=policy)
        self.assertTrue(any(t.macro_steps > 0 for t in transitions))


if __name__ == "__main__":
    unittest.main()
