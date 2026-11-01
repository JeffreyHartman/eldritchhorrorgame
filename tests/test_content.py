"""Tests for `content.loader`: the shipped data loads, and broken data fails with a clear path."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from conftest import Script, clear_board, load_from
from pursuit.bots import RandomBot
from pursuit.content.defs import EXPANSIONS, SKILLS
from pursuit.content.loader import DEFAULT_DATA_DIR, Content, load_content
from pursuit.content.reader import ContentError, Reader
from pursuit.effects.base import Ctx, run_effects
from pursuit.engine import rules
from pursuit.engine.setup import GameConfig, new_game
from pursuit.engine.state import ActiveMythos


def test_shipped_content_has_the_planned_size(content: Content) -> None:
    assert len(content.investigators) >= 12
    assert len(content.old_ones) >= 4
    assert len(content.locations) == 36
    assert len(content.encounters) >= 45
    assert len(content.mythos) >= 20
    assert sum(1 for a in content.assets.values() if a.kind == "spell") >= 8
    assert sum(1 for a in content.assets.values() if a.kind == "artifact") >= 6


def test_every_location_has_a_route(content: Content) -> None:
    for loc in content.locations.values():
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
    game = new_game(content, GameConfig("cthulhu", ("mark_harrigan", "akachi_onyele"), seed=seed), RandomBot(seed))
    for enc in content.encounters.values():
        runs = [(enc.text, enc.effects, enc.location)]
        runs += [(s.text, s.effects, s.location) for s in enc.sections]
        for _text, effects, section_location in runs:
            clear_board(game)
            inv = game.investigators[0]
            inv.health, inv.sanity, inv.defeated = inv.max_health, inv.max_sanity, False
            inv.clues = 3
            loc = section_location or enc.location or "arkham"
            inv.location = loc
            game.locations[loc].gate = enc.deck.startswith("other_world")
            game.locations[loc].clues = [loc] if enc.deck.startswith("research_") else []
            run_effects(effects, Ctx(game, inv, f"encounter:{enc.id}"))
            game.outcome = None


def test_every_mythos_card_resolves_without_error(content: Content) -> None:
    game = new_game(content, GameConfig("yog_sothoth", ("mark_harrigan", "akachi_onyele"), seed=1), RandomBot(1))
    for mdef in content.mythos.values():
        active = ActiveMythos(mdef.id, eldritch=mdef.eldritch, rumor_space=mdef.rumor_space)
        game.active_mythos.append(active)
        run_effects(mdef.effects, Ctx(game, None, f"mythos:{mdef.id}", mythos=active))
        run_effects(mdef.reckoning, Ctx(game, None, f"mythos:{mdef.id}", mythos=active))
        if mdef.encounter_effects:
            inv = game.investigators[0]
            inv.health, inv.sanity, inv.defeated = inv.max_health, inv.max_sanity, False
            inv.clues = 4
            run_effects(mdef.encounter_effects, Ctx(game, inv, f"mythos:{mdef.id}", mythos=active))
        rules.process_defeats(game)
        game.outcome = None
        game.doom = max(game.doom, 5)


def test_every_old_one_hook_resolves_without_error(content: Content) -> None:
    for old in content.old_ones.values():
        game = new_game(content, GameConfig(old.id, ("mark_harrigan", "akachi_onyele"), seed=1), RandomBot(1))
        run_effects(old.reckoning, Ctx(game, None, "reckoning"))
        rules.awaken(game)
        assert game.awakened
        if not old.awakening.lose_immediately:
            assert game.final_mystery is not None
            run_effects(old.awakening.reckoning, Ctx(game, None, "awake_reckoning"))


def test_every_ability_and_back_resolves_without_error(content: Content) -> None:
    game = new_game(content, GameConfig("cthulhu", ("mark_harrigan", "akachi_onyele"), seed=3), RandomBot(3))
    inv = game.investigators[0]
    for adef in content.assets.values():
        if adef.action is not None:
            inv.health, inv.sanity, inv.clues = inv.max_health, inv.max_sanity, 3
            run_effects(adef.action.effects, Ctx(game, inv, adef.id))
        for back in adef.backs:
            inv.health, inv.sanity, inv.defeated = inv.max_health, inv.max_sanity, False
            monster = rules.spawn_monster(game, inv.location, trigger=False)
            run_effects(back.effects, Ctx(game, inv, adef.id, monster=monster))
    for idef in content.investigators.values():
        if idef.action is not None:
            inv.health, inv.sanity, inv.clues = inv.max_health, inv.max_sanity, 3
            run_effects(idef.action.effects, Ctx(game, inv, idef.id))
    for cdef in content.conditions.values():
        for back in cdef.backs:
            inv.health, inv.sanity, inv.defeated = inv.max_health, inv.max_sanity, False
            run_effects(back.effects, Ctx(game, inv, cdef.id))
    game.outcome = None


# --- broken data ----------------------------------------------------------------------


def edit_json(path: Path, change: Callable[[Any], object]) -> None:
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


def test_every_content_record_names_an_expansion(content: Content) -> None:
    groups = (
        content.locations,
        content.investigators,
        content.monsters,
        content.assets,
        content.conditions,
        content.mythos,
        content.encounters,
        content.old_ones,
    )
    records = [record for group in groups for record in group.values()]
    records += [mystery for old in content.old_ones.values() for mystery in old.mysteries]
    assert all(record.expansion in EXPANSIONS for record in records)


def test_unknown_effect_type_names_the_path(data_copy: Path) -> None:
    edit_json(
        data_copy / "encounters" / "general.json",
        lambda d: d[0]["sections"][0]["effects"].append({"type": "summon_cake"}),
    )
    with pytest.raises(
        ContentError, match=r"general\.json\[0\]\.sections\[0\]\.effects\[1\]: unknown effect type 'summon_cake'"
    ):
        load_from(data_copy)


@pytest.mark.parametrize("value", [None, "NOT_A_SET"])
def test_a_card_needs_a_known_expansion(data_copy: Path, value: str | None) -> None:
    path = data_copy / "spells.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if value is None:
        del data[0]["expansion"]
    else:
        data[0]["expansion"] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ContentError, match=r"spells\.json\[0\].*expansion"):
        load_content(str(data_copy))


def test_typo_in_a_field_name_is_rejected(data_copy: Path) -> None:
    edit_json(data_copy / "monsters.json", lambda d: d[0].update({"toughnes": 3}))
    with pytest.raises(ContentError, match="unknown field"):
        load_from(data_copy)


def test_route_to_a_missing_location_is_rejected(data_copy: Path) -> None:
    edit_json(data_copy / "map.json", lambda d: d["routes"].append(["london", "atlantis", "ship"]))
    with pytest.raises(ContentError, match="unknown location 'atlantis'"):
        load_from(data_copy)


def test_reference_to_a_missing_condition_is_rejected(data_copy: Path) -> None:
    def change(d: list) -> None:
        d[0]["sections"][0]["effects"] = [{"type": "gain_condition", "id": "lycanthropy"}]

    edit_json(data_copy / "encounters" / "general.json", change)
    with pytest.raises(ContentError, match="unknown condition 'lycanthropy'"):
        load_from(data_copy)


def test_world_effect_that_needs_an_investigator_is_rejected(data_copy: Path) -> None:
    edit_json(
        data_copy / "mythos.json", lambda d: d[0]["effects"].append({"type": "health", "amount": -1})
    )
    with pytest.raises(ContentError, match="needs an investigator"):
        load_from(data_copy)


def test_missing_encounter_deck_is_rejected(data_copy: Path) -> None:
    (data_copy / "encounters" / "europe.json").unlink()
    with pytest.raises(ContentError, match="missing deck file"):
        load_from(data_copy)


def test_mythos_stage_count_must_be_three(data_copy: Path) -> None:
    edit_json(data_copy / "old_ones.json", lambda d: d[0]["stages"].pop())
    with pytest.raises(ContentError, match="expected 3 stages"):
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

