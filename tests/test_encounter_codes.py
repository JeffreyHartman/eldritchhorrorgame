"""Tests for `encounter_code`, the `code` on `encounter` events, and the code on the encounter panel."""

from __future__ import annotations

import io
import re
from collections import Counter

import pytest
from rich.console import Console

from conftest import MakeGame, Script
from pursuit.content.defs import encounter_code
from pursuit.content.loader import Content
from pursuit.controller import Event
from pursuit.engine import phases
from pursuit.engine.state import Game
from pursuit.ui.terminal import TerminalController


def panel(game: Game, event: Event) -> str:
    """Render one `encounter` event through `TerminalController` and return the text."""
    out = io.StringIO()
    TerminalController(Console(file=out, width=80, color_system=None)).notify(game, event)
    return out.getvalue()


@pytest.mark.parametrize(
    ("encounter_id", "code"),
    [
        ("research_yog_sothoth_city_2", "YOG-C2"),
        ("research_azathoth_wilderness_8", "AZA-W8"),
        ("research_cthulhu_sea_1", "CTH-S1"),
        ("research_shub_niggurath_city_3", "SHU-C3"),
        ("americas_1", "AME-1"),
        ("europe_8", "EUR-8"),
        ("asia_australia_4", "ASI-4"),
        ("general_12", "GEN-12"),
        ("expedition_the_amazon_1", "EXP-AMA1"),
        ("expedition_antarctica_2", "EXP-ANT2"),
        ("expedition_the_heart_of_africa_3", "EXP-HEA3"),
        ("other_world_city_of_the_great_race_4", "OTH-CIT4"),
        ("other_world_the_abyss_1", "OTH-ABY1"),
        ("special_rlyeh_6", "SPE-RLY6"),
        ("special_key_1", "SPE-KEY1"),
    ],
)
def test_encounter_code_abbreviates_the_id(encounter_id: str, code: str) -> None:
    assert encounter_code(encounter_id) == code


def test_every_encounter_code_is_unique(content: Content) -> None:
    codes = Counter(encounter_code(encounter_id) for encounter_id in content.encounters)
    assert [code for code, count in codes.items() if count > 1] == []


def test_every_encounter_code_has_at_most_12_characters(content: Content) -> None:
    assert max(len(encounter_code(encounter_id)) for encounter_id in content.encounters) <= 12


@pytest.mark.parametrize(
    ("old_one", "deck", "card_id", "code"),
    [
        ("azathoth", "research_azathoth", "research_azathoth_city_1", "AZA-C1"),
        ("azathoth", "americas", "americas_1", "AME-1"),
        ("azathoth", "general", "general_12", "GEN-12"),
        ("azathoth", "expedition", "expedition_the_amazon_1", "EXP-AMA1"),
        ("azathoth", "other_world", "other_world_yuggoth_2", "OTH-YUG2"),
        ("cthulhu", "special_cthulhu", "special_rlyeh_1", "SPE-RLY1"),
        ("yog_sothoth", "special_yog_sothoth", "special_key_1", "SPE-KEY1"),
    ],
)
def test_a_drawn_card_puts_its_code_on_the_panel(
    make_game: MakeGame, script: Script, old_one: str, deck: str, card_id: str, code: str
) -> None:
    game = make_game(old_one=old_one)
    pile = game.encounter_decks[deck].cards
    pile.remove(card_id)
    pile.insert(0, card_id)
    phases._draw_and_run_encounter(game, game.investigators[0], deck)
    event = next(e for e in script.events if e.kind == "encounter")
    assert event.data["code"] == code
    assert code in panel(game, event)


def test_a_panel_with_no_card_shows_no_code(make_game: MakeGame) -> None:
    game = make_game()
    event = Event("encounter", "A rumor spreads.", {"title": "Rumor", "deck": "rumor", "location": "arkham"})
    lines = panel(game, event).splitlines()
    assert lines[-1].strip("╰─╯ ") == ""


def test_a_code_is_dim_and_not_bold_on_a_bold_border(make_game: MakeGame) -> None:
    game = make_game()
    out = io.StringIO()
    console = Console(file=out, width=80, color_system="standard", force_terminal=True)
    data = {"title": "Yuggoth", "deck": "other_world", "code": "OTH-YUG2", "location": "arkham"}
    TerminalController(console).notify(game, Event("encounter", "A cold star.", data))
    match = re.search(r"\x1b\[([\d;]+)m[^\x1b]*OTH-YUG2", out.getvalue())
    assert match is not None
    attributes = match[1].split(";")
    assert "2" in attributes and "1" not in attributes
