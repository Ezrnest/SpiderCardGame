import json
from pathlib import Path

from modern_ui.ui_config import DIFFICULTY_ORDER

STATS_PATH = Path(__file__).with_name("stats.json")


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
        "by_difficulty": {d: _empty_bucket() for d in DIFFICULTY_ORDER},
    }


def _sanitize(data):
    out = _default_stats()
    if not isinstance(data, dict):
        return out
    for key in ("overall",):
        if isinstance(data.get(key), dict):
            out[key].update({k: data[key].get(k, out[key][k]) for k in out[key]})
    by = data.get("by_difficulty")
    if isinstance(by, dict):
        for d in DIFFICULTY_ORDER:
            src = by.get(d)
            if isinstance(src, dict):
                out["by_difficulty"][d].update({k: src.get(k, out["by_difficulty"][d][k]) for k in out["by_difficulty"][d]})
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


def record_game_started(stats, difficulty):
    stats = _sanitize(stats)
    stats["overall"]["games_started"] += 1
    stats["by_difficulty"][difficulty]["games_started"] += 1
    return stats


def record_game_won(stats, difficulty, duration_sec, actions):
    stats = _sanitize(stats)

    for bucket in (stats["overall"], stats["by_difficulty"][difficulty]):
        bucket["games_won"] += 1
        bucket["total_duration_sec"] += max(0.0, float(duration_sec))
        bucket["total_actions"] += max(0, int(actions))
        bucket["current_streak"] += 1
        bucket["best_streak"] = max(bucket["best_streak"], bucket["current_streak"])
    return stats


def record_game_lost(stats, difficulty):
    stats = _sanitize(stats)
    stats["overall"]["current_streak"] = 0
    stats["by_difficulty"][difficulty]["current_streak"] = 0
    return stats
