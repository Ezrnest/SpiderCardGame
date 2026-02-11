from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

from solver.analyzer import SearchLimits, analyze_seed


def _default_workers() -> int:
    try:
        avail = os.process_cpu_count()
    except Exception:
        avail = None
    if avail is None:
        avail = os.cpu_count() or 1
    return max(1, int(avail) - 1)


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

    @staticmethod
    def from_dict(data: dict) -> "SeedRow":
        return SeedRow(
            seed=int(data["seed"]),
            status=str(data["status"]),
            score=(None if data.get("score") is None else float(data["score"])),
            band=(None if data.get("band") is None else str(data["band"])),
            reason=(None if data.get("reason") is None else str(data["reason"])),
            elapsed_ms=float(data.get("elapsed_ms", 0.0)),
            expanded_nodes=int(data.get("expanded_nodes", 0)),
            unique_states=int(data.get("unique_states", 0)),
        )


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


def bucket_solved_rows(rows: Iterable[SeedRow]) -> tuple[dict[str, list[SeedRow]], dict[str, float]]:
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
    on_row: Optional[Callable[[int, list[SeedRow]], None]] = None,
) -> list[SeedRow]:
    rows: list[SeedRow] = []
    started = time.perf_counter()

    if workers <= 1:
        for idx, seed in enumerate(seeds, 1):
            row = _analyze_one(seed, suits, max_nodes, max_seconds, max_frontier, single_stage)
            rows.append(row)
            if on_row is not None:
                on_row(idx, rows)
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
                if on_row is not None:
                    on_row(done, rows)
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
            if on_row is not None:
                on_row(done, rows)
            if progress_every > 0 and done % progress_every == 0:
                elapsed = (time.perf_counter() - started) * 1000.0
                print(f"progress {done}/{len(seeds)} elapsed_ms={elapsed:.1f}")

    return rows


def _default_output_path(suits: int) -> Path:
    return Path(__file__).resolve().parents[1] / "data" / f"seed_pool_{suits}s.json"


def _derive_output_paths(meta_json_path: Path) -> tuple[Path, Path]:
    base_name = meta_json_path.stem
    parent = meta_json_path.parent
    rows_csv = parent / f"{base_name}_rows.csv"
    return meta_json_path, rows_csv


def _relative_file_ref(meta_json_path: Path, target_path: Path) -> str:
    try:
        return str(target_path.relative_to(meta_json_path.parent))
    except Exception:
        return str(target_path.name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build seed pools by quantile-bucketed difficulty.")
    parser.add_argument("--suits", type=int, choices=(1, 2, 3, 4), required=True, help="Suit count.")
    parser.add_argument("--start-seed", type=int, default=None, help="Start seed inclusive. Default: random.")
    parser.add_argument("--count", type=int, required=True, help="How many seeds to scan.")
    parser.add_argument("--workers", type=int, default=_default_workers(), help="Parallel workers.")
    parser.add_argument("--max-seconds", type=float, default=4.0, help="Per-seed search time budget.")
    parser.add_argument("--max-nodes", type=int, default=1_500_000, help="Per-seed node budget.")
    parser.add_argument("--max-frontier", type=int, default=800_000, help="Per-seed frontier budget.")
    parser.add_argument("--single-stage", action="store_true", help="Disable staged widening search.")
    parser.add_argument("--progress-every", type=int, default=10, help="Print progress every N completed seeds.")
    parser.add_argument("--save-interval-sec", type=float, default=60.0, help="Checkpoint save interval in seconds.")
    parser.add_argument(
        "--out",
        type=str,
        default="",
        help="Output JSON path. Default: data/seed_pool_{suits}s.json",
    )
    parser.add_argument("--raw-jsonl", type=str, default="", help="Optional raw per-seed JSONL path.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite output instead of merging existing json.")
    args = parser.parse_args()
    if not args.out:
        args.out = str(_default_output_path(args.suits))
    return args


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


def _load_existing_rows_from_csv(path: Path) -> list[SeedRow]:
    if not path.exists() or not path.is_file():
        return []
    rows: list[SeedRow] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for item in reader:
                if not isinstance(item, dict):
                    continue
                try:
                    rows.append(
                        SeedRow(
                            seed=int(item.get("seed", "0")),
                            status=str(item.get("status", "")),
                            score=(None if not item.get("score") else float(item["score"])),
                            band=(None if not item.get("band") else str(item["band"])),
                            reason=(None if not item.get("reason") else str(item["reason"])),
                            elapsed_ms=float(item.get("elapsed_ms", "0") or 0.0),
                            expanded_nodes=int(item.get("expanded_nodes", "0") or 0),
                            unique_states=int(item.get("unique_states", "0") or 0),
                        )
                    )
                except Exception:
                    continue
    except Exception:
        return []
    return rows


def _load_existing_rows_from_legacy_json(path: Path) -> list[SeedRow]:
    if not path.exists() or not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    raw_rows = data.get("all_rows")
    if not isinstance(raw_rows, list):
        return []
    rows: list[SeedRow] = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        try:
            rows.append(SeedRow.from_dict(item))
        except Exception:
            continue
    return rows


def _load_existing_rows(rows_csv_path: Path, meta_json_path: Path) -> list[SeedRow]:
    from_csv = _load_existing_rows_from_csv(rows_csv_path)
    if from_csv:
        return from_csv
    # Legacy csv fallback from previous format.
    legacy_details_csv = rows_csv_path.with_name(rows_csv_path.stem.replace("_rows", "_details") + rows_csv_path.suffix)
    if legacy_details_csv != rows_csv_path:
        from_legacy_csv = _load_existing_rows_from_csv(legacy_details_csv)
        if from_legacy_csv:
            return from_legacy_csv
    return _load_existing_rows_from_legacy_json(meta_json_path)


def merge_rows(existing: list[SeedRow], incoming: list[SeedRow]) -> list[SeedRow]:
    merged: dict[int, SeedRow] = {row.seed: row for row in existing}
    for row in incoming:
        merged[row.seed] = row
    return [merged[k] for k in sorted(merged)]


def _build_payload(
    args: argparse.Namespace,
    existing_rows: list[SeedRow],
    rows: list[SeedRow],
    started: float,
    in_progress: bool,
) -> dict:
    merged_rows = merge_rows(existing_rows, rows)
    solved_buckets, quantiles = bucket_solved_rows(merged_rows)
    unknown_rows = [row for row in merged_rows if row.status == "unknown"]
    buckets = dict(solved_buckets)
    buckets["unknown"] = unknown_rows
    stats = _stats(merged_rows)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "in_progress": in_progress,
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
            "merge_mode": "overwrite" if args.overwrite else "merge",
            "existing_rows_loaded": len(existing_rows),
            "incoming_rows": len(rows),
        },
        "stats": stats,
        "quantiles": quantiles,
        "buckets": {key: [row.seed for row in rows_for_bucket] for key, rows_for_bucket in buckets.items()},
        "build_elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
    }


def _write_json_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _write_csv_atomic(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    tmp.replace(path)


def _bucket_by_seed(buckets: dict[str, list[SeedRow]]) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for bucket_name, rows in buckets.items():
        for row in rows:
            mapping[row.seed] = bucket_name
    return mapping


def _build_rows_csv_rows(merged_rows: list[SeedRow], buckets: dict[str, list[SeedRow]]) -> list[dict]:
    bucket_map = _bucket_by_seed(buckets)
    out: list[dict] = []
    for row in merged_rows:
        score = "" if row.score is None else f"{float(row.score):.6f}"
        out.append(
            {
                "seed": int(row.seed),
                "status": row.status,
                "score": score,
                "bucket": bucket_map.get(row.seed, ""),
                "reason": ("" if row.reason is None else row.reason),
                "elapsed_ms": f"{float(row.elapsed_ms):.3f}",
                "expanded_nodes": int(row.expanded_nodes),
                "unique_states": int(row.unique_states),
            }
        )
    return out


def main() -> None:
    args = parse_args()
    if args.start_seed is None:
        args.start_seed = random.SystemRandom().randrange(0, 2_147_483_647)
        print(f"start-seed not set; selected random start_seed={args.start_seed}")
    seeds = list(range(args.start_seed, args.start_seed + args.count))
    meta_json_path = Path(args.out).expanduser()
    meta_json_path.parent.mkdir(parents=True, exist_ok=True)
    meta_json_path, rows_csv_path = _derive_output_paths(meta_json_path)
    existing_rows: list[SeedRow] = []
    if not args.overwrite:
        existing_rows = _load_existing_rows(rows_csv_path, meta_json_path)

    started = time.perf_counter()
    last_save_at = started

    def maybe_checkpoint(done: int, current_rows: list[SeedRow]) -> None:
        nonlocal last_save_at
        interval = max(0.0, float(args.save_interval_sec))
        if interval <= 0:
            return
        now = time.perf_counter()
        if (now - last_save_at) < interval:
            return
        merged_rows = merge_rows(existing_rows, list(current_rows))
        solved_buckets, _ = bucket_solved_rows(merged_rows)
        buckets = dict(solved_buckets)
        buckets["unknown"] = [row for row in merged_rows if row.status == "unknown"]
        payload = _build_payload(args, existing_rows, list(current_rows), started, in_progress=True)
        payload["files"] = {
            "rows_csv": _relative_file_ref(meta_json_path, rows_csv_path),
        }
        _write_json_atomic(meta_json_path, payload)
        _write_csv_atomic(
            rows_csv_path,
            fieldnames=["seed", "status", "score", "bucket", "reason", "elapsed_ms", "expanded_nodes", "unique_states"],
            rows=_build_rows_csv_rows(merged_rows, buckets),
        )
        last_save_at = now
        print(
            f"checkpoint saved out={meta_json_path} done={done}/{len(seeds)} "
            f"scanned={payload['stats']['scanned']} solved={payload['stats']['solved']}"
        )

    rows = _iter_rows_parallel(
        seeds=seeds,
        suits=args.suits,
        max_nodes=args.max_nodes,
        max_seconds=args.max_seconds,
        max_frontier=args.max_frontier,
        single_stage=args.single_stage,
        workers=max(1, args.workers),
        progress_every=max(0, args.progress_every),
        on_row=maybe_checkpoint,
    )
    rows.sort(key=lambda r: r.seed)

    merged_rows = merge_rows(existing_rows, rows)
    solved_buckets, _ = bucket_solved_rows(merged_rows)
    buckets = dict(solved_buckets)
    buckets["unknown"] = [row for row in merged_rows if row.status == "unknown"]

    payload = _build_payload(args, existing_rows, rows, started, in_progress=False)
    payload["files"] = {
        "rows_csv": _relative_file_ref(meta_json_path, rows_csv_path),
    }
    _write_json_atomic(meta_json_path, payload)
    _write_csv_atomic(
        rows_csv_path,
        fieldnames=["seed", "status", "score", "bucket", "reason", "elapsed_ms", "expanded_nodes", "unique_states"],
        rows=_build_rows_csv_rows(merged_rows, buckets),
    )
    stats = payload["stats"]
    quantiles = payload["quantiles"]

    if args.raw_jsonl:
        raw_path = Path(args.raw_jsonl).expanduser()
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        with raw_path.open("a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row.to_dict(), ensure_ascii=False) + "\n")

    print(
        f"done out={meta_json_path} scanned={stats['scanned']} solved={stats['solved']} "
        f"unknown={stats['unknown']} proven_unsolvable={stats['proven_unsolvable']} "
        f"q33={quantiles['q33']} q66={quantiles['q66']} "
        f"merged_existing={len(existing_rows)} incoming={len(rows)}"
    )


if __name__ == "__main__":
    main()
