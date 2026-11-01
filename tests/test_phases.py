"""Tests for `engine.phases`: the order of a round and what each phase does."""

from __future__ import annotations

from conftest import MakeGame, Script, first, set_dice
from pursuit.engine import phases, rules
from pursuit.engine.state import MonsterInst, Phase


def end_turns(script: Script, count: int) -> None:
    for _ in range(count):
        script.add("action", "End turn")


def test_action_phase_runs_each_investigator_from_lead_then_moves_to_encounters(
    make_game: MakeGame, script: Script
) -> None:
    game = make_game()
    end_turns(script, 2)
    phases.step(game)
    assert game.phase == Phase.ENCOUNTER and game.turn_index == 0
    assert script.checkpoints == 2
    assert [e.data.get("investigator") for e in script.events if e.kind == "turn"] == [
        "Mark Harrigan",
        "Akachi Onyele",
    ]


def test_encounter_draws_from_location_or_general_deck_and_discards(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    game.phase = Phase.ENCOUNTER
    phases.step(game)
    encounters = [e for e in script.events if e.kind == "encounter"]
    assert [e.data["deck"] for e in encounters] == ["general", "general"]
    assert len(game.encounter_decks["general"].discards) == 2
    assert game.phase == Phase.MYTHOS


def test_gate_offers_an_other_world_encounter(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    game.locations[inv.location].gate = True
    script.add("encounter", "Other World")
    phases.encounter_turn(game, inv)
    deck = next(e.data["deck"] for e in script.events if e.kind == "encounter")
    assert deck == "other_world"


def test_location_encounter_uses_the_section_for_the_current_city(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.location = "london"
    card_id = game.encounter_decks["europe"].cards[0]
    card = game.content.encounters[card_id]
    expected = next(section.text for section in card.sections if section.location == "london")
    phases.encounter_turn(game, inv)
    event = next(e for e in script.events if e.kind == "encounter")
    assert event.data["deck"] == "europe" and event.data["encounter"] == card_id
    assert event.text == expected


def test_general_encounter_uses_the_section_for_the_current_terrain(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.location = "space_13"
    card_id = game.encounter_decks["general"].cards[0]
    card = game.content.encounters[card_id]
    expected = next(section.text for section in card.sections if section.terrain == "sea")
    phases.encounter_turn(game, inv)
    event = next(e for e in script.events if e.kind == "encounter")
    assert event.data["deck"] == "general" and event.data["encounter"] == card_id
    assert event.text == expected


def test_clue_offers_a_research_encounter(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    game.locations[inv.location].clue = True
    script.add("encounter", "Research Encounter")
    phases.encounter_turn(game, inv)
    assert next(e.data["deck"] for e in script.events if e.kind == "encounter") == "research_azathoth"


def test_expedition_encounter_moves_active_expedition_token(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    assert game.active_expedition is not None
    inv.location = game.active_expedition
    script.add("encounter", "Expedition Encounter")
    phases.encounter_turn(game, inv)
    assert next(e.data["deck"] for e in script.events if e.kind == "encounter") == "expedition"
    assert game.active_expedition in game.content.locations


def test_monster_blocks_location_encounter_when_it_survives(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    game.locations[inv.location].monsters.append(MonsterInst(game.uid(), "zombie"))  # toughness 3
    set_dice(game, 5, 1, 1, 5, 1, 1, 1, 1, 1, 1, 1)  # 1 wound dealt, zombie survives
    phases.encounter_turn(game, inv)
    assert not [e for e in script.events if e.kind == "encounter"]


def test_mythos_phase_resolves_card_and_starts_new_round(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    game.phase = Phase.MYTHOS
    first(game).actions_taken = ["rest"]
    first(game).assets[0].exhausted = True
    phases.step(game)
    assert any(e.kind == "mythos" for e in script.events)
    assert game.round == 2 and game.phase == Phase.ACTION
    assert first(game).actions_taken == []
    assert not first(game).assets[0].exhausted


def test_empty_mythos_deck_loses_the_game(make_game: MakeGame) -> None:
    game = make_game()
    game.mythos_deck.clear()
    game.phase = Phase.MYTHOS
    phases.step(game)
    assert game.outcome == "loss"


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
    game.ctl.choose = lambda g, p, opts, kind, inv=None: (  # type: ignore[method-assign, misc]
        next(i for i, o in enumerate(opts) if o.value == ("end",))
        if kind == "action"
        else HeuristicBot().choose(g, p, opts, kind=kind, inv=inv)
    )
    assert phases.play(game) in ("win", "loss")
    assert game.round < 40


def test_replacement_investigator_chosen_at_end_of_mythos_phase(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    rules.change_health(game, inv, -99)
    rules.process_defeats(game)
    assert first(game).defeated
    game.phase = Phase.MYTHOS
    phases.step(game)
    assert not first(game).defeated
    assert first(game).def_id != "mark_harrigan"

