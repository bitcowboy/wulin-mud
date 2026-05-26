"""Eval CLI — run scenarios against a live LLM, print a report.

Invoke as::

    python -m wulin_mud.eval                  # all scenarios
    python -m wulin_mud.eval --npc npc_sun_popo
    python -m wulin_mud.eval --scenario sun_popo__03_mention_husband
    python -m wulin_mud.eval --verbose        # print rubric + reasoning
    python -m wulin_mud.eval --dry-run        # discover only, no LLM calls

Reads OPENAI_API_KEY from .env (project .env wins via override=True).

Exit codes:
  0 — every scenario passed
  1 — one or more scenarios failed an assertion
  2 — discovery / setup error
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from wulin_mud.eval.runner import ScenarioResult, run_scenario
from wulin_mud.eval.scenario import Scenario, load_scenario
from wulin_mud.llm.provider import FakeProvider, LLMProvider, OpenAIProvider

DEFAULT_SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "tests" / "eval" / "npc_consistency"


console = Console()


@dataclass
class CliConfig:
    scenarios_dir: Path
    npc_filter: str | None
    scenario_filter: str | None
    verbose: bool
    dry_run: bool


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_scenarios(
    scenarios_dir: Path,
    *,
    npc_filter: str | None = None,
    scenario_filter: str | None = None,
) -> list[Scenario]:
    """Walk ``scenarios_dir`` finding ``<npc_id>/scenario_*.yaml`` files.

    ``npc_filter`` restricts to one NPC's folder; ``scenario_filter``
    restricts to one ``scenario_id``.
    """
    if not scenarios_dir.exists():
        return []
    found: list[Scenario] = []
    for npc_dir in sorted(scenarios_dir.iterdir()):
        if not npc_dir.is_dir():
            continue
        if npc_filter and npc_dir.name != npc_filter:
            continue
        for path in sorted(npc_dir.glob("scenario_*.yaml")):
            scenario = load_scenario(path)
            if scenario_filter and scenario.scenario_id != scenario_filter:
                continue
            found.append(scenario)
    return found


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_summary(results: list[ScenarioResult], *, verbose: bool) -> None:
    table = Table(title="Eval summary", show_lines=False)
    table.add_column("Scenario", overflow="fold")
    table.add_column("NPC")
    table.add_column("Result", justify="center")
    table.add_column("Hard", justify="right")
    table.add_column("Soft (avg)", justify="right")

    for r in results:
        hard_pass = sum(1 for _, x in r.hard_results if x.passed)
        hard_total = len(r.hard_results)
        soft_scores = [x.score for _, x in r.soft_results if x.score is not None]
        soft_str = f"{sum(soft_scores) / len(soft_scores):.2f}/5" if soft_scores else "—"
        verdict = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        table.add_row(
            r.scenario_id,
            r.npc_id,
            verdict,
            f"{hard_pass}/{hard_total}",
            soft_str,
        )
    console.print(table)

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    pct = (100.0 * passed / total) if total else 0.0
    console.print(f"\n[bold]{passed}/{total} passed[/bold] ({pct:.0f}%)")

    if verbose:
        for r in results:
            console.print("\n" + r.format_report())


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def run_all(
    scenarios: Iterable[Scenario],
    *,
    dialogue_llm: LLMProvider,
    judge_llm: LLMProvider | None,
) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    for s in scenarios:
        console.print(f"  running [cyan]{s.scenario_id}[/cyan]...", end=" ")
        try:
            result = await run_scenario(s, dialogue_llm=dialogue_llm, judge_llm=judge_llm)
            mark = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
            console.print(mark)
            results.append(result)
        except Exception as exc:
            console.print(f"[red]ERROR[/red] ({type(exc).__name__}: {exc})")
            results.append(
                ScenarioResult(
                    scenario_id=s.scenario_id,
                    npc_id=s.npc_id,
                    reply=f"<runner error: {exc}>",
                )
            )
    return results


def _parse_args(argv: list[str] | None = None) -> CliConfig:
    parser = argparse.ArgumentParser(
        prog="python -m wulin_mud.eval",
        description="Run NPC-consistency scenarios against a live LLM.",
    )
    parser.add_argument(
        "--scenarios-dir",
        type=Path,
        default=DEFAULT_SCENARIOS_DIR,
        help="Root directory holding <npc_id>/scenario_*.yaml files.",
    )
    parser.add_argument(
        "--npc", dest="npc_filter", default=None, help="Only run scenarios under this NPC folder."
    )
    parser.add_argument(
        "--scenario", dest="scenario_filter", default=None, help="Only run this scenario_id."
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print full per-scenario report after the summary."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Discover scenarios but skip LLM calls."
    )
    args = parser.parse_args(argv)
    return CliConfig(
        scenarios_dir=args.scenarios_dir,
        npc_filter=args.npc_filter,
        scenario_filter=args.scenario_filter,
        verbose=args.verbose,
        dry_run=args.dry_run,
    )


def _build_providers(*, dry_run: bool) -> tuple[LLMProvider, LLMProvider | None]:
    """Return (dialogue_llm, judge_llm). Dry-run gets FakeProviders."""
    if dry_run:
        # Canned replies + judge scores so the framework can run end-to-end
        # without hitting the network. Useful for smoke-testing the CLI.
        return (
            FakeProvider(default="（FakeProvider 占位回复）"),
            FakeProvider(default='{"score": 3, "reasoning": "dry-run"}'),
        )
    dialogue = OpenAIProvider()
    judge = OpenAIProvider()
    return dialogue, judge


async def amain(config: CliConfig) -> int:
    scenarios = discover_scenarios(
        config.scenarios_dir,
        npc_filter=config.npc_filter,
        scenario_filter=config.scenario_filter,
    )
    if not scenarios:
        console.print(f"[red]No scenarios found under {config.scenarios_dir}[/red]")
        return 2
    console.print(f"Found [bold]{len(scenarios)}[/bold] scenario(s) under {config.scenarios_dir}.")

    try:
        dialogue_llm, judge_llm = _build_providers(dry_run=config.dry_run)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    results = await run_all(scenarios, dialogue_llm=dialogue_llm, judge_llm=judge_llm)
    console.print()
    _render_summary(results, verbose=config.verbose)
    return 0 if all(r.passed for r in results) else 1


def main(argv: list[str] | None = None) -> int:
    """Sync entry point. Loads .env then drives the async runner."""
    load_dotenv(override=True)
    config = _parse_args(argv)
    return asyncio.run(amain(config))


if __name__ == "__main__":
    sys.exit(main())
