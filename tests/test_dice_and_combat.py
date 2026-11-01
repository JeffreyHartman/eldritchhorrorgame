"""Tests for `engine.dice.run_test` and `engine.combat`, with scripted dice."""

from __future__ import annotations

from conftest import MakeGame, Script, first, set_dice
from pursuit.engine import combat, rules
from pursuit.engine.dice import dice_pool, run_test
from pursuit.engine.state import Game, MonsterInst


def test_pool_uses_highest_card_bonus_plus_additional_dice(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)  # Mark Harrigan: strength 5, +1 additional in combat, .38 Revolver (+2 strength in combat)
    assert dice_pool(game, inv, "observation", 0, ("encounter",)) == 2
    assert dice_pool(game, inv, "strength", 0, ("combat",)) == 5 + 1 + 2
    assert dice_pool(game, inv, "strength", 0, ("encounter",)) == 5

    # Adding a Shotgun (+4 strength in combat) replaces the +2 from .38 Revolver rather than stacking to +6
    shotgun = rules.draw_matching(game, asset_id="double_barreled_shotgun")
    assert shotgun is not None
    inv.assets.append(shotgun)
    assert dice_pool(game, inv, "strength", 0, ("combat",)) == 5 + 1 + 4


def test_at_least_one_die_is_rolled(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    set_dice(game, 6)
    result = run_test(game, inv, "lore", mod=-9)
    assert result.pool == 1 and result.passed


def test_fives_and_sixes_succeed_and_blessed_or_cursed_shift_threshold(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    set_dice(game, 4, 5, 6)
    result = run_test(game, inv, "will")
    assert result.successes == 2 and result.passed

    rules.gain_condition(game, inv, "blessed")
    set_dice(game, 4, 5, 6)
    assert run_test(game, inv, "will").successes == 3

    rules.gain_condition(game, inv, "cursed")  # cancels Blessed
    assert not rules.has_condition(inv, "blessed")
    rules.gain_condition(game, inv, "cursed")
    set_dice(game, 4, 5, 6)
    assert run_test(game, inv, "will").successes == 1


def test_clue_rerolls_one_failed_die_at_a_time(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.clues = 2
    script.add("reroll", True).add("reroll", False)
    set_dice(game, 1, 2, 5, 6)
    result = run_test(game, inv, "will", needed=2)
    # First roll: 1, 2, 5 -> 1 success. Spend 1 Clue to reroll the 1 -> 6 -> 2 successes.
    assert result.rolls == (6, 2, 5)
    assert result.successes == 2
    assert inv.clues == 1


def test_no_reroll_offer_when_the_test_already_passes(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.clues = 3
    set_dice(game, 6, 1, 1)
    run_test(game, inv, "will")
    assert not any(kind == "reroll" for kind, _ in script.asked)


def test_condition_modifier_lowers_the_pool(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "leg_injury")
    assert dice_pool(game, inv, "strength", 0, ("encounter",)) == 4


def test_old_one_modifier_applies_only_where_it_says(make_game: MakeGame) -> None:
    game = make_game(old_one="cthulhu")
    inv = first(game)
    assert dice_pool(game, inv, "will", 0, ("horror",)) == 3
    inv.location = "space_2"
    assert dice_pool(game, inv, "will", 0, ("horror",)) == 2


def test_card_reroll_ability_rerolls_one_die(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("jacqueline_fine", "mark_harrigan"))
    jacq = first(game)  # Jacqueline can reroll 1 Lore die
    jacq.clues = 0
    script.add("reroll_card", True)
    set_dice(game, 1, 2, 3, 4, 6)
    result = run_test(game, jacq, "lore")
    assert result.passed and result.successes == 1


# --- combat ---------------------------------------------------------------------------


def spawn(game: Game, loc: str, monster_id: str) -> MonsterInst:
    monster = rules.spawn_monster(game, loc, monster_id)
    assert monster is not None
    return monster


def test_combat_resolves_will_and_strength_and_returns_defeated_monster_to_cup(make_game: MakeGame) -> None:
    game = make_game(old_one="azathoth")
    inv = first(game)  # Mark: strength 5 + 1 + 2 = 8 in combat
    monster = spawn(game, inv.location, "ghoul")  # horror 1 (Will +1), damage 2, toughness 1
    cup_before = game.monster_cup.count("ghoul")
    # Will test (4 dice): 5, 1, 1, 1 -> 1 success, 0 sanity lost
    # Strength test (8 dice): 5, 6, 1, 1, 1, 1, 1, 1 -> 2 successes -> 0 health lost, 2 wounds -> defeated
    set_dice(game, 5, 1, 1, 1, 5, 6, 1, 1, 1, 1, 1, 1)
    assert combat.combat(game, inv, monster) == combat.DEFEATED
    assert not game.locations[inv.location].monsters
    assert game.monster_cup.count("ghoul") == cup_before + 1
    assert inv.health == inv.max_health and inv.sanity == inv.max_sanity


def test_combat_successes_reduce_horror_and_damage_taken(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    monster = spawn(game, inv.location, "star_spawn")  # horror 3 (-1), damage 3 (-2), toughness 3
    # Will test (3 - 1 = 2 dice): 5, 1 -> 1 success -> 3 - 1 = 2 Sanity lost
    # Strength test (8 - 2 = 6 dice): 5, 1, 1, 1, 1, 1 -> 1 success -> 3 - 1 = 2 Health lost, 1 wound dealt
    set_dice(game, 5, 1, 5, 1, 1, 1, 1, 1)
    assert combat.combat(game, inv, monster) == combat.SURVIVED
    assert monster.wounds == 1
    assert inv.sanity == inv.max_sanity - 2
    assert inv.health == inv.max_health - 2


def test_surviving_monster_blocks_location_encounter(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    spawn(game, inv.location, "zombie")
    # Will: 3 dice (5,1,1), Strength: 7 dice (5,1,1,1,1,1,1) -> 1 wound on toughness 2 zombie
    set_dice(game, 5, 1, 1, 5, 1, 1, 1, 1, 1, 1)
    assert combat.resolve_monsters(game, inv) is False
    assert game.locations[inv.location].monsters


def test_defeating_all_monsters_allows_location_encounter(make_game: MakeGame) -> None:
    game = make_game(old_one="yog_sothoth")
    inv = first(game)
    spawn(game, inv.location, "cultist")  # Yog cultist: horror 0, damage 1, fight -1, toughness 1
    set_dice(game, 6, 1, 1, 1, 1, 1, 1)
    assert combat.resolve_monsters(game, inv) is True
    assert not game.locations[inv.location].monsters


def test_defeating_an_epic_monster_solves_its_mystery_at_the_end_of_the_mythos_phase(make_game: MakeGame) -> None:
    game = make_game(old_one="cthulhu", seed=1)
    from pursuit.engine.state import MysteryState

    game.active_mystery = MysteryState("cth_watching_the_stars", 1)
    inv = first(game)
    priest = spawn(game, inv.location, "cthylla_epic")
    priest.wounds = 3
    # Will (3-1=2 dice): 6, 6; Strength (8-1=7 dice): 6, 1, 1, 1, 1, 1, 1
    set_dice(game, 6, 6, 6, 1, 1, 1, 1, 1, 1)
    combat.combat(game, inv, priest)
    assert "cth_watching_the_stars" not in game.solved_mysteries
    rules.solve_ready_mystery(game)
    assert "cth_watching_the_stars" in game.solved_mysteries

