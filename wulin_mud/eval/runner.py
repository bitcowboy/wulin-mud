"""Runner — execute one scenario against an LLM provider and grade the reply.

The runner is self-contained: it creates a fresh in-memory SQLite,
seeds the world from YAML, applies any per-scenario overrides, calls
the Talk action, captures the reply via ``ActionResult.narrative_hint``,
runs hard assertions in Python and soft assertions via
:func:`wulin_mud.eval.judge.evaluate_soft`.

Returns a :class:`ScenarioResult` you can pretty-print or feed into a
pytest assertion.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.engine import Engine
from sqlmodel import Session

from wulin_mud.actions import execute_action
from wulin_mud.core.enums import InitiatedBy, RelationshipType
from wulin_mud.eval.assertions import AssertionResult, evaluate_hard
from wulin_mud.eval.judge import evaluate_soft
from wulin_mud.eval.scenario import (
    HardAssertion,
    InitialState,
    Scenario,
    SoftAssertion,
)
from wulin_mud.llm.provider import LLMProvider
from wulin_mud.ontology import (
    NPC,
    PLAYER_ID,
    Item,
    Location,
    PlayerRelationship,
)
from wulin_mud.scripts.seed_world import (
    discover_item_seed_files,
    discover_location_seed_files,
    discover_npc_seed_files,
    load_items_yaml,
    load_locations_yaml,
    load_npc_yaml,
    seed_database,
)
from wulin_mud.world.persistence import (
    get_engine,
    init_db,
)
from wulin_mud.world.state import WorldState


@dataclass
class ScenarioResult:
    """Aggregate verdict for one scenario run."""

    scenario_id: str
    npc_id: str
    reply: str
    hard_results: list[tuple[HardAssertion, AssertionResult]] = field(default_factory=list)
    soft_results: list[tuple[SoftAssertion, AssertionResult]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for _, r in self.hard_results) and all(
            r.passed for _, r in self.soft_results
        )

    @property
    def has_judge_errors(self) -> bool:
        """True iff at least one soft assertion couldn't reach the judge.

        Distinct from "judge gave a low score": the soft result's
        ``score`` is None only when the provider raised.
        """
        return any(r.score is None for _, r in self.soft_results)

    def format_report(self) -> str:
        # Top-line verdict: PASS / FAIL / ERROR.
        # ERROR means at least one soft assertion couldn't be graded —
        # the scenario didn't get a real verdict, so don't claim FAIL.
        if self.passed:
            verdict = "PASS"
        elif self.has_judge_errors and not any(not r.passed for _, r in self.hard_results):
            verdict = "ERROR (judge unreachable — see soft assertion lines)"
        else:
            verdict = "FAIL"
        lines = [
            f"=== {self.scenario_id} ({self.npc_id}) ===",
            verdict,
            "",
            "Reply:",
            "  " + self.reply.replace("\n", "\n  "),
            "",
        ]
        if self.hard_results:
            lines.append("Hard assertions:")
            for hard, result in self.hard_results:
                mark = "✓" if result.passed else "✗"
                lines.append(f"  {mark} {hard.type.value}: {result.detail}")
        if self.soft_results:
            lines.append("Soft assertions:")
            for _soft, result in self.soft_results:
                # ⚠ means errored (judge didn't grade); ✗ means graded
                # but below threshold; ✓ means passed.
                if result.score is None:
                    mark = "⚠"
                elif result.passed:
                    mark = "✓"
                else:
                    mark = "✗"
                lines.append(f"  {mark} {result.detail}")
        return "\n".join(lines)


def _apply_initial_state(session: Session, *, npc_id: str, initial: InitialState) -> None:
    """Overlay the scenario's initial_state on the seeded world.

    The runner only mutates the target NPC + their PlayerRelationship —
    that's all current scenario YAMLs support.
    """
    world = WorldState(session)
    npc = world.get_npc(npc_id)
    if npc is None:
        raise RuntimeError(f"scenario targets {npc_id!r} which is not seeded")

    # NPC state overrides.
    npc_o = initial.npc
    update: dict[str, object] = {}
    if npc_o.mood is not None:
        from wulin_mud.ontology import Mood

        update["mood"] = Mood.model_validate({**npc.mood.model_dump(), **npc_o.mood})
    if npc_o.energy is not None:
        update["energy"] = npc_o.energy
    if npc_o.current_location_id is not None:
        update["current_location_id"] = npc_o.current_location_id
    if update:
        npc = npc.model_copy(update=update)

    # Player relationship overrides.
    pr_o = initial.player_relationship
    has_pr_override = any(
        v is not None
        for v in [
            pr_o.first_met_at,
            pr_o.affection,
            pr_o.trust,
            pr_o.familiarity,
            pr_o.impression_summary,
        ]
    )
    if has_pr_override:
        existing = npc.player_relationship
        pr = existing or PlayerRelationship(
            other_id=PLAYER_ID,
            affection=0.0,
            trust=0.0,
            familiarity=0.0,
            relationship_type=RelationshipType.STRANGER,
            relationship_label="外人",
        )
        new_values: dict[str, object] = {}
        for field_name in (
            "first_met_at",
            "affection",
            "trust",
            "familiarity",
            "impression_summary",
        ):
            v = getattr(pr_o, field_name)
            if v is not None:
                new_values[field_name] = v
        npc.player_relationship = pr.model_copy(update=new_values)

    world.save_npc(npc)
    session.commit()


async def run_scenario(
    scenario: Scenario,
    *,
    dialogue_llm: LLMProvider,
    judge_llm: LLMProvider | None = None,
    db_url: str | None = None,
) -> ScenarioResult:
    """Execute one scenario end-to-end.

    ``dialogue_llm`` is the provider used to generate the NPC's reply
    (and any interpretation memories that fall out of the Talk action).
    ``judge_llm`` is used for soft assertions; if ``None``, soft
    assertions are skipped and the scenario can still pass on hard
    assertions alone.

    ``db_url`` defaults to a fresh per-call temp SQLite file. (We
    can't use ``:memory:`` because the seeder opens its own Engine,
    and in-memory SQLite DBs aren't shared across engines.)
    """
    import tempfile
    from pathlib import Path

    cleanup_path: Path | None = None
    if db_url is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        cleanup_path = Path(tmp.name)
        db_url = f"sqlite:///{cleanup_path.as_posix()}"

    try:
        engine = get_engine(db_url=db_url)
        init_db(engine)

        # Fresh seed in this DB.
        npcs = [load_npc_yaml(p) for p in discover_npc_seed_files()]
        locations: list[Location] = []
        for p in discover_location_seed_files():
            locations.extend(load_locations_yaml(p))
        items: list[Item] = []
        for p in discover_item_seed_files():
            items.extend(load_items_yaml(p))
        seed_database(npcs=npcs, locations=locations, items=items, db_url=db_url)

        return await _execute_scenario(
            scenario=scenario,
            engine=engine,
            npcs=npcs,
            dialogue_llm=dialogue_llm,
            judge_llm=judge_llm,
        )
    finally:
        if cleanup_path is not None and cleanup_path.exists():
            try:
                cleanup_path.unlink()
            except OSError:
                pass


async def _execute_scenario(
    *,
    scenario: Scenario,
    engine: Engine,
    npcs: list[NPC],
    dialogue_llm: LLMProvider,
    judge_llm: LLMProvider | None,
) -> ScenarioResult:
    with Session(engine) as session:
        # Put the player into the NPC's room so Talk validates.
        from wulin_mud.world.persistence import PlayerStateRow

        target_npc = next((n for n in npcs if n.id == scenario.npc_id), None)
        if target_npc is None:
            raise RuntimeError(f"scenario targets {scenario.npc_id!r} which is not seeded")
        prow = session.get(PlayerStateRow, PLAYER_ID)
        if prow is not None:
            prow.current_location_id = target_npc.current_location_id
            session.add(prow)
            session.commit()

        # Now apply scenario-specific overrides.
        _apply_initial_state(session, npc_id=scenario.npc_id, initial=scenario.initial_state)

        # Run the player input through the Talk action.
        result = await execute_action(
            session=session,
            action_name="Talk",
            params={
                "target_id": scenario.npc_id,
                "content": scenario.player_input.strip(),
            },
            actor_id=PLAYER_ID,
            initiated_by=InitiatedBy.PLAYER_INPUT,
            llm=dialogue_llm,
        )
        if not result.succeeded:
            return ScenarioResult(
                scenario_id=scenario.scenario_id,
                npc_id=scenario.npc_id,
                reply=f"<scenario failed validation: {result.narrative_hint}>",
            )

        reply = (result.narrative_hint or "").strip()
        outcome = ScenarioResult(
            scenario_id=scenario.scenario_id, npc_id=scenario.npc_id, reply=reply
        )
        for hard in scenario.assertions.hard:
            outcome.hard_results.append((hard, evaluate_hard(reply, hard)))
        if judge_llm is not None:
            for soft in scenario.assertions.soft:
                outcome.soft_results.append(
                    (
                        soft,
                        await evaluate_soft(
                            provider=judge_llm,
                            scenario=scenario,
                            assertion=soft,
                            reply=reply,
                        ),
                    )
                )
        return outcome
