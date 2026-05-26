"""Hard-assertion unit tests. Pure functions, no DB, no LLM."""

from __future__ import annotations

from wulin_mud.eval.assertions import _count_sentences, evaluate_hard
from wulin_mud.eval.scenario import HardAssertion, HardAssertionType

# ---------------------------------------------------------------------------
# Sentence counter
# ---------------------------------------------------------------------------


def test_count_sentences_handles_chinese_terminators() -> None:
    assert _count_sentences("好的。等一等。") == 2
    assert _count_sentences("是啊！这就来！") == 2
    assert _count_sentences("当真？") == 1


def test_count_sentences_handles_ascii_terminators() -> None:
    assert _count_sentences("OK. Wait a second.") == 2


def test_count_sentences_trailing_unfinished_is_one_sentence() -> None:
    """A run of characters without a terminator still counts as 1."""
    assert _count_sentences("我先记下") == 1


def test_count_sentences_empty_or_whitespace_is_zero() -> None:
    assert _count_sentences("") == 0
    assert _count_sentences("   \n  ") == 0


def test_count_sentences_mixed_terminators() -> None:
    assert _count_sentences("嗯。等一下！还有事？") == 3


# ---------------------------------------------------------------------------
# MAX_SENTENCES
# ---------------------------------------------------------------------------


def test_max_sentences_within_limit_passes() -> None:
    r = evaluate_hard(
        "好的。等一等。",
        HardAssertion(type=HardAssertionType.MAX_SENTENCES, value=3),
    )
    assert r.passed
    assert "2 sentence" in r.detail


def test_max_sentences_over_limit_fails() -> None:
    reply = "一。二。三。四。"
    r = evaluate_hard(reply, HardAssertion(type=HardAssertionType.MAX_SENTENCES, value=3))
    assert not r.passed
    assert "4 sentence" in r.detail


# ---------------------------------------------------------------------------
# MUST_NOT_CONTAIN
# ---------------------------------------------------------------------------


def test_must_not_contain_clean_reply_passes() -> None:
    r = evaluate_hard(
        "我这有止血膏。",
        HardAssertion(
            type=HardAssertionType.MUST_NOT_CONTAIN,
            values=["丈夫", "凶手"],
        ),
    )
    assert r.passed


def test_must_not_contain_with_forbidden_term_fails() -> None:
    r = evaluate_hard(
        "我那已故的丈夫……",
        HardAssertion(
            type=HardAssertionType.MUST_NOT_CONTAIN,
            values=["丈夫", "凶手"],
        ),
    )
    assert not r.passed
    assert "丈夫" in r.detail


def test_must_not_contain_with_empty_list_passes() -> None:
    r = evaluate_hard(
        "随便说点什么。",
        HardAssertion(type=HardAssertionType.MUST_NOT_CONTAIN, values=[]),
    )
    assert r.passed


# ---------------------------------------------------------------------------
# MUST_CONTAIN_ONE_OF
# ---------------------------------------------------------------------------


def test_must_contain_one_of_with_match_passes() -> None:
    r = evaluate_hard(
        "我这有止血膏。",
        HardAssertion(
            type=HardAssertionType.MUST_CONTAIN_ONE_OF,
            values=["我", "回春堂"],
        ),
    )
    assert r.passed


def test_must_contain_one_of_with_no_match_fails() -> None:
    r = evaluate_hard(
        "客官请稍候。",
        HardAssertion(
            type=HardAssertionType.MUST_CONTAIN_ONE_OF,
            values=["我", "回春堂"],
        ),
    )
    assert not r.passed
