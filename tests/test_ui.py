"""Tests for the terminal UI. They render to a recording console, with no real terminal."""

from __future__ import annotations

import io
import random
from collections import deque
from pathlib import Path

import pytest
from rich.console import Console

from pursuit.content.loader import Content
from pursuit.engine import rules, save
from pursuit.engine.setup import GameConfig, new_game
from pursuit.ui import render
from pursuit.ui.app import App
from pursuit.ui.terminal import TerminalController


def make_console(width: int = 120) -> Console:
    return Console(file=io.StringIO(), width=width, color_system=None, force_terminal=False)


def output(console: Console) -> str:
    assert isinstance(console.file, io.StringIO)
    return console.file.getvalue()


class Keys:
    """Typed answers for the UI, in order. Fails the test if the UI asks for more."""

    def __init__(self, *answers: str) -> None:
        self.answers = deque(answers)

    def __call__(self, prompt: str) -> str:
        if not self.answers:
            raise AssertionError(f"the UI asked for more input: {prompt}")
        return self.answers.popleft()


class RandomPlayer(TerminalController):
    """Answers every prompt with a random valid key. On the action menu it sometimes opens
    a view, and it ends the turn often enough that every game finishes."""

    def __init__(self, console: Console, seed: int) -> None:
        super().__init__(console)
        self.rng = random.Random(seed)
        self.reads = 0

    def read(self, prompt: str, valid: list[str]) -> str:
        self.reads += 1
        if self.reads > 50_000:
            raise AssertionError("the game did not finish")
        if valid == [""]:
            return ""
        numbers = [v for v in valid if v.isdigit()]
        if "m" in valid:
            roll = self.rng.random()
            if roll < 0.08:
                return self.rng.choice(["m", "i", "r", "k", "l", "h"])
            if roll < 0.4:
                return max(numbers, key=int)
        if numbers:
            return self.rng.choice(numbers)
        return self.rng.choice(valid)


@pytest.fixture
def saves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PURSUIT_SAVES", str(tmp_path))
    return tmp_path


def test_every_view_renders(content: Content) -> None:
    from rich.console import Console

    console = Console(file=io.StringIO(), width=120, color_system="truecolor", force_terminal=True)
    game = new_game(content, GameConfig("cthulhu", ("hollis_grange", "ada_penhallow"), seed=3))
    inv = game.investigators[0]
    rules.gain_condition(game, inv, "leg_wound")
    for item in (
        render.header(game),
        render.investigator_panel(game, inv, current=True),
        render.location_panel(game, "south_pacific"),
        render.rites_panel(game),
        render.log_panel(game),
        render.market_table(game, inv),
        render.map_view(game),
        render.old_one_panel(game.old_one),
        render.investigator_card(content.investigators["ada_penhallow"], content),
        render.monster_panel(content.monsters["ghoul"], 1, 2),
        render.stats_table(game),
    ):
        console.print(item)
    text = output(console)
    assert "Hollis Grange" in text and "Leg Wound" in text and "South Pacific" in text


def test_map_marks_investigators_and_rifts(content: Content) -> None:
    console = make_console()
    game = new_game(content, GameConfig("king_in_yellow", ("hollis_grange",), seed=3))
    console.print(render.map_view(game))
    text = output(console)
    assert "CH" in text and "The World, 1926" in text
    assert "*" in text  # the legend marks where investigators stand


def test_map_fits_a_narrow_terminal(content: Content) -> None:
    console = make_console(width=80)
    game = new_game(content, GameConfig("king_in_yellow", ("hollis_grange",), seed=3))
    console.print(render.map_view(game))
    assert all(len(line) <= 80 for line in output(console).splitlines())


@pytest.mark.parametrize("seed", range(4))
def test_random_player_finishes_a_game_through_the_ui(content: Content, saves: Path, seed: int) -> None:
    console = make_console()
    app = App(console, content)
    app.ui = RandomPlayer(console, seed)
    old = sorted(content.old_ones)[seed]
    path = saves / "ui.json"
    game = new_game(content, GameConfig(old, ("tug_mulroney", "celestine_boudreaux"), seed=seed), app.ui)
    app.play(game, path)
    assert game.outcome in ("win", "loss")
    assert not path.exists(), "a finished game removes its save"
    text = output(console)
    assert "VICTORY" in text or "DEFEAT" in text


def test_main_menu_help_and_quit(content: Content, saves: Path) -> None:
    console = make_console()
    App(console, content, Keys("4", "", "5")).main_menu()
    assert "How to play" in output(console)


def test_invalid_input_asks_again(content: Content, saves: Path) -> None:
    console = make_console()
    App(console, content, Keys("banana", "9", "5")).main_menu()
    assert output(console).count("Please enter one of") == 2


def test_new_game_wizard_then_save_and_quit_then_continue(content: Content, saves: Path) -> None:
    console = make_console()
    keys = Keys(
        "1",  # main menu: new game
        "1",
        "y",  # first Old One (lowest difficulty), confirm
        "2",  # normal difficulty
        "2",  # two investigators
        "1",
        "y",  # first investigator, confirm
        "1",
        "y",  # next investigator, confirm
        "",  # read the introduction
        "m",
        "",  # look at the map, go back
        "s",
        "",  # save
        "q",
        "1",  # quit, saving first
        "2",  # main menu: continue
        "q",
        "2",  # quit without saving
        "5",  # quit the game
    )
    App(console, content, keys).main_menu()
    assert not keys.answers
    text = output(console)
    assert "Rites to complete" in text and "The World, 1926" in text and "Saved to" in text
    files = list(saves.glob("*.json"))
    assert len(files) == 1
    loaded = save.load_game(content, files[0])
    assert loaded.round == 1 and len(loaded.investigators) == 2


def test_broken_save_shows_an_error(content: Content, saves: Path) -> None:
    (saves / "broken.json").write_text('{"version": 1, "old_one": "x", "round": 1, "investigators": []}')
    console = make_console()
    App(console, content, Keys("2", "", "5")).main_menu()
    assert "Cannot load" in output(console)
