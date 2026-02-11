import unittest

from solver.analyzer import SearchLimits, SolverState, analyze_seed, analyze_state, solve_state


def visible(suit, num):
    return (suit * 13 + num, False)


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


if __name__ == "__main__":
    unittest.main()
