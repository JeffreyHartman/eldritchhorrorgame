"""Tests that resolve real cards through `run_effects`, one for each kind of fix from the issue 2 audit."""

from __future__ import annotations

import pytest

from conftest import MakeGame, Script, clue_here, first, holds, resolve, set_dice
from pursuit.effects.base import Ctx, run_effects
from pursuit.engine import rules
from pursuit.engine.state import Game, Investigator


def only_monster(game: Game, def_id: str) -> None:
    game.monster_cup[:] = [def_id]


def condition_ids(inv: Investigator) -> set[str]:
    return {c.def_id for c in inv.conditions}


def test_defeating_the_cultist_gains_the_clue_and_no_amnesia(make_game: MakeGame) -> None:
    game = make_game("cthulhu")
    inv = first(game)
    clue_here(game, inv)
    set_dice(game, *[6] * 20)
    resolve(game, inv, "research_cthulhu_city_7")
    assert inv.clues == 1
    assert not rules.has_condition(inv, "amnesia")
    assert not game.locations[inv.location].clues


def test_failing_to_defeat_the_cultist_moves_the_clue_and_gives_amnesia(make_game: MakeGame) -> None:
    game = make_game("cthulhu")
    inv = first(game)
    inv.location = "arkham"
    clue_here(game, inv)
    set_dice(game, *[1] * 20)
    resolve(game, inv, "research_cthulhu_city_7")
    assert inv.clues == 0
    assert rules.has_condition(inv, "amnesia")
    assert not game.locations["arkham"].clues
    spaces = [loc for loc, st in game.locations.items() if st.clues]
    assert [game.content.locations[loc].terrain for loc in spaces] == ["sea"]


def test_the_ruby_comes_only_from_defeating_the_deep_one(make_game: MakeGame) -> None:
    game = make_game("azathoth")
    inv = first(game)
    clue_here(game, inv)
    only_monster(game, "deep_one")
    set_dice(game, *[1] * 20)
    resolve(game, inv, "research_cthulhu_sea_8")
    assert inv.clues == 1
    assert not holds(inv, "ruby_of_rlyeh")


def test_star_spawn_retreats_doom_only_when_defeated(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    only_monster(game, "star_spawn")
    doom = game.doom
    set_dice(game, *[1] * 30)
    resolve(game, inv, "research_cthulhu_sea_5")
    assert game.doom == doom


def test_passing_the_deep_one_hybrids_test_costs_nothing(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    clue_here(game, inv)
    health = inv.health
    set_dice(game, *[6] * 12)
    resolve(game, inv, "research_cthulhu_city_8")
    assert inv.clues == 1 and inv.health == health
    assert not rules.has_condition(inv, "detained")


def test_failing_the_deep_one_hybrids_test_hurts_and_detains(make_game: MakeGame) -> None:
    game = make_game("azathoth", ("akachi_onyele", "mark_harrigan"))
    inv = first(game)
    health = inv.health
    set_dice(game, *[1] * 12)
    resolve(game, inv, "research_cthulhu_city_8")
    assert inv.health == health - 1
    assert rules.has_condition(inv, "detained")


def test_passing_order_of_the_deaths_head_does_not_advance_doom(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    clue_here(game, inv)
    doom = game.doom
    set_dice(game, *[6] * 12)
    resolve(game, inv, "research_shub_niggurath_city_1")
    assert game.doom == doom and inv.clues == 1


def test_failing_order_of_the_deaths_head_advances_doom(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    doom = game.doom
    set_dice(game, *[1] * 12)
    resolve(game, inv, "research_shub_niggurath_city_1")
    assert game.doom == doom - 1


def test_or_rewards_give_only_the_chosen_one(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    before = inv.skill("lore")
    set_dice(game, *[6] * 12)
    script.add("effect_choice", "Improve Lore")
    resolve(game, inv, "general_2", "wilderness")
    assert inv.clues == 0 and inv.skill("lore") == before + 1


def test_reserve_or_deck_text_offers_both(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    held = len(inv.assets)
    item = rules.draw_matching(game, kind="item")
    assert item is not None
    game.reserve.append(item)
    set_dice(game, *[6] * 12)
    script.add("gain_source", "Draw from the deck")
    resolve(game, inv, "general_1", "city")
    assert len(inv.assets) == held + 1
    assert ("gain_source", "Gain asset from where?") in script.asked


def test_weapon_rewards_can_be_a_trinket_weapon(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    inv.assets.clear()
    game.asset_deck.cards = [c for c in game.asset_deck.cards if c.def_id == "derringer_18"]
    set_dice(game, *[6] * 12)
    resolve(game, inv, "general_5", "city")
    assert holds(inv, "derringer_18")


def test_a_named_spell_trait_is_gained_before_the_test(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    inv.assets.clear()
    set_dice(game, *[6] * 12)
    resolve(game, inv, "americas_1", "arkham")
    assert ["incantation" in game.asset_def(c).traits for c in inv.assets] == [True]


def test_the_potion_is_optional(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    improvements = dict(inv.improvements)
    script.add("effect_choice", "Refuse")
    resolve(game, inv, "europe_7", "rome")
    assert inv.improvements == improvements
    assert not rules.has_condition(inv, "cursed")


def test_a_spell_lets_you_keep_the_clue_on_the_foggy_sea(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    clue_here(game, inv)
    spell = rules.draw_matching(game, kind="spell")
    assert spell is not None
    rules.gain_card(game, inv, spell)
    set_dice(game, *[1] * 12)
    script.add("effect_choice", "Discard 1 Spell")
    resolve(game, inv, "research_yog_sothoth_sea_1")
    assert spell not in inv.assets
    assert game.locations[inv.location].clues


def test_no_spell_discards_the_clue_on_the_foggy_sea(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    clue_here(game, inv)
    inv.assets = [c for c in inv.assets if game.asset_def(c).kind != "spell"]
    set_dice(game, *[1] * 12)
    resolve(game, inv, "research_yog_sothoth_sea_1")
    assert not game.locations[inv.location].clues


def test_the_mi_go_test_needs_a_spell(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    clue_here(game, inv)
    inv.assets = [c for c in inv.assets if game.asset_def(c).kind != "spell"]
    set_dice(game)
    resolve(game, inv, "research_yog_sothoth_wilderness_2")
    assert inv.clues == 1


def test_the_dragged_ship_moves_toward_the_gate_then_costs_sanity(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    inv.location = "arkham"
    clue_here(game, inv)
    game.locations["tokyo"].gate = True
    before = rules.distances(game, "tokyo")["arkham"]
    resolve(game, inv, "research_yog_sothoth_sea_8")
    assert inv.clues == 1
    assert rules.distances(game, "tokyo")[inv.location] == before - 1
    assert inv.sanity == inv.max_sanity - 2


@pytest.mark.parametrize("paid", [True, False])
def test_clues_close_the_gate_or_delay_you(make_game: MakeGame, script: Script, paid: bool) -> None:
    game = make_game("azathoth", ("akachi_onyele", "mark_harrigan"))
    inv = first(game)
    inv.clues = 2
    game.locations[inv.location].gate = True
    set_dice(game, *[6] * 12)
    script.add("pay", paid)
    resolve(game, inv, "other_world_lost_carcosa_4")
    assert game.locations[inv.location].gate != paid
    assert inv.delayed != paid


def test_a_clue_stops_the_sanity_loss_at_yuggoth(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.clues = 1
    set_dice(game, *[1] * 12)
    script.add("pay", True)
    resolve(game, inv, "other_world_yuggoth_1")
    assert inv.clues == 0 and inv.sanity == inv.max_sanity


def test_the_dreamlands_rolls_a_die_for_each_clue(make_game: MakeGame) -> None:
    game = make_game("azathoth", ("akachi_onyele", "mark_harrigan"))
    inv = first(game)
    inv.clues = 2
    # Will-1 plus 2 Clues rolls Will + 1 dice. Only the last one succeeds.
    set_dice(game, *[1] * inv.skill("will"), 6, *[1] * 12)
    resolve(game, inv, "other_world_the_dreamlands_1")
    assert not rules.has_condition(inv, "hallucinations")


def test_himalayas_ambush_leaves_the_monster_unless_you_escape(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    inv.location = "the_himalayas"
    only_monster(game, "ghoul")
    doom = game.doom
    dice = [1] * 8
    set_dice(game, *dice, *[6] * 8)
    resolve(game, inv, "expedition_the_himalayas_1")
    assert game.doom == doom + 1
    assert not game.locations["the_himalayas"].monsters


def test_the_gem_pulls_a_monster_to_you_and_you_encounter_it(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    inv.location = "tokyo"
    rules.spawn_monster(game, "arkham", "ghoul", trigger=False)
    set_dice(game, *[6] * 12)
    resolve(game, inv, "asia_australia_3", "tokyo")
    assert not game.locations["arkham"].monsters
    assert not game.locations["tokyo"].monsters


def test_gaining_a_madness_condition_adds_one(make_game: MakeGame) -> None:
    game = make_game("azathoth", ("akachi_onyele", "mark_harrigan"))
    inv = first(game)
    set_dice(game, *[1] * 12)
    resolve(game, inv, "general_7", "wilderness")
    assert inv.delayed
    assert condition_ids(inv) & {"amnesia", "paranoia", "hallucinations"}


def test_failing_rome_discards_blessed(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "blessed")
    set_dice(game, *[1] * 12)
    resolve(game, inv, "europe_3", "rome")
    assert not rules.has_condition(inv, "blessed")


def test_unwilling_servant_tests_lore(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    back = next(b for b in game.content.conditions["debt"].backs if b.text.startswith("Unwilling"))
    set_dice(game, *[1] * inv.skill("lore"))
    run_effects(back.effects, Ctx(game, inv, "condition"))
    assert rules.has_condition(inv, "amnesia")


def test_from_beyond_still_advances_doom_after_a_group_spend(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    first(game).clues = 2
    game.active_mythos.clear()
    doom = game.doom
    script.add("group_spend", True)
    run_effects(game.content.mythos["from_beyond"].effects, Ctx(game, None, "mythos"))
    assert game.doom == doom - 1


def test_the_wraith_lets_the_investigator_keep_cursed(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "cursed")
    script.add("effect_choice", "Keep it")
    run_effects(game.content.monsters["wraith"].on_defeat, Ctx(game, inv, "monster"))
    assert rules.has_condition(inv, "cursed")
