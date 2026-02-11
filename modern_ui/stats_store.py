import json
from pathlib import Path

from modern_ui.ui_config import DIFFICULTY_BUCKET_ORDER, LEGACY_DIFFICULTY_TO_PROFILE, SUIT_COUNT_ORDER

STATS_PATH = Path(__file__).with_name("stats.json")


def profile_key(suit_count: int, difficulty_bucket: str) -> str:
    return f"{int(suit_count)}s-{difficulty_bucket}"


def profile_order() -> tuple[str, ...]:
    return tuple(profile_key(s, d) for s in SUIT_COUNT_ORDER for d in DIFFICULTY_BUCKET_ORDER)


def _empty_bucket():
    return {
        "games_started": 0,
        "games_won": 0,
        "total_duration_sec": 0.0,
        "total_actions": 0,
        "current_streak": 0,
        "best_streak": 0,
    }


def _default_stats():
    return {
        "overall": _empty_bucket(),
        "by_profile": {k: _empty_bucket() for k in profile_order()},
    }


def _as_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


def _as_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def _merge_bucket(dst: dict, src: dict):
    if not isinstance(src, dict):
        return
    dst["games_started"] = max(0, _as_int(src.get("games_started"), dst["games_started"]))
    dst["games_won"] = max(0, _as_int(src.get("games_won"), dst["games_won"]))
    dst["total_duration_sec"] = max(0.0, _as_float(src.get("total_duration_sec"), dst["total_duration_sec"]))
    dst["total_actions"] = max(0, _as_int(src.get("total_actions"), dst["total_actions"]))
    dst["current_streak"] = max(0, _as_int(src.get("current_streak"), dst["current_streak"]))
    dst["best_streak"] = max(0, _as_int(src.get("best_streak"), dst["best_streak"]))


def _sanitize(data):
    out = _default_stats()
    if not isinstance(data, dict):
        return out

    _merge_bucket(out["overall"], data.get("overall"))

    touched = set()
    by_profile = data.get("by_profile")
    if isinstance(by_profile, dict):
        for key in profile_order():
            src = by_profile.get(key)
            if isinstance(src, dict):
                _merge_bucket(out["by_profile"][key], src)
                touched.add(key)

    # Legacy field migration from old builds.
    by_difficulty = data.get("by_difficulty")
    if isinstance(by_difficulty, dict):
        for difficulty_name, (suit_count, bucket_name) in LEGACY_DIFFICULTY_TO_PROFILE.items():
            key = profile_key(suit_count, bucket_name)
            if key in touched:
                continue
            src = by_difficulty.get(difficulty_name)
            if isinstance(src, dict):
                _merge_bucket(out["by_profile"][key], src)

    return out


def load_stats():
    if not STATS_PATH.exists():
        return _default_stats()
    try:
        return _sanitize(json.loads(STATS_PATH.read_text(encoding="utf-8")))
    except Exception:
        return _default_stats()


def save_stats(stats):
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATS_PATH.write_text(json.dumps(_sanitize(stats), ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_profile_bucket(stats: dict, suit_count: int, difficulty_bucket: str) -> str:
    key = profile_key(suit_count, difficulty_bucket)
    if key not in stats["by_profile"]:
        stats["by_profile"][key] = _empty_bucket()
    return key


def record_game_started(stats, suit_count, difficulty_bucket):
    stats = _sanitize(stats)
    key = _ensure_profile_bucket(stats, suit_count, difficulty_bucket)
    stats["overall"]["games_started"] += 1
    stats["by_profile"][key]["games_started"] += 1
    return stats


def record_game_won(stats, suit_count, difficulty_bucket, duration_sec, actions):
    stats = _sanitize(stats)
    key = _ensure_profile_bucket(stats, suit_count, difficulty_bucket)

    for bucket in (stats["overall"], stats["by_profile"][key]):
        bucket["games_won"] += 1
        bucket["total_duration_sec"] += max(0.0, float(duration_sec))
        bucket["total_actions"] += max(0, int(actions))
        bucket["current_streak"] += 1
        bucket["best_streak"] = max(bucket["best_streak"], bucket["current_streak"])
    return stats


def record_game_lost(stats, suit_count, difficulty_bucket):
    stats = _sanitize(stats)
    key = _ensure_profile_bucket(stats, suit_count, difficulty_bucket)
    stats["overall"]["current_streak"] = 0
    stats["by_profile"][key]["current_streak"] = 0
    return stats
