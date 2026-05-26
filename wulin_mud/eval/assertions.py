"""Hard-assertion implementations + the result struct shared with soft ones.

Each hard assertion is a pure function: ``(reply, HardAssertion) →
AssertionResult``. No I/O, no LLM, deterministic.

Sentence counting uses Chinese terminators 。 ！ ？ in addition to the
ASCII ones — the persona writes in Chinese.

Authoring discipline (the lesson from PRs #15, #18, #20, #21):

  **Hard rules enforce ENUMERABLE CONCRETE FACTS, not stylistic feel.**

  Good hard rules (use these):
    - ``must_not_contain`` of proper nouns, names, dates, specific
      identifiers — things that can be reverse-looked-up. Sun must
      not say "陈守业" / "京畿" / "初十" / a specific 价钱 she's
      forbidden to quote. These are deterministic safety nets the
      judge has been observed to miss.
    - ``max_sentences`` — structural, no judge equivalent.
    - ``must_not_contain`` of wrong-archetype words ("本店"/"本号"/
      "鄙人") when the NPC's speech_style explicitly uses a different
      self-reference. Lexically narrow, low false-positive risk.

  Bad hard rules (don't use; the judge handles these better):
    - ``must_contain_one_of`` of pronouns / recognition tokens /
      topic-engagement anchors. Natural language has too many ways
      to express the same idea; lists grow forever.
    - ``must_not_contain`` of stylistic agreement words ("好",
      "可以", "成交", "都行") — too generic, appear in many valid
      replies ("还好"/"就好"/"好了" all contain "好").
    - ``must_not_contain`` of warmth/welcome words ("欢迎", "高兴")
      — relies on lexical choice rather than tone; the judge's
      ``speech_style_match`` rubric reads the actual tone.

When in doubt, prefer a soft assertion. The judge is the workhorse
for character-quality grading; hard rules are the precise safety
nets for specific leaks.
"""

from __future__ import annotations

from dataclasses import dataclass

from wulin_mud.eval.scenario import HardAssertion, HardAssertionType

_TERMINATORS = "。！？.!?\n"


def _count_sentences(text: str) -> int:
    """Approximate sentence count by terminators.

    Trailing run of non-terminator characters counts as one sentence.
    Empty / whitespace-only text counts as 0.
    """
    stripped = text.strip()
    if not stripped:
        return 0
    count = 0
    in_sentence = False
    for ch in stripped:
        if ch in _TERMINATORS:
            if in_sentence:
                count += 1
                in_sentence = False
        elif not ch.isspace():
            in_sentence = True
    if in_sentence:
        count += 1
    return count


@dataclass(frozen=True)
class AssertionResult:
    """Outcome of one assertion's evaluation."""

    passed: bool
    detail: str
    """Human-readable explanation — what failed or what passed."""
    score: float | None = None
    """Only set by soft (LLM-as-judge) assertions."""


def evaluate_hard(reply: str, assertion: HardAssertion) -> AssertionResult:
    """Run one hard assertion against ``reply``."""
    if assertion.type is HardAssertionType.MAX_SENTENCES:
        max_n = assertion.value
        if max_n is None:
            return AssertionResult(False, "max_sentences requires `value`")
        n = _count_sentences(reply)
        if n <= max_n:
            return AssertionResult(True, f"reply has {n} sentence(s), within {max_n}")
        return AssertionResult(
            False,
            f"reply has {n} sentence(s); max_sentences={max_n}. ({assertion.reason or '太啰嗦'})",
        )

    if assertion.type is HardAssertionType.MUST_NOT_CONTAIN:
        offenders = [v for v in assertion.values if v in reply]
        if not offenders:
            return AssertionResult(True, f"reply contains none of forbidden {assertion.values!r}")
        return AssertionResult(
            False,
            f"reply contains forbidden term(s): {offenders!r}. ({assertion.reason or '违反禁词'})",
        )

    if assertion.type is HardAssertionType.MUST_CONTAIN_ONE_OF:
        hits = [v for v in assertion.values if v in reply]
        if hits:
            return AssertionResult(True, f"reply contains required anchor {hits!r}")
        return AssertionResult(
            False,
            f"reply contains none of required {assertion.values!r}. "
            f"({assertion.reason or '没有必需的语言锚'})",
        )

    raise NotImplementedError(f"hard assertion {assertion.type!r} not implemented")
