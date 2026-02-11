from __future__ import annotations

import argparse
import json
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from solver.analyzer import SearchLimits, analyze_seed


@dataclass(frozen=True, slots=True)
class SeedRow:
    seed: int
    status: str
    score: Optional[float]
    band: Optional[str]
    reason: Optional[str]
    elapsed_ms: float
    expanded_nodes: int
    unique_states: int

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "status": self.status,
            "score": self.score,
            "band": self.band,
            "reason": self.reason,
            "elapsed_ms": self.elapsed_ms,
            "expanded_nodes": self.expanded_nodes,
            "unique_states": self.unique_states,
        }


def _quantile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("empty values")
    if q <= 0:
        return values[0]
    if q >= 1:
        return values[-1]

    pos = (len(values) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return values[lo]
    alpha = pos - lo
    return values[lo] * (1.0 - alpha) + values[hi] * alpha


def bucket_solved_rows(rows: Iterable[SeedRow], max_per_bucket: int = 0) -> tuple[dict[str, list[SeedRow]], dict[str, float]]:
    solved = [row for row in rows if row.status == "solved" and row.score is not None]
    if not solved:
        return {"Easy": [], "Medium": [], "Hard": []}, {"q33": 0.0, "q66": 0.0}

    scores = sorted(float(row.score) for row in solved)
    q33 = _quantile(scores, 1.0 / 3.0)
    q66 = _quantile(scores, 2.0 / 3.0)

    buckets: dict[str, list[SeedRow]] = {"Easy": [], "Medium": [], "Hard": []}
    for row in sorted(solved, key=lambda r: (float(r.score), r.seed)):
        score = float(row.score)
        if score <= q33:
            key = "Easy"
        elif score <= q66:
            key = "Medium"
        else:
            key = "Hard"
        if max_per_bucket > 0 and len(buckets[key]) >= max_per_bucket:
            continue
        buckets[key].append(row)

    return buckets, {"q33": round(q33, 6), "q66": round(q66, 6)}


def _analyze_one(
    seed: int,
    suits: int,
    max_nodes: int,
    max_seconds: float,
    max_frontier: int,
    single_stage: bool,
) -> SeedRow:
    limits = SearchLimits(max_nodes=max_nodes, max_seconds=max_seconds, max_frontier=max_frontier)
    result = analyze_seed(seed=seed, suits=suits, limits=limits, staged=not single_stage)
    metrics = result.metrics
    return SeedRow(
        seed=seed,
        status=result.status,
        score=result.difficulty_score,
        band=result.difficulty_band,
        reason=metrics.get("reason"),
        elapsed_ms=float(metrics.get("elapsed_ms", 0.0)),
        expanded_nodes=int(metrics.get("expanded_nodes", 0)),
        unique_states=int(metrics.get("unique_states", 0)),
    )


def _iter_rows_parallel(
    seeds: list[int],
    suits: int,
    max_nodes: int,
    max_seconds: float,
    max_frontier: int,
    single_stage: bool,
    workers: int,
    progress_every: int,
) -> list[SeedRow]:
    rows: list[SeedRow] = []
    started = time.perf_counter()

    if workers <= 1:
        for idx, seed in enumerate(seeds, 1):
            row = _analyze_one(seed, suits, max_nodes, max_seconds, max_frontier, single_stage)
            rows.append(row)
            if progress_every > 0 and idx % progress_every == 0:
                elapsed = (time.perf_counter() - started) * 1000.0
                print(f"progress {idx}/{len(seeds)} elapsed_ms={elapsed:.1f}")
        return rows

    try:
        with ProcessPoolExecutor(max_workers=workers) as exe:
            futures = {
                exe.submit(_analyze_one, seed, suits, max_nodes, max_seconds, max_frontier, single_stage): seed
                for seed in seeds
            }
            done = 0
            for fut in as_completed(futures):
                rows.append(fut.result())
                done += 1
                if progress_every > 0 and done % progress_every == 0:
                    elapsed = (time.perf_counter() - started) * 1000.0
                    print(f"progress {done}/{len(seeds)} elapsed_ms={elapsed:.1f}")
        return rows
    except PermissionError:
        print("process pool unavailable in current environment; fallback to thread pool")

    with ThreadPoolExecutor(max_workers=workers) as exe:
        futures = {
            exe.submit(_analyze_one, seed, suits, max_nodes, max_seconds, max_frontier, single_stage): seed
            for seed in seeds
        }
        done = 0
        for fut in as_completed(futures):
            rows.append(fut.result())
            done += 1
            if progress_every > 0 and done % progress_every == 0:
                elapsed = (time.perf_counter() - started) * 1000.0
                print(f"progress {done}/{len(seeds)} elapsed_ms={elapsed:.1f}")

    return rows


def _default_output_path(suits: int) -> Path:
    return Path(__file__).resolve().parents[1] / "modern_ui" / f"seed_pool_{suits}s.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build seed pools by quantile-bucketed difficulty.")
    parser.add_argument("--suits", type=int, choices=(1, 2, 4), required=True, help="Suit count.")
    parser.add_argument("--start-seed", type=int, required=True, help="Start seed inclusive.")
    parser.add_argument("--count", type=int, required=True, help="How many seeds to scan.")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 1) - 1), help="Parallel workers.")
    parser.add_argument("--max-seconds", type=float, default=4.0, help="Per-seed search time budget.")
    parser.add_argument("--max-nodes", type=int, default=1_500_000, help="Per-seed node budget.")
    parser.add_argument("--max-frontier", type=int, default=800_000, help="Per-seed frontier budget.")
    parser.add_argument("--single-stage", action="store_true", help="Disable staged widening search.")
    parser.add_argument("--max-per-bucket", type=int, default=0, help="Cap seeds per bucket; 0 means unlimited.")
    parser.add_argument("--progress-every", type=int, default=10, help="Print progress every N completed seeds.")
    parser.add_argument("--out", type=str, default="", help="Output JSON path.")
    parser.add_argument("--raw-jsonl", type=str, default="", help="Optional raw per-seed JSONL path.")
    return parser.parse_args()


def _stats(rows: list[SeedRow]) -> dict:
    solved = sum(1 for r in rows if r.status == "solved")
    unknown = sum(1 for r in rows if r.status == "unknown")
    proven_unsolvable = sum(1 for r in rows if r.status == "proven_unsolvable")
    return {
        "scanned": len(rows),
        "solved": solved,
        "unknown": unknown,
        "proven_unsolvable": proven_unsolvable,
    }


def main() -> None:
    args = parse_args()
    seeds = list(range(args.start_seed, args.start_seed + args.count))

    started = time.perf_counter()
    rows = _iter_rows_parallel(
        seeds=seeds,
        suits=args.suits,
        max_nodes=args.max_nodes,
        max_seconds=args.max_seconds,
        max_frontier=args.max_frontier,
        single_stage=args.single_stage,
        workers=max(1, args.workers),
        progress_every=max(0, args.progress_every),
    )
    rows.sort(key=lambda r: r.seed)

    buckets, quantiles = bucket_solved_rows(rows, max_per_bucket=max(0, args.max_per_bucket))
    stats = _stats(rows)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suits": args.suits,
        "search": {
            "max_seconds": args.max_seconds,
            "max_nodes": args.max_nodes,
            "max_frontier": args.max_frontier,
            "single_stage": args.single_stage,
            "workers": max(1, args.workers),
        },
        "source": {
            "start_seed": args.start_seed,
            "count": args.count,
        },
        "stats": stats,
        "quantiles": quantiles,
        "buckets": {key: [row.seed for row in rows_for_bucket] for key, rows_for_bucket in buckets.items()},
        "bucket_entries": {key: [row.to_dict() for row in rows_for_bucket] for key, rows_for_bucket in buckets.items()},
        "all_rows": [row.to_dict() for row in rows],
        "build_elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
    }

    out_path = Path(args.out).expanduser() if args.out else _default_output_path(args.suits)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.raw_jsonl:
        raw_path = Path(args.raw_jsonl).expanduser()
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        with raw_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row.to_dict(), ensure_ascii=False) + "\n")

    print(
        f"done out={out_path} scanned={stats['scanned']} solved={stats['solved']} "
        f"unknown={stats['unknown']} proven_unsolvable={stats['proven_unsolvable']} "
        f"q33={quantiles['q33']} q66={quantiles['q66']}"
    )


if __name__ == "__main__":
    main()
