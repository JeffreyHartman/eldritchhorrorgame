"""Tests for `engine.rules`: health, defeat, omen, doom, gates, monsters, mysteries, and conditions."""

from __future__ import annotations

from conftest import MakeGame, Script, first, set_dice
from pursuit.engine import phases, rules
from pursuit.engine.state import MonsterInst, MysteryState


def test_health_never_goes_above_max_or_below_zero(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    rules.change_health(game, inv, 5)
    assert inv.health == inv.max_health
    rules.change_health(game, inv, -99)
    assert inv.health == 0 and inv.defeated


def test_defeated_investigator_relocates_to_nearest_city_and_advances_doom(
    make_game: MakeGame, script: Script
) -> None:
    game = make_game()
    inv = first(game)
    inv.location = "the_amazon"  # nearest city is Space 7 or Buenos Aires
    doom = game.doom
    rules.change_sanity(game, inv, -99)
    rules.process_defeats(game)
    assert game.doom == doom - 1
    assert any(st.fallen for st in game.locations.values())

    script.add("replacement", "Lily")
    rules.replace_defeated_investigators(game)
    new = first(game)
    assert new.def_id == "lily_chen"
    assert new.seat == 0
    assert "lily_chen" not in game.unused_investigators


def test_encountering_fallen_investigator_recovers_possessions_and_retreats_doom(
    make_game: MakeGame, script: Script
) -> None:
    game = make_game()
    a, b = game.investigators
    a.location = b.location
    rules.change_health(game, a, -99)
    rules.process_defeats(game)
    doom = game.doom
    script.add("encounter", "Encounter Mark Harrigan")
    set_dice(game, 6, 6)
    phases.encounter_turn(game, b)
    assert game.doom == doom + 1
    assert not game.locations[b.location].fallen


def test_no_replacement_after_awakening(make_game: MakeGame) -> None:
    game = make_game(old_one="yog_sothoth")
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
    assert game.final_mystery is not None
    assert not any(m.def_id == "cthulhu_epic" for m in game.locations["space_3"].monsters)
    game.solved_mysteries = ["a", "b", "c"]
    rules._spawn_final_monster(game)
    assert any(m.def_id == "cthulhu_epic" for m in game.locations["space_3"].monsters)


def test_azathoth_awakening_loses_immediately(make_game: MakeGame) -> None:
    game = make_game(old_one="azathoth")
    rules.advance_doom(game, game.doom)
    assert game.awakened and game.outcome == "loss"


def test_omen_track_advances_and_matching_gates_advance_doom(make_game: MakeGame) -> None:
    game = make_game(old_one="yog_sothoth")
    game.locations["london"].gate = True  # blue gate
    doom = game.doom
    rules.advance_omen(game, 1)  # green -> blue_a
    assert game.omen_color == "blue"
    assert game.doom == doom - 1


def test_azathoth_green_omen_advances_doom_by_eldritch_tokens(make_game: MakeGame) -> None:
    game = make_game(old_one="azathoth")
    assert game.green_eldritch == 1
    game.omen_index = 3  # blue_b, next is green
    doom = game.doom
    rules.advance_omen(game, 1)
    assert game.omen_space == "green"
    assert game.doom == doom - 1


def test_spawning_a_gate_spawns_a_monster(make_game: MakeGame) -> None:
    game = make_game()
    game.monster_cup = ["ghost"]
    game.gate_deck.cards.insert(0, "arkham")
    rules.spawn_gate(game)
    assert game.locations["arkham"].gate
    assert len(game.locations["arkham"].monsters) == 1


def test_monster_surge_spawns_at_matching_gates_or_spawns_a_new_gate(make_game: MakeGame) -> None:
    game = make_game()
    # No matching green gate -> spawns 1 Gate instead
    rules.monster_surge(game)
    assert len(game.open_gates()) == 1

    # Matching green gate at san_francisco -> spawns monster_surge monsters there
    clear_gates = list(game.open_gates())
    for g in clear_gates:
        game.locations[g].gate = False
    game.locations["san_francisco"].gate = True
    game.omen_index = 0  # green
    game.monster_cup = ["cultist"] * 5
    before = len(game.locations["san_francisco"].monsters)
    rules.monster_surge(game)
    assert len(game.locations["san_francisco"].monsters) == before + game.reference.monster_surge


def test_solving_three_mysteries_wins_before_awakening(make_game: MakeGame) -> None:
    game = make_game()
    game.solved_mysteries = ["m1", "m2"]
    game.active_mystery = MysteryState("az_omen_of_devastation", 1)
    rules.add_mystery_progress(game, game.active_mystery, 1)
    assert game.outcome is None
    rules.solve_ready_mystery(game)
    assert game.outcome == "win"


def test_roaming_monster_steps_toward_the_nearest_investigator(make_game: MakeGame) -> None:
    game = make_game()
    for inv in game.investigators:
        inv.location = "rome"
    game.locations["space_16"].monsters.append(MonsterInst(game.uid(), "goat_spawn"))
    game.locations["space_16"].monsters.append(MonsterInst(game.uid(), "ghoul"))
    rules.move_monsters(game)
    # goat_spawn roams from space_16 toward rome (via istanbul or space_14); ghoul does not roam
    assert [m.def_id for m in game.locations["space_16"].monsters] == ["ghoul"]
    assert any(
        m.def_id == "goat_spawn"
        for loc in ("istanbul", "space_14")
        for m in game.locations[loc].monsters
    )


def test_monster_cup_runs_out(make_game: MakeGame) -> None:
    game = make_game()
    game.monster_cup = []
    assert rules.spawn_monster(game, "rome") is None


def test_condition_back_is_hidden_until_flipped(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "debt")
    gained = script.texts("condition")[-1]
    for back in game.content.conditions["debt"].backs:
        assert back.text not in gained
    before = len(script.events)
    rules.flip_condition(game, inv, inv.conditions[0])
    resolved = " ".join(e.text for e in script.events[before:])
    assert any(b.text in resolved for b in game.content.conditions["debt"].backs)
    assert not inv.conditions


def test_condition_is_unique(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    assert rules.gain_condition(game, inv, "paranoia")
    assert not rules.gain_condition(game, inv, "paranoia")
    assert len(inv.conditions) == 1

