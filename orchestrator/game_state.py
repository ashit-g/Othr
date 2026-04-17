"""
game_state.py – Overthrone
Manages the canonical game state stored in Redis and exposes
anonymised snapshots for team bots.
"""

import json
import uuid
import redis
from typing import Dict, Any

# ──────────────────────────────────────────────────────────────
# Redis connection (configure via env or config file in prod)
# ──────────────────────────────────────────────────────────────
_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
    return _redis_client


# ──────────────────────────────────────────────────────────────
# Keys
# ──────────────────────────────────────────────────────────────
TEAMS_KEY      = "overthrone:teams"          # Hash  { real_id -> json(team_data) }
ANON_MAP_KEY   = "overthrone:anon_map"       # Hash  { anon_id -> real_id }        (per-epoch)
EPOCH_KEY      = "overthrone:epoch"          # String  current epoch number


# ──────────────────────────────────────────────────────────────
# Public helpers
# ──────────────────────────────────────────────────────────────

def get_all_teams() -> Dict[str, Dict[str, Any]]:
    """Return {real_id: team_data_dict} for every active team."""
    r = get_redis()
    raw = r.hgetall(TEAMS_KEY)
    return {k: json.loads(v) for k, v in raw.items()}


def get_team(real_id: str) -> Dict[str, Any] | None:
    r = get_redis()
    raw = r.hget(TEAMS_KEY, real_id)
    return json.loads(raw) if raw else None


def update_team(real_id: str, data: Dict[str, Any]) -> None:
    r = get_redis()
    r.hset(TEAMS_KEY, real_id, json.dumps(data))


def get_current_epoch() -> int:
    r = get_redis()
    val = r.get(EPOCH_KEY)
    return int(val) if val else 0


# ──────────────────────────────────────────────────────────────
# Anonymisation – regenerated every epoch
# ──────────────────────────────────────────────────────────────

def rotate_anon_map() -> Dict[str, str]:
    """
    Generate a fresh {anon_id -> real_id} mapping for this epoch
    and persist it in Redis.  Returns the new mapping.
    """
    r = get_redis()
    teams = get_all_teams()

    new_map: Dict[str, str] = {}
    for real_id in teams:
        anon_id = f"kingdom-{uuid.uuid4().hex[:8]}"   # e.g. "kingdom-a3f2c1d0"
        new_map[anon_id] = real_id

    # Atomically replace the old map
    pipe = r.pipeline()
    pipe.delete(ANON_MAP_KEY)
    if new_map:
        pipe.hset(ANON_MAP_KEY, mapping=new_map)
    pipe.execute()

    return new_map


def get_anon_map() -> Dict[str, str]:
    """Return the current {anon_id -> real_id} mapping."""
    r = get_redis()
    return r.hgetall(ANON_MAP_KEY)


def resolve_anon(anon_id: str) -> str | None:
    """Resolve an anon_id to its real_id.  Returns None if not found."""
    r = get_redis()
    return r.hget(ANON_MAP_KEY, anon_id)


def build_anonymised_snapshot(exclude_real_id: str | None = None) -> Dict[str, Any]:
    """
    Build the anonymised game-state dict that is handed to team bots.

    Keys are anon_ids.  Values contain only safe, non-identifying fields.
    Optionally excludes a team from its own snapshot so a bot cannot
    trivially identify itself.
    """
    anon_map = get_anon_map()      # {anon_id -> real_id}
    all_teams = get_all_teams()    # {real_id -> data}

    snapshot: Dict[str, Any] = {}
    for anon_id, real_id in anon_map.items():
        if real_id == exclude_real_id:
            continue
        team_data = all_teams.get(real_id, {})
        snapshot[anon_id] = {
            "hp":        team_data.get("hp", 0),
            "territory": team_data.get("territory", 0),
            "is_alive":  team_data.get("hp", 0) > 0,
        }

    return snapshot
