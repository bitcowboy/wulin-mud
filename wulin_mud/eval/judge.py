"""LLM-as-judge — score an NPC reply against a free-text rubric.

The judge call asks the LLM to return JSON
``{"score": <1-5 int>, "reasoning": "<short>"}``. We parse defensively:
anything that isn't valid JSON or falls outside [1, 5] is treated as
score 0 with the raw output captured in the detail string.

The judge runs at low temperature — we want consistent grades from
the same evidence, not creative rewrites.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from wulin_mud.eval.assertions import AssertionResult
from wulin_mud.eval.scenario import Scenario, SoftAssertion
from wulin_mud.llm.provider import LLMProvider

_JUDGE_TEMPERATURE = 0.1
# Bumped from 300 → 1000 after observing finish_reason='length' with
# empty content on scenarios 03/05. Some models (and some proxies)
# spend reasoning tokens that don't show in `content` but still count
# against max_tokens. 1000 gives headroom without being wasteful — a
# normal grade is ~30-80 tokens of actual JSON.
_JUDGE_MAX_TOKENS = 1000

_JUDGE_SYSTEM_PROMPT = """\
You are a Chinese-NPC dialogue grader. You will read a reply and a
rubric, and you must output EXACTLY ONE JSON object — nothing else.

The JSON object has exactly two keys:
  - "score": an integer from 1 to 5 (no decimals, no text)
      1 = totally off-character
      2 = mostly off, a few traces of the persona
      3 = half on, half off
      4 = mostly in character, minor slips
      5 = fully in character, no notes
  - "reasoning": a short Chinese string explaining your score

CRITICAL FORMATTING RULES:
- Output ONLY the JSON object. No prose before it. No prose after it.
- No markdown code fences (no ```json, no ```).
- Use ASCII double quotes, not Chinese 「」 or 「" "」 brackets.
- Inside "reasoning", do NOT include unescaped double quotes. If you
  need to quote a phrase from the reply, use Chinese 「」 instead.

Example of valid output:
{"score": 4, "reasoning": "回复务实简短，符合设定"}

Example of INVALID output (do not do this):
```json
{"score": 4, "reasoning": "回复务实"}
```

Example of INVALID output (do not do this either):
Here is my grade:
{"score": 4, "reasoning": "..."}"""


@dataclass(frozen=True)
class JudgeReply:
    score: int
    reasoning: str
    raw: str


def _build_judge_user(
    *,
    scenario: Scenario,
    assertion: SoftAssertion,
    reply: str,
) -> str:
    return (
        f"【场景】{scenario.scenario_id}\n"
        f"【被评分的 NPC】{scenario.npc_id}\n"
        f"【玩家说的话】\n{scenario.player_input.strip()}\n\n"
        f"【NPC 的回复】\n{reply.strip()}\n\n"
        f"【评分标准】\n{assertion.criterion.strip()}\n\n"
        f"【请输出 JSON】"
    )


def _parse_judge_output(text: str) -> JudgeReply:
    """Extract {score, reasoning} from the LLM's output, defensively.

    Tries multiple strategies in order:

    1. Direct ``json.loads`` on the whole output.
    2. Strip fenced code blocks (``` … ```) and parse the inside.
    3. Find the first balanced {…} block via regex and parse that.
    4. Last resort — regex-extract just ``"score": N`` from anywhere
       in the text. This rescues cases where the LLM produced
       valid-looking grading but invalid JSON (unescaped quotes,
       Chinese full-width punctuation, trailing comments).

    Strategy 4 marks the reasoning as "(extracted from non-JSON)" so
    you can tell the difference in reports.
    """
    raw = text.strip()
    candidates: list[str] = [raw]

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1))

    bare = re.search(r"\{.*\}", raw, re.DOTALL)
    if bare:
        candidates.append(bare.group(0))

    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        try:
            score = int(obj.get("score", 0))
        except (TypeError, ValueError):
            continue
        if not (1 <= score <= 5):
            continue
        reasoning = str(obj.get("reasoning", "")).strip()
        return JudgeReply(score=score, reasoning=reasoning, raw=raw)

    # Last-resort regex extraction. We try in decreasing specificity:
    #   1. "score": N        — the JSON shape, broken by something
    #   2. score：N           — Chinese full-width colon
    #   3. 评分 N / 给 N 分    — Chinese natural-language scoring
    #   4. just a bare 1-5 if the text is short
    score_patterns = [
        r'["“]?score["”]?\s*[:：=]\s*(\d+)',
        r"评\s*分?\s*[:：=]?\s*(\d+)",
        r"给\s*(\d+)\s*分",
        r"(\d+)\s*分\b",
    ]
    for pattern in score_patterns:
        m = re.search(pattern, raw)
        if not m:
            continue
        try:
            score = int(m.group(1))
        except ValueError:
            continue
        if not (1 <= score <= 5):
            continue
        reasoning_match = re.search(
            r'["“]?reasoning["”]?\s*[:：=]\s*["“]?(.+?)["”]?\s*[,}\n]',
            raw,
            re.DOTALL,
        )
        reasoning = (
            reasoning_match.group(1).strip() if reasoning_match else "(extracted from non-JSON)"
        )
        return JudgeReply(score=score, reasoning=reasoning, raw=raw)

    return JudgeReply(
        score=0,
        reasoning="judge output was not valid JSON",
        raw=raw,
    )


async def evaluate_soft(
    *,
    provider: LLMProvider,
    scenario: Scenario,
    assertion: SoftAssertion,
    reply: str,
    model: str | None = None,
) -> AssertionResult:
    """Run one soft assertion. Returns pass/fail relative to threshold.

    Distinguishes three outcomes:

    - **Pass** — judge scored ≥ threshold. ``score`` is the integer
      grade (as a float for the dataclass).
    - **Fail (parsed)** — judge scored below threshold. Same shape.
    - **Errored** — provider raised (after its own internal retry).
      Returns ``passed=False`` with ``score=None`` so the report can
      visually distinguish "judge thought it was bad" from "judge
      never gave us an answer". The detail line names the exception.

    The errored case is *not* the persona's fault — typically it's a
    proxy / content-filter / network issue.
    """
    user = _build_judge_user(scenario=scenario, assertion=assertion, reply=reply)
    chosen_model = model if model is not None else os.environ.get("WULIN_MODEL_JUDGE")
    try:
        raw = await provider.generate(
            system=_JUDGE_SYSTEM_PROMPT,
            user=user,
            model=chosen_model,
            temperature=_JUDGE_TEMPERATURE,
            max_tokens=_JUDGE_MAX_TOKENS,
        )
    except Exception as exc:
        return AssertionResult(
            passed=False,
            detail=(
                f"[{assertion.type.value}] JUDGE UNREACHABLE — "
                f"{type(exc).__name__}: {exc}. "
                "This is a tooling issue (proxy, network, content filter), "
                "not a verdict on the reply."
            ),
            score=None,
        )

    parsed = _parse_judge_output(raw)
    passed = parsed.score >= assertion.threshold
    detail = (
        f"[{assertion.type.value}] score={parsed.score}/5 "
        f"(threshold {assertion.threshold}). reasoning: {parsed.reasoning}"
    )
    # If parsing failed (score=0), surface the raw output so the
    # user can see what the judge actually produced. Cap at 400 chars.
    if parsed.score == 0:
        snippet = parsed.raw[:400] + ("…" if len(parsed.raw) > 400 else "")
        detail += f"\n     raw judge output: {snippet!r}"
    return AssertionResult(passed=passed, detail=detail, score=float(parsed.score))
