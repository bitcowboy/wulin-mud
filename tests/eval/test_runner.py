"""Runner integration: seed → reply → score, end-to-end with FakeProviders.

These tests use FakeProvider to keep the eval reproducible. The actual
scenarios (in tests/eval/npc_consistency/) are exercised against real
OpenAI manually via `python -m wulin_mud.eval.runner` (not in CI)."""

from __future__ import annotations

from pathlib import Path

from wulin_mud.eval import load_scenario, run_scenario
from wulin_mud.llm.provider import FakeProvider

SUN_POPO_DIR = Path(__file__).resolve().parents[1] / "eval" / "npc_consistency" / "sun_popo"


async def test_scenario_01_passes_on_good_reply() -> None:
    """A short, in-character reply passes all assertions."""
    scenario = load_scenario(SUN_POPO_DIR / "scenario_01_first_buy.yaml")
    dlg = FakeProvider(
        responses=[
            "我这有止血膏。八十文一副，伤在哪儿？",  # Talk reply
            "新来的小伙子。",  # interpretation
        ]
    )
    judge = FakeProvider(
        responses=[
            '{"score": 4, "reasoning": "ok"}',
            '{"score": 4, "reasoning": "ok"}',
        ]
    )
    result = await run_scenario(scenario, dialogue_llm=dlg, judge_llm=judge)
    assert result.passed
    assert "止血膏" in result.reply


async def test_scenario_01_fails_when_reply_violates_hard_constraint() -> None:
    """A reply that mentions husband / uses 本店 / runs long must FAIL."""
    scenario = load_scenario(SUN_POPO_DIR / "scenario_01_first_buy.yaml")
    bad = (
        "本店的止血膏家传秘方。客官您稍等。本号生意做了几十年。"
        "想当年我那已故的丈夫还在的时候。这又是一桩京城来的故事。"
    )
    dlg = FakeProvider(responses=[bad, "interp"])
    judge = FakeProvider(default='{"score": 1, "reasoning": "off"}')
    result = await run_scenario(scenario, dialogue_llm=dlg, judge_llm=judge)
    assert not result.passed
    failing = [(a, r) for a, r in result.hard_results if not r.passed]
    # Multiple hard assertions should have flagged this.
    assert len(failing) >= 2


async def test_scenario_can_run_without_judge() -> None:
    """If no judge_llm is supplied, the scenario still runs and passes
    on hard assertions alone (soft assertions are skipped)."""
    scenario = load_scenario(SUN_POPO_DIR / "scenario_01_first_buy.yaml")
    dlg = FakeProvider(
        responses=[
            "我这有止血膏。八十文一副，伤在哪儿？",
            "新来的。",
        ]
    )
    result = await run_scenario(scenario, dialogue_llm=dlg, judge_llm=None)
    assert result.passed
    assert result.soft_results == []


async def test_initial_state_overrides_apply_to_npc() -> None:
    """Override player_relationship; verify Sun's dialogue prompt
    sees the overridden affection (which we trigger via scenario_05)."""
    scenario = load_scenario(SUN_POPO_DIR / "scenario_05_after_offense.yaml")
    dlg = FakeProvider(
        responses=[
            "你这话我听着——先记下。",
            "他还想再来打听。",
        ]
    )
    result = await run_scenario(scenario, dialogue_llm=dlg, judge_llm=None)
    # The prompt should have carried the -0.30 affection narrative.
    dialogue_call = dlg.calls[0]  # first call is the Talk dialogue
    assert "厌恶" in dialogue_call.user or "芥蒂" in dialogue_call.user
    assert result.passed  # this is the "good cold reply" path


async def test_scenario_with_judge_errors_marked_as_error_not_fail() -> None:
    """If only the judge couldn't be reached (provider raised), the
    scenario verdict should be ERROR, not FAIL — the persona side
    still passed."""

    class BoomJudge:
        async def generate(self, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("proxy filtered the request")

    scenario = load_scenario(SUN_POPO_DIR / "scenario_01_first_buy.yaml")
    dlg = FakeProvider(
        responses=[
            "我这有止血膏。八十文一副。",  # Talk reply — clean
            "新来的小伙子。",  # interpretation
        ]
    )
    result = await run_scenario(scenario, dialogue_llm=dlg, judge_llm=BoomJudge())  # type: ignore[arg-type]
    # Persona-side passed
    assert all(r.passed for _, r in result.hard_results)
    # But soft errored → overall not "passed"
    assert not result.passed
    # The new flag distinguishes this from a real persona failure
    assert result.has_judge_errors
    # Report top line says ERROR, not FAIL
    report = result.format_report()
    assert "ERROR" in report
    assert "judge unreachable" in report.lower()
    # And the individual soft line uses the ⚠ marker, not ✗
    assert "⚠" in report


async def test_format_report_renders_pass_and_fail_marks() -> None:
    scenario = load_scenario(SUN_POPO_DIR / "scenario_01_first_buy.yaml")
    dlg = FakeProvider(
        responses=[
            "我这有止血膏。八十文一副。",
            "interp",
        ]
    )
    judge = FakeProvider(default='{"score": 4, "reasoning": "ok"}')
    result = await run_scenario(scenario, dialogue_llm=dlg, judge_llm=judge)
    report = result.format_report()
    assert "✓" in report
    assert "sun_popo__01_first_buy" in report
    assert "Reply:" in report
