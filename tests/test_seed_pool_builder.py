import unittest
from argparse import Namespace

from solver.seed_pool_builder import SeedRow, _build_payload, _quantile, bucket_solved_rows, merge_rows


class SeedPoolBuilderTestCase(unittest.TestCase):
    def test_quantile_interpolates(self):
        values = [10.0, 20.0, 30.0, 40.0]
        self.assertAlmostEqual(20.0, _quantile(values, 1.0 / 3.0), places=6)
        self.assertAlmostEqual(30.0, _quantile(values, 2.0 / 3.0), places=6)

    def test_bucket_solved_rows(self):
        rows = [
            SeedRow(seed=1, status="solved", score=10.0, band="Easy", reason=None, elapsed_ms=1.0, expanded_nodes=1, unique_states=1),
            SeedRow(seed=2, status="solved", score=20.0, band="Easy", reason=None, elapsed_ms=1.0, expanded_nodes=1, unique_states=1),
            SeedRow(seed=3, status="solved", score=30.0, band="Medium", reason=None, elapsed_ms=1.0, expanded_nodes=1, unique_states=1),
            SeedRow(seed=4, status="solved", score=40.0, band="Hard", reason=None, elapsed_ms=1.0, expanded_nodes=1, unique_states=1),
            SeedRow(seed=5, status="unknown", score=None, band=None, reason="limits_reached", elapsed_ms=1.0, expanded_nodes=1, unique_states=1),
        ]

        buckets, quantiles = bucket_solved_rows(rows)

        self.assertAlmostEqual(20.0, quantiles["q33"], places=6)
        self.assertAlmostEqual(30.0, quantiles["q66"], places=6)
        self.assertEqual([1, 2], [x.seed for x in buckets["Easy"]])
        self.assertEqual([3], [x.seed for x in buckets["Medium"]])
        self.assertEqual([4], [x.seed for x in buckets["Hard"]])

    def test_merge_rows_prefers_incoming_by_seed(self):
        existing = [
            SeedRow(seed=100, status="unknown", score=None, band=None, reason="limits_reached", elapsed_ms=10.0, expanded_nodes=10, unique_states=10),
            SeedRow(seed=101, status="solved", score=20.0, band="Easy", reason=None, elapsed_ms=12.0, expanded_nodes=12, unique_states=12),
        ]
        incoming = [
            SeedRow(seed=100, status="solved", score=25.0, band="Medium", reason=None, elapsed_ms=8.0, expanded_nodes=8, unique_states=8),
            SeedRow(seed=102, status="unknown", score=None, band=None, reason="limits_reached", elapsed_ms=9.0, expanded_nodes=9, unique_states=9),
        ]

        merged = merge_rows(existing, incoming)
        self.assertEqual([100, 101, 102], [r.seed for r in merged])

        by_seed = {r.seed: r for r in merged}
        self.assertEqual("solved", by_seed[100].status)
        self.assertEqual(25.0, by_seed[100].score)
        self.assertEqual("solved", by_seed[101].status)
        self.assertEqual("unknown", by_seed[102].status)

    def test_payload_contains_unknown_bucket(self):
        args = Namespace(
            suits=4,
            max_seconds=1.0,
            max_nodes=1000,
            max_frontier=500,
            single_stage=False,
            workers=1,
            start_seed=1,
            count=3,
            overwrite=False,
        )
        rows = [
            SeedRow(seed=1, status="solved", score=10.0, band="Easy", reason=None, elapsed_ms=1.0, expanded_nodes=1, unique_states=1),
            SeedRow(seed=2, status="unknown", score=None, band=None, reason="limits_reached", elapsed_ms=1.0, expanded_nodes=1, unique_states=1),
            SeedRow(seed=3, status="unknown", score=None, band=None, reason="limits_reached", elapsed_ms=1.0, expanded_nodes=1, unique_states=1),
        ]

        payload = _build_payload(args, existing_rows=[], rows=rows, started=0.0, in_progress=False)

        self.assertIn("unknown", payload["buckets"])
        self.assertEqual([2, 3], payload["buckets"]["unknown"])
        self.assertNotIn("bucket_entries", payload)


if __name__ == "__main__":
    unittest.main()
