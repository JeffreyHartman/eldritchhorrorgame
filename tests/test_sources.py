"""Tests that prompts, die rolls, and automatic gains and losses name their source."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from conftest import MakeGame, Script, set_dice
from pursuit.content.loader import Content
from pursuit.controller import Option
from pursuit.effects import library
from pursuit.effects.base import Ctx, parse_effects, run_effects
from pursuit.engine import combat, phases, rules
from pursuit.engine.state import AssetCard, Game, MonsterInst


def place(game: Game, monster_id: str, loc_id: str = "arkham") -> MonsterInst:
    monster = MonsterInst(game.uid(), monster_id)
    game.locations[loc_id].monsters.append(monster)
    return monster


def spell(game: Game) -> AssetCard:
    card = rules.draw_matching(game, kind="spell")
    assert card is not None
    return card


@pytest.mark.parametrize(
    ("source", "name"),
    [
        ("ability:mark_harrigan", "Mark Harrigan"),
        ("start:akachi_onyele", "Akachi Onyele"),
        ("asset:cat_burglar", "Cat Burglar"),
        ("asset_back:cat_burglar", "Cat Burglar"),
        ("reckoning_asset:cat_burglar", "Cat Burglar"),
        ("condition:dark_pact", "Dark Pact"),
        ("condition_action:dark_pact", "Dark Pact"),
        ("reckoning_condition:dark_pact", "Dark Pact"),
        ("monster:wraith", "Wraith"),
        ("monster_spawn:wraith", "Wraith"),
        ("mythos:treacherous_magic", "Treacherous Magic"),
        ("mythos_zero:treacherous_magic", "Treacherous Magic"),
        ("reckoning_mythos:treacherous_magic", "Treacherous Magic"),
        ("rumor:treacherous_magic", "Treacherous Magic"),
        ("setup:azathoth", "Azathoth"),
        ("awakening:azathoth", "Azathoth"),
        ("awakened_doom:azathoth", "Azathoth"),
        ("reckoning_ao:azathoth", "Azathoth"),
        ("eldritch_move:azathoth", "Azathoth"),
        ("encounter:general_1", "General Encounter"),
        ("encounter:other_world_city_of_the_great_race_1", "Other World Encounter"),
        ("no_prefix", ""),
    ],
)
def test_source_name_gives_the_display_name(make_game: MakeGame, source: str, name: str) -> None:
    assert Ctx(make_game(), None, source).source_name == name


def test_source_name_of_a_cultist_comes_from_the_old_one_sheet(make_game: MakeGame) -> None:
    game = make_game()
    assert Ctx(game, None, "reckoning_monster:cultist").source_name == game.old_one.cultist.name


def test_source_name_finds_a_mystery_of_the_old_one(make_game: MakeGame) -> None:
    game = make_game()
    mystery = game.old_one.mysteries[0]
    assert Ctx(game, None, f"mystery:{mystery.id}").source_name == mystery.name


def test_a_condition_reckoning_roll_shows_the_condition_and_the_die(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = game.investigators[0]
    rules.gain_condition(game, inv, "dark_pact")
    set_dice(game, 6)
    rules.reckon_condition(game, inv, inv.conditions[-1])
    assert "Dark Pact: the die shows 6." in script.texts()


def test_zombie_horde_reckoning_roll_is_in_the_log_with_its_source(make_game: MakeGame) -> None:
    game = make_game()
    place(game, "zombie_horde")
    set_dice(game, 2)
    rules.reckon_monsters(game)
    assert "Zombie Horde: the die shows 2." in game.log


def test_dunwich_horror_reckoning_roll_is_in_the_log_with_its_source(make_game: MakeGame) -> None:
    game = make_game()
    place(game, "dunwich_horror")
    set_dice(game, 5)
    rules.reckon_monsters(game)
    assert "The Dunwich Horror: the die shows 5." in game.log


def test_a_random_outcome_names_its_source(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    data = [{"type": "random", "outcomes": [{"weight": 1, "text": "It works."}, {"weight": 1, "text": "It works."}]}]
    run_effects(parse_effects(data, "t"), Ctx(game, None, "mythos:treacherous_magic"))
    assert "Treacherous Magic: It works." in script.texts()


def test_treacherous_magic_prompts_name_the_card(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = game.investigators[0]
    inv.assets.append(spell(game))
    script.add("shed", "Keep the rest")
    run_effects(game.content.mythos["treacherous_magic"].effects, Ctx(game, None, "mythos:treacherous_magic"))
    assert ("shed", "Treacherous Magic: Discard a possession?") in script.asked


def test_lose_asset_prompt_names_its_source(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = game.investigators[0]
    inv.assets = [spell(game), spell(game)]
    effects = parse_effects([{"type": "lose_asset", "kind": "spell"}], "t")
    run_effects(effects, Ctx(game, inv, "condition:dark_pact"))
    assert ("lose_asset", "Dark Pact: Choose a possession to discard.") in script.asked


def test_a_source_with_no_name_leaves_the_prompt_alone(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = game.investigators[0]
    inv.assets = [spell(game), spell(game)]
    run_effects(parse_effects([{"type": "lose_asset", "kind": "spell"}], "t"), Ctx(game, inv, "t"))
    assert ("lose_asset", "Choose a possession to discard.") in script.asked


def test_every_effect_prompt_goes_through_ctx_sourced() -> None:
    tree = ast.parse(Path(library.__file__).read_text(encoding="utf-8"))
    unsourced = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and (node.func.value.id, node.func.attr) in (("rules", "choose"), ("rules", "confirm"))
        and not (isinstance(node.args[1], ast.Call) and ast.unparse(node.args[1].func) == "ctx.sourced")
    ]
    assert not unsourced


def test_a_wraith_spawn_names_the_wraith_and_the_cancel(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    lead = game.lead_investigator()
    rules.gain_condition(game, lead, "blessed")
    game.monster_cup.append("wraith")
    rules.spawn_monster(game, "arkham", "wraith")
    assert not rules.has_condition(lead, "blessed") and not rules.has_condition(lead, "cursed")
    assert f"Wraith: Cursed cancels Blessed on {lead.name}." in script.texts()


def test_a_blessed_gain_names_the_cursed_it_cancels(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = game.investigators[0]
    rules.gain_condition(game, inv, "cursed")
    run_effects(parse_effects([{"type": "gain_condition", "id": "blessed"}], "t"), Ctx(game, inv, "asset:cat_burglar"))
    assert f"Cat Burglar: Blessed cancels Cursed on {inv.name}." in script.texts()


@pytest.mark.parametrize(
    ("effect", "line"),
    [
        ({"type": "health", "amount": -1}, "{name} loses 1 Health."),
        ({"type": "sanity", "amount": -1}, "{name} loses 1 Sanity."),
        ({"type": "clues", "amount": 1}, "{name} gains 1 Clue."),
        ({"type": "gain_condition", "id": "dark_pact"}, "{name} gains Dark Pact (deal): "),
    ],
)
def test_an_automatic_gain_or_loss_names_its_source(
    make_game: MakeGame, script: Script, effect: dict[str, object], line: str
) -> None:
    game = make_game()
    inv = game.investigators[0]
    run_effects(parse_effects([effect], "t"), Ctx(game, inv, "reckoning_mythos:treacherous_magic"))
    expected = "Treacherous Magic: " + line.format(name=inv.name)
    assert any(text.startswith(expected) for text in script.texts())


def test_a_lost_possession_names_its_source(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = game.investigators[0]
    inv.assets = [spell(game)]
    name = game.asset_def(inv.assets[0]).name
    run_effects(parse_effects([{"type": "lose_asset", "kind": "spell"}], "t"), Ctx(game, inv, "condition:dark_pact"))
    assert f"Dark Pact: {inv.name} discards {name}." in script.texts()


def test_a_removed_condition_names_its_source(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = game.investigators[0]
    rules.gain_condition(game, inv, "dark_pact")
    effects = parse_effects([{"type": "remove_condition", "id": "dark_pact"}], "t")
    run_effects(effects, Ctx(game, inv, "mythos:treacherous_magic"))
    assert f"Treacherous Magic: {inv.name} discards Dark Pact." in script.texts()


def test_doom_from_an_effect_names_its_source(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    place(game, "zombie_horde")
    set_dice(game, 1)
    rules.reckon_monsters(game)
    assert any(text.startswith("Doom advances by 1 (Zombie Horde).") for text in script.texts("doom"))


def test_a_line_that_names_its_source_is_not_prefixed(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = game.investigators[0]
    rules.gain_condition(game, inv, "dark_pact")
    ctx = Ctx(game, inv, "condition:dark_pact", condition=inv.conditions[-1])
    run_effects(parse_effects([{"type": "remove_self"}], "t"), ctx)
    assert f"{inv.name} discards Dark Pact." in script.texts()


def test_the_mythos_name_appears_immediately_before_its_effect(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = game.investigators[0]
    inv.assets.append(spell(game))
    last_line: list[str] = []

    def keep_the_rest(options: list[Option]) -> int:
        last_line.append(script.events[-1].text)
        return len(options) - 1

    script.add("shed", keep_the_rest)
    phases.resolve_mythos(game, game.content.mythos["treacherous_magic"])
    assert last_line[0].startswith("Treacherous Magic: Each investigator may discard")


def test_a_mythos_card_with_no_effect_is_not_shown_again(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    mdef = next(m for m in game.content.mythos.values() if not m.effects)
    phases.resolve_mythos(game, mdef)
    assert not any(text.startswith(f"{mdef.name}: {mdef.text}") for text in script.texts("mythos"))


def test_the_dunwich_horror_keeps_its_own_article(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = game.investigators[0]
    monster = place(game, "dunwich_horror", inv.location)
    set_dice(game, *[6] * 40)
    combat.combat(game, inv, monster)
    text = " ".join(script.texts())
    assert "encounters The Dunwich Horror." in text
    assert "the The" not in text and "The The" not in text


@pytest.mark.parametrize(
    ("monster_id", "the_name", "sentence_name"),
    [
        ("dunwich_horror", "The Dunwich Horror", "The Dunwich Horror"),
        ("zombie_horde", "the Zombie Horde", "The Zombie Horde"),
    ],
)
def test_monster_names_in_a_sentence(content: Content, monster_id: str, the_name: str, sentence_name: str) -> None:
    mdef = content.monsters[monster_id]
    assert (mdef.the_name, mdef.sentence_name) == (the_name, sentence_name)
