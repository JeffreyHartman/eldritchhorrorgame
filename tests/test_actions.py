"""Tests for `engine.actions`: the Day actions and their limits."""

from __future__ import annotations

from conftest import MakeGame, Script, first, kinds, set_dice
from pursuit.engine import actions, rules
from pursuit.engine.state import MonsterInst


def options(game, inv):
    return actions.day_options(game, inv)


def test_travel_moves_one_step_then_pays_for_rail(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)  # Hollis in Chicago with 2 Funds
    script.add("travel", "New York").add("travel_onward", "Providence").add("travel_onward", "North Atlantic")
    actions.perform(game, inv, ("travel",))
    assert inv.location == "north_atlantic"
    assert inv.funds == 0
    assert inv.actions_taken == ["travel"]


def test_travel_stops_when_funds_run_out(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.funds = 0
    script.add("travel", "New York")
    actions.perform(game, inv, ("travel",))
    assert inv.location == "new_york"
    assert not any(kind == "travel_onward" for kind, _ in script.asked)


def test_free_travel_perk_skips_the_first_fare(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("ingrid_solveig", "hollis_grange"))
    inv = first(game)  # Ingrid in Reykjavik, 3 Funds, 1 free step
    script.add("travel", "Paris").add("travel_onward", "Prague").add("travel_onward", "Moscow")
    actions.perform(game, inv, ("travel",))
    assert inv.location == "moscow"
    assert inv.funds == 2


def test_cancelled_travel_costs_no_action(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    script.add("travel", "Cancel")
    actions.perform(game, inv, ("travel",))
    assert inv.actions_taken == []


def test_each_action_works_once_per_round(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    inv.health -= 1
    actions.perform(game, inv, ("rest",))
    assert "rest" not in kinds(options(game, inv))
    assert "travel" in kinds(options(game, inv))


def test_two_actions_then_only_free_ones(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    inv.actions_taken = ["rest", "travel"]
    assert set(kinds(options(game, inv))) <= {"buy", "trade", "collect", "end"}


def test_rest_is_blocked_by_monsters(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    game.locations[inv.location].monsters.append(MonsterInst(game.uid(), "cultist"))
    assert "rest" not in kinds(options(game, inv))


def test_investigate_takes_the_clue(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)  # Hollis gets 1 extra clue
    game.locations[inv.location].clue = True
    set_dice(game, 6, 1, 1, 1, 1)
    actions.perform(game, inv, ("investigate",))
    assert inv.clues == 2
    assert not game.locations[inv.location].clue


def test_seal_needs_more_successes_against_yog_sothoth(make_game: MakeGame) -> None:
    game = make_game(old_one="yog_sothoth")
    inv = first(game)
    game.locations[inv.location].rift = True
    set_dice(game, 6, 1)
    actions.perform(game, inv, ("seal",))
    assert game.locations[inv.location].rift, "one success is not enough"
    assert inv.sanity == inv.max_sanity - 1


def test_seal_closes_the_rift(make_game: MakeGame) -> None:
    game = make_game(investigators=("miriam_achterberg", "hollis_grange"))
    inv = first(game)  # Miriam: lore 4, +1 from her journal, +1 when sealing
    game.locations[inv.location].rift = True
    set_dice(game, 5, 1, 1, 1, 1, 1)
    actions.perform(game, inv, ("seal",))
    assert not game.locations[inv.location].rift
    assert inv.trophies == 1


def test_earn_funds_only_in_a_city(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    set_dice(game, 5, 6)
    actions.perform(game, inv, ("earn",))
    assert inv.funds == 2 + 1 + 2
    inv.location = "sahara"
    inv.actions_taken = []
    assert "earn" not in kinds(options(game, inv))


def test_wanted_condition_blocks_earn_and_buy(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "wanted")
    available = kinds(options(game, inv))
    assert "earn" not in available and "buy" not in available


def test_spend_rite_takes_clues(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    rite = game.rites[0]
    rite.def_id = "ky_lake"
    rite.required = 4
    inv = first(game)
    inv.location = "tibet"
    inv.clues = 3
    assert ("rite", 0) in [o.value for o in options(game, inv) if o.enabled]
    script.add("rite_amount", "Give 3")
    actions.perform(game, inv, ("rite", 0))
    assert rite.progress == 3 and inv.clues == 0


def test_test_rite_adds_successes(make_game: MakeGame) -> None:
    game = make_game()
    rite = game.rites[0]
    rite.def_id = "ky_second_act"
    rite.required = 4
    inv = first(game)
    inv.location = "paris"
    set_dice(game, 5, 6)
    actions.perform(game, inv, ("rite", 0))
    assert rite.progress == 2


def test_relic_rite_discards_a_relic(make_game: MakeGame, script: Script) -> None:
    game = make_game(old_one="cthulhu")
    rite = game.rites[0]
    rite.def_id = "cth_idol"
    rite.required = 1
    inv = first(game)
    inv.location = "north_atlantic"
    relic = rules.draw_matching(game, kind="relic")
    assert relic is not None
    inv.assets.append(relic)
    actions.perform(game, inv, ("rite", 0))
    assert rite.done and relic not in inv.assets


def test_asset_action_exhausts_and_discards(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    flask = rules.draw_matching(game, asset_id="whiskey_flask")
    assert flask is not None
    inv.assets.append(flask)
    inv.sanity = 2
    actions.perform(game, inv, ("asset", flask.uid))
    assert inv.sanity == 4
    assert flask not in inv.assets
    assert inv.actions_taken == [f"asset:{flask.uid}"]


def test_investigator_ability_can_target_another_investigator(make_game: MakeGame, script: Script) -> None:
    game = make_game(investigators=("kenji_mori", "tug_mulroney"))
    kenji, tug = game.investigators
    tug.location = kenji.location
    tug.health = 2
    rules.gain_condition(game, tug, "leg_wound")
    script.add("ability_target", "Tug")
    actions.perform(game, kenji, ("ability",))
    assert tug.health == 5
    assert not tug.conditions


def test_ability_cost_is_paid(make_game: MakeGame) -> None:
    game = make_game(investigators=("ada_penhallow", "tug_mulroney"))
    ada = first(game)
    actions.perform(game, ada, ("ability",))
    assert ada.sanity == ada.max_sanity - 1
    assert sum(game.asset_def(c).kind == "spell" for c in ada.assets) == 2


def test_cure_with_a_cost(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "leg_wound")
    uid = inv.conditions[0].uid
    actions.perform(game, inv, ("cure", uid))
    assert not inv.conditions and inv.funds == 0


def test_buy_from_the_market(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.funds = 10
    card = game.market[0]
    price = rules.market_price(game, inv, card)
    script.add("buy", 0).add("buy", "Leave")
    actions.perform(game, inv, ("buy",))
    assert inv.funds == 10 - price
    assert len(game.market) == game.content.rules.market_size
    if game.asset_def(card).kind != "service":
        assert card in inv.assets


def test_trade_moves_assets_and_funds(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    a, b = game.investigators
    b.location = a.location
    revolver = a.assets[0]
    script.add("trade", "Give an asset").add("trade_asset", 0).add("trade", "Take 1 Funds").add("trade", "Done")
    actions.perform(game, a, ("trade",))
    assert revolver in b.assets and revolver not in a.assets
    assert a.funds == 3 and b.funds == 1


def test_collect_belongings(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    card = rules.new_card(game, "pump_shotgun")
    game.locations[inv.location].belongings.append(card)
    script.add("collect", "Pump Shotgun")
    actions.perform(game, inv, ("collect",))
    assert card in inv.assets
