"""
╔══════════════════════════════════════════════════════════════╗
║              OVERTHRONE  –  SOVEREIGN BOT                    ║
║                  Team-Visible Interface                      ║
╚══════════════════════════════════════════════════════════════╝

This is the ONLY file you should edit.

Your task is to implement `decide_target(game_state)`.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT IS game_state?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A dictionary of rival kingdoms, identified by anonymous IDs.

Example:
{
    "kingdom-a3f2c1d0": {"hp": 3200, "territory": 64, "is_alive": True},
    "kingdom-bb8e7f12": {"hp":  800, "territory": 16, "is_alive": True},
    "kingdom-c04d9a33": {"hp":    0, "territory":  0, "is_alive": False},
}

  • Anonymous IDs change every Epoch – you CANNOT hard-code a target.
  • Your own kingdom is NOT included (you cannot attack yourself).
  • Only kingdoms with is_alive == True can be attacked.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT SHOULD YOU RETURN?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Return the anonymous ID (string) of the kingdom you want to attack.
Return None if you do not want to attack this epoch.

Your function MUST be named `decide_target`.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONSTRAINTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  • Execution time limit: 2 seconds
  • No imports allowed
  • No file / network / system access
  • Allowed builtins: abs, all, any, bool, dict, enumerate,
    filter, float, int, isinstance, len, list, map, max, min,
    print, range, round, sorted, str, sum, tuple, zip

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


def decide_target(game_state: dict) -> str | None:
    """
    Default strategy: attack the kingdom with the lowest HP.

    Modify this function to implement your own strategy.

    Parameters
    ----------
    game_state : dict
        {anon_id: {"hp": int, "territory": int, "is_alive": bool}, ...}
        (only rival kingdoms; yours is excluded)

    Returns
    -------
    str | None
        The anon_id to attack, or None to skip this epoch.
    """
    # Filter to only living kingdoms
    alive = {k: v for k, v in game_state.items() if v["is_alive"]}

    if not alive:
        return None   # no valid targets

    # Attack the weakest kingdom
    return min(alive, key=lambda k: alive[k]["hp"])


# ──────────────────────────────────────────────────────────────
# STRATEGY IDEAS (delete this block before submitting if you
# don't want opponents to read your code):
#
#   • Attack highest HP (eliminate the strongest)
#   • Attack lowest territory (easiest to collapse)
#   • Weighted score:  0.7 * (1/hp) + 0.3 * (1/territory)
#   • Random among alive kingdoms (unpredictable)
#   • Save AP for one decisive blow (return None until threshold)
# ──────────────────────────────────────────────────────────────
