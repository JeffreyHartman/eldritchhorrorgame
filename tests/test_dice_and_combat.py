"""Tests for `engine.dice.run_test` and `engine.combat`, with scripted dice."""

from __future__ import annotations

from conftest import MakeGame, Script, first, set_dice
from pursuit.engine import combat, rules
from pursuit.engine.dice import dice_pool, run_test
from pursuit.engine.state import Game, MonsterInst


def test_pool_is_skill_plus_modifiers(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)  # Hollis: wits 5, revolver gives +2 Brawn in combat
    assert dice_pool(game, inv, "wits", 0, ("encounter",)) == 5
    assert dice_pool(game, inv, "brawn", 0, ("combat",)) == 3 + 2
    assert dice_pool(game, inv, "brawn", 0, ("encounter",)) == 3


def test_at_least_one_die_is_rolled(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    set_dice(game, 6)
    result = run_test(game, inv, "lore", mod=-9)
    assert result.pool == 1 and result.passed


def test_fives_and_sixes_succeed(make_game: MakeGame) -> None:
    game = make_game()
    set_dice(game, 1, 4, 5, 6, 2)
    result = run_test(game, first(game), "wits")
    assert result.successes == 2 and result.passed


def test_clue_rerolls_only_the_failed_dice(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.clues = 1
    script.add("reroll", True)
    set_dice(game, 1, 2, 3, 4, 5, 6, 6, 1, 1)
    result = run_test(game, inv, "wits", needed=4)
    # First roll: 1 2 3 4 5 -> 1 success. Reroll the four failures: 6 6 1 1 -> 3 successes.
    assert result.rolls == (6, 6, 1, 1, 5)
    assert result.successes == 3
    assert inv.clues == 0


def test_no_reroll_offer_when_the_test_already_passes(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.clues = 3
    set_dice(game, 6, 1, 1, 1, 1)
    run_test(game, inv, "wits")
    assert not any(kind == "reroll" for kind, _ in script.asked)


def test_condition_modifier_lowers_the_pool(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "hexed")
    assert dice_pool(game, inv, "wits", 0, ("encounter",)) == 4


def test_old_one_modifier_applies_only_where_it_says(make_game: MakeGame) -> None:
    game = make_game(old_one="cthulhu")
    inv = first(game)
    assert dice_pool(game, inv, "nerve", 0, ("horror",)) == 2
    inv.location = "north_atlantic"
    assert dice_pool(game, inv, "nerve", 0, ("horror",)) == 1


def test_boost_costs_sanity_and_exhausts(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("ada_penhallow", "tug_mulroney"))
    ada = first(game)  # starts with Withering Word: +3 dice in combat for 1 Sanity
    script.add("boost", True)
    set_dice(game, *[1] * 4)
    result = run_test(game, ada, "brawn", contexts=("combat",))
    assert result.pool == 1 + 3
    assert ada.sanity == ada.max_sanity - 1
    assert ada.assets[0].exhausted


def test_discard_boost_removes_the_card(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    knife = rules.draw_matching(game, asset_id="dynamite")
    assert knife is not None
    inv.assets.append(knife)
    script.add("boost", True)
    set_dice(game, *[1] * 9)
    result = run_test(game, inv, "brawn", contexts=("combat",))
    assert result.pool == 3 + 2 + 4
    assert knife not in inv.assets
    assert knife in game.asset_deck.discards


# --- combat ---------------------------------------------------------------------------


def spawn(game: Game, loc: str, monster_id: str) -> MonsterInst:
    monster = rules.spawn_monster(game, loc, monster_id)
    assert monster is not None
    return monster


def test_fight_that_kills_returns_the_monster_to_the_cup(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    monster = spawn(game, inv.location, "cultist")
    cup_before = game.monster_cup.count("cultist")
    script.add("combat", "Fight")
    set_dice(game, 5, 1, 1, 1, 1)
    assert combat.combat(game, inv, monster) == combat.DEFEATED
    assert not game.locations[inv.location].monsters
    assert game.monster_cup.count("cultist") == cup_before + 1
    assert inv.funds == 3  # the cultist drops 1 Funds


def test_surviving_monster_strikes_and_keeps_its_wounds(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    monster = spawn(game, inv.location, "ghoul")  # horror 1, damage 2, toughness 2
    script.add("combat", "Fight")
    set_dice(game, 6, 1, 1, 5, 1, 1, 1, 1)  # pass horror check, then 1 success in 5 fight dice
    assert combat.combat(game, inv, monster) == combat.STRUCK
    assert monster.wounds == 1
    assert inv.health == inv.max_health - 2


def test_failed_horror_check_costs_sanity(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    monster = spawn(game, inv.location, "ghoul")
    script.add("combat", "Fight")
    set_dice(game, 1, 1, 1, 6, 6, 1, 1, 1)
    combat.combat(game, inv, monster)
    assert inv.sanity == inv.max_sanity - 1


def test_evade_pass_allows_a_location_encounter(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    spawn(game, inv.location, "cultist")
    script.add("combat", "Evade")
    set_dice(game, 6, 1, 1, 1, 1)
    assert combat.resolve_monsters(game, inv) is True
    assert game.locations[inv.location].monsters


def test_evade_fail_blocks_the_encounter_and_hurts(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    spawn(game, inv.location, "cultist")
    script.add("combat", "Evade")
    set_dice(game, 1, 1, 1, 1, 1)
    assert combat.resolve_monsters(game, inv) is False
    assert inv.health == inv.max_health - 1


def test_defeating_an_epic_monster_completes_its_rite(make_game: MakeGame, script: Script) -> None:
    game = make_game(old_one="king_in_yellow", seed=1)
    rite = next((r for r in game.rites if game.rite_def(r).kind == "defeat"), None)
    if rite is None:
        game.rites[0].def_id = "ky_phantom"
        rite = game.rites[0]
    inv = first(game)
    phantom = spawn(game, inv.location, "phantom_of_truth")
    phantom.wounds = 5
    script.add("combat", "Fight")
    set_dice(game, 6, 6, 1, 1, 1, 1)
    combat.combat(game, inv, phantom)
    assert rite.done
