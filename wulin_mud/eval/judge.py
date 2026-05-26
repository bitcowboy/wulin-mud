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
_JUDGE_MAX_TOKENS = 300

_JUDGE_SYSTEM_PROMPT = """\
你是一个 NPC 对白评分员。你要根据给定的人设和评分标准，
判断一段 NPC 的回复符合得多好。

输出只有一个 JSON 对象，**两个字段**：
  - "score": 1 到 5 的整数
      1 = 完全偏离设定
      2 = 大体偏离，零星地有一点点像
      3 = 一半像一半不像
      4 = 大体符合，偶有违和
      5 = 完全符合，挑不出毛病
  - "reasoning": 一两句话解释你为什么给这个分

不要写解释、不要写代码块、不要写多余的字段。
直接输出 JSON。"""


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

    Some models wrap JSON in ```json ... ``` or prepend a sentence.
    We extract the first balanced {...} object we can find.
    """
    raw = text.strip()
    # Strip fenced code blocks if present.
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    else:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        candidate = match.group(0) if match else raw

    try:
        obj = json.loads(candidate)
        score = int(obj.get("score", 0))
        if not (1 <= score <= 5):
            score = 0
        reasoning = str(obj.get("reasoning", "")).strip()
    except (json.JSONDecodeError, TypeError, ValueError):
        score = 0
        reasoning = "judge output was not valid JSON"
    return JudgeReply(score=score, reasoning=reasoning, raw=raw)


async def evaluate_soft(
    *,
    provider: LLMProvider,
    scenario: Scenario,
    assertion: SoftAssertion,
    reply: str,
    model: str | None = None,
) -> AssertionResult:
    """Run one soft assertion. Returns pass/fail relative to threshold."""
    user = _build_judge_user(scenario=scenario, assertion=assertion, reply=reply)
    chosen_model = model if model is not None else os.environ.get("WULIN_MODEL_JUDGE")
    raw = await provider.generate(
        system=_JUDGE_SYSTEM_PROMPT,
        user=user,
        model=chosen_model,
        temperature=_JUDGE_TEMPERATURE,
        max_tokens=_JUDGE_MAX_TOKENS,
    )
    parsed = _parse_judge_output(raw)
    passed = parsed.score >= assertion.threshold
    detail = (
        f"[{assertion.type.value}] score={parsed.score}/5 "
        f"(threshold {assertion.threshold}). reasoning: {parsed.reasoning}"
    )
    return AssertionResult(passed=passed, detail=detail, score=float(parsed.score))
