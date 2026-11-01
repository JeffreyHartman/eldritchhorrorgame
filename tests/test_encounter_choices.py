"""Tests for optional costs on encounter cards: accepting, refusing, and being unable to pay."""

from __future__ import annotations

import pytest

from conftest import MakeGame, Script, first, set_dice
from pursuit.content.loader import Content
from pursuit.effects.base import Ctx, run_effects, walk
from pursuit.effects.library import Choice, Pay
from pursuit.engine import rules
from pursuit.engine.state import Game, Investigator

LISTED_SECTIONS = [
    ("americas_1", "san_francisco"),
    ("americas_4", "arkham"),
    ("americas_4", "buenos_aires"),
    ("americas_5", "san_francisco"),
    ("americas_7", "arkham"),
    ("americas_7", "buenos_aires"),
    ("asia_australia_2", "tokyo"),
    ("asia_australia_5", "shanghai"),
    ("asia_australia_5", "sydney"),
    ("asia_australia_7", "shanghai"),
    ("asia_australia_7", "tokyo"),
    ("asia_australia_8", "sydney"),
    ("europe_2", "istanbul"),
    ("europe_4", "london"),
    ("europe_4", "rome"),
    ("europe_5", "istanbul"),
    ("europe_8", "london"),
    ("general_5", "wilderness"),
    ("general_5", "sea"),
    ("general_11", "wilderness"),
    ("other_world_city_of_the_great_race_3", None),
    ("other_world_yuggoth_3", None),
    ("research_azathoth_sea_5", None),
    ("research_cthulhu_sea_1", None),
    ("research_shub_niggurath_city_8", None),
    ("research_shub_niggurath_wilderness_3", None),
    ("research_shub_niggurath_sea_6", None),
    ("research_yog_sothoth_city_1", None),
    ("research_yog_sothoth_city_2", None),
    ("research_yog_sothoth_city_8", None),
    ("research_yog_sothoth_sea_5", None),
    ("research_yog_sothoth_sea_7", None),
]


def resolve(game: Game, inv: Investigator, card_id: str, location: str | None = None) -> None:
    """Resolve the section of an encounter card that matches `location`, or the whole card."""
    edef = game.content.encounters[card_id]
    effects = edef.effects
    if location is not None:
        effects = next(s for s in edef.sections if location in (s.location, s.terrain)).effects
    tag = "other_world" if card_id.startswith("other_world") else None
    run_effects(effects, Ctx(game, inv, f"encounter:{card_id}", tag=tag))


def clue_here(game: Game, inv: Investigator) -> None:
    game.locations[inv.location].clues = [inv.location]


def holds(game: Game, inv: Investigator, asset_id: str) -> bool:
    return any(card.def_id == asset_id for card in inv.assets)


def test_accepting_the_necronomicon_gives_the_clue_the_pact_and_the_book(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    clue_here(game, inv)
    clues = inv.clues
    script.add("effect_choice", "Dark Pact")
    resolve(game, inv, "research_yog_sothoth_city_2")
    assert inv.clues == clues + 1
    assert rules.has_condition(inv, "dark_pact")
    assert holds(game, inv, "necronomicon")
    assert not game.locations[inv.location].clues


def test_refusing_the_necronomicon_discards_the_clue(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    clue_here(game, inv)
    clues = inv.clues
    script.add("effect_choice", "Refuse")
    resolve(game, inv, "research_yog_sothoth_city_2")
    assert inv.clues == clues
    assert not rules.has_condition(inv, "dark_pact")
    assert not holds(game, inv, "necronomicon")
    assert not game.locations[inv.location].clues


@pytest.mark.parametrize(("card_id", "location"), LISTED_SECTIONS)
def test_listed_section_offers_a_decision(content: Content, card_id: str, location: str | None) -> None:
    edef = content.encounters[card_id]
    effects = edef.effects
    if location is not None:
        effects = next(s for s in edef.sections if location in (s.location, s.terrain)).effects
    assert any(isinstance(e, Choice | Pay) for e in walk(effects))


def test_a_clue_cost_is_not_offered_without_a_clue(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.clues = 0
    before = inv.skill("observation")
    resolve(game, inv, "americas_1", "san_francisco")
    assert not script.asked
    assert inv.skill("observation") == before


def test_spending_the_clue_improves_the_skill(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.clues = 1
    before = inv.skill("observation")
    script.add("pay", True)
    resolve(game, inv, "americas_1", "san_francisco")
    assert inv.clues == 0
    assert inv.skill("observation") == before + 1


def test_refusing_the_clue_cost_changes_nothing(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.clues = 1
    before = inv.skill("observation")
    script.add("pay", False)
    resolve(game, inv, "americas_1", "san_francisco")
    assert inv.clues == 1
    assert inv.skill("observation") == before


def test_a_dark_pact_cost_is_not_offered_to_a_holder(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "dark_pact")
    clue_here(game, inv)
    clues = inv.clues
    resolve(game, inv, "research_yog_sothoth_city_2")
    assert not script.asked
    assert inv.clues == clues
    assert not holds(game, inv, "necronomicon")
    assert not game.locations[inv.location].clues


def test_a_delay_cost_is_not_offered_while_delayed(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.delayed = True
    before = len(inv.assets)
    resolve(game, inv, "americas_7", "arkham")
    assert not script.asked
    assert len(inv.assets) == before


def test_a_delay_cost_applies_to_an_investigator_who_ignores_delay(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.assets.append(rules.new_card(game, "pocket_watch"))
    before = len(inv.assets)
    script.add("effect_choice", "Become Delayed")
    resolve(game, inv, "americas_7", "arkham")
    assert inv.delayed
    assert len(inv.assets) == before + 2


def test_refusing_the_star_spawn_discards_the_clue_and_ambushes(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    clue_here(game, inv)
    set_dice(game, *[1] * 40)
    script.add("effect_choice", "Refuse")
    resolve(game, inv, "research_cthulhu_sea_1")
    assert not game.locations[inv.location].clues
    assert not holds(game, inv, "mists_of_relah")
    assert any("Star Spawn" in text for text in script.texts())


def test_refusing_the_goat_masks_gives_paranoia_with_no_improvement(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    clue_here(game, inv)
    before = inv.skill("strength")
    script.add("effect_choice", "Refuse")
    resolve(game, inv, "research_shub_niggurath_wilderness_3")
    assert rules.has_condition(inv, "paranoia")
    assert inv.skill("strength") == before
    assert game.locations[inv.location].clues


def test_accepting_the_goat_masks_gives_the_dark_pact(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    clue_here(game, inv)
    before = inv.skill("strength")
    script.add("effect_choice", "Dark Pact")
    resolve(game, inv, "research_shub_niggurath_wilderness_3")
    assert rules.has_condition(inv, "dark_pact")
    assert not rules.has_condition(inv, "paranoia")
    assert inv.skill("strength") == before + 1


def test_the_branding_discards_only_the_chosen_condition(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "cursed")
    rules.gain_condition(game, inv, "dark_pact")
    clue_here(game, inv)
    health = inv.health
    script.add("effect_choice", "Discard Dark Pact")
    resolve(game, inv, "research_shub_niggurath_sea_6")
    assert inv.health == health - 2
    assert rules.has_condition(inv, "cursed")
    assert not rules.has_condition(inv, "dark_pact")


def test_the_branding_gives_no_condition_and_no_prompt_without_one(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    clue_here(game, inv)
    resolve(game, inv, "research_shub_niggurath_sea_6")
    assert not script.asked
    assert not inv.conditions


def test_the_silver_key_costs_a_spell_after_a_passed_test(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    clue_here(game, inv)
    spell = rules.draw_matching(game, kind="spell")
    assert spell is not None
    rules.gain_card(game, inv, spell)
    set_dice(game, *[6] * 12)
    script.add("effect_choice", "Discard 1 Spell")
    resolve(game, inv, "research_yog_sothoth_city_1")
    assert spell not in inv.assets
    assert holds(game, inv, "silver_key")


def test_no_spell_means_no_silver_key_and_no_prompt(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    clue_here(game, inv)
    inv.assets = [c for c in inv.assets if game.asset_def(c).kind != "spell"]
    clues = inv.clues
    set_dice(game, *[6] * 12)
    resolve(game, inv, "research_yog_sothoth_city_1")
    assert inv.clues == clues + 1
    assert not holds(game, inv, "silver_key")
    assert not any(kind == "effect_choice" for kind, _ in script.asked)


def test_failing_the_lurker_test_discards_the_clue_and_curses(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    clue_here(game, inv)
    set_dice(game, *[1] * 12)
    resolve(game, inv, "research_yog_sothoth_city_8")
    assert not game.locations[inv.location].clues
    assert rules.has_condition(inv, "cursed")


def test_patching_the_rift_discards_the_chosen_gate(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    clue_here(game, inv)
    spell = rules.draw_matching(game, kind="spell")
    assert spell is not None
    rules.gain_card(game, inv, spell)
    game.locations["arkham"].gate = True
    game.locations["tokyo"].gate = True
    set_dice(game, *[6] * 12)
    script.add("effect_choice", "Discard 1 Spell").add("choose_space", "Tokyo")
    resolve(game, inv, "research_yog_sothoth_sea_7")
    assert game.locations["arkham"].gate
    assert not game.locations["tokyo"].gate


def test_general_11_discards_one_madness_condition(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "amnesia")
    rules.gain_condition(game, inv, "paranoia")
    script.add("effect_choice", "Become Delayed").add("effect_choice", "Discard Paranoia")
    resolve(game, inv, "general_11", "wilderness")
    assert rules.has_condition(inv, "amnesia")
    assert not rules.has_condition(inv, "paranoia")


def test_a_refused_other_world_clue_resolves_the_fail_effect(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.clues = 1
    health, sanity = inv.health, inv.sanity
    set_dice(game, *[1] * 12)
    script.add("pay", False)
    resolve(game, inv, "other_world_city_of_the_great_race_3")
    assert inv.clues == 1
    assert (inv.health, inv.sanity) == (health - 1, sanity - 1)


def test_a_spent_other_world_clue_resolves_the_pass_effect(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.clues = 1
    game.locations[inv.location].gate = True
    set_dice(game, *[6] * 12)
    script.add("pay", True)
    resolve(game, inv, "other_world_yuggoth_3")
    assert inv.clues == 0
    assert not game.locations[inv.location].gate


def test_the_constable_gives_a_weapon(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.assets.clear()
    script.add("effect_choice", "Become Delayed")
    resolve(game, inv, "asia_australia_8", "sydney")
    assert ["weapon" in game.asset_def(card).traits for card in inv.assets] == [True]
