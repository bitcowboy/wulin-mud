"""CLI entry point for wulin-mud.

Run with::

    python -m wulin_mud

Loads the ``.env`` file, opens the configured SQLite database, builds
an :class:`OpenAIProvider`, and drops the player into the REPL.

If the database has never been seeded, the program errors out and tells
you to run ``python -m wulin_mud.scripts.seed_world`` first. Keeping
"seed" and "play" as separate commands makes it harder to accidentally
wipe your save by re-launching.
"""

from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from sqlmodel import Session

from wulin_mud.cli.repl import Quit, Repl
from wulin_mud.llm.provider import OpenAIProvider
from wulin_mud.world.persistence import PlayerStateRow, get_engine

console = Console()


def _banner() -> None:
    console.print(
        Panel.fit(
            Text.from_markup(
                "[bold cyan]武林 MUD · wulin-mud[/bold cyan]\n"
                "v0.1.0a0 — pre-alpha\n\n"
                "[dim]输入 /help 查看命令。直接打字会和在场的 NPC 说话。[/dim]"
            ),
            border_style="cyan",
        )
    )


async def _run(session: Session) -> None:
    llm = OpenAIProvider()
    repl = Repl(session=session, llm=llm)

    # Greet the player with their starting location.
    look = await repl.cmd_look([])
    console.print(look.output)

    while True:
        try:
            line = await asyncio.to_thread(_read_line)
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再会。[/dim]")
            return
        try:
            turn = await repl.handle(line)
        except Quit:
            console.print("[dim]再会。[/dim]")
            return
        if turn.output:
            console.print(turn.output)


def _read_line() -> str:
    """Single-line prompt. Kept tiny so asyncio.to_thread is cheap."""
    return input("> ")


def main() -> None:
    """Entry point. Bridges from blocking ``__main__`` into the async REPL."""
    load_dotenv()
    _banner()

    engine = get_engine()
    with Session(engine) as session:
        if session.get(PlayerStateRow, "player") is None:
            console.print(
                "[red]世界还没有种子数据。先跑：[/red]\n"
                "  [yellow]python -m wulin_mud.scripts.seed_world[/yellow]"
            )
            sys.exit(1)
        try:
            asyncio.run(_run(session))
        except RuntimeError as exc:
            # Most likely: OPENAI_API_KEY not set.
            console.print(f"[red]{exc}[/red]")
            sys.exit(2)


if __name__ == "__main__":
    main()
