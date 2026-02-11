from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from solver.analyzer import SearchLimits, analyze_seed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch seed mining for Spider solver/analyzer.")
    parser.add_argument("--suits", type=int, choices=(1, 2, 3, 4), required=True, help="Suit count.")
    parser.add_argument("--start-seed", type=int, required=True, help="Start seed (inclusive).")
    parser.add_argument("--count", type=int, required=True, help="How many seeds to scan.")
    parser.add_argument("--max-seconds", type=float, default=10.0, help="Per-seed solver time limit.")
    parser.add_argument("--max-nodes", type=int, default=2_000_000, help="Per-seed node limit.")
    parser.add_argument("--max-frontier", type=int, default=1_000_000, help="Per-seed frontier limit.")
    parser.add_argument("--target-solved", type=int, default=1, help="Stop early after this many solved seeds.")
    parser.add_argument("--jsonl", type=str, default="", help="Optional output jsonl path.")
    parser.add_argument("--single-stage", action="store_true", help="Disable staged widening search.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    limits = SearchLimits(max_nodes=args.max_nodes, max_seconds=args.max_seconds, max_frontier=args.max_frontier)

    out_path = Path(args.jsonl).expanduser() if args.jsonl else None
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)

    solved = 0
    unknown = 0
    proven_unsolvable = 0
    started = time.perf_counter()

    for i in range(args.count):
        seed = args.start_seed + i
        t0 = time.perf_counter()
        result = analyze_seed(seed=seed, suits=args.suits, limits=limits, staged=not args.single_stage)
        wall_ms = (time.perf_counter() - t0) * 1000.0

        payload = result.to_dict()
        payload["wall_ms"] = round(wall_ms, 3)

        if out_path is not None:
            with out_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")

        if result.status == "solved":
            solved += 1
        elif result.status == "proven_unsolvable":
            proven_unsolvable += 1
        else:
            unknown += 1

        metrics = result.metrics
        print(
            f"seed={seed} status={result.status} reason={metrics.get('reason')} "
            f"wall_ms={wall_ms:.1f} solver_ms={metrics['elapsed_ms']} "
            f"expanded={metrics['expanded_nodes']} unique={metrics['unique_states']} "
            f"score={result.difficulty_score}"
        )

        if solved >= args.target_solved:
            break

    total_ms = (time.perf_counter() - started) * 1000.0
    print(
        f"summary suits={args.suits} scanned={solved + unknown + proven_unsolvable} solved={solved} "
        f"unknown={unknown} proven_unsolvable={proven_unsolvable} total_ms={total_ms:.1f}"
    )


if __name__ == "__main__":
    main()
