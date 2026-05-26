"""Eval CLI — discovery + dispatch tests. No real LLM."""

from __future__ import annotations

from pathlib import Path

import pytest

from wulin_mud.eval.cli import (
    DEFAULT_SCENARIOS_DIR,
    CliConfig,
    _parse_args,
    amain,
    discover_scenarios,
)

# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_discover_finds_all_seeded_scenarios() -> None:
    scenarios = discover_scenarios(DEFAULT_SCENARIOS_DIR)
    ids = {s.scenario_id for s in scenarios}
    assert "sun_popo__01_first_buy" in ids
    assert "sun_popo__05_after_offense" in ids
    assert len(scenarios) >= 5


def test_discover_with_npc_filter() -> None:
    scenarios = discover_scenarios(DEFAULT_SCENARIOS_DIR, npc_filter="sun_popo")
    assert scenarios
    assert all(s.npc_id == "npc_sun_popo" for s in scenarios)


def test_discover_with_scenario_filter() -> None:
    scenarios = discover_scenarios(
        DEFAULT_SCENARIOS_DIR, scenario_filter="sun_popo__03_mention_husband"
    )
    assert len(scenarios) == 1
    assert scenarios[0].scenario_id == "sun_popo__03_mention_husband"


def test_discover_returns_empty_on_missing_dir(tmp_path: Path) -> None:
    assert discover_scenarios(tmp_path / "does_not_exist") == []


# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------


def test_parse_args_defaults() -> None:
    cfg = _parse_args([])
    assert cfg.npc_filter is None
    assert cfg.scenario_filter is None
    assert cfg.verbose is False
    assert cfg.dry_run is False
    assert cfg.scenarios_dir == DEFAULT_SCENARIOS_DIR


def test_parse_args_with_all_flags() -> None:
    cfg = _parse_args(
        [
            "--scenarios-dir",
            "/tmp/foo",
            "--npc",
            "sun_popo",
            "--scenario",
            "sun_popo__01_first_buy",
            "--verbose",
            "--dry-run",
        ]
    )
    assert cfg.scenarios_dir == Path("/tmp/foo")
    assert cfg.npc_filter == "sun_popo"
    assert cfg.scenario_filter == "sun_popo__01_first_buy"
    assert cfg.verbose is True
    assert cfg.dry_run is True


# ---------------------------------------------------------------------------
# amain end-to-end (dry-run path, no live LLM)
# ---------------------------------------------------------------------------


async def test_amain_dry_run_returns_nonzero_when_assertions_fail() -> None:
    """Dry-run uses a FakeProvider placeholder reply that can't pass
    real assertions. Exit code must be 1."""
    config = CliConfig(
        scenarios_dir=DEFAULT_SCENARIOS_DIR,
        npc_filter=None,
        scenario_filter="sun_popo__01_first_buy",
        verbose=False,
        dry_run=True,
    )
    code = await amain(config)
    assert code == 1


async def test_amain_with_no_scenarios_returns_two(tmp_path: Path) -> None:
    """Discovery failure → exit code 2 (not 1, which is reserved for
    'ran but failed assertions')."""
    config = CliConfig(
        scenarios_dir=tmp_path,
        npc_filter=None,
        scenario_filter=None,
        verbose=False,
        dry_run=True,
    )
    code = await amain(config)
    assert code == 2


async def test_amain_filter_by_scenario_runs_only_that_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = CliConfig(
        scenarios_dir=DEFAULT_SCENARIOS_DIR,
        npc_filter=None,
        scenario_filter="sun_popo__03_mention_husband",
        verbose=False,
        dry_run=True,
    )
    await amain(config)
    # We can't easily read rich's output via capsys (it writes to a
    # rich Console). Instead verify by re-running discovery.
    scenarios = discover_scenarios(config.scenarios_dir, scenario_filter=config.scenario_filter)
    assert len(scenarios) == 1
