"""Prompt for the Memory.interpretation generator.

Given the objective facts of an event + the witness NPC's stable
personality + their current mood + their current view of the participants,
the LLM produces the NPC's first-person, in-character reading of what
just happened. That reading is then *frozen* on the Memory row
(write-once invariant from PR #1).

The prompt is intentionally structured: every section is a section
header so that retrieval-aware future prompts can subset cleanly.
"""

from __future__ import annotations

from typing import NamedTuple

from wulin_mud.ontology import NPC, Memory


class InterpretationPrompt(NamedTuple):
    system: str
    user: str


_SYSTEM_PROMPT = """\
你正在扮演武侠小镇清河镇的一位 NPC。这一刻你刚目击或参与了一件事。
你的任务是用第一人称、一两句话写下你此刻心里对这件事的真实印象。

【铁律】
1. 严格符合你的人设维度（personality + constraints + speech_style）。
2. 印象要短、要具体、要符合你的语气。不要写大段心理分析。
3. 不要重复事实本身——只写你的看法或感觉。
4. 这句话之后会被固化为你这条记忆的解读，永远跟着你。"""


def _format_personality(npc: NPC) -> str:
    p = npc.personality
    return (
        f"openness={p.openness:.2f} conscientiousness={p.conscientiousness:.2f} "
        f"extraversion={p.extraversion:.2f} agreeableness={p.agreeableness:.2f} "
        f"neuroticism={p.neuroticism:.2f}\n"
        f"honesty={p.honesty:.2f} courage={p.courage:.2f} greed={p.greed:.2f} "
        f"loyalty={p.loyalty:.2f} pride={p.pride:.2f}"
    )


def _format_speech_style(npc: NPC) -> str:
    s = npc.speech_style
    lines: list[str] = []
    if s.self_reference:
        lines.append(f"自称：{s.self_reference}")
    if s.tone:
        lines.append(f"语气：{s.tone}")
    if s.catchphrases:
        lines.append("口头禅：" + " / ".join(s.catchphrases))
    if s.avoids:
        lines.append("避免：" + " / ".join(s.avoids))
    return "\n".join(lines) if lines else "（无特殊设定）"


def _format_relationship_with_actor(npc: NPC, actor_id: str) -> str:
    """Show how this NPC currently sees the actor — affection, trust, label."""
    if actor_id == "player":
        pr = npc.player_relationship
        if pr is None:
            return "你和对方还不熟，今天可能是第一次见。"
        return (
            f"对方是个外来的年轻人。\n"
            f"affection={pr.affection:+.2f}  trust={pr.trust:.2f}  "
            f"familiarity={pr.familiarity:.2f}\n"
            f"你对他的标签：{pr.relationship_label or '陌生'}\n"
            f"你之前对他的总印象：{pr.impression_summary or '（还没形成总印象）'}"
        )
    rel = npc.relationships.get(actor_id)
    if rel is None:
        return f"对方是 {actor_id}，你和他之前没什么交集。"
    return (
        f"对方是 {actor_id}。\n"
        f"affection={rel.affection:+.2f}  trust={rel.trust:.2f}  "
        f"familiarity={rel.familiarity:.2f}\n"
        f"你对他的标签：{rel.relationship_label}（{rel.relationship_type.value}）"
    )


def _format_raw_facts(facts: dict[str, object]) -> str:
    if not facts:
        return "（无额外结构化事实）"
    lines = [f"- {k}: {v}" for k, v in facts.items()]
    return "\n".join(lines)


def build_interpretation_prompt(
    *,
    npc: NPC,
    memory: Memory,
    actor_id: str,
) -> InterpretationPrompt:
    """Compose the (system, user) prompt pair for one witness's interpretation.

    ``npc`` is the witness — the NPC whose first-person reading we want.
    ``memory`` carries the objective layer (event_type, raw_facts, etc.).
    ``actor_id`` is the prime mover of the event (so we can show the
    NPC's view of that specific party).
    """
    user_sections = [
        f"【你是谁】\n你的名字：{npc.name}，{npc.age} 岁，{npc.role}\n",
        f"【你的背景】\n{npc.background}\n",
        f"【你的人设维度】\n{_format_personality(npc)}\n",
        f"【你的说话风格】\n{_format_speech_style(npc)}\n",
        (f"【你此刻的心情】\nvalence={npc.mood.valence:+.2f}  arousal={npc.mood.arousal:.2f}\n"),
        f"【你和对方的当前关系】\n{_format_relationship_with_actor(npc, actor_id)}\n",
        (
            "【刚刚发生了什么（客观事实）】\n"
            f"event_type: {memory.event_type.value}\n"
            f"location_id: {memory.location_id}\n"
            f"participants: {', '.join(memory.participants)}\n"
            f"raw_facts:\n{_format_raw_facts(memory.raw_facts)}\n"
        ),
        (
            "【请输出】\n"
            "一两句你此刻对这件事的内心印象。第一人称。"
            "不要解释、不要分析、不要加引号。只写那一句话。"
        ),
    ]
    return InterpretationPrompt(system=_SYSTEM_PROMPT, user="\n".join(user_sections))
