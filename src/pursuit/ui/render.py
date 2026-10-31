"""Turn game state into `rich` renderables. Nothing here reads input or changes state."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from pursuit.content.defs import SKILLS, AssetDef, ConditionDef, InvestigatorDef, MonsterDef, OldOneDef
from pursuit.content.loader import Content
from pursuit.engine import actions
from pursuit.engine.dice import dice_pool
from pursuit.engine.rules import toughness
from pursuit.engine.state import Game, Investigator, Phase

ART_DIR = Path(__file__).resolve().parent / "art"
TERRAIN_STYLE = {"city": "yellow", "wilderness": "green", "sea": "blue"}
EVENT_STYLE = {
    "gain": "green",
    "loss": "red",
    "condition": "magenta",
    "rift": "bold red",
    "clue": "cyan",
    "doom": "bold red",
    "dread": "bold magenta",
    "monster": "red",
    "combat": "bold white",
    "travel": "white",
    "rite": "bold yellow",
    "defeat": "bold red",
    "info": "white",
    "outcome": "bold",
}
DREAD_NAMES = {1: "I", 2: "II", 3: "III"}


@cache
def art(name: str) -> str:
    path = ART_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8").rstrip("\n") if path.exists() else ""


def art_text(name: str, style: str) -> Text:
    return Text(art(name), style=style, no_wrap=True, overflow="crop")


def meter(value: int, maximum: int, style: str, empty: str = "grey30") -> Text:
    text = Text()
    text.append("█" * max(0, value), style=style)
    text.append("░" * max(0, maximum - value), style=empty)
    return text


def doom_meter(game: Game) -> Text:
    if game.awakened:
        text = Text("AWAKENED ", style="bold red blink")
        text.append(f"nights left {game.endgame} ", style="bold red")
        text.append_text(meter(game.endgame, game.old_one.awakening.nights, "red"))
        return text
    style = {1: "yellow", 2: "dark_orange", 3: "red"}[game.dread]
    text = Text("Doom ", style="bold")
    text.append_text(meter(game.doom, game.start_doom, style))
    text.append(f" {game.doom}", style=f"bold {style}")
    return text


def header(game: Game) -> RenderableType:
    phase = {Phase.DAY: "Day", Phase.ENCOUNTER: "Encounters", Phase.NIGHT: "Night"}[game.phase]
    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(justify="left")
    grid.add_column(justify="center")
    grid.add_column(justify="right")
    rites = game.active_rites()
    done = sum(r.done for r in rites)
    left = Text(f"Round {game.round} · {phase}", style="bold")
    right = Text(f"Dread {DREAD_NAMES[game.dread]}   Rites {done}/{len(rites)}", style="bold magenta")
    grid.add_row(left, doom_meter(game), right)
    old = game.old_one
    return Panel(grid, title=f"[bold]{old.name}[/], {old.title}", border_style="magenta", box=box.HEAVY)


def skills_text(game: Game | None, inv: Investigator | None, idef: InvestigatorDef) -> Text:
    text = Text()
    for i, skill in enumerate(SKILLS):
        value = inv.skill(skill) if inv else idef.skills[skill]
        if game and inv:
            bonus = dice_pool(game, inv, skill, 0, ("any",)) - value
            shown = f"{value}{'+' + str(bonus) if bonus > 0 else str(bonus) if bonus < 0 else ''}"
        else:
            shown = str(value)
        if i:
            text.append("  ")
        text.append(f"{skill.title()} ", style="dim")
        text.append(shown, style="bold")
    return text


def asset_line(adef: AssetDef, exhausted: bool = False) -> Text:
    style = {"spell": "magenta", "relic": "bold yellow", "ally": "cyan"}.get(adef.kind, "white")
    text = Text(adef.name, style=style + (" dim" if exhausted else ""))
    text.append(f" ({adef.kind})", style="dim")
    text.append(f" {adef.text}", style="grey70")
    return text


def condition_line(cdef: ConditionDef) -> Text:
    text = Text(cdef.name, style="bold magenta")
    text.append(f" [{', '.join(cdef.traits)}]", style="dim")
    text.append(f" {cdef.text}", style="grey70")
    return text


def investigator_panel(game: Game, inv: Investigator, *, current: bool = False) -> Panel:
    content = game.content
    idef = content.investigators[inv.def_id]
    body = Table.grid(padding=(0, 1))
    body.add_column()
    vitals = Text("Health ", style="dim")
    vitals.append_text(meter(inv.health, inv.max_health, "red"))
    vitals.append(f" {inv.health}/{inv.max_health}   ", style="bold red")
    vitals.append("Sanity ", style="dim")
    vitals.append_text(meter(inv.sanity, inv.max_sanity, "blue"))
    vitals.append(f" {inv.sanity}/{inv.max_sanity}", style="bold blue")
    body.add_row(vitals)
    body.add_row(skills_text(game, inv, idef))
    res = Text()
    res.append("Funds ", style="dim")
    res.append(f"${inv.funds}", style="bold green")
    res.append("   Clues ", style="dim")
    res.append(str(inv.clues), style="bold cyan")
    res.append("   Trophies ", style="dim")
    res.append(str(inv.trophies), style="bold yellow")
    if game.phase == Phase.DAY:
        res.append("   Actions left ", style="dim")
        res.append(str(actions.actions_left(game, inv)), style="bold")
    body.add_row(res)
    if idef.passive_text:
        body.add_row(Text(f"Gift: {idef.passive_text}", style="italic grey70"))
    for card in inv.assets:
        body.add_row(asset_line(content.assets[card.def_id], card.exhausted))
    for inst in inv.conditions:
        body.add_row(condition_line(content.conditions[inst.def_id]))
    if inv.delayed:
        body.add_row(Text("Delayed: loses the next Day turn.", style="bold red"))
    status = " [red](defeated)[/]" if inv.defeated else " [red](out)[/]" if inv.eliminated else ""
    loc = content.locations[inv.location].name
    return Panel(
        body,
        title=f"[bold]{inv.name}[/], {idef.occupation}{status}",
        subtitle=f"in {loc}",
        border_style="bold cyan" if current else "grey50",
    )


def location_panel(game: Game, loc_id: str) -> Panel:
    content = game.content
    ldef = content.locations[loc_id]
    state = game.locations[loc_id]
    style = TERRAIN_STYLE[ldef.terrain]
    parts: list[RenderableType] = [
        art_text("rift" if state.rift else ldef.terrain, "bold red" if state.rift else style)
    ]
    parts.append(Text(ldef.text, style="italic"))
    flags = Text()
    if state.rift:
        flags.append(" RIFT ", style="bold white on red")
        flags.append(" ")
    if state.clue:
        flags.append(" CLUE ", style="bold black on cyan")
        flags.append(" ")
    if ldef.hub:
        flags.append(" OWN ENCOUNTERS ", style="bold black on yellow")
    if flags:
        parts.append(flags)
    for monster in state.monsters:
        mdef = content.monsters[monster.def_id]
        line = Text(f"Monster: {mdef.name}", style="bold red")
        full = toughness(game, monster.def_id)
        line.append(f"  Health {full - monster.wounds}/{full}", style="red")
        parts.append(line)
    people = [i.name for i in game.investigators_at(loc_id)]
    if people:
        parts.append(Text("Here: " + ", ".join(people), style="cyan"))
    if state.belongings:
        parts.append(
            Text("Belongings left here: " + ", ".join(game.asset_def(c).name for c in state.belongings), style="yellow")
        )
    routes = Text("Routes: ", style="dim")
    for i, (dest, kind) in enumerate(content.adjacency[loc_id]):
        if i:
            routes.append(", ", style="dim")
        routes.append(content.locations[dest].name, style=TERRAIN_STYLE[content.locations[dest].terrain])
        routes.append(f" ({kind})", style="dim")
    parts.append(routes)
    return Panel(Group(*parts), title=f"[bold {style}]{ldef.name}[/] ({ldef.terrain})", border_style=style)


def location_line(game: Game, inv: Investigator) -> Text:
    """One line of status for an investigator's location, for screens with no room for art."""
    ldef = game.content.locations[inv.location]
    state = game.locations[inv.location]
    text = Text(f"{inv.name} is in ", style="dim")
    text.append(ldef.name, style="bold " + TERRAIN_STYLE[ldef.terrain])
    text.append(f"   Health {inv.health}/{inv.max_health}  Sanity {inv.sanity}/{inv.max_sanity}", style="dim")
    if state.rift:
        text.append("   RIFT", style="bold red")
    for monster in state.monsters:
        text.append(f"   {game.content.monsters[monster.def_id].name}", style="red")
    return text


def rites_panel(game: Game) -> Panel:
    table = Table(box=box.SIMPLE_HEAD, expand=True, show_edge=False)
    table.add_column("Rite", style="bold yellow", ratio=2)
    table.add_column("Progress", justify="center")
    table.add_column("How", ratio=4)
    for rite in game.active_rites():
        rdef = game.rite_def(rite)
        progress = Text(f"{rite.progress}/{rite.required}", style="bold green" if rite.done else "bold")
        table.add_row(rdef.name, progress, Text(rdef.text, style="grey70"))
    title = "The Final Rite" if game.awakened else "Rites to complete"
    return Panel(table, title=title, border_style="yellow")


def log_panel(game: Game, lines: int = 8) -> Panel:
    recent = game.log[-lines:]
    text = Text()
    for i, line in enumerate(recent):
        if i:
            text.append("\n")
        text.append("· " + line, style="grey70")
    return Panel(text or Text("Nothing yet.", style="dim"), title="Recent events", border_style="grey50")


def market_table(game: Game, inv: Investigator | None = None) -> Table:
    from pursuit.engine.rules import market_price

    table = Table(title="The Market", box=box.SIMPLE_HEAD, expand=True)
    table.add_column("Asset", style="bold")
    table.add_column("Cost", justify="right")
    table.add_column("Effect")
    for card in game.market:
        adef = game.asset_def(card)
        price = market_price(game, inv, card) if inv else adef.cost
        table.add_row(adef.name, f"${price}", Text(adef.text, style="grey70"))
    return table


def map_view(game: Game) -> RenderableType:
    content = game.content
    lines = [Text(line.ljust(100), style="dim green") for line in art("map").splitlines()]
    for line in lines:
        line.highlight_regex(r"~", "blue")
    seats = {i.location for i in game.active_investigators() if not i.defeated}
    for loc in content.locations.values():
        x, y = loc.pos
        state = game.locations[loc.id]
        if loc.id in seats:
            style = "bold white on dark_magenta"
        elif state.rift:
            style = "bold white on red"
        elif state.monsters:
            style = "bold red"
        elif state.clue:
            style = "bold black on cyan"
        else:
            style = "bold " + TERRAIN_STYLE[loc.terrain]
        line = lines[y]
        new = Text()
        new.append_text(line[:x])
        new.append(loc.code, style=style)
        new.append_text(line[x + 2 :])
        lines[y] = new
    map_text = Text("\n").join(lines)
    map_text.no_wrap = True
    map_text.overflow = "crop"

    legend = Table(box=None, padding=(0, 1), expand=True)
    for _ in range(4):
        legend.add_column(no_wrap=True)
    cells = []
    for loc in sorted(content.locations.values(), key=lambda loc: loc.code):
        state = game.locations[loc.id]
        cell = Text(f"{loc.code} ", style="bold " + TERRAIN_STYLE[loc.terrain])
        cell.append(loc.name, style="white")
        marks = []
        if state.rift:
            marks.append(("R", "bold red"))
        if state.clue:
            marks.append(("C", "bold cyan"))
        if state.monsters:
            marks.append((f"M{len(state.monsters)}", "red"))
        if loc.id in seats:
            marks.append(("*", "bold magenta"))
        for mark, style in marks:
            cell.append(f" {mark}", style=style)
        cells.append(cell)
    for i in range(0, len(cells), 4):
        legend.add_row(*cells[i : i + 4], *[Text("")] * (4 - len(cells[i : i + 4])))
    key = Text.assemble(
        ("Key: ", "dim"),
        ("XX", "bold white on dark_magenta"),
        (" investigators  ", "dim"),
        ("XX", "bold white on red"),
        (" rift (R)  ", "dim"),
        ("XX", "bold red"),
        (" monsters (M)  ", "dim"),
        ("XX", "bold black on cyan"),
        (" clue (C)  ", "dim"),
        ("city ", "yellow"),
        ("wilderness ", "green"),
        ("sea", "blue"),
    )
    return Group(Panel(map_text, title="The World, 1926", border_style="green", box=box.DOUBLE), key, legend)


def dice_text(rolls: list[int], success_on: int) -> Text:
    text = Text()
    for i, roll in enumerate(rolls):
        if i:
            text.append(" ")
        text.append(f"[{roll}]", style="bold green" if roll >= success_on else "grey50")
    return text


def monster_panel(mdef: MonsterDef, wounds: int, full: int) -> Panel:
    stats = Table.grid(padding=(0, 2))
    stats.add_column(style="dim")
    stats.add_column(style="bold")
    stats.add_row("Health", f"{full - wounds}/{full}" if full < 99 else "beyond counting")
    stats.add_row("Horror", f"{mdef.horror} Sanity (Nerve {mdef.horror_mod:+})" if mdef.horror else "none")
    stats.add_row("Strike", f"{mdef.damage} Health")
    stats.add_row("Fight", f"Brawn {mdef.fight_mod:+}")
    stats.add_row("Evade", f"Wits {mdef.evade_mod:+}")
    if mdef.roams:
        stats.add_row("Roams", "moves toward investigators")
    grid = Table.grid(padding=(0, 3))
    grid.add_row(art_text(mdef.art or mdef.form, "red"), stats)
    return Panel(Group(grid, Text(mdef.text, style="italic")), title=f"[bold red]{mdef.name}[/]", border_style="red")


def old_one_panel(odef: OldOneDef, *, full: bool = True) -> Panel:
    parts: list[RenderableType] = [art_text(odef.art, "bold magenta")]
    parts.append(Text(odef.description, style="italic"))
    if full:
        info = Text()
        info.append(
            f"Difficulty: {odef.difficulty}   Doom: {odef.doom}   Rites needed: {odef.rites_needed}\n", style="bold"
        )
        for rule in odef.rules_text:
            info.append(f"• {rule}\n", style="grey85")
        parts.append(info)
    return Panel(Group(*parts), title=f"[bold magenta]{odef.name}[/], {odef.title}", border_style="magenta")


def investigator_card(idef: InvestigatorDef, content: Content) -> Panel:
    body = Table.grid(padding=(0, 1))
    body.add_column()
    body.add_row(Text(f"Health {idef.health}   Sanity {idef.sanity}   Funds ${idef.funds}", style="bold"))
    body.add_row(skills_text(None, None, idef))
    body.add_row(Text(f"Starts in {content.locations[idef.start].name}", style="dim"))
    if idef.passive_text:
        body.add_row(Text(f"Gift: {idef.passive_text}", style="cyan"))
    if idef.action:
        body.add_row(Text(f"Action: {idef.action.text}", style="cyan"))
    for asset_id in idef.assets:
        body.add_row(asset_line(content.assets[asset_id]))
    body.add_row(Text(idef.bio, style="italic grey70"))
    body.add_row(Text(f'"{idef.quote}"', style="italic yellow"))
    return Panel(body, title=f"[bold]{idef.name}[/], {idef.occupation}", border_style="cyan")


def stats_table(game: Game) -> Table:
    table = Table(title="The record of the investigation", box=box.SIMPLE_HEAD, min_width=44)
    table.add_column("What")
    table.add_column("Count", justify="right", style="bold")
    labels = [
        ("Rounds played", game.round),
        ("Encounters", game.stats.get("encounters", 0)),
        ("Monsters defeated", game.stats.get("monsters_defeated", 0)),
        ("Rifts sealed", game.stats.get("rifts_sealed", 0)),
        ("Rifts opened", game.stats.get("rifts_opened", 0)),
        ("Clues gathered", game.stats.get("clues_gained", 0)),
        ("Rites completed", game.stats.get("rites_completed", 0)),
        ("Investigators lost", game.stats.get("investigators_lost", 0)),
    ]
    for label, value in labels:
        table.add_row(label, str(value))
    return table
