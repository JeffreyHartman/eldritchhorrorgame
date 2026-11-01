"""The application shell: main menu, new-game setup, loading, help, and the end screen."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from pursuit import __version__
from pursuit.content.loader import Content, load_content
from pursuit.content.reader import ContentError
from pursuit.controller import Option
from pursuit.engine import phases, save
from pursuit.engine.setup import GameConfig, new_game
from pursuit.engine.state import Game
from pursuit.ui import render
from pursuit.ui.terminal import HELP_TEXT, InputFn, QuitToMenu, TerminalController

INTRO = """\
Across the globe, ancient gates are tearing open and an Ancient One stirs in its slumber.
Travel the world, acquire assets and spells, gather clues through research, close gates in
other worlds, and solve three Mysteries before humanity's time runs out.
"""


class App:
    def __init__(self, console: Console, content: Content, input_fn: InputFn | None = None) -> None:
        self.console = console
        self.content = content
        self.ui = TerminalController(console, input_fn)

    # --- helpers ----------------------------------------------------------------------

    def menu(self, prompt: str, options: list[Option]) -> int:
        return self.ui.menu(prompt, options)

    def title_screen(self) -> None:
        self.console.clear()
        self.console.print(Align.center(render.art_text("title", "bold magenta")))
        self.console.print(Align.center(render.art_text("eye", "green")))
        self.console.print(
            Align.center(Text(f"A co-op cosmic-horror game for the terminal · v{__version__}", style="dim"))
        )
        self.console.print(Rule(style="magenta"))

    # --- main menu --------------------------------------------------------------------

    def main_menu(self) -> None:
        while True:
            self.title_screen()
            saves = [(p, s) for p, s in save.list_saves() if not s.get("outcome")]
            options = [
                Option("New game"),
                Option(
                    "Continue", detail=self._save_label(saves[0][1]) if saves else "no saved game", enabled=bool(saves)
                ),
                Option("Load a saved game", enabled=bool(saves)),
                Option("How to play"),
                Option("Quit"),
            ]
            pick = self.menu("What will you do?", options)
            if pick == 0:
                self.new_game()
            elif pick == 1:
                self.load(saves[0][0])
            elif pick == 2:
                self.choose_save(saves)
            elif pick == 3:
                self.ui.show(
                    Panel(Text(INTRO, style="italic")), Panel(Text.from_markup(HELP_TEXT), title="How to play")
                )
            else:
                self.console.print("[dim]The stars wheel on without you.[/]")
                return

    def _save_label(self, summary: dict) -> str:
        who = ", ".join(summary["investigators"])
        old = self.content.old_ones.get(summary["old_one"])
        name = old.name if old else summary["old_one"]
        return f"{name}, round {summary['round']}, {who} ({summary['saved_at'].replace('T', ' ')})"

    def choose_save(self, saves: list[tuple[Path, dict]]) -> None:
        options = [Option(path.stem, detail=self._save_label(summary)) for path, summary in saves]
        options.append(Option("Back"))
        pick = self.menu("Load which game?", options)
        if pick < len(saves):
            self.load(saves[pick][0])

    def load(self, path: Path) -> None:
        try:
            game = save.load_game(self.content, path)
        except save.SaveError as exc:
            self.console.print(f"[red]Cannot load {path.name}: {exc}[/]")
            self.ui.read("[dim]Press Enter...[/]", [""])
            return
        self.play(game, path)

    # --- new game ---------------------------------------------------------------------

    def new_game(self) -> None:
        content = self.content
        self.console.clear()
        self.console.print(Panel(Text(INTRO, style="italic"), title="A new investigation", border_style="magenta"))

        old_ones = sorted(content.old_ones.values(), key=lambda o: ("low", "medium", "high").index(o.difficulty))
        while True:
            options = [Option(o.name, detail=f"{o.title} · difficulty {o.difficulty}") for o in old_ones]
            options.append(Option("Back to the main menu"))
            pick = self.menu("Which Old One stirs?", options)
            if pick == len(old_ones):
                return
            old = old_ones[pick]
            self.console.clear()
            self.console.print(render.old_one_panel(old))
            if self.ui.ask_yes_no(f"Face {old.name}?"):
                break

        diffs = list(content.rules.difficulties.values())
        self.console.clear()
        pick = self.menu("Difficulty?", [Option(d.label, detail=d.text) for d in diffs])
        difficulty = diffs[pick].id

        most = content.rules.max_investigators
        count = 1 + self.menu(
            "How many investigators? (You control all of them. Two or more is easier.)",
            [Option(str(n), detail="alone against the dark" if n == 1 else "") for n in range(1, most + 1)],
        )

        chosen: list[str] = []
        roster = sorted(content.investigators.values(), key=lambda d: d.name)
        while len(chosen) < count:
            self.console.clear()
            self.console.print(Rule(f"Investigator {len(chosen) + 1} of {count}", style="cyan"))
            free = [d for d in roster if d.id not in chosen]
            options = [
                Option(
                    d.name,
                    detail=f"{d.occupation} · Health {d.health} Sanity {d.sanity} · {content.locations[d.start].name}",
                )
                for d in free
            ]
            pick = self.menu("Choose an investigator.", options)
            idef = free[pick]
            self.console.clear()
            self.console.print(render.investigator_card(idef, content))
            if self.ui.ask_yes_no(f"Take {idef.name}?"):
                chosen.append(idef.id)

        config = GameConfig(old.id, tuple(chosen), difficulty)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = save.saves_dir() / f"{old.id}-{stamp}.json"
        self.ui.save_path = path
        game = new_game(content, config, self.ui)
        self.console.clear()
        self.console.print(render.old_one_panel(game.old_one, full=True))
        self.console.print(render.rites_panel(game))
        self.console.print(Text("The game saves itself at the start of each investigator's turn.", style="dim"))
        self.ui.unread = True
        self.play(game, path)

    # --- playing ----------------------------------------------------------------------

    def play(self, game: Game, path: Path) -> None:
        self.ui.save_path = path
        game.ctl = self.ui
        try:
            phases.play(game)
        except QuitToMenu:
            self.ui.unread = False
            return
        self.ui.pause()
        self.end_screen(game)
        path.unlink(missing_ok=True)

    def end_screen(self, game: Game) -> None:
        won = game.outcome == "win"
        art = render.art_text("victory" if won else "defeat", "bold green" if won else "bold red")
        title = "[bold green]VICTORY[/]" if won else "[bold red]DEFEAT[/]"
        body = Group(Align.center(art), Text(""), Text(game.outcome_reason, style="bold", justify="center"))
        self.ui.show(Panel(body, title=title, border_style="green" if won else "red"), render.stats_table(game))


def run(console: Console | None = None, input_fn: InputFn | None = None) -> int:
    console = console or Console()
    try:
        content = load_content()
    except ContentError as exc:
        console.print(f"[bold red]The game data has an error:[/] {exc}")
        return 1
    try:
        App(console, content, input_fn).main_menu()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Goodbye.[/]")
    return 0


if __name__ == "__main__":
    sys.exit(run())
