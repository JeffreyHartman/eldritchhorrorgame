"""Tests for `content.loader`: the shipped data loads, and broken data fails with a clear path."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from conftest import Script, clear_board
from pursuit.bots import RandomBot
from pursuit.content.defs import SKILLS
from pursuit.content.loader import DEFAULT_DATA_DIR, Content, load_content
from pursuit.content.reader import ContentError, Reader
from pursuit.effects.base import Ctx, run_effects
from pursuit.engine import rules
from pursuit.engine.setup import GameConfig, new_game


def test_shipped_content_has_the_planned_size(content: Content) -> None:
    assert len(content.investigators) >= 8
    assert len(content.old_ones) >= 4
    assert len(content.locations) >= 30
    assert len(content.encounters) >= 60
    assert len(content.portents) >= 20
    assert sum(1 for a in content.assets.values() if a.kind == "spell") >= 8
    assert sum(1 for a in content.assets.values() if a.kind == "relic") >= 6


def test_every_location_has_a_deck_and_a_route(content: Content) -> None:
    for loc in content.locations.values():
        assert content.deck_for_location(loc.id) in content.decks
        assert content.adjacency[loc.id]


def test_routes_are_symmetric(content: Content) -> None:
    for here, links in content.adjacency.items():
        for there, kind in links:
            assert (here, kind) in content.adjacency[there]


def test_map_positions_fit_the_map_art(content: Content) -> None:
    art = (Path(DEFAULT_DATA_DIR).parent / "ui" / "art" / "map.txt").read_text().splitlines()
    for loc in content.locations.values():
        x, y = loc.pos
        assert 0 <= y < len(art), loc.id
        assert x >= 0 and x + 1 < 100, loc.id


def test_every_investigator_has_all_skills(content: Content) -> None:
    for inv in content.investigators.values():
        assert set(inv.skills) == set(SKILLS)


@pytest.mark.parametrize("seed", range(3))
def test_every_encounter_resolves_without_error(content: Content, seed: int) -> None:
    game = new_game(content, GameConfig("cthulhu", ("hollis_grange", "kenji_mori"), seed=seed), RandomBot(seed))
    for enc in content.encounters.values():
        clear_board(game)
        inv = game.investigators[0]
        inv.health, inv.sanity, inv.defeated = inv.max_health, inv.max_sanity, False
        inv.funds, inv.clues = 5, 2
        loc = (
            enc.deck
            if enc.deck in content.locations
            else next(loc.id for loc in content.locations.values() if loc.terrain == enc.deck or enc.deck == "rift")
        )
        inv.location = loc
        game.locations[loc].rift = enc.deck == "rift"
        run_effects(enc.effects, Ctx(game, inv, f"encounter:{enc.id}"))
        game.outcome = None


@pytest.mark.parametrize("dread", [1, 2, 3])
def test_every_portent_tier_resolves_without_error(content: Content, dread: int) -> None:
    game = new_game(
        content, GameConfig("king_in_yellow", ("tug_mulroney", "ada_penhallow"), seed=dread), RandomBot(dread)
    )
    game.dread = dread
    for portent in content.portents.values():
        if portent.min_dread > dread:
            continue
        run_effects(portent.tier(dread).effects, Ctx(game, None, f"portent:{portent.id}"))
        rules.process_defeats(game)
        game.outcome = None
        game.doom = max(game.doom, 5)


def test_every_old_one_hook_resolves_without_error(content: Content) -> None:
    for old in content.old_ones.values():
        game = new_game(content, GameConfig(old.id, ("tug_mulroney", "ada_penhallow"), seed=1), RandomBot(1))
        run_effects(old.night, Ctx(game, None, "night"))
        rules.awaken(game)
        assert game.awakened and game.final_rite is not None
        run_effects(old.awakening.night, Ctx(game, None, "awake"))


def test_every_ability_resolves_without_error(content: Content) -> None:
    game = new_game(content, GameConfig("cthulhu", ("tug_mulroney", "ada_penhallow"), seed=3), RandomBot(3))
    inv = game.investigators[0]
    for adef in content.assets.values():
        if adef.action is not None:
            inv.health, inv.sanity, inv.funds, inv.trophies = inv.max_health, inv.max_sanity, 9, 2
            run_effects(adef.action.effects, Ctx(game, inv, adef.id))
    for idef in content.investigators.values():
        if idef.action is not None:
            inv.health, inv.sanity, inv.funds, inv.trophies = inv.max_health, inv.max_sanity, 9, 2
            run_effects(idef.action.effects, Ctx(game, inv, idef.id))
    for cdef in content.conditions.values():
        for outcome in cdef.outcomes:
            inv.health, inv.sanity, inv.defeated = inv.max_health, inv.max_sanity, False
            run_effects(outcome.effects, Ctx(game, inv, cdef.id))
    game.outcome = None


# --- broken data ----------------------------------------------------------------------


@pytest.fixture
def data_copy(tmp_path: Path) -> Path:
    target = tmp_path / "data"
    shutil.copytree(DEFAULT_DATA_DIR, target)
    return target


def edit_json(path: Path, change: Callable[[Any], object]) -> None:
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


def load_from(path: Path) -> Content:
    return load_content.__wrapped__(str(path))


def test_unknown_effect_type_names_the_path(data_copy: Path) -> None:
    edit_json(data_copy / "encounters" / "city.json", lambda d: d[0]["effects"].append({"type": "summon_cake"}))
    with pytest.raises(ContentError, match=r"city\.json\[0\]\.effects\[1\]: unknown effect type 'summon_cake'"):
        load_from(data_copy)


def test_typo_in_a_field_name_is_rejected(data_copy: Path) -> None:
    edit_json(data_copy / "monsters.json", lambda d: d[0].update({"toughnes": 3}))
    with pytest.raises(ContentError, match="unknown field"):
        load_from(data_copy)


def test_route_to_a_missing_location_is_rejected(data_copy: Path) -> None:
    edit_json(data_copy / "map.json", lambda d: d["routes"].append(["paris", "atlantis", "sea"]))
    with pytest.raises(ContentError, match="unknown location 'atlantis'"):
        load_from(data_copy)


def test_reference_to_a_missing_condition_is_rejected(data_copy: Path) -> None:
    def change(d: list) -> None:
        d[0]["effects"] = [{"type": "gain_condition", "id": "lycanthropy"}]

    edit_json(data_copy / "encounters" / "sea.json", change)
    with pytest.raises(ContentError, match="unknown condition 'lycanthropy'"):
        load_from(data_copy)


def test_world_effect_that_needs_an_investigator_is_rejected(data_copy: Path) -> None:
    edit_json(
        data_copy / "portents.json", lambda d: d[0]["tiers"][0]["effects"].append({"type": "health", "amount": -1})
    )
    with pytest.raises(ContentError, match="needs an investigator"):
        load_from(data_copy)


def test_missing_hub_deck_is_rejected(data_copy: Path) -> None:
    (data_copy / "encounters" / "paris.json").unlink()
    with pytest.raises(ContentError, match="missing deck file"):
        load_from(data_copy)


def test_portent_tier_count_must_match_min_dread(data_copy: Path) -> None:
    edit_json(data_copy / "portents.json", lambda d: d[0].update({"min_dread": 2}))
    with pytest.raises(ContentError, match="needs 2 tier"):
        load_from(data_copy)


def test_invalid_json_reports_the_line(data_copy: Path) -> None:
    (data_copy / "rules.json").write_text('{\n  "actions_per_turn": 2,\n}')
    with pytest.raises(ContentError, match="invalid JSON at line 3"):
        load_from(data_copy)


def test_reader_rejects_a_boolean_where_an_integer_belongs() -> None:
    r = Reader({"amount": True}, "x")
    with pytest.raises(ContentError, match="expected an integer, got a boolean"):
        r.get_int("amount")


def test_script_fixture_is_usable(script: Script) -> None:
    assert script.events == []
