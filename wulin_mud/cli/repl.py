"""REPL — parse player input, dispatch actions, render results.

The REPL is split out from ``main.py`` so the parse/dispatch logic can
be tested with a FakeProvider against an in-memory SQLite without
spinning up a real TTY.

Commands:

  ``<bare text>``        Talk to the only NPC in your current room
                         (errors if 0 or 2+ NPCs present)
  ``/go <location>``     Move to an adjacent location (by name or id)
  ``/greet [<name>]``    Greet an NPC by name; defaults to the only
                         NPC in the room
  ``/buy <item> [price]`` Buy an item by name; price defaults to base_price
  ``/offend <name> [<desc>]``  Insult an NPC
  ``/look``              Re-describe the current location + occupants
  ``/me``                Show your own state (location, wealth, inventory)
  ``/help``              List commands
  ``/quit``              Exit

Resolution rules:

- NPC names match against ``NPC.name`` (exact) or ``NPC.id``.
- Locations match against ``Location.name`` (exact) or ``Location.id``.
- Items match against ``Item.name`` (exact) or ``Item.id`` — and only
  among items currently owned by an NPC at your location (a "vendor")
  or by you.
"""

from __future__ import annotations

import shlex
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlmodel import Session, select

from wulin_mud.actions import (
    ActionCallerNotPermitted,
    ActionNotFound,
    execute_action,
)
from wulin_mud.actions.base import ActionResult
from wulin_mud.core.enums import InitiatedBy
from wulin_mud.llm.provider import LLMProvider
from wulin_mud.ontology import NPC, PLAYER_ID, Item, Location, PlayerState
from wulin_mud.world.persistence import ItemRow
from wulin_mud.world.state import WorldState

HELP_TEXT = """\
命令：
  /look                  看看四周
  /me                    看看自己
  /go <地名>             去某地（相邻才能去）
  /greet [<姓名>]        打招呼
  /buy <物品> [<价钱>]   买东西（默认按基础价）
  /talk <姓名> <内容>    指明对谁说话（房里多人时用）
  /offend <姓名> [<事>]  冒犯某人
  /tick [<次数>]         手动让世界走一段时间（心情/记忆衰减）
  /help                  显示帮助
  /quit                  退出

不加斜杠的文字会直接说给在场的 NPC 听。"""


class Quit(Exception):
    """Raised by handlers to break the outer REPL loop."""


@dataclass(frozen=True)
class RenderedTurn:
    """What a single REPL turn produced, for display + assertion."""

    output: str
    action_result: ActionResult | None = None


Handler = Callable[["Repl", list[str]], Awaitable[RenderedTurn]]


class Repl:
    """One game session. Holds the Session + provider; dispatches commands."""

    def __init__(self, session: Session, llm: LLMProvider) -> None:
        self._session = session
        self._llm = llm
        # The NPC the player has "addressed" most recently. Set by
        # /greet, /offend, /talk, and successful bare-text Talks.
        # Cleared by /go (the player walked away). Bare text in a
        # multi-NPC room falls through to this target.
        self._current_talk_target: str | None = None

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def _world(self, *, initiated_by: InitiatedBy = InitiatedBy.PLAYER_INPUT) -> WorldState:
        return WorldState(self._session, llm=self._llm, initiated_by=initiated_by)

    def _player(self) -> PlayerState:
        ws = self._world()
        p = ws.get_player()
        if p is None:
            raise RuntimeError(
                "Player state is missing — run `python -m wulin_mud.scripts.seed_world`."
            )
        return p

    def _current_location(self) -> Location:
        ws = self._world()
        player = self._player()
        loc = ws.get_location(player.current_location_id)
        if loc is None:
            raise RuntimeError(
                f"Player is at {player.current_location_id!r} but that location is not seeded."
            )
        return loc

    def _npcs_here(self) -> list[NPC]:
        ws = self._world()
        loc = self._current_location()
        return ws.npcs_at_location(loc.id)

    def _resolve_npc(self, name_or_id: str) -> NPC | None:
        for npc in self._npcs_here():
            if name_or_id == npc.id or name_or_id == npc.name:
                return npc
        return None

    def _resolve_location(self, name_or_id: str) -> Location | None:
        ws = self._world()
        current = self._current_location()
        for connected_id in current.connected_to:
            loc = ws.get_location(connected_id)
            if loc is None:
                continue
            if name_or_id == loc.id or name_or_id == loc.name:
                return loc
        return None

    def _resolve_item(self, name_or_id: str) -> Item | None:
        """Find an item at the player's location or in their inventory."""
        from wulin_mud.world.persistence import row_to_item

        loc = self._current_location()
        npc_ids_here = {n.id for n in self._npcs_here()}
        candidate_owners = npc_ids_here | {PLAYER_ID}

        rows = self._session.exec(select(ItemRow)).all()
        for row in rows:
            if row.owner_id not in candidate_owners:
                continue
            # Vendor items must be at the same location as us.
            if row.owner_id != PLAYER_ID and row.location_id != loc.id:
                continue
            if name_or_id == row.id or name_or_id == row.name:
                return row_to_item(row)
        return None

    # ------------------------------------------------------------------
    # Action plumbing
    # ------------------------------------------------------------------

    async def _run_action(self, action_name: str, params: dict[str, object]) -> ActionResult:
        return await execute_action(
            session=self._session,
            action_name=action_name,
            params=params,
            actor_id=PLAYER_ID,
            initiated_by=InitiatedBy.PLAYER_INPUT,
            llm=self._llm,
        )

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def cmd_look(self, _args: list[str]) -> RenderedTurn:
        loc = self._current_location()
        npcs = self._npcs_here()
        lines = [
            f"[ {loc.name} ]",
            loc.description.strip() if loc.description else "",
        ]
        if npcs:
            lines.append("在这里：" + "，".join(f"{n.name}" for n in npcs))
        else:
            lines.append("这里没有别人。")
        if loc.connected_to:
            connected_names: list[str] = []
            ws = self._world()
            for cid in loc.connected_to:
                cl = ws.get_location(cid)
                connected_names.append(cl.name if cl else cid)
            lines.append("可去：" + "，".join(connected_names))
        return RenderedTurn(output="\n".join(filter(None, lines)))

    async def cmd_me(self, _args: list[str]) -> RenderedTurn:
        p = self._player()
        loc = self._current_location()
        inv = "、".join(p.inventory_item_ids) if p.inventory_item_ids else "(空)"
        out = f"你在 {loc.name}。\n身上有 {p.wealth} 文钱。\n行李：{inv}"
        return RenderedTurn(output=out)

    async def cmd_go(self, args: list[str]) -> RenderedTurn:
        if not args:
            return RenderedTurn(output="/go 后面要跟一个地名。")
        target = self._resolve_location(args[0])
        if target is None:
            return RenderedTurn(output=f"这里去不了 {args[0]!r}。")
        result = await self._run_action("MoveTo", {"destination_id": target.id})
        if not result.succeeded:
            return RenderedTurn(output=f"去不了：{result.narrative_hint}", action_result=result)
        # Walking away ends the current conversation thread.
        self._current_talk_target = None
        # Show the new room after moving.
        look = await self.cmd_look([])
        return RenderedTurn(output=look.output, action_result=result)

    async def cmd_greet(self, args: list[str]) -> RenderedTurn:
        npc = self._resolve_action_target(args)
        if isinstance(npc, RenderedTurn):
            return npc
        result = await self._run_action("Greet", {"target_id": npc.id})
        if not result.succeeded:
            return RenderedTurn(output=f"招呼没打成：{result.narrative_hint}", action_result=result)
        # Bare text from now on goes to this NPC until you walk away.
        self._current_talk_target = npc.id
        return RenderedTurn(output=f"你向 {npc.name} 点了点头。", action_result=result)

    async def cmd_offend(self, args: list[str]) -> RenderedTurn:
        if not args:
            return RenderedTurn(output="/offend 至少要带一个 NPC 姓名。")
        npc_name = args[0]
        npc = self._resolve_npc(npc_name)
        if npc is None:
            return RenderedTurn(output=f"这里没有叫 {npc_name!r} 的人。")
        description = " ".join(args[1:]) if len(args) > 1 else None
        params: dict[str, object] = {"target_id": npc.id}
        if description:
            params["description"] = description
        result = await self._run_action("OffendNPC", params)
        if not result.succeeded:
            return RenderedTurn(output=f"动作没做成：{result.narrative_hint}", action_result=result)
        # You're now arguing with this person; subsequent bare text goes to them.
        self._current_talk_target = npc.id
        return RenderedTurn(output=f"你冒犯了 {npc.name}。", action_result=result)

    async def cmd_buy(self, args: list[str]) -> RenderedTurn:
        if not args:
            return RenderedTurn(output="/buy 后面要跟物品名，例如 /buy 止血膏 60。")
        item = self._resolve_item(args[0])
        if item is None:
            return RenderedTurn(output=f"这里没有 {args[0]!r}。")
        if len(args) >= 2:
            try:
                price = int(args[1])
            except ValueError:
                return RenderedTurn(output=f"价钱 {args[1]!r} 不是个数字。")
        else:
            price = item.base_price
        result = await self._run_action("BuyItem", {"item_id": item.id, "price": price})
        if not result.succeeded:
            return RenderedTurn(output=f"买不成：{result.narrative_hint}", action_result=result)
        return RenderedTurn(output=f"你花了 {price} 文，买下了 {item.name}。", action_result=result)

    async def cmd_talk(self, content: str) -> RenderedTurn:
        """Bare-text path. Routes to the only NPC present, or the
        last-addressed NPC if there are several."""
        npcs = self._npcs_here()
        if not npcs:
            return RenderedTurn(output="这里没有人可以说话。")

        target = None
        if len(npcs) == 1:
            target = npcs[0]
        elif self._current_talk_target is not None:
            for n in npcs:
                if n.id == self._current_talk_target:
                    target = n
                    break

        if target is None:
            names = "、".join(n.name for n in npcs)
            return RenderedTurn(
                output=(
                    f"这里有好几个人（{names}）。\n"
                    "用 `/greet <姓名>` 先指明，或者 `/talk <姓名> <要说的话>`。"
                )
            )

        return await self._run_talk(target, content)

    async def cmd_talk_explicit(self, args: list[str]) -> RenderedTurn:
        """`/talk <name> <content>` — explicit form. Doesn't require
        a prior /greet."""
        if len(args) < 2:
            return RenderedTurn(output="用法：/talk <姓名> <要说的话>")
        name, *rest = args
        npc = self._resolve_npc(name)
        if npc is None:
            return RenderedTurn(output=f"这里没有叫 {name!r} 的人。")
        content = " ".join(rest)
        return await self._run_talk(npc, content)

    async def _run_talk(self, target: NPC, content: str) -> RenderedTurn:
        """Shared body for bare-text Talk and explicit /talk."""
        result = await self._run_action("Talk", {"target_id": target.id, "content": content})
        if not result.succeeded:
            return RenderedTurn(output=f"对方没接话：{result.narrative_hint}", action_result=result)
        # Future bare text stays on this NPC.
        self._current_talk_target = target.id
        reply = result.narrative_hint or "（沉默）"
        return RenderedTurn(output=f"{target.name}：{reply}", action_result=result)

    async def cmd_help(self, _args: list[str]) -> RenderedTurn:
        return RenderedTurn(output=HELP_TEXT)

    async def cmd_quit(self, _args: list[str]) -> RenderedTurn:
        raise Quit()

    async def cmd_tick(self, args: list[str]) -> RenderedTurn:
        """Run one world tick: mood drift + memory decay.

        Optional first arg: how many ticks to fire in sequence
        (default 1, max 100 to avoid runaway).
        """
        n = 1
        if args:
            try:
                n = int(args[0])
            except ValueError:
                return RenderedTurn(output=f"{args[0]!r} 不是个整数。")
            if n < 1:
                return RenderedTurn(output="次数要 ≥ 1。")
            if n > 100:
                return RenderedTurn(output="一次最多跑 100 个 tick。")

        from wulin_mud.world.tick import run_tick

        decay_total = 0
        protected_total = 0
        archived_total = 0
        moods_moved = 0
        for _ in range(n):
            result = await run_tick(session=self._session)
            for fx in result.decay_memories.side_effects_applied:
                decay_total += int(fx.get("decayed", 0))
                protected_total += int(fx.get("protected_by_recall", 0))
                archived_total += int(fx.get("archived", 0))
            for fx in result.drift_mood.side_effects_applied:
                moods_moved += int(fx.get("moved", 0))

        return RenderedTurn(
            output=(
                f"时间走了 {n} 个 tick。\n"
                f"  心情漂移：{moods_moved} 个 NPC\n"
                f"  记忆衰减：{decay_total} 条；被想起跳过 {protected_total} 条；"
                f"归档 {archived_total} 条"
            )
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_action_target(self, args: list[str]) -> NPC | RenderedTurn:
        """Resolve the NPC for /greet (defaults to the one NPC in the room)."""
        if args:
            npc = self._resolve_npc(args[0])
            if npc is None:
                return RenderedTurn(output=f"这里没有叫 {args[0]!r} 的人。")
            return npc
        npcs = self._npcs_here()
        if not npcs:
            return RenderedTurn(output="这里没有别人。")
        if len(npcs) > 1:
            return RenderedTurn(output="这里有好几个人。请指明：" + "、".join(n.name for n in npcs))
        return npcs[0]

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def handle(self, line: str) -> RenderedTurn:
        """Parse one line of input, run the corresponding command,
        return what to render."""
        stripped = line.strip()
        if not stripped:
            return RenderedTurn(output="")

        if not stripped.startswith("/"):
            return await self.cmd_talk(stripped)

        # Slash command
        try:
            tokens = shlex.split(stripped[1:])
        except ValueError as exc:
            return RenderedTurn(output=f"解析失败：{exc}")
        if not tokens:
            return RenderedTurn(output="空命令。试试 /help。")

        cmd, *args = tokens
        dispatch: dict[str, Handler] = {
            "look": Repl.cmd_look,
            "me": Repl.cmd_me,
            "go": Repl.cmd_go,
            "greet": Repl.cmd_greet,
            "offend": Repl.cmd_offend,
            "buy": Repl.cmd_buy,
            "talk": Repl.cmd_talk_explicit,
            "tick": Repl.cmd_tick,
            "help": Repl.cmd_help,
            "quit": Repl.cmd_quit,
            "exit": Repl.cmd_quit,
        }
        handler = dispatch.get(cmd.lower())
        if handler is None:
            return RenderedTurn(output=f"没听过 /{cmd}。试试 /help。")
        try:
            return await handler(self, args)
        except (ActionNotFound, ActionCallerNotPermitted) as exc:
            return RenderedTurn(output=f"动作不允许：{exc}")
