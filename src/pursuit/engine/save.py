"""Save and load games as JSON. Definitions are not saved, only ids that point at them."""

from __future__ import annotations

import json
import os
import random
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from pursuit.content.loader import Content
from pursuit.engine.state import (
    ActiveMythos,
    AssetCard,
    ConditionInst,
    Deck,
    FallenInvestigator,
    Game,
    Investigator,
    LocationState,
    MonsterInst,
    MysteryState,
    Phase,
)

SAVE_VERSION = 4


class SaveError(Exception):
    pass


def saves_dir() -> Path:
    override = os.environ.get("PURSUIT_SAVES")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "eldritch-pursuit" / "saves"


def _deck(deck: Deck[Any], encode: Any = lambda x: x) -> dict[str, list[Any]]:
    return {"cards": [encode(c) for c in deck.cards], "discards": [encode(c) for c in deck.discards]}


def _card_deck(deck: Deck[AssetCard]) -> dict[str, list[Any]]:
    return _deck(deck, asdict)


def to_dict(game: Game) -> dict[str, Any]:
    version, internal, gauss = game.rng.getstate()
    return {
        "version": SAVE_VERSION,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "seed": game.seed,
        "rng": [version, list(internal), gauss],
        "old_one": game.old_one_id,
        "difficulty": game.difficulty,
        "doom": game.doom,
        "start_doom": game.start_doom,
        "omen_index": game.omen_index,
        "green_eldritch": game.green_eldritch,
        "sheet_tokens": game.sheet_tokens,
        "round": game.round,
        "phase": game.phase.value,
        "turn_index": game.turn_index,
        "lead_seat": game.lead_seat,
        "awakened": game.awakened,
        "active_expedition": game.active_expedition,
        "mystery_deck": list(game.mystery_deck),
        "active_mystery": asdict(game.active_mystery) if game.active_mystery else None,
        "solved_mysteries": list(game.solved_mysteries),
        "final_mystery": asdict(game.final_mystery) if game.final_mystery else None,
        "investigators": [asdict(i) for i in game.investigators],
        "locations": {k: asdict(v) for k, v in game.locations.items()},
        "reserve": [asdict(c) for c in game.reserve],
        "asset_deck": _card_deck(game.asset_deck),
        "spell_deck": _card_deck(game.spell_deck),
        "artifact_deck": _card_deck(game.artifact_deck),
        "encounter_decks": {k: _deck(v) for k, v in game.encounter_decks.items()},
        "mythos_deck": list(game.mythos_deck),
        "mythos_discards": list(game.mythos_discards),
        "active_mythos": [asdict(m) for m in game.active_mythos],
        "gate_deck": _deck(game.gate_deck),
        "clue_deck": _deck(game.clue_deck),
        "other_world_deck": _deck(game.other_world_deck),
        "monster_cup": list(game.monster_cup),
        "set_aside": list(game.set_aside),
        "epics_gone": list(game.epics_gone),
        "unused_investigators": list(game.unused_investigators),
        "next_uid": game.next_uid,
        "outcome": game.outcome,
        "outcome_reason": game.outcome_reason,
        "log": list(game.log),
        "stats": dict(game.stats),
    }


def _cards(raw: list[dict[str, Any]]) -> list[AssetCard]:
    return [AssetCard(**c) for c in raw]


def _load_card_deck(raw: dict[str, Any]) -> Deck[AssetCard]:
    return Deck(_cards(raw["cards"]), _cards(raw["discards"]))


def _load_deck(raw: dict[str, Any]) -> Deck[str]:
    return Deck(list(raw["cards"]), list(raw["discards"]))


def _investigator(raw: dict[str, Any]) -> Investigator:
    data = dict(raw)
    data["assets"] = _cards(data["assets"])
    data["conditions"] = [ConditionInst(**c) for c in data["conditions"]]
    data["tickets"] = list(data.get("tickets", []))
    return Investigator(**data)


def _fallen(raw: dict[str, Any]) -> FallenInvestigator:
    data = dict(raw)
    data["assets"] = _cards(data.get("assets", []))
    data["tickets"] = list(data.get("tickets", []))
    return FallenInvestigator(**data)


def _location(raw: dict[str, Any]) -> LocationState:
    data = dict(raw)
    data["monsters"] = [MonsterInst(**m) for m in data["monsters"]]
    data["fallen"] = [_fallen(f) for f in data.get("fallen", [])]
    return LocationState(**data)


def from_dict(content: Content, data: dict[str, Any]) -> Game:
    if data.get("version") != SAVE_VERSION:
        raise SaveError(f"this save uses format {data.get('version')}, but the game reads format {SAVE_VERSION}")
    try:
        rng = random.Random()
        version, internal, gauss = data["rng"]
        rng.setstate((version, tuple(internal), gauss))
        game = Game(
            content=content,
            rng=rng,
            seed=data["seed"],
            old_one_id=data["old_one"],
            difficulty=data["difficulty"],
            investigators=[_investigator(i) for i in data["investigators"]],
            locations={k: _location(v) for k, v in data["locations"].items()},
            doom=data["doom"],
            start_doom=data["start_doom"],
            omen_index=data.get("omen_index", 0),
            green_eldritch=data.get("green_eldritch", 0),
            sheet_tokens=data.get("sheet_tokens", 0),
            round=data["round"],
            phase=Phase(data["phase"]),
            turn_index=data["turn_index"],
            lead_seat=data.get("lead_seat", 0),
            awakened=data["awakened"],
            active_expedition=data.get("active_expedition"),
            mystery_deck=list(data["mystery_deck"]),
            active_mystery=MysteryState(**data["active_mystery"]) if data.get("active_mystery") else None,
            solved_mysteries=list(data.get("solved_mysteries", [])),
            final_mystery=MysteryState(**data["final_mystery"]) if data.get("final_mystery") else None,
            reserve=_cards(data["reserve"]),
            asset_deck=_load_card_deck(data["asset_deck"]),
            spell_deck=_load_card_deck(data["spell_deck"]),
            artifact_deck=_load_card_deck(data["artifact_deck"]),
            encounter_decks={k: _load_deck(v) for k, v in data["encounter_decks"].items()},
            mythos_deck=list(data["mythos_deck"]),
            mythos_discards=list(data.get("mythos_discards", [])),
            active_mythos=[ActiveMythos(**m) for m in data.get("active_mythos", [])],
            gate_deck=_load_deck(data["gate_deck"]),
            clue_deck=_load_deck(data["clue_deck"]),
            other_world_deck=_load_deck(data["other_world_deck"]) if "other_world_deck" in data else Deck(),
            monster_cup=list(data["monster_cup"]),
            set_aside=list(data.get("set_aside", [])),
            epics_gone=list(data.get("epics_gone", [])),
            unused_investigators=list(data["unused_investigators"]),
            next_uid=data["next_uid"],
            outcome=data["outcome"],
            outcome_reason=data["outcome_reason"],
            log=list(data["log"]),
            stats=dict(data["stats"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SaveError(f"the save file is damaged: {exc}") from None
    _check_refs(content, game)
    return game


def _check_refs(content: Content, game: Game) -> None:
    """Reject a save that refers to content this version of the game does not have."""
    missing: list[str] = []

    def need(table: dict[str, Any], key: str, what: str) -> None:
        if key not in table:
            missing.append(f"{what} '{key}'")

    need(content.old_ones, game.old_one_id, "Old One")
    need(content.rules.difficulties, game.difficulty, "difficulty")
    for inv in game.investigators:
        need(content.investigators, inv.def_id, "investigator")
        for card in inv.assets:
            need(content.assets, card.def_id, "asset")
        for cond in inv.conditions:
            need(content.conditions, cond.def_id, "condition")
    for loc_id, state in game.locations.items():
        need(content.locations, loc_id, "location")
        if state.other_world is not None and state.other_world not in content.other_worlds:
            missing.append(f"Other World '{state.other_world}'")
        for monster in state.monsters:
            need(content.monsters, monster.def_id, "monster")
        for fallen in state.fallen:
            need(content.investigators, fallen.def_id, "investigator")
            for card in fallen.assets:
                need(content.assets, card.def_id, "asset")
    for world in game.other_world_deck.cards + game.other_world_deck.discards:
        if world not in content.other_worlds:
            missing.append(f"Other World '{world}'")
    for name in game.encounter_decks:
        need(content.decks, name, "encounter deck")
        for enc in game.encounter_decks[name].cards + game.encounter_decks[name].discards:
            need(content.encounters, enc, "encounter")
    for mid in game.mythos_deck + game.mythos_discards + [m.def_id for m in game.active_mythos]:
        need(content.mythos, mid, "mythos")
    if missing:
        raise SaveError("the save refers to content that no longer exists: " + ", ".join(missing[:5]))


def save_game(game: Game, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(to_dict(game), indent=1), encoding="utf-8")
    tmp.replace(path)


def load_game(content: Content, path: Path) -> Game:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SaveError(f"no save file at {path}") from None
    except json.JSONDecodeError as exc:
        raise SaveError(f"the save file is not valid JSON: {exc.msg}") from None
    return from_dict(content, data)


def list_saves() -> list[tuple[Path, dict[str, Any]]]:
    """Every readable save file, newest first, with a short summary of each."""
    folder = saves_dir()
    if not folder.is_dir():
        return []
    found = []
    for path in folder.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        summary = {
            "old_one": data.get("old_one", "?"),
            "round": data.get("round", "?"),
            "investigators": [i.get("name", "?") for i in data.get("investigators", [])],
            "saved_at": data.get("saved_at", ""),
            "outcome": data.get("outcome"),
        }
        found.append((path, summary))
    found.sort(key=lambda item: item[0].stat().st_mtime, reverse=True)
    return found

