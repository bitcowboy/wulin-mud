"""World tick orchestrator.

Per docs/architecture.md §4. One tick = one slice of game time
during which every NPC's mood drifts toward its personality target
and every Memory's importance decays.

v0.1 scope:

- Tick is invoked manually (the CLI's ``/tick`` command, or a test)
  rather than by a background scheduler. That keeps the player in
  control of time pacing and the implementation small.
- Two system Actions run per tick, in this order:
    1. ``DriftMood`` (so NPCs feel a touch more rested before their
       memories of the last interaction lose importance)
    2. ``DecayMemories``
- ``tick_dt_game_days`` defaults to whatever ``WULIN_TICK_INTERVAL``
  (real seconds) and ``WULIN_TIME_RATIO`` (1 real second = how many
  game seconds) say. With the .env defaults
  (``WULIN_TICK_INTERVAL=300``, ``WULIN_TIME_RATIO=6`` from the
  "1 real minute = 10 game minutes" rule, i.e. ratio 10/60 → but
  v0.1 keeps real time = game time, so a 5-min real tick is 5 game
  minutes / 1440 ≈ 0.00347 game days. The 1:10 mapping is a v0.2
  goal — see roadmap.md "技术债与重构节点").

Background scheduling is a follow-up: a small ``asyncio.create_task``
loop that calls ``run_tick`` every WULIN_TICK_INTERVAL seconds. Out
of scope for Day 13-17.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlmodel import Session

from wulin_mud.actions.executor import execute_action
from wulin_mud.core.enums import InitiatedBy
from wulin_mud.world.memory_retrieval import SECONDS_PER_GAME_DAY

if TYPE_CHECKING:
    from wulin_mud.actions.base import ActionResult


DEFAULT_TICK_INTERVAL_SECONDS = 300.0
"""Real seconds between ticks if WULIN_TICK_INTERVAL is unset."""

DEFAULT_TIME_RATIO = 1.0
"""How many game seconds per real second. v0.1 default 1:1."""

SYSTEM_ACTOR_ID = "system_tick"
"""Actor id used for all tick-generated ActionRecords. The executor's
caller classifier maps any id that isn't 'player' or 'npc_*' to
CallerType.SYSTEM, so this value is what authorizes the tick actions."""


@dataclass(frozen=True)
class TickResult:
    """Aggregate side-effects from one tick."""

    drift_mood: ActionResult
    decay_memories: ActionResult


def _tick_dt_game_days() -> float:
    """Compute one tick's worth of game time, in game days.

    Reads WULIN_TICK_INTERVAL (real seconds per tick) and
    WULIN_TIME_RATIO (game seconds per real second) from env.
    """
    try:
        tick_interval = float(os.environ.get("WULIN_TICK_INTERVAL", DEFAULT_TICK_INTERVAL_SECONDS))
    except ValueError:
        tick_interval = DEFAULT_TICK_INTERVAL_SECONDS
    try:
        time_ratio = float(os.environ.get("WULIN_TIME_RATIO", DEFAULT_TIME_RATIO))
    except ValueError:
        time_ratio = DEFAULT_TIME_RATIO
    return (tick_interval * time_ratio) / SECONDS_PER_GAME_DAY


async def run_tick(
    *,
    session: Session,
    tick_dt_game_days: float | None = None,
    alpha: float = 0.1,
    now: float | None = None,
) -> TickResult:
    """Run one world tick against ``session``.

    ``tick_dt_game_days`` defaults to the env-derived per-tick game-day
    delta. ``alpha`` is the mood-drift step (0.1 ≈ "close 10% of the
    gap"). Both system actions commit in their own transactions.
    """
    dt_days = tick_dt_game_days if tick_dt_game_days is not None else _tick_dt_game_days()

    drift_result = await execute_action(
        session=session,
        action_name="DriftMood",
        params={"alpha": alpha},
        actor_id=SYSTEM_ACTOR_ID,
        initiated_by=InitiatedBy.WORLD_TICK,
        now=now,
    )
    decay_result = await execute_action(
        session=session,
        action_name="DecayMemories",
        params={"tick_dt_game_days": dt_days},
        actor_id=SYSTEM_ACTOR_ID,
        initiated_by=InitiatedBy.WORLD_TICK,
        now=now,
    )

    return TickResult(drift_mood=drift_result, decay_memories=decay_result)
