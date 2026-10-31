"""Tests for `engine.phases`: the order of a round and what each phase does."""

from __future__ import annotations

from conftest import MakeGame, Script, first
from pursuit.engine import phases, rules
from pursuit.engine.state import MonsterInst, Phase


def end_turns(script: Script, count: int) -> None:
    for _ in range(count):
        script.add("action", "End turn")


def test_day_runs_each_investigator_then_moves_to_encounters(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    end_turns(script, 2)
    phases.step(game)
    assert game.phase == Phase.ENCOUNTER and game.turn_index == 0
    assert script.checkpoints == 2
    assert [e.data.get("investigator") for e in script.events if e.kind == "turn"] == [
        "Hollis Grange",
        "Dr. Miriam Achterberg",
    ]


def test_encounter_draws_from_the_location_deck_and_discards(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    game.phase = Phase.ENCOUNTER
    phases.step(game)
    encounters = [e for e in script.events if e.kind == "encounter"]
    assert [e.data["deck"] for e in encounters] == ["city", "cairo"]
    assert len(game.encounter_decks["cairo"].discards) == 1
    assert game.phase == Phase.NIGHT


def test_rift_offers_a_rift_encounter(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    game.locations[inv.location].rift = True
    script.add("encounter", "Step through the rift")
    phases.encounter_turn(game, inv)
    assert [e.data["deck"] for e in script.events if e.kind == "encounter"] == ["rift"]


def test_monster_blocks_the_location_encounter_when_it_survives(make_game: MakeGame, script: Script) -> None:
    from conftest import set_dice

    game = make_game()
    inv = first(game)
    game.locations[inv.location].monsters.append(MonsterInst(game.uid(), "grave_revenant"))
    script.add("combat", "Fight")
    set_dice(game, 6, 1, 1, 1, 1, 1, 1)  # 2 Nerve dice for horror, then 5 Brawn dice that all miss
    phases.encounter_turn(game, inv)
    assert not [e for e in script.events if e.kind == "encounter"]


def test_night_advances_doom_draws_a_portent_and_starts_a_new_round(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    game.phase = Phase.NIGHT
    first(game).actions_taken = ["rest"]
    first(game).assets[0].exhausted = True
    doom = game.doom
    phases.step(game)
    assert game.doom <= doom - 1
    assert any(e.kind == "portent" for e in script.events)
    assert game.round == 2 and game.phase == Phase.DAY
    assert first(game).actions_taken == []
    assert not first(game).assets[0].exhausted


def test_open_rifts_press_doom_at_night(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    game.portent_deck.cards = ["quiet_night"]
    sites = [loc.id for loc in game.content.locations.values() if loc.rift_site][:4]
    for site in sites:
        game.locations[site].rift = True
    doom = game.doom
    game.phase = Phase.NIGHT
    phases.step(game)
    assert game.doom == doom - 2


def test_awakened_night_hook_waits_one_night(make_game: MakeGame, script: Script) -> None:
    game = make_game(old_one="cthulhu")
    game.portent_deck.cards = ["quiet_night"]
    game.doom = 1
    game.phase = Phase.NIGHT
    sanity = [i.sanity for i in game.investigators]
    phases.step(game)
    assert game.awakened
    assert [i.sanity for i in game.investigators] == [
        min(s + 1, i.max_sanity) for s, i in zip(sanity, game.investigators, strict=True)
    ]


def test_full_round_with_scripted_turns(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    end_turns(script, 2)
    for _ in range(3):
        phases.step(game)
    assert game.round == 2


def test_play_until_loss_with_passive_investigators(make_game: MakeGame) -> None:
    from pursuit.bots import HeuristicBot

    game = make_game()
    game.ctl = Script(fallback="first")
    # Every turn ends at once, so Doom wins in a bounded number of rounds.
    game.ctl.choose = lambda g, p, opts, kind, inv=None: (  # type: ignore[method-assign, misc]
        next(i for i, o in enumerate(opts) if o.value == ("end",))
        if kind == "action"
        else HeuristicBot().choose(g, p, opts, kind=kind, inv=inv)
    )
    assert phases.play(game) == "loss"
    assert game.round < 40


def test_replacement_investigator_waits_for_next_round(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    rules.change_health(game, inv, -99)
    rules.process_defeats(game)
    assert first(game).actions_taken == ["arrived", "arrived"]
    phases.start_round(game)
    assert first(game).actions_taken == []
