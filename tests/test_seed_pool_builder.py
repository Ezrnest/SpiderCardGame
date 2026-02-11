import unittest

from solver.seed_pool_builder import SeedRow, _quantile, bucket_solved_rows


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

    def test_bucket_cap(self):
        rows = [
            SeedRow(seed=1, status="solved", score=10.0, band="Easy", reason=None, elapsed_ms=1.0, expanded_nodes=1, unique_states=1),
            SeedRow(seed=2, status="solved", score=11.0, band="Easy", reason=None, elapsed_ms=1.0, expanded_nodes=1, unique_states=1),
            SeedRow(seed=3, status="solved", score=12.0, band="Easy", reason=None, elapsed_ms=1.0, expanded_nodes=1, unique_states=1),
        ]

        buckets, _ = bucket_solved_rows(rows, max_per_bucket=1)
        self.assertLessEqual(len(buckets["Easy"]), 1)
        self.assertLessEqual(len(buckets["Medium"]), 1)
        self.assertLessEqual(len(buckets["Hard"]), 1)


if __name__ == "__main__":
    unittest.main()
