"""
admin.py – Overthrone
Organiser-only CLI utilities:
  • Seed initial team data
  • Upload a team's bot code to Redis
  • Trigger an epoch manually
  • Show the leaderboard
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from orchestrator.game_state import get_redis, update_team, get_all_teams, TEAMS_KEY
from orchestrator.epoch_runner import run_epoch, BOT_SOURCE_KEY_PREFIX
from orchestrator.attack_engine import get_leaderboard


# ──────────────────────────────────────────────────────────────
# Seed
# ──────────────────────────────────────────────────────────────

def cmd_seed(args):
    """Seed *n* dummy teams into Redis for local testing."""
    r = get_redis()
    n = args.count
    for i in range(1, n + 1):
        real_id = f"team-{i:03d}"
        data = {
            "name":          f"Team {i}",
            "hp":            5000,
            "territory":     100,
            "attack_points": 0,
            "is_alive":      True,
        }
        r.hset(TEAMS_KEY, real_id, json.dumps(data))
    print(f"✓ Seeded {n} teams.")


# ──────────────────────────────────────────────────────────────
# Upload bot
# ──────────────────────────────────────────────────────────────

def cmd_upload_bot(args):
    """Push a team's bot file to Redis."""
    r = get_redis()
    with open(args.file, "r", encoding="utf-8") as fh:
        source = fh.read()
    key = f"{BOT_SOURCE_KEY_PREFIX}{args.team_id}"
    r.set(key, source)
    print(f"✓ Bot for '{args.team_id}' uploaded from '{args.file}'.")


# ──────────────────────────────────────────────────────────────
# Award attack points
# ──────────────────────────────────────────────────────────────

def cmd_award(args):
    """Award attack points to a team (after they complete a challenge)."""
    from orchestrator.game_state import get_team, update_team
    team = get_team(args.team_id)
    if team is None:
        print(f"✗ Team '{args.team_id}' not found.")
        return
    team["attack_points"] = team.get("attack_points", 0) + args.points
    update_team(args.team_id, team)
    print(f"✓ Awarded {args.points} AP to '{args.team_id}'. "
          f"New total: {team['attack_points']} AP.")


# ──────────────────────────────────────────────────────────────
# Epoch
# ──────────────────────────────────────────────────────────────

def cmd_run_epoch(args):
    """Trigger a simulation epoch."""
    summary = run_epoch()
    print(f"\n── Epoch {summary['epoch']} complete ──")
    print(f"  Attacks executed : {len(summary['attacks'])}")
    print(f"  Bot errors       : {len(summary['bot_errors'])}")
    print("\n  Leaderboard:")
    for rank, row in enumerate(summary["leaderboard"], 1):
        status = "✓" if row["is_alive"] else "✗"
        print(f"    {rank}. [{status}] {row['team_name']:20s}  HP: {row['hp']:6d}  "
              f"Territory: {row['territory']}")
    if summary["bot_errors"]:
        print("\n  Bot errors:")
        for tid, err in summary["bot_errors"].items():
            print(f"    {tid}: {err}")


# ──────────────────────────────────────────────────────────────
# Leaderboard
# ──────────────────────────────────────────────────────────────

def cmd_leaderboard(args):
    rows = get_leaderboard()
    print("\n  Current Leaderboard:")
    for rank, row in enumerate(rows, 1):
        status = "✓" if row["is_alive"] else "✗"
        print(f"  {rank:2d}. [{status}] {row['team_name']:20s}  HP: {row['hp']:6d}  "
              f"Territory: {row['territory']}")


# ──────────────────────────────────────────────────────────────
# CLI wiring
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(prog="admin", description="Overthrone admin CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_seed = sub.add_parser("seed", help="Seed dummy teams")
    p_seed.add_argument("--count", "-n", type=int, default=5)
    p_seed.set_defaults(func=cmd_seed)

    p_upload = sub.add_parser("upload-bot", help="Upload bot source for a team")
    p_upload.add_argument("team_id")
    p_upload.add_argument("file")
    p_upload.set_defaults(func=cmd_upload_bot)

    p_award = sub.add_parser("award", help="Award attack points to a team")
    p_award.add_argument("team_id")
    p_award.add_argument("points", type=int)
    p_award.set_defaults(func=cmd_award)

    p_epoch = sub.add_parser("run-epoch", help="Execute one simulation epoch")
    p_epoch.set_defaults(func=cmd_run_epoch)

    p_lb = sub.add_parser("leaderboard", help="Show current standings")
    p_lb.set_defaults(func=cmd_leaderboard)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
