"""Regression tests for rulebook behavior in `engine`. Page numbers refer to the rulebook."""

from __future__ import annotations

import random
from collections import Counter

import pytest

from conftest import MakeGame, Script, first, kinds, set_dice
from pursuit.bots import RandomBot
from pursuit.content.defs import Cost
from pursuit.content.loader import Content
from pursuit.effects import library
from pursuit.effects.base import Ctx, run_effects
from pursuit.engine import actions, combat, dice, phases, rules
from pursuit.engine.setup import GameConfig, new_game
from pursuit.engine.state import ActiveMythos, Game, Investigator, MonsterInst, MysteryState, Phase


class FixedBack(random.Random):
    """An rng whose `choices` always takes the card back at `index`."""

    def __init__(self, index: int) -> None:
        super().__init__(0)
        self.index = index

    def choices(self, population, weights=None, *, cum_weights=None, k=1):  # type: ignore[no-untyped-def]
        return [population[self.index]]


def test_acquire_assets_offers_clue_rerolls_after_the_first_success(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.clues = 2
    script.add("reroll_extra", True)
    set_dice(game, *[6] + [1] * (inv.skill("influence") - 1), 6)
    result = dice.run_test(game, inv, "influence", contexts=("acquire",), open_ended=True)
    assert result.successes == 2 and inv.clues == 1


def test_a_passed_closed_test_does_not_offer_clue_rerolls(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.clues = 2
    set_dice(game, *[6] + [1] * (inv.skill("lore") - 1))
    dice.run_test(game, inv, "lore")
    assert not [kind for kind, _ in script.asked if kind.startswith("reroll")]


def test_damage_reduction_applies_before_successes(make_game: MakeGame) -> None:
    game = make_game(investigators=("silas_marsh", "lily_chen"))
    inv = first(game)
    monster = rules.spawn_monster(game, inv.location, "hound_of_tindalos")
    assert monster is not None
    health = inv.health
    will, strength = inv.skill("will"), inv.skill("strength") - 1
    set_dice(game, *[1] * will, 6, 6, *[1] * (strength - 2))
    combat.combat(game, inv, monster)
    assert inv.health == health


def test_silas_gets_three_actions_when_his_action_comes_first(make_game: MakeGame) -> None:
    game = make_game(investigators=("silas_marsh", "lily_chen"))
    inv = first(game)
    actions.perform(game, inv, ("ability",))
    assert actions.actions_left(game, inv) == 2


def test_silas_cannot_repeat_an_action_with_his_additional_action(make_game: MakeGame) -> None:
    game = make_game(investigators=("silas_marsh", "lily_chen"))
    inv = first(game)
    actions.perform(game, inv, ("rest",))
    actions.perform(game, inv, ("ability",))
    rest = next(o for o in actions.action_options(game, inv) if o.label == "Rest")
    assert actions.actions_left(game, inv) == 1 and not rest.enabled


def test_charlie_kane_grants_an_immediate_action_to_another_investigator(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("charlie_kane", "lily_chen"))
    charlie, lily = game.investigators
    script.add("action", "Rest")
    actions.perform(game, charlie, ("ability",))
    assert lily.actions_taken == ["rest"] and actions.actions_left(game, lily) == 2


def test_an_ongoing_card_is_not_in_play_during_its_own_reckoning_step(make_game: MakeGame) -> None:
    game = make_game()
    game.phase = Phase.MYTHOS
    game.mythos_deck.insert(0, "driven_to_bankruptcy")
    phases.mythos_phase(game)
    assert [a.def_id for a in game.active_mythos] == ["driven_to_bankruptcy"]


def test_a_defeat_that_causes_the_awakening_still_gets_a_replacement(make_game: MakeGame) -> None:
    game = make_game(old_one="yog_sothoth", investigators=("silas_marsh",))
    game.doom = 1
    old = first(game)
    rules.change_health(game, old, -99)
    rules.process_defeats(game)
    assert game.awakened and game.outcome is None and not old.eliminated
    rules.replace_defeated_investigators(game)
    assert first(game).def_id != "silas_marsh" and not first(game).defeated


def test_a_defeat_after_the_awakening_eliminates_the_investigator(make_game: MakeGame) -> None:
    game = make_game(old_one="yog_sothoth", investigators=("silas_marsh", "lily_chen"))
    game.doom = 1
    rules.advance_doom(game, 1)
    inv = first(game)
    rules.change_health(game, inv, -99)
    rules.process_defeats(game)
    assert inv.eliminated


def test_research_encounters_use_the_terrain_of_the_space(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.location = "space_3"
    phases._draw_and_run_encounter(game, inv, "research_azathoth")
    drawn = next(e for e in script.events if e.kind == "encounter").data["encounter"]
    assert game.content.encounters[drawn].terrain == "sea"


def test_expedition_spaces_offer_no_location_deck(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.location = "the_amazon"
    labels: list[str] = []

    def spy(options: list) -> int:
        labels.extend(o.label for o in options)
        return 0

    script.add("encounter", spy)
    phases.encounter_turn(game, inv)
    assert not [label for label in labels if "Americas" in label]


def test_becoming_delayed_ends_the_action_turn(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)

    def delay_me(options: list) -> int:
        inv.delayed = True
        return next(i for i, o in enumerate(options) if o.value == ("rest",))

    script.add("action", delay_me)
    phases.action_turn(game, inv)
    assert len(inv.actions_taken) == 1


def test_mysteries_solve_only_at_the_end_of_the_mythos_phase(make_game: MakeGame) -> None:
    game = make_game()
    mys = game.active_mystery
    assert mys is not None
    rules.add_mystery_progress(game, mys, mys.required)
    assert not mys.done
    game.phase = Phase.MYTHOS
    phases.mythos_phase(game)
    assert mys.done and game.active_mystery is not mys




def put(game: Game, inv: Investigator, monster_id: str) -> MonsterInst:
    monster = rules.spawn_monster(game, inv.location, monster_id, trigger=False)
    assert monster is not None
    return monster


def fail_dice(game: Game) -> None:
    game.roll = lambda: 1


def test_ghoul_gives_paranoia_when_health_is_lost(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    fail_dice(game)
    combat.combat(game, inv, put(game, inv, "ghoul"))
    assert rules.has_condition(inv, "paranoia")


def test_vampire_stops_combat_on_a_failed_will_test(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    fail_dice(game)
    health = inv.health
    combat.combat(game, inv, put(game, inv, "vampire"))
    assert inv.health == health


def test_witch_curses_on_a_failed_will_test(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    fail_dice(game)
    combat.combat(game, inv, put(game, inv, "witch"))
    assert rules.has_condition(inv, "cursed")


def test_ghost_loses_health_from_will_successes(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    game.roll = lambda: 6
    ghost = put(game, inv, "ghost")
    assert combat.combat(game, inv, ghost) == combat.DEFEATED


def test_tick_tock_men_forbid_clue_rerolls(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.clues = 3
    fail_dice(game)
    combat.combat(game, inv, put(game, inv, "tick_tock_men"))
    assert inv.clues == 3 and not [k for k, _ in script.asked if k == "reroll"]


def test_gug_defeat_blocks_the_additional_encounter(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    put(game, inv, "gug").wounds = 3
    game.roll = lambda: 6
    assert combat.resolve_monsters(game, inv, encounter_phase=True) is False


def test_shub_niggurath_cannot_lose_health_before_three_mysteries(make_game: MakeGame) -> None:
    game = make_game(old_one="shub_niggurath")
    inv = first(game)
    shub = put(game, inv, "shub_niggurath_epic")
    assert rules.wound_monster(game, inv, shub, 3) is False and shub.wounds == 0
    game.solved_mysteries = ["a", "b", "c"]
    rules.wound_monster(game, inv, shub, 3)
    assert shub.wounds == 3


def test_a_spawn_effect_moves_the_monster_but_an_ambush_ignores_it(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    mummy = rules.spawn_monster(game, "arkham", "mummy")
    assert mummy is not None and rules.monster_location(game, mummy) == "the_pyramids"
    game.locations["the_pyramids"].monsters.remove(mummy)
    game.monster_cup.append("mummy")
    game.roll = lambda: 1
    combat.ambush(game, inv, "mummy")
    assert "mummy" in game.monster_cup and not game.locations[inv.location].monsters


def test_reckoning_effects_apply_only_to_their_own_monster(make_game: MakeGame) -> None:
    game = make_game()
    shoggoth = rules.spawn_monster(game, "arkham", "shoggoth")
    zombie = rules.spawn_monster(game, "london", "lloigor")
    assert shoggoth is not None and zombie is not None
    shoggoth.wounds = zombie.wounds = 2
    rules.resolve_reckoning(game)
    assert shoggoth.wounds == 0 and zombie.wounds == 2


def test_deep_one_reckoning_affects_only_its_space(make_game: MakeGame) -> None:
    game = make_game(old_one="yog_sothoth")
    a, b = game.investigators
    a.location, b.location = "arkham", "london"
    game.set_aside.append("deep_one")
    put(game, a, "deep_one")
    sanity_a, sanity_b = a.sanity, b.sanity
    rules.resolve_reckoning(game)
    assert a.sanity == sanity_a - 1 and b.sanity == sanity_b


def test_epic_monsters_cannot_be_discarded_or_moved(make_game: MakeGame) -> None:
    game = make_game()
    epic = rules.spawn_monster(game, "arkham", "wind_walker")
    assert epic is not None
    rules.discard_monster(game, "arkham", epic)
    rules.move_monster(game, epic, "london")
    rules.move_monsters(game)
    assert rules.monster_location(game, epic) == "arkham"


def test_a_defeated_epic_monster_does_not_return(make_game: MakeGame) -> None:
    game = make_game()
    epic = rules.spawn_monster(game, "arkham", "zombie_horde")
    assert epic is not None
    rules.defeat_monster(game, None, "arkham", epic)
    assert rules.spawn_monster(game, "arkham", "zombie_horde") is None


def test_awakened_cultist_uses_the_back_of_the_sheet(make_game: MakeGame) -> None:
    game = make_game(old_one="cthulhu")
    assert rules.toughness(game, "cultist") == 1
    game.awakened = True
    assert rules.toughness(game, "cultist") == 2


def test_set_aside_monsters_are_not_in_the_cup(make_game: MakeGame) -> None:
    game = make_game(old_one="shub_niggurath", clean=False)
    assert sorted(game.set_aside) == ["dark_young", "ghoul", "ghoul", "goat_spawn", "goat_spawn"]
    assert not {"dark_young", "ghoul", "goat_spawn"} & set(game.monster_cup)


def set_mystery(game: Game, def_id: str) -> MysteryState:
    mdef = next(m for m in game.old_one.mysteries if m.id == def_id)
    game.active_mystery = MysteryState(def_id, mdef.required(len(game.investigators)))
    run_effects(mdef.on_enter, Ctx(game, None, "test"))
    return game.active_mystery


def test_omen_of_devastation_needs_a_gate_that_matches_the_omen(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    mys = set_mystery(game, "az_omen_of_devastation")
    inv = first(game)
    inv.clues = 2
    game.omen_index = 0
    game.locations["arkham"].gate = True
    rules.close_gate(game, inv, "arkham")
    assert mys.progress == 0
    game.locations["san_francisco"].gate = True
    script.add("mystery_spend", True)
    rules.close_gate(game, inv, "san_francisco")
    assert mys.progress == 1 and inv.clues == 1


def test_where_the_old_ones_broke_through_removes_the_gate_from_the_game(make_game: MakeGame, script: Script) -> None:
    game = make_game(old_one="yog_sothoth")
    mys = set_mystery(game, "ys_where_the_old_ones_broke_through")
    inv = first(game)
    inv.assets += [rules.new_card(game, "blessing_of_isis"), rules.new_card(game, "blessing_of_isis")]
    game.locations["arkham"].gate = True
    game.gate_deck.discards.clear()
    script.add("mystery_spend", True)
    rules.close_gate(game, inv, "arkham")
    assert mys.progress == 1 and not game.gate_deck.discards
    assert not [c for c in inv.assets if c.def_id == "blessing_of_isis"]


def test_research_mystery_takes_a_clue_gained_from_the_encounter(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    mys = set_mystery(game, "az_occult_research")
    inv = first(game)
    game.locations[inv.location].clue = True
    game.roll = lambda: 6
    script.add("encounter", "Research").add("mystery_spend", True)
    phases.encounter_turn(game, inv)
    assert mys.progress == 1


def test_the_true_name_places_tokens_and_spends_them(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    mys = set_mystery(game, "az_the_true_name")
    inv = first(game)
    spaces = [loc for loc, st in game.locations.items() if st.eldritch]
    assert sum(game.locations[loc].eldritch for loc in spaces) == 1
    inv.location = spaces[0]
    inv.clues = 2
    script.add("encounter", "Mystery").add("mystery_spend", True)
    phases.encounter_turn(game, inv)
    assert mys.progress == 1 and game.locations[spaces[0]].eldritch == 0 and inv.clues == 0


def test_hunting_the_thousand_counts_toughness_and_keeps_the_monster(make_game: MakeGame, script: Script) -> None:
    game = make_game(old_one="shub_niggurath")
    mys = set_mystery(game, "sn_hunting_the_thousand")
    inv = first(game)
    inv.clues = 2
    lloigor = rules.spawn_monster(game, "arkham", "lloigor")
    assert lloigor is not None
    script.add("mystery_spend", True)
    rules.defeat_monster(game, inv, "arkham", lloigor)
    assert mys.progress == 4 and "lloigor" not in game.monster_cup


def test_deep_ones_attack_needs_the_ambush_won(make_game: MakeGame, script: Script) -> None:
    game = make_game(old_one="cthulhu")
    mys = set_mystery(game, "cth_the_deep_ones_attack")
    inv = first(game)
    loc = next(loc for loc, st in game.locations.items() if st.eldritch)
    inv.location = loc
    inv.clues = 1
    game.roll = lambda: 6
    script.add("encounter", "Mystery").add("mystery_spend", True)
    phases.encounter_turn(game, inv)
    assert mys.progress == 1 and game.locations[loc].eldritch == 0


def test_rlyeh_risen_uses_special_encounters(make_game: MakeGame, script: Script) -> None:
    game = make_game(old_one="cthulhu")
    mys = set_mystery(game, "cth_ryleh_risen")
    inv = first(game)
    inv.location = "space_3"
    game.roll = lambda: 6
    script.add("encounter", "Mystery")
    phases.encounter_turn(game, inv)
    assert mys.progress == 1


def test_moving_onto_an_eldritch_token_delays_under_cthulhu(make_game: MakeGame) -> None:
    game = make_game(old_one="cthulhu", investigators=("silas_marsh", "akachi_onyele"))
    inv = first(game)
    game.locations["space_2"].eldritch = 1
    sanity = inv.sanity
    rules.move_investigator(game, inv, "space_2")
    assert inv.delayed and inv.sanity == sanity - 1


def test_cthulhu_reckoning_places_a_token_on_an_empty_sea_space(make_game: MakeGame) -> None:
    game = make_game(old_one="cthulhu")
    first(game).location = "space_2"
    rules.resolve_reckoning(game)
    assert game.locations["space_2"].eldritch == 1


def test_shub_niggurath_reckoning_spawns_and_advances_doom_at_ten_monsters(make_game: MakeGame) -> None:
    game = make_game(old_one="shub_niggurath")
    game.monster_cup = ["nightgaunt"] * 12
    for _ in range(9):
        rules.spawn_monster(game, "arkham")
    doom = game.doom
    rules.resolve_reckoning(game)
    assert game.doom == doom - 2


def test_shub_niggurath_awakening_gathers_her_young_and_loses_at_six(make_game: MakeGame) -> None:
    game = make_game(old_one="shub_niggurath")
    game.set_aside.append("ghoul")
    ghoul = rules.spawn_monster(game, "london", "ghoul")
    assert ghoul is not None
    game.monster_cup = ["nightgaunt"] * 8
    rules.advance_doom(game, game.doom)
    heart = game.locations["the_heart_of_africa"].monsters
    assert {m.def_id for m in heart} == {"shub_niggurath_epic", "ghoul"}
    for _ in range(4):
        rules.advance_doom(game, 1)
    assert len(heart) == 6 and game.outcome == "loss"


def test_yog_sothoth_awakened_doom_places_gates_on_the_sheet(make_game: MakeGame) -> None:
    game = make_game(old_one="yog_sothoth")
    rules.advance_doom(game, game.doom)
    game.locations["arkham"].gate = True
    game.omen_index = 1
    rules.advance_omen(game, 1)
    assert game.omen_color == "red" and game.sheet_tokens == 1 and not game.locations["arkham"].gate
    rules.advance_doom(game, 2)
    assert game.sheet_tokens == 3 and game.outcome == "loss"


def test_yog_sothoth_final_mystery_needs_three_solved_mysteries(make_game: MakeGame) -> None:
    game = make_game(old_one="yog_sothoth")
    rules.advance_doom(game, game.doom)
    inv = first(game)
    game.locations[inv.location].gate = True
    assert game.final_mystery is not None
    assert not phases._mystery_encounter_open(game, inv, game.final_mystery)
    game.solved_mysteries = ["a", "b", "c"]
    assert phases._mystery_encounter_open(game, inv, game.final_mystery)


def test_cthulhu_awakened_reckoning_scales_with_sheet_sanity(make_game: MakeGame) -> None:
    game = make_game(old_one="cthulhu")
    rules.advance_doom(game, game.doom)
    rules.advance_doom(game, 2)
    inv = first(game)
    sanity = inv.sanity
    rules.resolve_reckoning(game)
    assert game.sheet_tokens == 2 and inv.sanity == sanity - 2


def test_key_and_gate_clue_bonus_adds_successes(make_game: MakeGame, script: Script) -> None:
    game = make_game(old_one="yog_sothoth")
    rules.advance_doom(game, game.doom)
    mys = game.final_mystery
    assert mys is not None
    game.solved_mysteries = ["a", "b", "c"]
    game.active_mystery = None
    inv = first(game)
    inv.clues = 3
    game.roll = lambda: 1
    effect = library.Test("influence", 0, 3, "encounter", (library.MysteryProgress(1),), (), (), True, False, None)
    script.add("reroll", False)
    for _ in range(3):
        script.add("spend_for_test", True)
    effect.apply(Ctx(game, inv, "test"))
    assert mys.progress == 1 and inv.clues == 0


def give(game: Game, inv: Investigator, asset_id: str) -> None:
    inv.assets.append(rules.new_card(game, asset_id))


def active(game: Game, mythos_id: str) -> ActiveMythos:
    card = ActiveMythos(mythos_id, game.content.mythos[mythos_id].eldritch, game.content.mythos[mythos_id].rumor_space)
    game.active_mythos.append(card)
    return card


def test_component_counts_match_the_rulebook(content: Content) -> None:
    def total(kinds: tuple[str, ...]) -> int:
        return sum(a.count for a in content.assets.values() if a.kind in kinds and a.id != "bank_loan")

    colors = Counter(m.color for m in content.mythos.values())
    assert total(("item", "ally", "service", "trinket")) == 40
    assert total(("spell",)) == 20
    assert total(("artifact",)) == 14
    assert colors == {"green": 18, "yellow": 21, "blue": 12}
    assert len(content.decks["other_world"]) == 24


def test_the_nine_core_gates_have_the_wiki_colors(content: Content) -> None:
    gates = {loc.id: loc.gate_color for loc in content.locations.values() if loc.gate_color}
    assert gates == {
        "san_francisco": "green",
        "istanbul": "green",
        "arkham": "red",
        "rome": "red",
        "shanghai": "red",
        "sydney": "red",
        "buenos_aires": "blue",
        "london": "blue",
        "tokyo": "blue",
    }


@pytest.mark.parametrize(("difficulty", "absent"), [("easy", "hard"), ("hard", "easy")])
def test_difficulty_removes_mythos_cards_and_keeps_doom(make_game: MakeGame, difficulty: str, absent: str) -> None:
    game = make_game(difficulty=difficulty)
    assert game.doom == game.old_one.doom
    assert all(game.content.mythos[m].difficulty != absent for m in game.mythos_deck)


def test_a_solo_game_removes_teamwork_cards(make_game: MakeGame) -> None:
    game = make_game(investigators=("mark_harrigan",))
    assert not [c for c in game.asset_deck.cards if "teamwork" in game.asset_def(c).traits]


def test_no_gate_can_spawn_advances_doom_by_one(make_game: MakeGame) -> None:
    game = make_game()
    game.gate_deck.cards, game.gate_deck.discards = [], []
    doom = game.doom
    assert rules.spawn_gate(game) is None
    assert game.doom == doom - 1


def test_a_second_blessed_flips_the_card_and_keeps_it(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    game.rng = FixedBack(2)
    rules.gain_condition(game, inv, "blessed")
    rules.gain_condition(game, inv, "blessed")
    assert inv.clues == 2 and rules.has_condition(inv, "blessed")


def test_a_second_cursed_flips_the_card(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    game.rng = FixedBack(1)
    rules.gain_condition(game, inv, "cursed")
    rules.gain_condition(game, inv, "cursed")
    assert not rules.has_condition(inv, "cursed")


def test_the_rest_roll_discards_an_injury_on_a_five(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "leg_injury")
    set_dice(game, 5)
    actions.perform(game, inv, ("rest",))
    assert not rules.has_condition(inv, "leg_injury")


def test_the_rest_roll_keeps_a_madness_on_a_four(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "amnesia")
    set_dice(game, 4)
    actions.perform(game, inv, ("rest",))
    assert rules.has_condition(inv, "amnesia")


def test_detained_blocks_every_action_except_its_own(make_game: MakeGame) -> None:
    game = make_game(investigators=("silas_marsh", "akachi_onyele"))
    inv = first(game)
    rules.gain_condition(game, inv, "detained")
    assert kinds(actions.action_options(game, inv)) == ["condition", "end"]


def test_detained_stops_movement_from_any_effect(make_game: MakeGame) -> None:
    game = make_game(investigators=("silas_marsh", "akachi_onyele"))
    inv = first(game)
    rules.gain_condition(game, inv, "detained")
    start = inv.location
    rules.move_investigator(game, inv, "arkham" if start != "arkham" else "london")
    assert inv.location == start


def test_detained_replaces_the_encounter_even_with_a_monster(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("silas_marsh", "akachi_onyele"))
    inv = first(game)
    inv.clues = 1
    rules.spawn_monster(game, inv.location, "ghost", trigger=False)
    rules.gain_condition(game, inv, "detained")
    script.add("pay", True)
    phases.encounter_turn(game, inv)
    assert not rules.has_condition(inv, "detained") and inv.clues == 0
    assert not [e for e in script.events if e.kind == "combat"]


def test_delayed_on_your_own_turn_loses_actions_instead(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    give(game, inv, "dynamite")
    run = actions.perform

    def perform_and_delay(game: Game, who: Investigator, value: tuple) -> None:
        run(game, who, value)
        who.delayed = True

    script.add("action", "Rest")
    actions.perform = perform_and_delay  # type: ignore[assignment]
    phases.action_turn(game, inv)
    actions.perform = run  # type: ignore[assignment]
    assert not inv.delayed and inv.actions_taken == ["rest"]


def test_pocket_watch_stops_forced_delay_but_not_a_chosen_one(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    give(game, inv, "pocket_watch")
    rules.delay(game, inv)
    assert not inv.delayed
    rules.delay(game, inv, chosen=True)
    assert inv.delayed


def test_silas_marsh_has_eight_health_and_four_sanity(make_game: MakeGame) -> None:
    silas = first(make_game(investigators=("silas_marsh", "lily_chen")))
    assert (silas.max_health, silas.max_sanity) == (8, 4)


def test_lily_chen_moves_any_number_of_points(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("lily_chen", "mark_harrigan"))
    lily = first(game)
    lily.sanity = 2
    script.add("effect_choice", "Spend Health").add("amount", "3")
    actions.perform(game, lily, ("ability",))
    assert (lily.health, lily.sanity) == (3, 5)


def test_arcane_tome_tests_lore_with_no_penalty_and_has_no_action(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("diana_stanley", "mark_harrigan"))
    inv = first(game)
    give(game, inv, "arcane_tome")
    assert game.content.assets["arcane_tome"].action is None
    spells = sum(game.asset_def(c).kind == "spell" for c in inv.assets)
    script.add("rest_card", True)
    set_dice(game, *[6] * inv.skill("lore"))
    actions.perform(game, inv, ("rest",))
    assert sum(game.asset_def(c).kind == "spell" for c in inv.assets) == spells + 1


def test_the_axe_lets_the_player_choose_the_dice(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    give(game, inv, "axe")
    inv.clues = 0
    pool = dice.dice_pool(game, inv, "strength", 0, ("combat", "fight"))
    script.add("reroll_card", True).add("reroll_dice", "showing 4").add("reroll_dice", "Roll the chosen")
    set_dice(game, 4, *[1] * (pool - 1), 6)
    result = dice.run_test(game, inv, "strength", contexts=("combat", "fight"))
    assert result.successes == 1 and sorted(result.rolls)[-1] == 6 and 4 not in result.rolls


def test_a_six_counts_twice_with_the_shotgun(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    give(game, inv, "double_barreled_shotgun")
    pool = dice.dice_pool(game, inv, "strength", 0, ("combat", "fight"))
    set_dice(game, 6, *[1] * (pool - 1))
    assert dice.run_test(game, inv, "strength", contexts=("combat", "fight")).successes == 2


def test_the_derringer_adds_one_to_a_die(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    give(game, inv, "derringer_18")
    script.add("reroll_card", True)
    pool = dice.dice_pool(game, inv, "strength", 0, ("combat", "fight"))
    set_dice(game, 4, *[1] * (pool - 1))
    assert dice.run_test(game, inv, "strength", contexts=("combat", "fight")).successes == 1


def test_kerosene_is_discarded_for_five_strength(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    card = next(c for c in inv.assets if c.def_id == "kerosene")
    base = dice.dice_pool(game, inv, "strength", 0, ("combat", "fight"))
    revolver = 2
    script.add("boost", True)
    set_dice(game, *[1] * (base - revolver + 5))
    result = dice.run_test(game, inv, "strength", contexts=("combat", "fight"))
    assert result.pool == base - revolver + 5 and card not in inv.assets


def test_holy_water_lasts_for_both_tests_of_one_combat(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    give(game, inv, "holy_water")
    game.monster_cup.append("ghost")
    monster = rules.spawn_monster(game, inv.location, "ghost", trigger=False)
    assert monster is not None
    script.add("boost", True)
    game.roll = lambda: 6
    combat.combat(game, inv, monster)
    rolled = [e.data["rolls"] for e in script.events if e.kind == "dice"]
    assert len(rolled[0]) == inv.skill("will") + 5 + game.monster_def("ghost").horror_mod
    assert not game.boosts


def test_bandages_prevent_health_loss_for_an_investigator_on_the_space(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    a, b = game.investigators
    b.location = a.location
    give(game, b, "bandages")
    script.add("prevent", True)
    health = a.health
    rules.change_health(game, a, -3)
    assert a.health == health - 1 and not b.assets[1:] and "bandages" not in [c.def_id for c in b.assets]


def test_prevention_does_not_apply_to_spent_health(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    give(game, inv, "bandages")
    rules.change_health(game, inv, -1, preventable=False)
    assert not [kind for kind, _ in script.asked if kind == "prevent"]


def test_flute_defeats_monsters_but_not_epic_monsters(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    give(game, inv, "flute_of_the_outer_gods")
    rules.spawn_monster(game, inv.location, "ghost", trigger=False)
    rules.spawn_monster(game, inv.location, "wind_walker", trigger=False)
    health = inv.health
    actions.perform(game, inv, ("asset", inv.assets[-1].uid))
    left = [m.def_id for m in game.locations[inv.location].monsters]
    assert left == ["wind_walker"] and inv.health == health - 2


def test_ruby_grants_an_action_without_using_one(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    give(game, inv, "ruby_of_rlyeh")
    before = actions.actions_left(game, inv)
    actions.perform(game, inv, ("asset", inv.assets[-1].uid))
    assert actions.actions_left(game, inv) == before + 1


def test_silver_key_pays_one_less_clue(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    give(game, inv, "silver_key")
    inv.clues = 1
    assert rules.can_pay(game, inv, Cost(clues=2))
    rules.pay_cost(game, inv, Cost(clues=2))
    assert inv.clues == 0 and inv.assets[-1].exhausted


def test_pallid_mask_lets_an_investigator_skip_the_monster(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    give(game, inv, "pallid_mask_artifact")
    rules.spawn_monster(game, inv.location, "ghost", trigger=False)
    script.add("ignore_monsters", True)
    phases.encounter_turn(game, inv)
    assert not [e for e in script.events if e.kind == "combat"]


def test_gate_box_adds_a_die_and_a_clue_in_an_other_world(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    give(game, inv, "gate_box")
    assert dice.dice_pool(game, inv, "will", 0, ("encounter", "other_world")) == inv.skill("will") + 1
    game.locations[inv.location].gate = True
    library.CloseGate().apply(Ctx(game, inv, "t", tag="other_world"))
    assert inv.clues == 1


def test_buying_information_gives_clues_equal_to_the_result(make_game: MakeGame) -> None:
    game = make_game()
    lead = first(game)
    pool = dice.dice_pool(game, lead, "influence", 0, ("encounter",))
    set_dice(game, 6, 6, *[1] * (pool - 2))
    run_effects(game.content.mythos["buying_information"].effects, Ctx(game, None, "t"))
    assert lead.clues == 2


def test_patrolling_the_border_delays_on_entry(make_game: MakeGame) -> None:
    game = make_game(investigators=("silas_marsh", "akachi_onyele"))
    game.mythos_deck.insert(0, "patrolling_the_border")
    game.phase = Phase.MYTHOS
    phases.mythos_phase(game)
    assert first(game).delayed


def test_mysterious_lights_stops_a_gate_from_closing(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    game.locations[inv.location].gate = True
    active(game, "mysterious_lights")
    rules.close_gate(game, inv, inv.location)
    assert game.locations[inv.location].gate


def test_mysterious_lights_does_not_stop_a_discard(make_game: MakeGame) -> None:
    game = make_game()
    game.locations["arkham"].gate = True
    active(game, "mysterious_lights")
    assert rules.discard_gate(game, "arkham")


def test_driven_to_bankruptcy_keeps_the_reserve_empty(make_game: MakeGame) -> None:
    game = make_game()
    card = active(game, "driven_to_bankruptcy")
    run_effects(game.content.mythos["driven_to_bankruptcy"].effects, Ctx(game, None, "t", mythos=card))
    assert game.reserve == []
    rules.refill_reserve(game)
    assert game.reserve == []
    run_effects(game.content.mythos["driven_to_bankruptcy"].reckoning, Ctx(game, None, "t", mythos=card))
    assert len(game.reserve) == 4 and not game.active_mythos


def test_defeating_the_wind_walker_solves_its_rumor(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    active(game, "the_wind_walker")
    monster = rules.spawn_monster(game, inv.location, "wind_walker", trigger=False)
    assert monster is not None
    rules.defeat_monster(game, inv, inv.location, monster)
    assert not game.active_mythos


def test_the_wind_walker_deals_six_health_on_its_last_token(make_game: MakeGame) -> None:
    game = make_game(investigators=("silas_marsh", "akachi_onyele"))
    inv = first(game)
    inv.health = inv.max_health = 8
    card = active(game, "the_wind_walker")
    card.eldritch = 1
    run_effects(game.content.mythos["the_wind_walker"].reckoning, Ctx(game, None, "t", mythos=card))
    assert inv.health == 2 and inv.delayed and not game.active_mythos


def test_web_between_worlds_keeps_its_token_when_the_group_spends(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    first(game).clues = 1
    card = active(game, "web_between_worlds")
    script.add("group_spend", True)
    run_effects(game.content.mythos["web_between_worlds"].reckoning, Ctx(game, None, "t", mythos=card))
    assert card.eldritch == 3 and first(game).clues == 0


def test_web_between_worlds_loses_the_game_with_no_tokens(make_game: MakeGame) -> None:
    game = make_game()
    card = active(game, "web_between_worlds")
    card.eldritch = 1
    run_effects(game.content.mythos["web_between_worlds"].reckoning, Ctx(game, None, "t", mythos=card))
    assert game.outcome == "loss"


def test_legitimate_banking_treats_all_rolls_as_ones(make_game: MakeGame) -> None:
    game = make_game()
    lead = first(game)
    game.rng = FixedBack(2)
    rules.gain_condition(game, lead, "debt")
    health = lead.health
    run_effects(game.content.mythos["legitimate_banking"].effects, Ctx(game, None, "t"))
    assert lead.health == health - 3 and not rules.has_condition(lead, "debt")


def test_all_for_nothing_returns_a_solved_mystery_to_the_deck(make_game: MakeGame) -> None:
    game = make_game()
    solved = game.mystery_deck.pop()
    game.solved_mysteries.append(solved)
    run_effects(game.content.mythos["all_for_nothing"].effects, Ctx(game, None, "t"))
    assert game.solved_mysteries == [] and solved in game.mystery_deck


def test_the_storm_resolves_a_rumor_from_the_box_when_none_is_in_play(make_game: MakeGame) -> None:
    game = make_game()
    game.mythos_box = ["stars_aligned"]
    run_effects(game.content.mythos["the_storm"].effects, Ctx(game, None, "t"))
    assert [a.def_id for a in game.active_mythos] == ["stars_aligned"]


def test_return_of_the_ancient_ones_collects_toughness(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("mark_harrigan",))
    inv = first(game)
    inv.location = "space_19"
    inv.clues = 1
    active(game, "return_of_the_ancient_ones")
    monster = rules.spawn_monster(game, "space_19", "ghost", trigger=False)
    assert monster is not None
    script.add("pay", True)
    rules.defeat_monster(game, inv, "space_19", monster)
    assert not game.active_mythos and inv.clues == 0


def test_a_rumor_at_the_active_expedition_follows_the_token(make_game: MakeGame) -> None:
    game = make_game()
    card = active(game, "secrets_of_the_past")
    game.active_expedition = "tunguska"
    assert rules.rumor_location(game, card) == "tunguska"


def test_secrets_of_the_past_blocks_expedition_encounters(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    active(game, "secrets_of_the_past")
    game.active_expedition = inv.location
    phases.encounter_turn(game, inv)
    menu = [e for e in script.asked if e[0] == "encounter"]
    assert not any("Expedition Encounter" in text for _, text in menu)


@pytest.mark.parametrize("seed", range(3))
def test_every_mythos_card_resolves(content: Content, seed: int) -> None:
    for mythos_id, mdef in content.mythos.items():
        game = new_game(content, GameConfig("azathoth", ("mark_harrigan", "lily_chen", "diana_stanley"), seed=seed))
        game.ctl = RandomBot(seed)
        for loc in ("arkham", "london"):
            rules.spawn_gate(game, loc)
        rules.spawn_monster(game, "arkham", "cultist", trigger=False)
        for inv in game.investigators:
            inv.clues = 3
            rules.gain_condition(game, inv, "debt")
        phases.resolve_mythos(game, mdef)
        rules.process_defeats(game)
        for active_card in list(game.active_mythos):
            run_effects(
                game.content.mythos[active_card.def_id].reckoning, Ctx(game, None, "t", mythos=active_card)
            )
        assert game.mythos_deck, mythos_id


@pytest.mark.parametrize(
    ("inv_id", "health", "sanity", "strength", "will"),
    [("leo_anderson", 6, 6, 3, 3), ("mark_harrigan", 8, 4, 4, 4), ("trish_scarborough", 7, 5, 3, 2)],
)
def test_sheet_stats_match_the_wiki(
    content: Content, inv_id: str, health: int, sanity: int, strength: int, will: int
) -> None:
    sheet = content.investigators[inv_id]
    assert (sheet.health, sheet.sanity, sheet.skills["strength"], sheet.skills["will"]) == (
        health,
        sanity,
        strength,
        will,
    )


def test_a_kept_condition_shows_the_same_back_each_flip(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    game.rng = FixedBack(2)
    rules.gain_condition(game, inv, "blessed")
    game.rng = FixedBack(0)
    inst = inv.conditions[0]
    rules.flip_condition(game, inv, inst)
    rules.flip_condition(game, inv, inst)
    assert inv.clues == 4


def test_akachi_moves_only_after_an_other_world_close(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("akachi_onyele", "mark_harrigan"))
    inv = first(game)
    start = inv.location
    game.locations[start].gate = True
    game.locations["arkham"].gate = True
    rules.close_gate(game, inv, start)
    assert inv.location == start
    game.locations[start].gate = True
    script.add("move", "Arkham")
    library.CloseGate().apply(Ctx(game, inv, "t", tag="other_world"))
    assert inv.location == "arkham"


def test_charlie_cannot_give_an_action_to_a_delayed_investigator(make_game: MakeGame) -> None:
    game = make_game(investigators=("charlie_kane", "lily_chen"))
    charlie, lily = game.investigators
    lily.delayed = True
    ability = next(o for o in actions.action_options(game, charlie) if o.value == ("ability",))
    assert not ability.enabled


def test_diana_discards_all_monsters_with_a_cultist_here(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("diana_stanley", "mark_harrigan"))
    inv = first(game)
    rules.spawn_monster(game, inv.location, "cultist", trigger=False)
    rules.spawn_monster(game, inv.location, "ghost", trigger=False)
    script.add("effect_choice", "Discard all")
    actions.perform(game, inv, ("ability",))
    assert game.locations[inv.location].monsters == []


def test_diana_needs_a_cultist_for_her_action(make_game: MakeGame) -> None:
    game = make_game(investigators=("diana_stanley", "mark_harrigan"))
    ability = next(o for o in actions.action_options(game, first(game)) if o.value == ("ability",))
    assert not ability.enabled


def test_diana_loses_no_sanity_with_one_success_against_any_horror(make_game: MakeGame) -> None:
    game = make_game(investigators=("diana_stanley", "mark_harrigan"))
    inv = first(game)
    monster = rules.spawn_monster(game, inv.location, "hound_of_tindalos", trigger=False)
    assert monster is not None
    sanity = inv.sanity
    set_dice(game, *[6] * dice.dice_pool(game, inv, "will", game.monster_def(monster.def_id).horror_mod, ("combat",)))
    combat._will_test(game, inv, game.monster_def(monster.def_id), Ctx(game, inv, "t", monster=monster))
    assert inv.sanity == sanity


def test_jacqueline_gains_a_clue_once_per_round_for_a_condition(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("jacqueline_fine", "mark_harrigan"))
    jacqueline, mark = game.investigators
    clues = jacqueline.clues
    script.add("watch_condition", True)
    rules.gain_condition(game, mark, "amnesia")
    rules.gain_condition(game, mark, "paranoia")
    assert jacqueline.clues == clues + 1


def test_jacqueline_ignores_common_conditions(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("jacqueline_fine", "mark_harrigan"))
    rules.gain_condition(game, game.investigators[1], "debt")
    assert not [k for k, _ in script.asked if k == "watch_condition"]


def test_jacqueline_trades_clues_at_a_distance(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("jacqueline_fine", "mark_harrigan"))
    jacqueline, mark = game.investigators
    jacqueline.clues, mark.clues = 2, 1
    script.add("amount", "2").add("amount", "0")
    actions.perform(game, jacqueline, ("ability",))
    assert (jacqueline.clues, mark.clues) == (0, 3)


def test_leo_takes_an_ally_from_the_discard_pile(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("leo_anderson", "mark_harrigan"))
    inv = first(game)
    guide = rules.draw_matching(game, asset_id="urban_guide")
    assert guide is not None
    game.asset_deck.discard(guide)
    game.reserve = [c for c in game.reserve if not game.asset_def(c).is_a("ally")]
    set_dice(game, *[6] * inv.skill("influence"))
    actions.perform(game, inv, ("ability",))
    assert guide in inv.assets


def test_lola_starts_with_an_improved_skill(make_game: MakeGame) -> None:
    lola = first(make_game(investigators=("lola_hayes", "mark_harrigan")))
    assert sum(lola.improvements.values()) == 1


def test_lola_turns_a_plus_two_token_into_two_improvements(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("lola_hayes", "mark_harrigan"))
    lola = first(game)
    lola.improvements = {"lore": 2}
    script.add("spend_token", "Lore").add("improve", 1).add("improve", 2)
    actions.perform(game, lola, ("ability",))
    assert lola.improvements == {"influence": 1, "observation": 1}


def test_lola_lends_a_die_once_per_round(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("lola_hayes", "mark_harrigan"))
    lola, mark = game.investigators
    mark.location = lola.location
    script.add("lend_die", True)
    set_dice(game, *[1] * (mark.skill("lore") + 1 + mark.skill("lore")))
    assert dice.run_test(game, mark, "lore", allow_clues=False).pool == mark.skill("lore") + 1
    assert dice.run_test(game, mark, "lore", allow_clues=False).pool == mark.skill("lore")


def test_lily_improves_twice_only_from_no_token(make_game: MakeGame) -> None:
    game = make_game(investigators=("lily_chen", "mark_harrigan"))
    lily = first(game)
    library.ImproveSkill("lore", 1).apply(Ctx(game, lily, "t"))
    assert lily.improvements["lore"] == 2


def test_mark_ignores_forced_delay_and_detained(make_game: MakeGame) -> None:
    game = make_game()
    mark = first(game)
    rules.delay(game, mark)
    rules.gain_condition(game, mark, "detained")
    assert not mark.delayed and not rules.has_condition(mark, "detained")


def test_mark_and_one_monster_each_lose_one_health(make_game: MakeGame) -> None:
    game = make_game()
    mark = first(game)
    monster = rules.spawn_monster(game, mark.location, "ghoul", trigger=False)
    assert monster is not None
    health = mark.health
    actions.perform(game, mark, ("ability",))
    assert mark.health == health - 1 and monster.wounds == 1


def test_norman_discards_a_monster_at_a_gate_for_two_clues(make_game: MakeGame) -> None:
    game = make_game(investigators=("norman_withers", "mark_harrigan"))
    norman = first(game)
    norman.clues = 2
    game.locations["london"].gate = True
    rules.spawn_monster(game, "london", "ghost", trigger=False)
    actions.perform(game, norman, ("ability",))
    assert game.locations["london"].monsters == [] and norman.clues == 0


def test_norman_spends_sanity_for_one_clue_each_round(make_game: MakeGame) -> None:
    game = make_game(investigators=("norman_withers", "mark_harrigan"))
    norman = first(game)
    norman.clues = 1
    sanity = norman.sanity
    assert rules.can_pay(game, norman, Cost(clues=2))
    rules.pay_cost(game, norman, Cost(clues=2))
    assert norman.clues == 0 and norman.sanity == sanity - 1
    assert not rules.sanity_clue_ready(game, norman)


def test_trish_gains_a_clue_only_with_no_clues(make_game: MakeGame) -> None:
    game = make_game(investigators=("trish_scarborough", "mark_harrigan"))
    trish = first(game)
    trish.clues = 1
    ability = next(o for o in actions.action_options(game, trish) if o.value == ("ability",))
    assert not ability.enabled


def test_trish_lets_a_clue_reroll_two_dice(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("trish_scarborough", "mark_harrigan"))
    trish = first(game)
    trish.clues = 1
    script.add("reroll", True)
    set_dice(game, *[1] * trish.skill("observation"), 6, 6)
    assert dice.run_test(game, trish, "observation", open_ended=False).successes == 2


def test_wither_adds_strength_for_the_encounter(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("diana_stanley", "mark_harrigan"))
    inv = first(game)
    wither = next(c for c in inv.assets if c.def_id == "wither")
    wither.back = 1
    script.add("cast_spell", True)
    set_dice(game, *[6] * dice.dice_pool(game, inv, "lore", 0, ("cast",)))
    combat._offer_combat_spells(game, inv)
    assert dice.dice_pool(game, inv, "strength", 0, ("combat",)) == inv.skill("strength") + 3
    assert game.free_rerolls == 1


def test_flesh_ward_prevents_two_health_on_any_space(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("jacqueline_fine", "mark_harrigan"))
    jacqueline, mark = game.investigators
    ward = next(c for c in jacqueline.assets if c.def_id == "flesh_ward")
    ward.back = 1
    script.add("cast_spell", True)
    health = mark.health
    set_dice(game, 6, *[1] * (dice.dice_pool(game, jacqueline, "lore", 0, ("cast",)) - 1))
    rules.change_health(game, mark, -3)
    assert mark.health == health - 1 and ward.exhausted


def test_mists_of_releh_skips_combat_on_a_pass(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("akachi_onyele", "mark_harrigan"))
    inv = first(game)
    rules.spawn_monster(game, inv.location, "ghost", trigger=False)
    script.add("cast_spell", True)
    next(c for c in inv.assets if c.def_id == "mists_of_relah").back = 0
    set_dice(game, *[6] * dice.dice_pool(game, inv, "lore", 0, ("cast",)))
    assert not phases._offer_encounter_spells(game, inv)
    assert game.ignore_monsters


def test_shriveling_wounds_by_the_test_result_on_three_successes(make_game: MakeGame) -> None:
    game = make_game(investigators=("jim_culver", "mark_harrigan"))
    inv = first(game)
    inv.skills["lore"] = 3
    monster = rules.spawn_monster(game, inv.location, "shoggoth", trigger=False)
    assert monster is not None
    card = next(c for c in inv.assets if c.def_id == "shrivelling")
    card.back = 0
    set_dice(game, *[6] * dice.dice_pool(game, inv, "lore", 0, ("cast",)))
    actions.perform(game, inv, ("asset", card.uid))
    assert monster.wounds == 3


def test_a_spell_keeps_the_caster_as_the_tester(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("norman_withers", "mark_harrigan"))
    norman, mark = game.investigators
    mark.location = norman.location
    card = next(c for c in norman.assets if c.def_id == "feed_the_mind")
    pool = dice.dice_pool(game, norman, "lore", -1, ("cast",))
    set_dice(game, *[1] * pool)
    actions.perform(game, norman, ("asset", card.uid))
    assert len(next(e for e in script.events if e.kind == "dice").data["rolls"]) == pool != mark.skill("lore") - 1


def test_the_starting_rumor_is_in_play_without_extra_clues(content: Content) -> None:
    game = new_game(content, GameConfig("azathoth", ("mark_harrigan",), seed=2, starting_rumor=True))
    assert len(game.active_mythos) == 1
    assert game.active_mythos[0].def_id not in game.mythos_box


def test_score_follows_the_reference_guide(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    game.doom = 5
    inv.clues = 4
    game.locations["arkham"].gate = True
    rules.spawn_monster(game, "arkham", "ghost", trigger=False)
    rules.gain_condition(game, inv, "cursed")
    active(game, "stars_aligned")
    assert rules.score(game) == 1 + 1 + 1 + 3 - 2 - 5


@pytest.mark.parametrize("seed", range(4))
def test_every_ability_and_spell_action_resolves(content: Content, seed: int) -> None:
    people = tuple(content.investigators)
    for start in range(0, len(people), 3):
        game = new_game(content, GameConfig("azathoth", people[start : start + 3], seed=seed), RandomBot(seed))
        here = game.investigators[0].location
        for inv in game.investigators:
            inv.location = here
            inv.clues = 3
            for spell in ("wither", "conjuration", "plumb_the_void", "blessing_of_isis", "shrivelling"):
                if not any(c.def_id == spell for c in inv.assets):
                    inv.assets.append(rules.new_card(game, spell))
        rules.spawn_gate(game, here)
        rules.spawn_monster(game, here, "cultist", trigger=False)
        for inv in game.investigators:
            for option in actions.action_options(game, inv):
                if option.enabled and option.value[0] in ("ability", "asset") and not game.outcome and not inv.defeated:
                    actions.perform(game, inv, option.value)
                    inv.actions_taken = []
