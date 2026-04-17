"""
attack_engine.py – Overthrone
Resolves a bot's chosen anon_id into a real attack and applies damage.

HP / territory math can be tuned here without touching team-visible code.
"""

from __future__ import annotations

import logging
from typing import Dict, Any

from .game_state import (
    get_team,
    update_team,
    get_all_teams,
    resolve_anon,
)

logger = logging.getLogger("overthrone.attack")

# ──────────────────────────────────────────────────────────────
# Constants (tune per game balance)
# ──────────────────────────────────────────────────────────────
HP_PER_ATTACK_POINT   = 1     # 1 attack point  = 1 HP stolen
MAX_STEAL_RATIO       = 0.25  # cannot steal more than 25 % of target's HP in one epoch
MIN_ATTACK_POINTS     = 100   # minimum AP needed to launch an attack


# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────

class AttackResult:
    def __init__(
        self,
        attacker_id:  str,
        target_id:    str,
        attack_points_spent: int,
        hp_stolen:    int,
        target_eliminated: bool,
    ):
        self.attacker_id         = attacker_id
        self.target_id           = target_id
        self.attack_points_spent = attack_points_spent
        self.hp_stolen           = hp_stolen
        self.target_eliminated   = target_eliminated

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__


def resolve_and_attack(
    attacker_real_id: str,
    chosen_anon_id:   str,
) -> AttackResult | None:
    """
    1. Resolve anon_id → target real_id  (orchestrator-only, hidden from teams)
    2. Deduct attack points from attacker
    3. Apply HP damage to target
    4. Persist both updates atomically (best-effort; Redis pipeline)

    Returns an AttackResult, or None if the attack cannot proceed.
    """
    # Resolve target
    target_real_id = resolve_anon(chosen_anon_id)
    if target_real_id is None:
        logger.warning("Attack from %s: anon_id '%s' could not be resolved.",
                       attacker_real_id, chosen_anon_id)
        return None

    attacker = get_team(attacker_real_id)
    target   = get_team(target_real_id)

    if attacker is None or target is None:
        logger.error("Attack aborted – team data missing for %s or %s.",
                     attacker_real_id, target_real_id)
        return None

    if attacker.get("hp", 0) <= 0:
        logger.info("Dead team %s cannot attack.", attacker_real_id)
        return None

    if target.get("hp", 0) <= 0:
        logger.info("Target %s (%s) is already eliminated.",
                    target_real_id, chosen_anon_id)
        return None

    attack_points = attacker.get("attack_points", 0)
    if attack_points < MIN_ATTACK_POINTS:
        logger.info("Team %s has insufficient attack points (%d).",
                    attacker_real_id, attack_points)
        return None

    # Calculate damage
    raw_damage    = int(attack_points * HP_PER_ATTACK_POINT)
    max_damage    = int(target["hp"] * MAX_STEAL_RATIO)
    damage        = min(raw_damage, max_damage)

    target_new_hp        = max(0, target["hp"] - damage)
    attacker_new_hp      = attacker["hp"] + damage          # stolen HP = territory gain
    target_eliminated    = target_new_hp == 0

    # Persist
    attacker_updated = {**attacker, "hp": attacker_new_hp,   "attack_points": 0}
    target_updated   = {**target,   "hp": target_new_hp,     "is_alive": not target_eliminated}

    update_team(attacker_real_id, attacker_updated)
    update_team(target_real_id,   target_updated)

    result = AttackResult(
        attacker_id          = attacker_real_id,
        target_id            = target_real_id,
        attack_points_spent  = attack_points,
        hp_stolen            = damage,
        target_eliminated    = target_eliminated,
    )

    logger.info(
        "ATTACK | %s → %s (via anon %s) | AP spent: %d | HP stolen: %d | eliminated: %s",
        attacker_real_id, target_real_id, chosen_anon_id,
        attack_points, damage, target_eliminated,
    )

    return result


def get_leaderboard() -> list[Dict[str, Any]]:
    """Return teams sorted by HP descending (for display / logs)."""
    teams = get_all_teams()
    rows  = []
    for real_id, data in teams.items():
        rows.append({
            "team_id":   real_id,
            "team_name": data.get("name", real_id),
            "hp":        data.get("hp", 0),
            "territory": data.get("territory", 0),
            "is_alive":  data.get("hp", 0) > 0,
        })
    return sorted(rows, key=lambda r: r["hp"], reverse=True)
