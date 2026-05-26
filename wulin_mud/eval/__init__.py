"""Eval framework — regression coverage for NPC consistency.

See docs/llm-integration.md §6. Scenario YAMLs live in
``tests/eval/npc_consistency/<npc_id>/scenario_*.yaml``. The runner
seeds an in-memory world, executes the scenario's player input as a
Talk action, captures the NPC's reply, and grades the reply against
two layers of assertion:

- **hard** — pure-Python, deterministic. Length, forbidden words,
  required phrases. Must always pass.
- **soft** — LLM-as-judge. A separate LLM grades the reply against
  a rubric on a 1-5 scale; the assertion passes when score ≥
  threshold.

A scenario passes overall iff every hard assertion passes AND every
soft assertion clears its threshold.
"""

from wulin_mud.eval.assertions import AssertionResult, evaluate_hard
from wulin_mud.eval.runner import ScenarioResult, run_scenario
from wulin_mud.eval.scenario import (
    HardAssertion,
    HardAssertionType,
    InitialState,
    Scenario,
    SoftAssertion,
    SoftAssertionType,
    load_scenario,
)

__all__ = [
    "AssertionResult",
    "HardAssertion",
    "HardAssertionType",
    "InitialState",
    "Scenario",
    "ScenarioResult",
    "SoftAssertion",
    "SoftAssertionType",
    "evaluate_hard",
    "load_scenario",
    "run_scenario",
]
