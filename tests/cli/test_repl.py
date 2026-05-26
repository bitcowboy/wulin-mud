"""REPL parse + dispatch. FakeProvider attached; no live API calls."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from wulin_mud.cli.repl import Quit, Repl
from wulin_mud.llm.provider import FakeProvider

# ---------------------------------------------------------------------------
# Read-only commands
# ---------------------------------------------------------------------------


async def test_look_shows_location_and_npcs(repl: Repl) -> None:
    turn = await repl.handle("/look")
    assert "回春堂" in turn.output
    assert "孙婆婆" in turn.output
    # connected_to is rendered
    assert "清河主街" in turn.output


async def test_me_shows_player_state(repl: Repl) -> None:
    turn = await repl.handle("/me")
    assert "回春堂" in turn.output
    assert "200" in turn.output


async def test_help_lists_commands(repl: Repl) -> None:
    turn = await repl.handle("/help")
    assert "/look" in turn.output
    assert "/go" in turn.output
    assert "/buy" in turn.output


# ---------------------------------------------------------------------------
# Bare text → Talk
# ---------------------------------------------------------------------------


async def test_bare_text_routes_to_talk_with_only_npc(repl: Repl, llm: FakeProvider) -> None:
    llm.queue("小哥进来坐。", "新来的小子。")  # dialogue, then interpretation
    turn = await repl.handle("婆婆好。")
    assert turn.action_result is not None
    assert turn.action_result.succeeded
    assert "孙婆婆" in turn.output
    assert "小哥进来坐。" in turn.output


async def test_bare_text_with_no_npc_in_room_explains(
    repl: Repl, session: Session, llm: FakeProvider
) -> None:
    """Walk the player to a room with no NPCs, then try to talk."""
    # /go 清河主街 (Granny Sun stays in the pharmacy)
    await repl.handle("/go 清河主街")
    llm.reset()  # forget the LLM calls made during MoveTo (there were none)
    turn = await repl.handle("有人吗。")
    assert "没有人" in turn.output


async def test_bare_text_with_multiple_npcs_asks_to_disambiguate(
    repl: Repl, wang_in_pharmacy: Session
) -> None:
    turn = await repl.handle("各位好。")
    assert "好几个" in turn.output or "好几位" in turn.output
    assert "孙婆婆" in turn.output and "王老九" in turn.output


# ---------------------------------------------------------------------------
# /go
# ---------------------------------------------------------------------------


async def test_go_by_name_moves_player(repl: Repl, session: Session) -> None:
    turn = await repl.handle("/go 清河主街")
    assert turn.action_result is not None
    assert turn.action_result.succeeded
    # New room rendered.
    assert "清河主街" in turn.output


async def test_go_by_id_also_works(repl: Repl) -> None:
    turn = await repl.handle("/go loc_main_street")
    assert turn.action_result is not None
    assert turn.action_result.succeeded


async def test_go_to_nonexistent_location_explains(repl: Repl) -> None:
    turn = await repl.handle("/go 月亮")
    assert turn.action_result is None
    assert "去不了" in turn.output


async def test_go_with_no_arg_errors(repl: Repl) -> None:
    turn = await repl.handle("/go")
    assert turn.action_result is None
    assert "地名" in turn.output


# ---------------------------------------------------------------------------
# /greet
# ---------------------------------------------------------------------------


async def test_greet_defaults_to_single_npc(repl: Repl, llm: FakeProvider) -> None:
    llm.queue("打招呼了。")  # interpretation only — Greet doesn't generate dialogue
    turn = await repl.handle("/greet")
    assert turn.action_result is not None
    assert turn.action_result.succeeded
    assert "孙婆婆" in turn.output


async def test_greet_with_unknown_name_errors(repl: Repl) -> None:
    turn = await repl.handle("/greet 张三")
    assert turn.action_result is None
    assert "张三" in turn.output


async def test_greet_with_multiple_npcs_requires_name(
    repl: Repl, wang_in_pharmacy: Session, llm: FakeProvider
) -> None:
    turn = await repl.handle("/greet")
    assert turn.action_result is None
    assert "好几个" in turn.output or "请指明" in turn.output


# ---------------------------------------------------------------------------
# /buy
# ---------------------------------------------------------------------------


async def test_buy_at_default_price(repl: Repl, llm: FakeProvider) -> None:
    llm.queue("钱倒是给得痛快。")  # interpretation
    turn = await repl.handle("/buy 止血膏")
    assert turn.action_result is not None
    assert turn.action_result.succeeded
    assert "80" in turn.output  # price


async def test_buy_with_haggled_price(repl: Repl, llm: FakeProvider) -> None:
    llm.queue("讲价讲得贼斯文。")
    turn = await repl.handle("/buy 止血膏 50")
    assert turn.action_result is not None
    assert turn.action_result.succeeded
    assert "50" in turn.output


async def test_buy_unknown_item_errors(repl: Repl) -> None:
    turn = await repl.handle("/buy 月亮")
    assert turn.action_result is None
    assert "没有" in turn.output


async def test_buy_with_non_numeric_price_errors(repl: Repl) -> None:
    turn = await repl.handle("/buy 止血膏 便宜点")
    assert turn.action_result is None
    assert "数字" in turn.output


async def test_buy_propagates_validation_failure(
    repl: Repl, session: Session, llm: FakeProvider
) -> None:
    """Try to overpay — BuyItem rejects > 2× base price (160)."""
    turn = await repl.handle("/buy 止血膏 200")
    assert turn.action_result is not None
    assert turn.action_result.succeeded is False
    assert "买不成" in turn.output


# ---------------------------------------------------------------------------
# /offend
# ---------------------------------------------------------------------------


async def test_offend_passes_description_to_action(
    repl: Repl, llm: FakeProvider, session: Session
) -> None:
    llm.queue("嘲我医术？")  # interpretation
    turn = await repl.handle("/offend 孙婆婆 嘲讽她的医术")
    assert turn.action_result is not None
    assert turn.action_result.succeeded
    assert "冒犯" in turn.output


async def test_offend_without_target_errors(repl: Repl) -> None:
    turn = await repl.handle("/offend")
    assert turn.action_result is None
    assert "姓名" in turn.output


# ---------------------------------------------------------------------------
# /quit + unknown commands
# ---------------------------------------------------------------------------


async def test_quit_raises_quit(repl: Repl) -> None:
    with pytest.raises(Quit):
        await repl.handle("/quit")


async def test_exit_alias_also_quits(repl: Repl) -> None:
    with pytest.raises(Quit):
        await repl.handle("/exit")


async def test_unknown_command_explains(repl: Repl) -> None:
    turn = await repl.handle("/dance")
    assert "没听过" in turn.output or "/help" in turn.output


async def test_empty_line_is_noop(repl: Repl) -> None:
    turn = await repl.handle("   ")
    assert turn.output == ""


async def test_bad_quoting_is_handled(repl: Repl) -> None:
    """shlex.split raises on unterminated quotes — must not crash REPL."""
    turn = await repl.handle('/go "broken')
    assert "解析失败" in turn.output


# ---------------------------------------------------------------------------
# Sticky talk target
# ---------------------------------------------------------------------------


async def test_greet_sets_talk_target_in_multi_npc_room(
    repl: Repl, wang_in_pharmacy: Session, llm: FakeProvider
) -> None:
    """The reported bug: /greet <X> then bare text should go to X."""
    llm.queue("打个招呼。")  # interpretation for Greet
    await repl.handle("/greet 王老九")

    # Bare text — multi-NPC room. Should target wang (just greeted).
    llm.queue("不该笑话回春堂的药。", "他还在念叨上回那事呢。")
    turn = await repl.handle("先生看上去真精神啊")
    assert turn.action_result is not None
    assert turn.action_result.succeeded
    assert "王老九" in turn.output  # NOT the disambiguation error


async def test_go_clears_talk_target(
    repl: Repl, wang_in_pharmacy: Session, llm: FakeProvider
) -> None:
    """Walking away ends the conversational thread."""
    llm.queue("打个招呼。")
    await repl.handle("/greet 王老九")
    await repl.handle("/go 清河主街")
    await repl.handle("/go 回春堂")

    # Now bare text in a multi-NPC room should ask to disambiguate.
    turn = await repl.handle("各位好")
    assert turn.action_result is None
    assert "好几个" in turn.output


async def test_offend_also_sets_talk_target(
    repl: Repl, wang_in_pharmacy: Session, llm: FakeProvider
) -> None:
    """After insulting someone, bare text continues the argument with them."""
    llm.queue("这小子嘴上没分寸。")  # interpretation for OffendNPC
    await repl.handle("/offend 王老九 嘲讽他的茶水")
    llm.queue("接着说啊，我倒看你怎么说下去。", "他还在挑事。")
    turn = await repl.handle("茶水还不算贵。")
    assert turn.action_result is not None and turn.action_result.succeeded
    assert "王老九" in turn.output


async def test_explicit_talk_command_targets_by_name(
    repl: Repl, wang_in_pharmacy: Session, llm: FakeProvider
) -> None:
    """/talk <name> <content> works without a prior /greet."""
    llm.queue("这小哥嘴甜。", "新面孔。")
    turn = await repl.handle("/talk 王老九 茶水可还便宜？")
    assert turn.action_result is not None and turn.action_result.succeeded
    assert "王老九" in turn.output


async def test_explicit_talk_without_content_errors(repl: Repl, wang_in_pharmacy: Session) -> None:
    turn = await repl.handle("/talk 王老九")
    assert turn.action_result is None
    assert "用法" in turn.output


async def test_explicit_talk_to_unknown_name_errors(repl: Repl, wang_in_pharmacy: Session) -> None:
    turn = await repl.handle("/talk 张三 你好")
    assert turn.action_result is None
    assert "张三" in turn.output


# ---------------------------------------------------------------------------
# Multi-turn smoke
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# /tick
# ---------------------------------------------------------------------------


async def test_tick_default_runs_once_and_reports_stats(repl: Repl, llm: FakeProvider) -> None:
    """`/tick` with no arg runs one tick and reports moved+decayed+archived."""
    turn = await repl.handle("/tick")
    assert "tick" in turn.output
    assert "心情漂移" in turn.output
    assert "记忆衰减" in turn.output


async def test_tick_takes_count(repl: Repl) -> None:
    """`/tick 5` runs 5 ticks in sequence."""
    turn = await repl.handle("/tick 5")
    assert "5 个 tick" in turn.output


async def test_tick_rejects_non_integer_count(repl: Repl) -> None:
    turn = await repl.handle("/tick 多次")
    assert "整数" in turn.output


async def test_tick_rejects_unreasonable_count(repl: Repl) -> None:
    turn = await repl.handle("/tick 1000")
    assert "100" in turn.output


async def test_tick_drifts_mood_visible_via_me(
    repl: Repl, session: Session, llm: FakeProvider
) -> None:
    """End-to-end: offend Granny Sun, run ticks, mood recovers toward target."""
    llm.queue("嘲我医术？")  # interpretation for the offense
    await repl.handle("/offend 孙婆婆 嘲讽她的医术")
    session.expire_all()
    sun = repl._world().get_npc("npc_sun_popo")
    assert sun is not None
    valence_after_offense = sun.mood.valence
    assert valence_after_offense < 0  # offended

    # 20 ticks should bring mood ~halfway back to baseline (~0 for neutral
    # personality). 0.1 alpha × 20 ticks ≈ 0.88 of the gap closed.
    await repl.handle("/tick 20")
    session.expire_all()
    sun_after = repl._world().get_npc("npc_sun_popo")
    assert sun_after is not None
    assert (
        sun_after.mood.valence > valence_after_offense
    ), "mood should have drifted upward toward neutral target"


async def test_two_turn_dialogue_works_through_repl(repl: Repl, llm: FakeProvider) -> None:
    llm.queue(
        "小哥进来坐。",  # turn 1 dialogue
        "新来的。",  # turn 1 interpretation
        "止血膏八十文。",  # turn 2 dialogue
        "讲价讲得贼斯文。",  # turn 2 interpretation
    )
    t1 = await repl.handle("婆婆好。")
    t2 = await repl.handle("止血膏多少文？")
    assert t1.action_result and t1.action_result.succeeded
    assert t2.action_result and t2.action_result.succeeded
    assert "小哥进来坐。" in t1.output
    assert "止血膏八十文。" in t2.output
