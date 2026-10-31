"""Tests for `engine.rules`: health, defeat, doom, dread, rifts, monsters, and conditions."""

from __future__ import annotations

from conftest import MakeGame, Script, first, set_dice
from pursuit.content.loader import Content
from pursuit.engine import rules
from pursuit.engine.state import MonsterInst


def test_health_never_goes_above_max_or_below_zero(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    rules.change_health(game, inv, 5)
    assert inv.health == inv.max_health
    rules.change_health(game, inv, -99)
    assert inv.health == 0 and inv.defeated


def test_defeated_investigator_is_replaced_and_doom_advances(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    loc = inv.location
    doom = game.doom
    script.add("replacement", "Kenji")
    rules.change_sanity(game, inv, -99)
    rules.process_defeats(game)
    new = first(game)
    assert new.def_id == "kenji_mori"
    assert new.seat == 0
    assert game.doom == doom - 1
    assert game.locations[loc].belongings, "the fallen investigator's assets stay behind"
    assert "kenji_mori" not in game.unused_investigators


def test_no_replacement_after_awakening(make_game: MakeGame) -> None:
    game = make_game()
    rules.awaken(game)
    inv = first(game)
    rules.change_health(game, inv, -99)
    rules.process_defeats(game)
    assert first(game).eliminated
    assert game.outcome is None
    other = game.investigators[1]
    rules.change_health(game, other, -99)
    rules.process_defeats(game)
    assert game.outcome == "loss"


def test_doom_reaching_zero_awakens_the_old_one(make_game: MakeGame) -> None:
    game = make_game(old_one="cthulhu")
    rules.advance_doom(game, game.doom)
    assert game.awakened
    assert game.endgame == game.old_one.awakening.nights
    assert game.final_rite is not None and game.final_rite.required == 3 * 2
    assert any(m.def_id == "dreamer_risen" for m in game.locations["south_pacific"].monsters)


def test_doom_after_awakening_spends_the_endgame_clock(make_game: MakeGame) -> None:
    game = make_game()
    rules.awaken(game)
    rules.advance_doom(game, game.endgame)
    assert game.outcome == "loss"


def test_dread_rises_with_doom_and_adds_portents(make_game: MakeGame, content: Content) -> None:
    game = make_game()
    before = len(game.portent_deck)
    rules.advance_doom(game, game.doom - game.old_one.dread_at[0])
    assert game.dread == 2
    added = sum(1 for p in content.portents.values() if p.min_dread == 2)
    assert len(game.portent_deck) == before + added
    rules.retreat_doom(game, 5)
    assert game.dread == 2, "dread never falls"


def test_opening_a_rift_spawns_a_monster(make_game: MakeGame) -> None:
    game = make_game()
    game.rift_deck.cards.insert(0, "sahara")
    rules.open_rift(game)
    assert game.locations["sahara"].rift
    assert len(game.locations["sahara"].monsters) == 1


def test_a_rift_on_a_rift_widens_and_advances_doom(make_game: MakeGame) -> None:
    game = make_game()
    game.locations["sahara"].rift = True
    game.rift_deck.cards.insert(0, "sahara")
    doom = game.doom
    rules.open_rift(game)
    assert game.doom == doom - 1


def test_rift_limit_loses_the_game(make_game: MakeGame) -> None:
    game = make_game(old_one="yog_sothoth")
    sites = [loc.id for loc in game.content.locations.values() if loc.rift_site]
    for site in sites[:7]:
        game.locations[site].rift = True
    game.rift_deck.cards.insert(0, sites[7])
    rules.open_rift(game)
    assert game.outcome == "loss"


def test_closing_a_rift_gives_a_trophy_and_seal_progress(make_game: MakeGame) -> None:
    game = make_game()
    game.rites[0].def_id = "ky_seal"
    inv = first(game)
    game.locations[inv.location].rift = True
    rules.close_rift(game, inv, inv.location)
    assert inv.trophies == 1
    assert game.rites[0].progress == 1


def test_completing_every_rite_wins(make_game: MakeGame) -> None:
    game = make_game()
    for rite in game.rites:
        rules.add_rite_progress(game, rite, rite.required)
    assert game.outcome == "win"


def test_roaming_monster_steps_toward_the_nearest_investigator(make_game: MakeGame) -> None:
    game = make_game()
    for inv in game.investigators:
        inv.location = "paris"
    game.locations["moscow"].monsters.append(MonsterInst(game.uid(), "wendigo"))
    game.locations["moscow"].monsters.append(MonsterInst(game.uid(), "ghoul"))
    rules.move_monsters(game)
    assert [m.def_id for m in game.locations["prague"].monsters] == ["wendigo"]
    assert [m.def_id for m in game.locations["moscow"].monsters] == ["ghoul"]


def test_monster_cup_runs_out(make_game: MakeGame) -> None:
    game = make_game()
    game.monster_cup = []
    assert rules.spawn_monster(game, "paris") is None


def test_clue_never_lands_on_a_location_that_has_one(make_game: MakeGame) -> None:
    game = make_game()
    for _ in range(100):
        rules.spawn_clue(game)
    clues = [loc for loc, s in game.locations.items() if s.clue]
    assert len(clues) == sum(1 for loc in game.content.locations.values() if loc.terrain != "sea")


def test_condition_outcome_is_hidden_until_it_resolves(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "leg_wound")
    gained = script.texts("condition")[-1]
    for outcome in game.content.conditions["leg_wound"].outcomes:
        assert outcome.text not in gained
    before = len(script.events)
    rules.resolve_condition(game, inv, inv.conditions[0])
    resolved = " ".join(e.text for e in script.events[before:])
    assert any(o.text in resolved for o in game.content.conditions["leg_wound"].outcomes)


def test_condition_is_unique(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    assert rules.gain_condition(game, inv, "hexed")
    assert not rules.gain_condition(game, inv, "hexed")
    assert len(inv.conditions) == 1


def test_night_trigger_uses_the_chance_roll(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "jungle_fever")  # chance 2
    set_dice(game, 3)
    rules.trigger_conditions(game, inv, "night")
    assert inv.conditions, "a roll of 3 is above the chance, so nothing happens"
    hp, sp = inv.health, inv.sanity
    set_dice(game, 2)
    rules.trigger_conditions(game, inv, "night")
    assert not inv.conditions or inv.health < hp or inv.sanity < sp


def test_market_refills_and_rotates(make_game: MakeGame) -> None:
    game = make_game()
    assert len(game.market) == game.content.rules.market_size
    oldest = game.market[0]
    rules.rotate_market(game)
    assert oldest not in game.market
    assert oldest in game.asset_deck.discards
    assert len(game.market) == game.content.rules.market_size
