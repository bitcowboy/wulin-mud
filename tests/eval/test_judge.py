"""LLM-as-judge parsing + scoring tests."""

from __future__ import annotations

from wulin_mud.eval.judge import _parse_judge_output, evaluate_soft
from wulin_mud.eval.scenario import (
    AssertionGroups,
    Scenario,
    SoftAssertion,
    SoftAssertionType,
)
from wulin_mud.llm.provider import FakeProvider

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_parses_clean_json() -> None:
    r = _parse_judge_output('{"score": 4, "reasoning": "good"}')
    assert r.score == 4
    assert r.reasoning == "good"


def test_parses_fenced_json() -> None:
    text = '```json\n{"score": 5, "reasoning": "perfect"}\n```'
    r = _parse_judge_output(text)
    assert r.score == 5


def test_parses_json_with_leading_chatter() -> None:
    text = '好的，下面是评分：\n{"score": 3, "reasoning": "中等"}'
    r = _parse_judge_output(text)
    assert r.score == 3
    assert r.reasoning == "中等"


def test_score_out_of_range_becomes_zero() -> None:
    r = _parse_judge_output('{"score": 7, "reasoning": "off the chart"}')
    assert r.score == 0


def test_score_below_one_becomes_zero() -> None:
    r = _parse_judge_output('{"score": 0, "reasoning": "broken"}')
    assert r.score == 0


def test_unparseable_output_becomes_zero() -> None:
    r = _parse_judge_output("I cannot grade this in JSON")
    assert r.score == 0
    assert "not valid JSON" in r.reasoning


def test_extracts_score_from_non_json_prose() -> None:
    """Last-resort path: judge gave a natural-language reply but
    included `"score": N` somewhere. We pull the number out so a
    formatting flake doesn't get marked as 0/5."""
    text = '抱歉我不能输出 JSON，但根据评分标准我会给 "score": 4。'
    r = _parse_judge_output(text)
    assert r.score == 4


def test_extracts_score_with_chinese_punctuation() -> None:
    """Some models use 中文：instead of ASCII colon."""
    text = "评分如下：score：5，理由：完全符合设定。"
    r = _parse_judge_output(text)
    assert r.score == 5


def test_handles_unescaped_quote_in_reasoning() -> None:
    """The judge wrote unescaped " inside reasoning, breaking JSON.
    Fallback should still recover the score."""
    text = '{"score": 4, "reasoning": "回复 "符合设定" 没问题"}'
    r = _parse_judge_output(text)
    assert r.score == 4


def test_handles_trailing_text_after_json() -> None:
    """The judge appended extra prose after the JSON. Bare-regex
    extraction handles this."""
    text = '{"score": 5, "reasoning": "完美"}\n\n顺便说一句，这条评分很合理。'
    r = _parse_judge_output(text)
    assert r.score == 5


def test_handles_object_with_decimal_score() -> None:
    """A decimal like 4.5 should fall through (we want integers 1-5).
    Fallback regex `(\\d+)` would still match '4', so result is 4."""
    text = '{"score": 4.5, "reasoning": "borderline"}'
    r = _parse_judge_output(text)
    # int(4.5) raises in earlier strict path; fallback regex finds 4.
    # Either way: we get a usable integer rather than a hard 0.
    assert r.score == 4


def test_handles_object_score_out_of_range_with_fallback_int() -> None:
    """Even with fallback regex, scores outside 1-5 stay 0."""
    text = '{"score": 99, "reasoning": "over the top"}'
    r = _parse_judge_output(text)
    assert r.score == 0


# ---------------------------------------------------------------------------
# evaluate_soft
# ---------------------------------------------------------------------------


def _stub_scenario() -> Scenario:
    return Scenario(
        scenario_id="stub",
        npc_id="npc_sun_popo",
        player_input="测试。",
        assertions=AssertionGroups(),
    )


async def test_evaluate_soft_passes_above_threshold() -> None:
    provider = FakeProvider(default='{"score": 4, "reasoning": "ok"}')
    assertion = SoftAssertion(
        type=SoftAssertionType.IN_CHARACTER,
        criterion="测试用",
        threshold=3.5,
    )
    result = await evaluate_soft(
        provider=provider,
        scenario=_stub_scenario(),
        assertion=assertion,
        reply="测试回复。",
    )
    assert result.passed
    assert result.score == 4.0
    assert "score=4/5" in result.detail


async def test_evaluate_soft_fails_below_threshold() -> None:
    provider = FakeProvider(default='{"score": 2, "reasoning": "weak"}')
    assertion = SoftAssertion(
        type=SoftAssertionType.IN_CHARACTER,
        criterion="测试用",
        threshold=3.5,
    )
    result = await evaluate_soft(
        provider=provider,
        scenario=_stub_scenario(),
        assertion=assertion,
        reply="bad reply",
    )
    assert not result.passed


async def test_judge_uses_low_temperature() -> None:
    """We want the judge to be consistent, not creative."""
    provider = FakeProvider(default='{"score": 4, "reasoning": "ok"}')
    assertion = SoftAssertion(
        type=SoftAssertionType.SPEECH_STYLE_MATCH,
        criterion="x",
        threshold=3.0,
    )
    await evaluate_soft(
        provider=provider,
        scenario=_stub_scenario(),
        assertion=assertion,
        reply="x",
    )
    assert provider.calls[0].temperature <= 0.2
