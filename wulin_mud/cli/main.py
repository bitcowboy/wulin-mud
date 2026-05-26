"""CLI entry point for wulin-mud.

This is a placeholder for v0.1. The real REPL will live here once the
ontology + action + LLM layers are wired up.

For now it just prints a friendly stub so the package can be installed
and `python -m wulin_mud` runs end-to-end.
"""

from rich.console import Console
from rich.panel import Panel

console = Console()


def main() -> None:
    """Entry point. Will become the game REPL."""
    console.print(
        Panel.fit(
            "[bold cyan]武林 MUD · wulin-mud[/bold cyan]\n\n"
            "v0.1.0a0 — pre-alpha. Skeleton only.\n\n"
            "See [yellow]docs/architecture.md[/yellow] before contributing.\n"
            "See [yellow]docs/roadmap.md[/yellow] for current goals.",
            border_style="cyan",
        )
    )


if __name__ == "__main__":
    main()
