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
            {"type": "funds", "amount": 3},
            {"type": "clues", "amount": 2},
            {"type": "trophies", "amount": 1},
        ],
    )
    assert (inv.health, inv.sanity, inv.funds, inv.clues, inv.trophies) == (5, 5, 5, 2, 1)


def test_test_effect_branches(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    effect = [
        {
            "type": "test",
            "skill": "wits",
            "pass": [{"type": "clues", "amount": 1}],
            "fail": [{"type": "funds", "amount": -1}],
        }
    ]
    set_dice(game, 6, 1, 1, 1, 1)
    run(game, inv, effect)
    set_dice(game, 1, 1, 1, 1, 1)
    run(game, inv, effect)
    assert inv.clues == 1 and inv.funds == 1


def test_later_effects_stop_after_defeat(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    run(game, inv, [{"type": "health", "amount": -99}, {"type": "funds", "amount": 5}])
    assert inv.defeated and inv.funds == 2


def test_choice_respects_requirements(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.funds = 0
    script.add("effect_choice", lambda opts: next(i for i, o in enumerate(opts) if o.enabled))
    run(
        game,
        inv,
        [
            {
                "type": "choice",
                "options": [
                    {"label": "Rich", "requires": {"funds_at_least": 5}, "effects": [{"type": "clues", "amount": 5}]},
                    {"label": "Poor", "effects": [{"type": "clues", "amount": 1}]},
                ],
            }
        ],
    )
    assert inv.clues == 1


def test_pay_runs_then_or_else(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    data = [
        {
            "type": "pay",
            "cost": {"funds": 2},
            "then": [{"type": "clues", "amount": 1}],
            "else": [{"type": "sanity", "amount": -1}],
        }
    ]
    script.add("pay", True)
    run(game, inv, data)
    assert inv.funds == 0 and inv.clues == 1
    script.add("pay", True)
    run(game, inv, data)
    assert inv.sanity == inv.max_sanity - 1, "cannot pay with 0 Funds, so the else branch runs"


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
                {"weight": 1, "effects": [{"type": "funds", "amount": 1}]},
            ],
        }
    ]
    results = []
    for _ in range(2):
        game = make_game(seed=99)
        inv = first(game)
        for _ in range(10):
            run(game, inv, data)
        results.append((inv.clues, inv.funds))
    assert results[0] == results[1]
    assert sum(results[0]) == 10 + 2


def test_gain_and_lose_assets(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    run(game, inv, [{"type": "gain_asset", "kind": "spell"}, {"type": "gain_asset", "id": "bronze_sickle"}])
    names = [game.asset_def(c).id for c in inv.assets]
    assert "bronze_sickle" in names
    assert any(game.asset_def(c).kind == "spell" for c in inv.assets)
    run(game, inv, [{"type": "lose_asset", "kind": "spell"}])
    assert not any(game.asset_def(c).kind == "spell" for c in inv.assets)
    run(game, inv, [{"type": "lose_asset", "all": True}])
    assert inv.assets == []


def test_gain_from_market_refills_it(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    run(game, inv, [{"type": "gain_asset", "source": "market"}])
    assert len(game.market) == game.content.rules.market_size


def test_conditions_and_remove_self(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    run(game, inv, [{"type": "gain_condition", "id": "hexed"}, {"type": "gain_condition", "id": "paranoia"}])
    run(game, inv, [{"type": "remove_condition", "trait": "madness"}])
    assert [c.def_id for c in inv.conditions] == ["hexed"]
    run_effects(parse_effects([{"type": "remove_self"}], "t"), Ctx(game, inv, "t", condition=inv.conditions[0]))
    assert inv.conditions == []


def test_improve_skill_has_a_cap(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    for _ in range(5):
        run(game, inv, [{"type": "improve_skill", "skill": "lore"}])
    assert inv.skill("lore") == inv.skills["lore"] + game.content.rules.max_improvement


def test_move_keywords(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    inv.location = "sahara"
    run(game, inv, [{"type": "move", "to": "nearest_city"}])
    assert game.content.locations[inv.location].terrain == "city"
    run(game, inv, [{"type": "move", "to": "start"}])
    assert inv.location == "chicago"
    script.add("move", "Yukon")
    run(game, inv, [{"type": "move", "to": "choose_within", "range": 1}])
    assert inv.location == "yukon"


def test_delay_skips_the_next_day_turn(make_game: MakeGame) -> None:
    from pursuit.engine.phases import day_turn

    game = make_game()
    inv = first(game)
    run(game, inv, [{"type": "delay"}])
    day_turn(game, inv)
    assert not inv.delayed
    assert inv.actions_taken == ["delayed", "delayed"]


def test_world_effects(make_game: MakeGame) -> None:
    game = make_game()
    run(game, None, [{"type": "open_rift", "count": 2}, {"type": "spawn_clue", "count": 2}])
    assert len(game.open_rifts()) == 2
    assert sum(s.clue for s in game.locations.values()) == 2
    monsters = sum(len(s.monsters) for s in game.locations.values())
    run(game, None, [{"type": "spawn_monster", "at": "rifts"}])
    assert sum(len(s.monsters) for s in game.locations.values()) == monsters + 2


def test_each_investigator_with_a_filter(make_game: MakeGame) -> None:
    game = make_game()
    a, b = game.investigators
    a.location = "north_atlantic"
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
    assert (a.clues, b.clues) == (1, 0)


def test_one_investigator_picks_lowest_sanity(make_game: MakeGame) -> None:
    game = make_game()
    a, b = game.investigators
    b.sanity = 1
    run(
        game, None, [{"type": "one_investigator", "pick": "lowest_sanity", "effects": [{"type": "clues", "amount": 1}]}]
    )
    assert (a.clues, b.clues) == (0, 1)


def test_ambush_spawns_and_fights(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    inv = first(game)
    script.add("combat", "Fight")
    set_dice(game, 6, 1, 1, 1, 1)
    run(game, inv, [{"type": "ambush", "id": "cultist"}])
    assert not game.locations[inv.location].monsters


def test_close_rift_effect(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    game.locations[inv.location].rift = True
    run(game, inv, [{"type": "close_rift"}])
    assert not game.locations[inv.location].rift and inv.trophies == 1


def test_doom_effects(make_game: MakeGame) -> None:
    game = make_game()
    doom = game.doom
    run(game, None, [{"type": "advance_doom", "amount": 2}, {"type": "retreat_doom", "amount": 1}])
    assert game.doom == doom - 1


def test_rite_progress_effect(make_game: MakeGame, script: Script) -> None:
    game = make_game()
    game.rites[0].def_id = "ky_lake"
    game.rites[0].required = 4
    run(game, None, [{"type": "rite_progress", "amount": 2}])
    assert any(r.progress == 2 for r in game.rites)


def test_resolve_conditions_reveals_outcomes(make_game: MakeGame) -> None:
    game = make_game()
    inv = first(game)
    rules.gain_condition(game, inv, "blessed")  # its only outcome removes it
    run(game, inv, [{"type": "resolve_conditions", "trait": "boon"}])
    assert inv.conditions == []


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"type": "health"}, "missing required field 'amount'"),
        ({"type": "health", "amount": 0}, "cannot be 0"),
        ({"type": "test", "skill": "luck"}, "not one of"),
        ({"type": "choice", "options": [{"label": "only", "effects": []}]}, "at least 2 options"),
        ({"type": "move", "to": "choose_within"}, "range"),
        ({"type": "pay", "cost": {}}, "needs a cost"),
        ({"type": "gain_asset", "source": "market", "kind": "spell"}, "market kind"),
        ({"type": "remove_condition"}, "needs 'id' or 'trait'"),
    ],
)
def test_bad_effect_data_is_rejected(data: dict[str, Any], message: str) -> None:
    with pytest.raises(ContentError, match=message):
        parse_effects([data], "test")
