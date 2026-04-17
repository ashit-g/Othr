"""
sandbox.py – Overthrone
Executes a team's decision function in a restricted environment.

Security model
--------------
* The team function runs inside RestrictedPython – a safe subset of
  Python that blocks dangerous builtins, imports, and attribute access.
* The function receives ONLY the anonymised snapshot (no Redis client,
  no real IDs, no network access).
* A hard CPU / wall-clock timeout kills runaway functions.
* The function may only return a single anon_id string.  Anything else
  is rejected.
"""

from __future__ import annotations

import signal
import threading
import types
from typing import Any, Dict

from RestrictedPython import compile_restricted, safe_globals, safe_builtins
from RestrictedPython.Guards import (
    safe_globals,
    guarded_getattr,
    guarded_getitem,
    guarded_iter,
)

# ──────────────────────────────────────────────────────────────
# Timeout helper (cross-platform via threading)
# ──────────────────────────────────────────────────────────────
_TIMEOUT_SECONDS = 2   # max wall-clock time for a team function


class _TimeoutError(Exception):
    pass


def _run_with_timeout(fn, *args, timeout=_TIMEOUT_SECONDS, **kwargs):
    """Run *fn* in a daemon thread and raise _TimeoutError if it exceeds timeout."""
    result_box: list = [None]
    error_box:  list = [None]

    def _target():
        try:
            result_box[0] = fn(*args, **kwargs)
        except Exception as exc:          # noqa: BLE001
            error_box[0] = exc

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout)

    if t.is_alive():
        raise _TimeoutError(f"Bot function timed out after {timeout}s")
    if error_box[0]:
        raise error_box[0]
    return result_box[0]


# ──────────────────────────────────────────────────────────────
# Restricted globals handed to team code
# ──────────────────────────────────────────────────────────────

def _make_restricted_globals() -> Dict[str, Any]:
    glb = dict(safe_globals)            # copy, never mutate the original

    # Whitelist builtins: only pure-functional ones
    _allowed_builtins = {
        "abs", "all", "any", "bool", "dict", "enumerate",
        "filter", "float", "int", "isinstance", "len", "list",
        "map", "max", "min", "print", "range", "round",
        "sorted", "str", "sum", "tuple", "zip",
        # Exceptions teams might catch
        "Exception", "ValueError", "TypeError",
    }
    restricted_builtins = {
        k: v for k, v in safe_builtins.items() if k in _allowed_builtins
    }
    # Also allow the guard hooks RestrictedPython needs
    restricted_builtins["_getattr_"]   = guarded_getattr
    restricted_builtins["_getitem_"]   = guarded_getitem
    restricted_builtins["_getiter_"]   = guarded_iter

    glb["__builtins__"] = restricted_builtins

    # Block any module-level imports entirely
    glb["__import__"] = _blocked_import

    return glb


def _blocked_import(*args, **kwargs):
    raise ImportError("Imports are not allowed inside the bot function.")


# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────

class BotExecutionError(Exception):
    """Raised when a team's bot code fails for any reason."""


def execute_team_bot(
    source_code: str,
    game_snapshot: Dict[str, Any],
    own_anon_id: str,
    valid_anon_ids: set[str],
) -> str | None:
    """
    Compile and run *source_code* (the team's decide_target function).

    Parameters
    ----------
    source_code    : The raw Python source the team submitted.
    game_snapshot  : Anonymised {anon_id: {hp, territory, is_alive}} dict.
    own_anon_id    : The anon_id assigned to this team in this epoch.
    valid_anon_ids : Set of anon_ids the function is allowed to target.

    Returns
    -------
    The anon_id the team's bot chose to attack, or None on error/no target.
    """
    # 1. Compile with RestrictedPython
    try:
        byte_code = compile_restricted(source_code, filename="<team_bot>", mode="exec")
    except SyntaxError as exc:
        raise BotExecutionError(f"Syntax error in bot code: {exc}") from exc

    # 2. Build an isolated globals namespace
    glb = _make_restricted_globals()

    # 3. Execute the module-level code (defines decide_target)
    try:
        exec(byte_code, glb)                   # noqa: S102
    except Exception as exc:                   # noqa: BLE001
        raise BotExecutionError(f"Error during bot module exec: {exc}") from exc

    # 4. Locate the required entry point
    decide_target = glb.get("decide_target")
    if decide_target is None or not callable(decide_target):
        raise BotExecutionError("Bot must define a callable named 'decide_target'.")

    # 5. Run with timeout, passing only the safe snapshot
    try:
        chosen = _run_with_timeout(
            decide_target,
            game_snapshot,   # the ONLY argument the function receives
            timeout=_TIMEOUT_SECONDS,
        )
    except _TimeoutError as exc:
        raise BotExecutionError(str(exc)) from exc
    except Exception as exc:                   # noqa: BLE001
        raise BotExecutionError(f"Runtime error in decide_target: {exc}") from exc

    # 6. Validate the return value
    if chosen is None:
        return None
    if not isinstance(chosen, str):
        raise BotExecutionError(
            f"decide_target must return a string anon_id, got {type(chosen).__name__}."
        )
    if chosen not in valid_anon_ids:
        raise BotExecutionError(
            f"Returned anon_id '{chosen}' is not a valid target this epoch."
        )
    if chosen == own_anon_id:
        raise BotExecutionError("A bot cannot target itself.")

    return chosen
