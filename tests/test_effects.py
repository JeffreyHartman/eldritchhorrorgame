"""Tests for each effect type in `effects.library`, parsed from JSON-shaped data."""

from __future__ import annotations

from typing import Any

import pytest

from conftest import MakeGame, Script, first, set_dice
from pursuit.content.reader import ContentError
from pursuit.effects.base import Ctx, parse_effects, run_effects
from pursuit.engine import rules
from pursuit.engine.state import Game, Investigator


def run(game: Game, inv: Investigator | None, data: list[dict[str, Any]]) -> None:
    run_effects(parse_effects(data, "test"), Ctx(game, inv, "test"))


def test_resource_effects(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    inv.health = 3
    run(
        game,
        inv,
        [
            {"type": "health", "amount": 2},
            {"type": "sanity", "amount": -1},
            {"type": "clues", "amount": 2},
            {"type": "gain_ticket", "kind": "train"},
        ],
    )
    assert (inv.health, inv.sanity, inv.clues, inv.tickets) == (5, 3, 2, ["train"])


def test_test_effect_branches(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    effect = [
        {
            "type": "test",
            "skill": "observation",
            "pass": [{"type": "clues", "amount": 1}],
            "fail": [{"type": "sanity", "amount": -1}],
        }
    ]
    set_dice(game, 6, 1)
    run(game, inv, effect)
    set_dice(game, 1, 1)
    run(game, inv, effect)
    assert inv.clues == 1 and inv.sanity == inv.max_sanity - 1


def test_later_effects_stop_after_defeat(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    run(game, inv, [{"type": "health", "amount": -99}, {"type": "clues", "amount": 5}])
    assert inv.defeated and inv.clues == 0


def test_choice_respects_requirements(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.clues = 0
    script.add("effect_choice", lambda opts: next(i for i, o in enumerate(opts) if o.enabled))
    run(
        game,
        inv,
        [
            {
                "type": "choice",
                "options": [
                    {
                        "label": "Has Clues",
                        "requires": {"clues_at_least": 5},
                        "effects": [{"type": "clues", "amount": 5}],
                    },
                    {"label": "No Clues", "effects": [{"type": "clues", "amount": 1}]},
                ],
            }
        ],
    )
    assert inv.clues == 1


def test_pay_runs_then_or_else(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.clues = 2
    data = [
        {
            "type": "pay",
            "cost": {"clues": 2},
            "then": [{"type": "gain_ticket", "kind": "ship"}],
            "else": [{"type": "sanity", "amount": -1}],
        }
    ]
    script.add("pay", True)
    run(game, inv, data)
    assert inv.clues == 0 and inv.tickets == ["ship"]
    script.add("pay", True)
    run(game, inv, data)
    assert inv.sanity == inv.max_sanity - 1, "cannot pay with 0 Clues, so the else branch runs"


def test_if_checks_the_investigator(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    data = [
        {
            "type": "if",
            "has": {"asset_trait": "weapon"},
            "then": [{"type": "clues", "amount": 1}],
            "else": [{"type": "clues", "amount": 3}],
        }
    ]
    run(game, inv, data)
    assert inv.clues == 1
    inv.assets.clear()
    run(game, inv, data)
    assert inv.clues == 4


def test_random_is_deterministic_for_a_seed(make_game: MakeGame) -> None:
    data = [
        {
            "type": "random",
            "outcomes": [
                {"weight": 1, "effects": [{"type": "clues", "amount": 1}]},
                {"weight": 1, "effects": [{"type": "gain_ticket", "kind": "train"}]},
            ],
        }
    ]
    results = []
    for _ in range(2):
        game = make_game(seed=99)
        inv = first(game)
        for _ in range(4):
            run(game, inv, data)
        results.append((inv.clues, len(inv.tickets)))
    assert results[0] == results[1]


def test_gain_and_lose_assets(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    run(game, inv, [{"type": "gain_asset", "kind": "spell"}, {"type": "gain_asset", "id": "lightning_gun"}])
    names = [game.asset_def(c).id for c in inv.assets]
    assert "lightning_gun" in names
    assert any(game.asset_def(c).kind == "spell" for c in inv.assets)
    run(game, inv, [{"type": "lose_asset", "kind": "spell"}])
    assert not any(game.asset_def(c).kind == "spell" for c in inv.assets)
    run(game, inv, [{"type": "lose_asset", "all": True}])
    assert inv.assets == []


def test_gain_from_reserve_refills_it(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    run(game, inv, [{"type": "gain_asset", "source": "reserve"}])
    assert len(game.reserve) == game.content.rules.reserve_size


def test_conditions_and_remove_self(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    run(game, inv, [{"type": "gain_condition", "id": "cursed"}, {"type": "gain_condition", "id": "paranoia"}])
    run(game, inv, [{"type": "remove_condition", "trait": "madness"}])
    assert [c.def_id for c in inv.conditions] == ["cursed"]
    run_effects(parse_effects([{"type": "remove_self"}], "t"), Ctx(game, inv, "t", condition=inv.conditions[0]))
    assert inv.conditions == []


def test_improve_skill_has_a_cap_and_lily_chen_doubles(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    for _ in range(5):
        run(game, inv, [{"type": "improve_skill", "skill": "lore"}])
    assert inv.skill("lore") == inv.skills["lore"] + game.content.rules.max_improvement

    game2 = make_game(investigators=("lily_chen", "mark_harrigan"))
    lily = first(game2)
    run(game2, lily, [{"type": "improve_skill", "skill": "lore"}])
    assert lily.skill("lore") == lily.skills["lore"] + 2


def test_move_keywords(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.location = "the_amazon"
    run(game, inv, [{"type": "move", "to": "nearest_city"}])
    assert game.content.locations[inv.location].terrain == "city"
    run(game, inv, [{"type": "move", "to": "start"}])
    assert inv.location == "space_14"
    script.add("move", "Rome")
    run(game, inv, [{"type": "move", "to": "choose_within", "range": 1}])
    assert inv.location == "rome"


def test_delay_skips_the_next_action_turn(make_game: MakeGame) -> None:
    from pursuit.engine.phases import action_turn

    game = make_game(investigators=("silas_marsh", "akachi_onyele"))
    inv = first(game)
    run(game, inv, [{"type": "delay"}])
    action_turn(game, inv)
    assert not inv.delayed
    assert inv.actions_taken == ["delayed", "delayed"]


def test_world_effects(make_game: MakeGame) -> None:
    game = make_game()
    run(game, None, [{"type": "spawn_gate", "count": 2}, {"type": "spawn_clue", "count": 2}])
    assert len(game.open_gates()) == 2
    assert sum(len(s.clues) for s in game.locations.values()) == 2
    monsters = sum(len(s.monsters) for s in game.locations.values())
    run(game, None, [{"type": "spawn_monster", "at": "gates"}])
    assert sum(len(s.monsters) for s in game.locations.values()) == monsters + 2


def test_each_investigator_with_a_filter(make_game: MakeGame) -> None:
    game = make_game()
    a, b = game.investigators
    a.location = "space_2"
    run(
        game,
        None,
        [
            {
                "type": "each_investigator",
                "where": {"at": {"terrain": "sea"}},
                "effects": [{"type": "clues", "amount": 1}],
            }
        ],
    )
    assert (a.clues, b.clues) == (1, 1)  # Akachi starts with 1 Clue


def test_one_investigator_picks_lowest_sanity(make_game: MakeGame) -> None:
    game = make_game()
    a, b = game.investigators
    b.sanity = 1
    run(
        game, None, [{"type": "one_investigator", "pick": "lowest_sanity", "effects": [{"type": "clues", "amount": 1}]}]
    )
    assert (a.clues, b.clues) == (0, 2)


def test_ambush_spawns_fights_and_returns_to_cup_even_if_undefeated(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    # Shoggoth (toughness 3): Will 2 dice (5,5), Strength 7 dice (5,1,1,1,1,1,1) -> 1 wound, returned to cup
    set_dice(game, 5, 5, 5, 1, 1, 1, 1, 1, 1)
    run(game, inv, [{"type": "ambush", "id": "shoggoth"}])
    assert not game.locations[inv.location].monsters


def test_close_gate_effect(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    game.locations[inv.location].gate = True
    script.add("mystery_spend", False)
    run(game, inv, [{"type": "close_gate"}])
    assert not game.locations[inv.location].gate


def test_doom_effects(make_game: MakeGame) -> None:
    game = make_game()
    doom = game.doom
    run(game, None, [{"type": "advance_doom", "amount": 2}, {"type": "retreat_doom", "amount": 1}])
    assert game.doom == doom - 1


def test_mystery_progress_effect(make_game: MakeGame) -> None:
    game = make_game()
    assert game.active_mystery is not None
    game.active_mystery.required = 2
    run(game, None, [{"type": "mystery_progress", "amount": 1}])
    assert game.active_mystery.progress == 1


def test_flip_conditions_resolves_back_and_discards(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "amnesia")
    run(game, inv, [{"type": "flip_conditions", "id": "amnesia"}])
    assert not rules.has_condition(inv, "amnesia")


def test_flip_conditions_keeps_a_card_whose_back_says_flip(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "blessed")
    run(game, inv, [{"type": "flip_conditions", "trait": "boon"}])
    assert rules.has_condition(inv, "blessed")


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"type": "health"}, "missing required field 'amount'"),
        ({"type": "health", "amount": 0}, "cannot be 0"),
        ({"type": "test", "skill": "luck"}, "not one of"),
        ({"type": "choice", "options": [{"label": "only", "effects": []}]}, "at least 2 options"),
        ({"type": "move", "to": "choose_within"}, "range"),
        ({"type": "pay", "cost": {}}, "needs a cost"),
        ({"type": "gain_asset", "source": "reserve", "kind": "spell"}, "reserve kind"),
        ({"type": "remove_condition"}, "needs 'id' or 'trait'"),
    ],
)
def test_bad_effect_data_is_rejected(data: dict[str, Any], message: str) -> None:
    with pytest.raises(ContentError, match=message):
        parse_effects([data], "test")



def test_targeted_spell_flips_and_discards_the_casters_copy(make_game: MakeGame) -> None:
    from pursuit.engine import actions

    game = make_game(investigators=("akachi_onyele", "mark_harrigan"))
    caster, target = game.investigators
    target.location = caster.location
    owned = rules.new_card(game, "blessing_of_isis")
    caster.assets.append(owned)
    owned.back = 1
    set_dice(game, 1, 1)  # 0 successes: the back costs the caster 1 Health
    health = caster.health
    actions.perform(game, caster, ("asset", owned.uid))
    assert caster.health == health - 1 and not rules.has_condition(target, "blessed")


def test_discard_clue_removes_one_token_with_no_gain(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    game.locations[inv.location].clues = [inv.location, inv.location]
    clues = inv.clues
    run(game, inv, [{"type": "discard_clue"}])
    assert game.locations[inv.location].clues == [inv.location]
    assert inv.clues == clues


def test_discard_gate_removes_the_chosen_gate_without_closing_it(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    game.locations["arkham"].gate = True
    game.locations["tokyo"].gate = True
    script.add("choose_space", "Tokyo")
    run(game, None, [{"type": "discard_gate"}])
    assert game.open_gates() == ["arkham"]
    assert game.stats.get("gates_closed", 0) == 0


def test_choice_with_one_enabled_option_resolves_with_no_prompt(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.delayed = True
    sanity = inv.sanity = 1
    options = [
        {"label": "a", "requires": {"delayed": False}, "effects": []},
        {"label": "b", "effects": [{"type": "sanity", "amount": 1}]},
    ]
    run(game, inv, [{"type": "choice", "options": options}])
    assert not script.asked
    assert inv.sanity == sanity + 1
