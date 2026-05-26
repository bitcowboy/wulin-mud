"""ActionExecutor — the one entry point that runs an Action against the world.

Pipeline (per docs/action-types.md §4):

    1. Caller submits (action_name, params, actor_id, initiated_by).
    2. Executor opens a DB transaction and builds a WorldState.
    3. action.validate(...) — fail returns an ActionRecord with
       succeeded=False; the world is *not* mutated.
    4. action.declare_side_effects(...) — surfaced for inspection; the
       action itself decides what to do with the resulting witness set.
    5. action.execute(...) — applies side effects, generates witness
       Memories, builds and saves the ActionRecord, returns ActionResult.
    6. Executor commits (or rolls back on exception).

Engineering red line backed by this design: the LLM can only nudge the
world by *proposing an action name + params*. Validation, mutation, and
audit are the executor's responsibility — there is no other write path
into the persistence layer.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session

from wulin_mud.actions.base import ACTION_REGISTRY, ActionResult, CallerType
from wulin_mud.core.enums import InitiatedBy
from wulin_mud.world.state import WorldState


class ActionNotFound(KeyError):
    """Raised when the requested action name is not in ACTION_REGISTRY."""


class ActionCallerNotPermitted(PermissionError):
    """Raised when an action is invoked by a caller type it doesn't allow."""


def _classify_caller(actor_id: str) -> CallerType:
    if actor_id == "player":
        return CallerType.PLAYER
    if actor_id.startswith("npc_"):
        return CallerType.NPC
    return CallerType.SYSTEM


async def execute_action(
    *,
    session: Session,
    action_name: str,
    params: dict[str, Any],
    actor_id: str,
    initiated_by: InitiatedBy,
    llm_reasoning: str | None = None,
    now: float | None = None,
) -> ActionResult:
    """Run one action end-to-end in a single DB transaction."""
    action = ACTION_REGISTRY.get(action_name)
    if action is None:
        raise ActionNotFound(action_name)

    caller = _classify_caller(actor_id)
    if caller not in action.callable_by:
        raise ActionCallerNotPermitted(f"action {action_name!r} not callable by {caller.value!r}")

    world = WorldState(session, now=now, initiated_by=initiated_by, llm_reasoning=llm_reasoning)

    # ----- 1. Validate -----
    validation = action.validate(params, world, actor_id)

    if not validation.ok:
        # Failed actions still leave a trail. The "why" goes into
        # llm_reasoning if no reason was provided by the LLM; otherwise
        # we keep the LLM's reasoning and stash the validation reason in
        # parameters under a sentinel key for forensic value.
        failed_params = dict(params)
        failed_params["__validation_reason__"] = validation.reason
        record = world.build_action_record(
            action_type=action_name,
            actor_id=actor_id,
            parameters=failed_params,
            succeeded=False,
        )
        world.save_action_record(record)
        session.commit()
        return ActionResult(
            succeeded=False,
            action_record_id=record.id,
            narrative_hint=validation.reason,
        )

    # ----- 2/3. Side-effect declaration + execute -----
    try:
        result = await action.execute(params, world, actor_id)
    except Exception:
        session.rollback()
        raise

    session.commit()
    return result
