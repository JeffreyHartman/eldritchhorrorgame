"""Regression tests for rulebook behavior in `engine`. Page numbers refer to the rulebook."""

from __future__ import annotations

from conftest import MakeGame, Script, first, set_dice
from pursuit.engine import actions, combat, dice, phases, rules
from pursuit.engine.state import Game, Investigator, MonsterInst, Phase


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
