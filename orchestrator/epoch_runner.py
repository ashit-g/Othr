"""
epoch_runner.py – Overthrone
Orchestrates a full simulation epoch:

  1. Rotate the anon map (new IDs every epoch → hard-coding is useless)
  2. Load each team's bot code from Redis
  3. Run every bot in the sandbox (parallel)
  4. Resolve attacks via the attack engine
  5. Log results and persist the new epoch counter
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
from typing import Dict, Any, List

from .game_state import (
    get_all_teams,
    get_redis,
    rotate_anon_map,
    build_anonymised_snapshot,
    get_anon_map,
    get_current_epoch,
    EPOCH_KEY,
)
from .sandbox       import execute_team_bot, BotExecutionError
from .attack_engine import resolve_and_attack, AttackResult, get_leaderboard

logger = logging.getLogger("overthrone.epoch")

# Redis key where each team's bot source is stored: "overthrone:bot:<real_id>"
BOT_SOURCE_KEY_PREFIX = "overthrone:bot:"


# ──────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────

def _load_bot_source(real_id: str) -> str:
    """Fetch a team's bot source code from Redis."""
    r = get_redis()
    src = r.get(f"{BOT_SOURCE_KEY_PREFIX}{real_id}")
    return src or _default_bot_source()


def _default_bot_source() -> str:
    """
    The default bot strategy shown to all teams.
    Teams may replace decide_target() with their own logic.
    """
    return '''
def decide_target(game_state):
    """
    game_state: dict  { anon_id -> {"hp": int, "territory": int, "is_alive": bool} }
    Return the anon_id of the kingdom you want to attack.
    """
    # Default strategy: attack the kingdom with the lowest HP
    alive = {k: v for k, v in game_state.items() if v["is_alive"]}
    if not alive:
        return None
    return min(alive, key=lambda k: alive[k]["hp"])
'''


def _run_single_bot(
    real_id:       str,
    source_code:   str,
    snapshot:      Dict[str, Any],
    own_anon_id:   str,
    valid_anon_ids: set,
) -> tuple[str, str | None, str | None]:
    """
    Returns (real_id, chosen_anon_id | None, error_message | None).
    Designed to run in a thread-pool worker.
    """
    try:
        chosen = execute_team_bot(source_code, snapshot, own_anon_id, valid_anon_ids)
        return real_id, chosen, None
    except BotExecutionError as exc:
        return real_id, None, str(exc)


# ──────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────

def run_epoch() -> Dict[str, Any]:
    """
    Execute one full simulation epoch.  Returns a summary dict.
    """
    epoch = get_current_epoch() + 1
    logger.info("═══ EPOCH %d STARTING ═══", epoch)

    # 1. Rotate anonymous IDs  (invalidates any hard-coded targets)
    anon_map = rotate_anon_map()                # {anon_id -> real_id}
    real_to_anon = {v: k for k, v in anon_map.items()}   # inverse

    # 2. Build valid target set
    all_teams      = get_all_teams()
    alive_real_ids = {rid for rid, d in all_teams.items() if d.get("hp", 0) > 0}
    valid_anon_ids = {anon for anon, real in anon_map.items() if real in alive_real_ids}

    # 3. Run all bots concurrently
    bot_results: List[tuple] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(alive_real_ids) or 1) as pool:
        futures = {}
        for real_id in alive_real_ids:
            source      = _load_bot_source(real_id)
            own_anon_id = real_to_anon.get(real_id, "")
            # Each bot gets the full snapshot EXCLUDING itself
            snapshot    = build_anonymised_snapshot(exclude_real_id=real_id)

            fut = pool.submit(
                _run_single_bot,
                real_id, source, snapshot, own_anon_id, valid_anon_ids,
            )
            futures[fut] = real_id

        for fut in concurrent.futures.as_completed(futures):
            bot_results.append(fut.result())

    # 4. Resolve attacks
    attack_log: List[Dict[str, Any]] = []
    errors:     Dict[str, str]       = {}

    for real_id, chosen_anon, error in bot_results:
        if error:
            errors[real_id] = error
            logger.warning("Bot error for team %s: %s", real_id, error)
            continue

        if chosen_anon is None:
            logger.info("Team %s chose no target.", real_id)
            continue

        result = resolve_and_attack(real_id, chosen_anon)
        if result:
            attack_log.append(result.to_dict())

    # 5. Increment epoch counter
    get_redis().set(EPOCH_KEY, epoch)

    # 6. Build summary
    summary = {
        "epoch":      epoch,
        "attacks":    attack_log,
        "bot_errors": errors,
        "leaderboard": get_leaderboard(),
    }

    logger.info("═══ EPOCH %d COMPLETE | %d attacks | leaderboard: %s ═══",
                epoch, len(attack_log),
                [(r["team_name"], r["hp"]) for r in summary["leaderboard"]])

    return summary
