"""Prompt for NPC dialogue generation.

System prompt is the anti-drift contract from docs/llm-integration.md §2
("铁律"). User prompt assembles the full per-turn context: identity,
constraints, speech_style, mood, relationship-to-actor, top-N retrieved
memories, recent dialogue turns, and finally the player's input.

The output is a short in-character reply (1–3 sentences) — the player's
direct experience of the NPC.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from wulin_mud.ontology import NPC, Memory


class DialoguePrompt(NamedTuple):
    system: str
    user: str


_SYSTEM_PROMPT = """\
你正在扮演武侠小镇清河镇的一位 NPC。
你的任务不是"陪玩家聊天"，而是"作为这个具体的人，在这个具体时刻，做出真实反应"。

【铁律】
1. 严格遵守人设维度（personality + constraints + speech_style）。
   你不会突然变开朗、变冷漠、突然博学。
2. 严格遵守 constraints。这些是你的底线，比 personality 更硬。
3. 你的知识就是 knowledge 列表里的内容。除此之外的事，你不知道。
4. 你听过的传闻就是 heard_rumors 列表里的。不要凭空"听说"任何事。
5. 你对对方的态度由 player_relationship + recent memories 决定，不由"客气"决定。
6. 你不知道自己是 NPC。你不知道有"玩家"这个概念。对你而言，对方就是个外来的年轻人。
7. 永远使用 speech_style 中的语言风格。用你的口头禅，模仿你的语气。

【输出格式】
- 1-3 句话。话短优先。
- 可以包含动作神态（写在括号里），但不要长篇大论。
- 不要解释你自己的心理活动。
- 不要用引号包裹你的话。
- 如果对方问起你不想谈的话题（参见 constraints），用你的方式回避。
- 直接以你的身份说话——不要加"作为孙婆婆，我说："这种前缀。"""


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
    if s.address_young:
        lines.append(f"对年轻人称：{s.address_young}")
    if s.address_old:
        lines.append(f"对老人称：{s.address_old}")
    if s.tone:
        lines.append(f"语气：{s.tone}")
    if s.catchphrases:
        lines.append("口头禅：" + " / ".join(s.catchphrases))
    if s.avoids:
        lines.append("避免：" + " / ".join(s.avoids))
    return "\n".join(lines) if lines else "（无特殊设定）"


def _format_constraints(npc: NPC) -> str:
    if not npc.constraints:
        return "（无明确底线，但保持人设一致）"
    return "\n".join(f"- {c}" for c in npc.constraints)


def _format_secrets_for_self(npc: NPC) -> str:
    """Secrets are visible to the NPC herself but must not be volunteered."""
    if not npc.secrets:
        return "（无）"
    return "\n".join(
        f"- {s.content}（被发现难度 {s.discovery_difficulty:.2f}）" for s in npc.secrets
    )


def _format_knowledge(npc: NPC) -> str:
    if not npc.knowledge:
        return "（除日常常识外，没有特别的事实知识）"
    return "\n".join(f"- {k.content}" for k in npc.knowledge)


def _format_heard_rumors(npc: NPC) -> str:
    if not npc.heard_rumors:
        return "（没听说过什么传闻）"
    return "\n".join(
        f"- {h.content}（来源 {h.source}，可信度 {h.credibility:.2f}）" for h in npc.heard_rumors
    )


def _format_player_relationship(npc: NPC) -> str:
    pr = npc.player_relationship
    if pr is None:
        return "对方是个新面孔，你之前没见过他。"
    return (
        f"affection={pr.affection:+.2f}  trust={pr.trust:.2f}  "
        f"familiarity={pr.familiarity:.2f}\n"
        f"你给他贴的标签：{pr.relationship_label or '陌生'}\n"
        f"你之前对他的总印象：{pr.impression_summary or '（还没形成总印象）'}"
    )


def _format_memory_row(mem: Memory) -> str:
    """One bullet showing the NPC's own *interpretation* — not the raw_facts.

    The interpretation IS the NPC's read of the event. Using raw_facts
    here would dump objective JSON into the prompt and dilute character.
    """
    interp = mem.interpretation.strip()
    if interp:
        return f"- [{mem.event_type.value}] {interp}"
    # Fallback if interpretation is unset (e.g. legacy rows seeded before LLM
    # layer existed). Show event type + a hint from raw_facts.
    return f"- [{mem.event_type.value}] (无主观印象) raw_facts={mem.raw_facts}"


def _format_recent_dialogue(turns: Sequence[Memory], actor_id: str) -> str:
    if not turns:
        return "（你和对方今天还没说过话）"
    lines: list[str] = []
    for t in turns:
        said = t.raw_facts.get("said")
        replied = t.raw_facts.get("replied")
        # The actor's line came first; the NPC's came second.
        if said:
            lines.append(f"对方：{said}")
        if replied:
            lines.append(f"你：{replied}")
    # actor_id used only for forward-compat (NPC↔NPC dialogue later);
    # in v0.1 it's always "player".
    del actor_id
    return "\n".join(lines)


def build_dialogue_prompt(
    *,
    npc: NPC,
    actor_id: str,
    player_input: str,
    relevant_memories: Sequence[Memory] = (),
    recent_dialogue: Sequence[Memory] = (),
) -> DialoguePrompt:
    """Compose the (system, user) prompt pair for one dialogue turn.

    - ``npc`` is the speaker — the NPC whose reply we're generating.
    - ``actor_id`` is the other party (in v0.1 always ``"player"``).
    - ``relevant_memories`` are the top-N retrieved Memories of the NPC
      about anything, ordered by ranking score.
    - ``recent_dialogue`` is the small set of recent TALKED Memories
      between this NPC and the actor, oldest first.
    """
    user_sections = [
        f"【你是谁】\n你的名字：{npc.name}，{npc.age} 岁，{npc.role}\n",
        f"【你的背景】\n{npc.background}\n",
        f"【你的人设维度】\n{_format_personality(npc)}\n",
        f"【你的行为底线（constraints）】\n{_format_constraints(npc)}\n",
        f"【你的说话风格】\n{_format_speech_style(npc)}\n",
        f"【你藏着的秘密（不会主动说）】\n{_format_secrets_for_self(npc)}\n",
        f"【你的客观知识】\n{_format_knowledge(npc)}\n",
        f"【你听过的传闻】\n{_format_heard_rumors(npc)}\n",
        (
            "【你此刻的状态】\n"
            f"位置：{npc.current_location_id}\n"
            f"心情：valence={npc.mood.valence:+.2f}  arousal={npc.mood.arousal:.2f}\n"
            f"健康：{npc.health:.2f}  精力：{npc.energy:.2f}\n"
        ),
        f"【你和对方的当前关系】\n{_format_player_relationship(npc)}\n",
        "【你对他的记忆（按重要性排序）】\n"
        + (
            "\n".join(_format_memory_row(m) for m in relevant_memories)
            if relevant_memories
            else "（暂无关于他的具体记忆）"
        )
        + "\n",
        f"【最近几轮对话】\n{_format_recent_dialogue(recent_dialogue, actor_id)}\n",
        f"【对方刚才说的话】\n{player_input}\n",
        "【请回应】",
    ]
    return DialoguePrompt(system=_SYSTEM_PROMPT, user="\n".join(user_sections))
