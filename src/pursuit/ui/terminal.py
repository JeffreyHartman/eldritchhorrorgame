"""The terminal controller: shows events with `rich` and reads the player's decisions."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from rich import box
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from pursuit.controller import Event, Option
from pursuit.engine import rules, save
from pursuit.engine.actions import FREE_ACTIONS
from pursuit.engine.state import Game, Investigator
from pursuit.ui import render

InputFn = Callable[[str], str]

HOTKEYS = {
    "m": "Map",
    "i": "Investigators",
    "r": "Mysteries",
    "k": "Reserve",
    "l": "Log",
    "h": "Help",
    "s": "Save",
    "q": "Quit",
}

HELP_TEXT = """\
[bold]Action Phase[/]
You have 2 actions. Each action works at most once per round.
  Travel              Move 1 space along any path, then spend Train/Ship Tickets for extra steps.
  Rest                Recover 1 Health and 1 Sanity (not while a Monster is on your space).
  Trade               Trade possessions, Clues, and tickets with an investigator on your space.
  Prepare for Travel  On a City space, gain 1 Train or Ship Ticket matching a connected path (max 2).
  Acquire Assets      On a City space with no Monsters, test Influence to gain cards from the reserve.
  Component Actions   Perform an Action or Local Action on a card or Investigator sheet.

[bold]Tests[/]
Roll dice equal to your skill + your single highest positive card bonus + additional dice - penalties.
Each 5 or 6 is a success (4+ if Blessed, 6 if Cursed).
Spend 1 Clue to reroll 1 die.

[bold]Encounter Phase[/]
If Monsters are on your space, fight each one (Will test vs horror, Strength test vs damage).
If no Monsters remain on your space, choose a location or token encounter:
  Research (Clue token), Other World (Gate token), Expedition, Rumor, Mystery, or Fallen Investigator.

[bold]Mythos Phase[/]
Draw 1 Mythos card and resolve its icons in order:
  Advance Omen, Reckoning, Spawn Gates, Monster Surge, Spawn Clues, Rumor, Eldritch tokens, Card Effect.

[bold]Winning[/]
Solve 3 Mysteries before the Ancient One awakens (or also solve the Final Mystery if it awakens).
"""


class QuitToMenu(Exception):
    """The player chose to leave the game and return to the main menu."""


class TerminalController:
    def __init__(self, console: Console, input_fn: InputFn | None = None, save_path: Path | None = None) -> None:
        self.console = console
        self.input_fn: InputFn = input_fn or (lambda prompt: console.input(prompt))
        self.save_path = save_path
        self.unread = False

    # --- input ------------------------------------------------------------------------

    def read(self, prompt: str, valid: list[str]) -> str:
        """Ask until the answer is one of `valid` (compared in lower case)."""
        while True:
            answer = self.input_fn(prompt).strip().lower()
            if answer in valid:
                return answer
            self.console.print(
                f"[red]Please enter one of: {', '.join(valid[:12])}{'...' if len(valid) > 12 else ''}[/]"
            )

    def pause(self) -> None:
        if self.unread:
            self.read("[dim]Press Enter to continue...[/]", [""])
            self.unread = False

    def show(self, *items: RenderableType) -> None:
        """Show a full screen and wait for Enter."""
        self.console.clear()
        for item in items:
            self.console.print(item)
        self.read("\n[dim]Press Enter to go back...[/]", [""])
        self.unread = False

    # --- the controller protocol ------------------------------------------------------

    def choose(
        self, game: Game, prompt: str, options: list[Option], *, kind: str, inv: Investigator | None = None
    ) -> int:
        if kind == "action" and inv is not None:
            return self._action_menu(game, prompt, options, inv)
        return self.menu(prompt, options)

    def confirm(self, game: Game, prompt: str, *, kind: str, inv: Investigator | None = None) -> bool:
        return self.ask_yes_no(prompt)

    def ask_yes_no(self, prompt: str) -> bool:
        answer = self.read(f"[bold cyan]{prompt}[/] [yellow](y/n)[/] ", ["y", "n", "yes", "no"])
        self.unread = False
        return answer.startswith("y")

    def checkpoint(self, game: Game) -> None:
        if self.save_path is not None:
            save.save_game(game, self.save_path)

    def notify(self, game: Game, event: Event) -> None:
        handler = getattr(self, f"_on_{event.kind}", None)
        if handler is not None:
            handler(game, event)
        else:
            style = render.EVENT_STYLE.get(event.kind, "white")
            self.console.print(Text("  • " + event.text, style=style))
        # The Action dashboard shows the round and whose turn it is, so these need no pause.
        quiet = event.kind in ("phase", "turn") and event.data.get("phase") == "action"
        if not quiet:
            self.unread = True

    # --- menus ------------------------------------------------------------------------

    def _option_table(self, options: list[Option], shown: list[int]) -> Table:
        table = Table.grid(padding=(0, 1))
        table.add_column(justify="right", style="bold green")
        table.add_column()
        for number, index in enumerate(shown, start=1):
            option = options[index]
            label = Text(option.label, style="bold" if option.enabled else "grey42")
            if option.detail:
                label.append(f"  {option.detail}", style="grey62" if option.enabled else "grey35")
            table.add_row(f"{number}." if option.enabled else Text(f"{number}.", style="grey35"), label)
        return table

    def _ask(self, options: list[Option], shown: list[int], extra: list[str]) -> str | int:
        """Read a menu answer. Returns the chosen option's index, or a hotkey letter."""
        self.console.print(self._option_table(options, shown))
        valid = [str(n) for n, i in enumerate(shown, start=1) if options[i].enabled]
        answer = self.read("[bold cyan]>[/] ", valid + extra)
        if answer.isdigit():
            self.unread = False
            return shown[int(answer) - 1]
        return answer

    def menu(self, prompt: str, options: list[Option]) -> int:
        self.console.print(Text(prompt, style="bold cyan"))
        pick = self._ask(options, list(range(len(options))), [])
        assert isinstance(pick, int)
        return pick

    def _dashboard(self, game: Game, inv: Investigator) -> None:
        self.console.clear()
        self.console.print(render.header(game))
        wide = self.console.width >= 110
        left = render.investigator_panel(game, inv, current=True)
        right = render.location_panel(game, inv.location)
        if wide:
            grid = Table.grid(expand=True, padding=(0, 1))
            grid.add_column(ratio=1)
            grid.add_column(ratio=1)
            grid.add_row(left, right)
            self.console.print(grid)
        else:
            self.console.print(left)
            self.console.print(right)
        self.console.print(render.log_panel(game, 6))

    def _action_menu(self, game: Game, prompt: str, options: list[Option], inv: Investigator) -> int:
        while True:
            self.pause()
            self._dashboard(game, inv)
            self.console.print(Text(prompt, style="bold cyan"))
            keys = "  ".join(f"[bold yellow]{k.upper()}[/] {v}" for k, v in HOTKEYS.items())
            self.console.print(Text.from_markup(f"[dim]Views:[/] {keys}"))
            # Free actions that are impossible here only add noise, so they stay hidden.
            shown = [i for i, o in enumerate(options) if o.enabled or o.value[0] not in FREE_ACTIONS]
            pick = self._ask(options, shown, list(HOTKEYS))
            if isinstance(pick, int):
                return pick
            self._hotkey(game, inv, pick)

    def _hotkey(self, game: Game, inv: Investigator, key: str) -> None:
        if key == "m":
            self.show(render.map_view(game))
        elif key == "i":
            self.show(*(render.investigator_panel(game, i, current=i is inv) for i in game.investigators))
        elif key == "r":
            self.show(render.old_one_panel(game.old_one), render.rites_panel(game))
        elif key == "k":
            self.show(render.market_table(game, inv))
        elif key == "l":
            text = Text("\n".join(game.log[-40:]) or "Nothing yet.", style="grey85")
            self.show(Panel(text, title="The last 40 events"))
        elif key == "h":
            self.show(Panel(Text.from_markup(HELP_TEXT), title="How to play", border_style="cyan"))
        elif key == "s":
            self._save(game)
        elif key == "q":
            self._quit(game)

    def _save(self, game: Game) -> None:
        if self.save_path is None:
            self.console.print("[red]This game has no save file.[/]")
            self.unread = True
            return
        save.save_game(game, self.save_path)
        self.console.print(f"[green]Saved to {self.save_path}.[/]")
        self.unread = True

    def _quit(self, game: Game) -> None:
        options = [Option("Save and quit to the main menu"), Option("Quit without saving"), Option("Keep playing")]
        pick = self.menu("Leave the game?", options)
        if pick == 0:
            if self.save_path is not None:
                save.save_game(game, self.save_path)
            raise QuitToMenu
        if pick == 1:
            raise QuitToMenu

    # --- event screens ----------------------------------------------------------------

    def _on_phase(self, game: Game, event: Event) -> None:
        self.pause()
        self.console.clear()
        self.console.print(render.header(game))
        phase = event.data.get("phase")
        if phase == "mythos":
            self.console.print(render.art_text("night", "bold blue"), justify="center")
            self.console.print(Rule(f"[bold blue]{event.text}[/]", style="blue"))
        elif phase == "encounter":
            self.console.print(Rule(f"[bold yellow]{event.text}[/]", style="yellow"))
        else:
            self.console.print(Rule(f"[bold]{event.text}[/]"))

    def _on_turn(self, game: Game, event: Event) -> None:
        if event.data.get("phase") == "encounter":
            self.pause()
            self.console.clear()
            self.console.print(render.header(game))
            self.console.print(Rule(f"[bold yellow]{event.text}[/]", style="yellow"))
            inv = next((i for i in game.investigators if i.name == event.data.get("investigator")), None)
            if inv is not None:
                self.console.print(render.location_line(game, inv))
        else:
            self.console.print(Rule(f"[bold cyan]{event.text}[/]", style="cyan"))

    def _on_dice(self, game: Game, event: Event) -> None:
        line = Text("  ")
        line.append_text(render.dice_text(event.data["rolls"], event.data["success_on"]))
        ok = event.data["successes"] >= event.data["needed"]
        line.append(f"  {event.text}", style="green" if ok else "yellow")
        self.console.print(line)

    def _on_encounter(self, game: Game, event: Event) -> None:
        deck = event.data.get("deck", "")
        is_other_world = deck.startswith("other_world")
        terrain = "rift" if is_other_world else game.content.locations[event.data["location"]].terrain
        style = "bold red" if is_other_world else render.TERRAIN_STYLE[terrain]
        body = Group(render.art_text(terrain, style), Text(event.text, style="italic"))
        self.console.print(Panel(body, title=f"[bold]{event.data.get('title', 'Encounter')}[/]", border_style=style))

    def _on_mythos(self, game: Game, event: Event) -> None:
        if "title" not in event.data:
            self.console.print(Text("  • " + event.text, style="bold magenta"))
            return
        body = Group(
            Text(event.data.get("flavor", ""), style="italic grey70"),
            Text(""),
            Text(event.text, style="bold"),
        )
        color = event.data.get("color", "yellow")
        title = f"[bold magenta]Mythos ({color}): {event.data.get('title', '')}[/]"
        icons = ", ".join(event.data.get("icons", []))
        self.console.print(Panel(body, title=title, subtitle=icons, border_style="magenta", box=box.DOUBLE))

    def _on_combat(self, game: Game, event: Event) -> None:
        if event.data.get("start"):
            mdef = game.content.monsters[event.data["monster"]]
            full = rules.toughness(game, mdef.id)
            self.console.print(render.monster_panel(mdef, event.data.get("wounds", 0), full))
        else:
            style = "bold green" if event.data.get("defeated") else "bold white"
            self.console.print(Text("  ⚔ " + event.text, style=style))

    def _on_awaken(self, game: Game, event: Event) -> None:
        self.pause()
        self.console.clear()
        old = game.old_one
        body = Group(render.art_text(old.art, "bold red"), Text(""), Text(event.text, style="bold"))
        self.console.print(Panel(body, title=f"[bold red]{old.name} AWAKENS[/]", border_style="red", box=box.HEAVY))
        self.console.print(render.rites_panel(game))

    def _on_outcome(self, game: Game, event: Event) -> None:
        style = "bold green" if event.data.get("result") == "win" else "bold red"
        self.console.print(Text("\n" + event.text, style=style))
