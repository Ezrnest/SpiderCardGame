import json
import random
from pathlib import Path

from modern_ui.ui_config import DIFFICULTY_BUCKET_ORDER


def seed_pool_path(suit_count: int) -> Path:
    return Path(__file__).with_name(f"seed_pool_{int(suit_count)}s.json")


def load_seed_pool_buckets(suit_count: int) -> dict[str, list[int]]:
    out = {key: [] for key in DIFFICULTY_BUCKET_ORDER}
    path = seed_pool_path(suit_count)
    if not path.exists():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out

    buckets = data.get("buckets")
    if not isinstance(buckets, dict):
        return out

    for key in DIFFICULTY_BUCKET_ORDER:
        raw = buckets.get(key, [])
        if not isinstance(raw, list):
            continue
        seeds: list[int] = []
        for value in raw:
            try:
                seeds.append(int(value))
            except Exception:
                continue
        out[key] = seeds
    return out


def choose_seed_for_bucket(suit_count: int, difficulty_bucket: str, rng: random.Random | None = None) -> int | None:
    pools = load_seed_pool_buckets(suit_count)
    options = pools.get(difficulty_bucket, [])
    if not options:
        return None
    pick_rng = rng if rng is not None else random
    return int(options[pick_rng.randrange(len(options))])
