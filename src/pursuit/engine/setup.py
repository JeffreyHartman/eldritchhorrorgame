"""Create a new game from content and a setup choice."""

from __future__ import annotations

import random
from dataclasses import dataclass

from pursuit.content.defs import MARKET_KINDS
from pursuit.content.loader import Content
from pursuit.controller import Controller
from pursuit.effects.base import Ctx, run_effects
from pursuit.engine import rules
from pursuit.engine.state import AssetCard, ConditionInst, Deck, Game, Investigator, LocationState, RiteState


class SetupError(ValueError):
    pass


@dataclass(frozen=True)
class GameConfig:
    old_one: str
    investigators: tuple[str, ...]
    difficulty: str = "normal"
    seed: int | None = None


def new_game(content: Content, config: GameConfig, ctl: Controller | None = None) -> Game:
    _validate(content, config)
    seed = config.seed if config.seed is not None else random.SystemRandom().randrange(2**31)
    rng = random.Random(seed)
    old = content.old_ones[config.old_one]
    diff = content.rules.difficulties[config.difficulty]
    doom = max(old.dread_at[0] + 1, old.doom + diff.doom_mod)
    game = Game(
        content=content,
        rng=rng,
        seed=seed,
        old_one_id=old.id,
        difficulty=diff.id,
        investigators=[],
        locations={loc_id: LocationState(loc_id) for loc_id in content.locations},
        doom=doom,
        start_doom=doom,
    )
    if ctl is not None:
        game.ctl = ctl

    _build_decks(game)
    game.unused_investigators = sorted(
        (i for i in content.investigators if i not in config.investigators),
        key=lambda i: content.investigators[i].name,
    )
    for seat, def_id in enumerate(config.investigators):
        game.investigators.append(create_investigator(game, def_id, seat))
    rules.refill_market(game)

    n = len(config.investigators)
    chosen = rng.sample(list(old.rites), old.rites_needed)
    game.rites = [RiteState(r.id, r.required(n)) for r in chosen]

    for _ in range(max(0, content.rules.start_rifts + diff.start_rifts_mod)):
        rules.open_rift(game)
    for _ in range(content.rules.start_clues):
        rules.spawn_clue(game)
    rules.setup_rite_monsters(game)
    run_effects(old.setup, Ctx(game, None, f"setup:{old.id}"))
    rules.update_dread(game)
    return game


def _validate(content: Content, config: GameConfig) -> None:
    if config.old_one not in content.old_ones:
        raise SetupError(f"unknown Old One '{config.old_one}'")
    if config.difficulty not in content.rules.difficulties:
        raise SetupError(f"unknown difficulty '{config.difficulty}'")
    count = len(config.investigators)
    if not 1 <= count <= content.rules.max_investigators:
        raise SetupError(f"choose 1 to {content.rules.max_investigators} investigators, not {count}")
    if len(set(config.investigators)) != count:
        raise SetupError("each investigator can be chosen only once")
    for inv_id in config.investigators:
        if inv_id not in content.investigators:
            raise SetupError(f"unknown investigator '{inv_id}'")


def _build_decks(game: Game) -> None:
    content = game.content
    rng = game.rng

    def cards(kinds: tuple[str, ...]) -> list[AssetCard]:
        out: list[AssetCard] = []
        for adef in content.assets.values():
            if adef.kind in kinds:
                out.extend(AssetCard(game.uid(), adef.id) for _ in range(adef.count))
        rng.shuffle(out)
        return out

    game.asset_deck = Deck(cards(MARKET_KINDS))
    game.spell_deck = Deck(cards(("spell",)))
    game.relic_deck = Deck(cards(("relic",)))
    for name, ids in content.decks.items():
        deck = list(ids)
        rng.shuffle(deck)
        game.encounter_decks[name] = Deck(deck)
    portents = [p.id for p in content.portents.values() if p.min_dread == 1]
    rng.shuffle(portents)
    game.portent_deck = Deck(portents)
    rifts = [loc.id for loc in content.locations.values() if loc.rift_site]
    rng.shuffle(rifts)
    game.rift_deck = Deck(rifts)
    clues = [loc.id for loc in content.locations.values() if loc.terrain != "sea"]
    rng.shuffle(clues)
    game.clue_deck = Deck(clues)
    cup = []
    for mdef in content.monsters.values():
        if not mdef.epic:
            cup.extend([mdef.id] * mdef.count)
    cup.extend(game.old_one.monsters)
    game.monster_cup = sorted(cup)


def create_investigator(game: Game, def_id: str, seat: int) -> Investigator:
    content = game.content
    d = content.investigators[def_id]
    diff = content.rules.difficulties[game.difficulty]
    inv = Investigator(
        seat=seat,
        def_id=d.id,
        name=d.name,
        health=d.health,
        sanity=d.sanity,
        max_health=d.health,
        max_sanity=d.sanity,
        skills=dict(d.skills),
        location=d.start,
        funds=max(0, d.funds + diff.funds_mod),
        clues=d.clues,
    )
    inv.assets = [rules.new_card(game, a) for a in d.assets]
    inv.conditions = [ConditionInst(game.uid(), c) for c in d.conditions]
    return inv
