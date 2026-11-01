"""Regression tests for rulebook behavior in `engine`. Page numbers refer to the rulebook."""

from __future__ import annotations

from conftest import MakeGame, Script, first, set_dice
from pursuit.engine import actions, combat, dice, phases, rules
from pursuit.engine.state import Phase


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


