"""Executor-level invariants: caller permissions, validation failures
leave audit trails, exceptions roll back."""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from tests.actions.conftest import DoAction
from wulin_mud.actions import (
    ACTION_REGISTRY,
    ActionCallerNotPermitted,
    ActionNotFound,
)
from wulin_mud.actions.base import (
    ActionResult,
    ActionType,
    CallerType,
    SideEffectManifest,
    ValidationResult,
    register_action,
)
from wulin_mud.core.enums import InitiatedBy
from wulin_mud.world.persistence import ActionRecordRow
from wulin_mud.world.state import WorldState


async def test_unknown_action_raises(do_action: DoAction, world_seeded: WorldState) -> None:
    with pytest.raises(ActionNotFound):
        await do_action("NoSuchAction", {}, "player")


async def test_caller_not_permitted_raises(do_action: DoAction, world_seeded: WorldState) -> None:
    # BuyItem is callable by PLAYER and NPC, NOT by SYSTEM. A system
    # actor id (not "player", not prefixed npc_) should be rejected.
    with pytest.raises(ActionCallerNotPermitted):
        await do_action(
            "BuyItem",
            {"item_id": "item_zhixue_gao", "price": 50},
            "system_tick",
            initiated_by=InitiatedBy.WORLD_TICK,
        )


async def test_failed_validation_writes_record_with_succeeded_false(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    """A failed action must still leave an ActionRecord(succeeded=False)."""
    result = await do_action("Greet", {"target_id": "npc_does_not_exist"}, "player")
    assert result.succeeded is False
    assert result.action_record_id

    rows = session.exec(
        select(ActionRecordRow).where(ActionRecordRow.id == result.action_record_id)
    ).all()
    assert len(rows) == 1
    record = rows[0]
    assert record.succeeded is False
    assert record.action_type == "Greet"
    assert record.actor_id == "player"
    # The validation reason is preserved for forensics.
    assert "__validation_reason__" in record.parameters


async def test_executor_rolls_back_on_exception(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    """If an action.execute() raises, no partial mutations survive."""

    class ExplodingAction(ActionType):
        name = "Exploding"
        description = "raises mid-execute"
        callable_by = {CallerType.PLAYER}  # noqa: RUF012

        def validate(self, params, world, actor_id):  # type: ignore[no-untyped-def]
            return ValidationResult(ok=True)

        def declare_side_effects(self, params):  # type: ignore[no-untyped-def]
            return SideEffectManifest()

        async def execute(self, params, world, actor_id) -> ActionResult:  # type: ignore[no-untyped-def]
            player = world.get_player()
            assert player is not None
            world.save_player(player.model_copy(update={"wealth": player.wealth + 1_000_000}))
            raise RuntimeError("boom")

    register_action(ExplodingAction())
    try:
        wealth_before = world_seeded.get_player().wealth  # type: ignore[union-attr]
        with pytest.raises(RuntimeError, match="boom"):
            await do_action("Exploding", {}, "player")
        # Re-open a clean view of the session to confirm rollback.
        session.expire_all()
        wealth_after = world_seeded.get_player().wealth  # type: ignore[union-attr]
        assert wealth_after == wealth_before, (
            "exploding action's mutation must have been rolled back"
        )
    finally:
        ACTION_REGISTRY.pop("Exploding", None)


async def test_initiated_by_flows_to_record(
    do_action: DoAction, session: Session, world_seeded: WorldState, sun_popo
) -> None:
    """The executor's initiated_by must end up on the ActionRecord."""
    result = await do_action(
        "Greet",
        {"target_id": sun_popo.id},
        "player",
        initiated_by=InitiatedBy.LLM_DECISION,
        llm_reasoning="player chose to greet",
    )
    assert result.succeeded
    row = session.get(ActionRecordRow, result.action_record_id)
    assert row is not None
    assert row.initiated_by == InitiatedBy.LLM_DECISION.value
    assert row.llm_reasoning == "player chose to greet"
