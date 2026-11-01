"""Tests for `engine.actions`: the Action Phase actions and their limits."""

from __future__ import annotations

from conftest import MakeGame, Script, first, kinds, set_dice
from pursuit.engine import actions, rules
from pursuit.engine.state import MonsterInst


def options(game, inv):
    return actions.action_options(game, inv)


def test_travel_moves_one_space_then_spends_matching_tickets(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)  # Mark Harrigan in Space 14 (connected by train to Rome and Space 16)
    inv.tickets = ["train", "ship"]
    script.add("travel", "Rome").add("travel_onward", "London").add("travel_onward", "Stop")
    actions.perform(game, inv, ("travel",))
    assert inv.location == "london"
    assert inv.tickets == ["train"]  # Rome -> London used the Ship ticket
    assert inv.actions_taken == ["travel"]


def test_prepare_for_travel_gains_ticket_and_enforces_max_two(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)  # Space 14 has only train paths
    inv.tickets = ["train", "ship"]
    script.add("discard_ticket", 0)
    actions.perform(game, inv, ("prepare",))
    assert len(inv.tickets) == 2


def test_prepare_for_travel_requires_a_city_with_train_or_ship_path(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    inv.location = "the_amazon"  # wilderness
    assert "prepare" not in kinds(options(game, inv))


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


def test_two_actions_then_only_end_turn(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    inv.actions_taken = ["rest", "travel"]
    assert set(kinds(options(game, inv))) == {"end"}


def test_rest_and_acquire_are_blocked_by_monsters(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    game.locations[inv.location].monsters.append(MonsterInst(game.uid(), "cultist"))
    avail = kinds(options(game, inv))
    assert "rest" not in avail and "acquire" not in avail


def test_detained_condition_blocks_travel_and_prepare(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "detained")
    avail = kinds(options(game, inv))
    assert "travel" not in avail and "prepare" not in avail


def test_acquire_assets_buys_cards_with_influence_successes(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)  # Mark Harrigan: Influence 2
    game.reserve[0] = rules.new_card(game, "bandages")  # cost 1
    card = game.reserve[0]
    set_dice(game, 5, 6)  # 2 successes
    script.add("bank_loan", False).add("acquire", 0).add("acquire", "Done")
    actions.perform(game, inv, ("acquire",))
    assert card in inv.assets
    assert len(game.reserve) == game.content.rules.reserve_size


def test_acquire_assets_with_bank_loan_adds_two_successes_and_debt(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    game.reserve[0] = rules.new_card(game, "spirit_dagger")  # cost 2
    card = game.reserve[0]
    set_dice(game, 1, 1)  # 0 successes + 2 from Bank Loan
    script.add("bank_loan", True).add("acquire", 0).add("acquire", "Done")
    actions.perform(game, inv, ("acquire",))
    assert card in inv.assets
    assert rules.has_condition(inv, "debt")


def test_acquire_assets_with_no_purchases_can_discard_one_reserve_card(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    dropped = game.reserve[0]
    set_dice(game, 1, 1)
    script.add("bank_loan", False).add("acquire_discard", 0)
    actions.perform(game, inv, ("acquire",))
    assert dropped not in game.reserve
    assert dropped in game.asset_deck.discards
    assert len(game.reserve) == game.content.rules.reserve_size


def test_component_actions_from_different_components_can_both_run(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    dynamite = rules.new_card(game, "dynamite")
    inv.assets.append(dynamite)
    actions.perform(game, inv, ("asset", dynamite.uid))
    assert dynamite not in inv.assets
    assert "ability" in kinds(options(game, inv))


def test_local_action_on_another_investigators_condition(make_game: MakeGame) -> None:
    game = make_game()
    a, b = game.investigators
    b.location = a.location
    rules.gain_condition(game, b, "debt")
    inst = b.conditions[0]
    set_dice(game, 6, 1)
    actions.perform(game, a, ("condition", b.seat, inst.uid))
    assert not b.conditions


def test_trade_is_an_action_and_moves_possessions_clues_and_tickets(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    a, b = game.investigators
    b.location = a.location
    a.tickets = ["train"]
    card = a.assets[0]
    script.add("trade", "Give a card").add("trade", "Take 1 Clue").add("trade", "Give a Ticket").add("trade", "Done")
    actions.perform(game, a, ("trade",))
    assert card in b.assets
    assert a.clues == 1 and b.clues == 0
    assert b.tickets == ["train"]
    assert a.actions_taken == ["trade"]

