"""Create a new game from content and a setup choice."""

from __future__ import annotations

import random
from dataclasses import dataclass

from pursuit.content.defs import MYTHOS_COLORS, RESERVE_KINDS
from pursuit.content.loader import Content
from pursuit.controller import Controller
from pursuit.effects.base import Ctx, run_effects
from pursuit.engine import rules
from pursuit.engine.state import AssetCard, ConditionInst, Deck, Game, Investigator, LocationState


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
    doom = max(1, old.doom + diff.doom_mod)
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
    rules.refill_reserve(game)
    rules.update_expedition(game)

    ref = game.reference
    gates = max(0, ref.spawn_gates + diff.start_gates_mod)
    for _ in range(gates):
        rules.spawn_gate(game)
    for _ in range(ref.spawn_clues):
        rules.spawn_clue(game)

    rules.draw_mystery(game)
    run_effects(old.setup, Ctx(game, None, f"setup:{old.id}"))
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
    old = game.old_one

    def cards(kinds: tuple[str, ...]) -> list[AssetCard]:
        out: list[AssetCard] = []
        for adef in content.assets.values():
            if adef.kind in kinds and adef.id != "bank_loan":
                out.extend(AssetCard(game.uid(), adef.id) for _ in range(adef.count))
        rng.shuffle(out)
        return out

    game.asset_deck = Deck(cards(RESERVE_KINDS))
    game.spell_deck = Deck(cards(("spell",)))
    game.artifact_deck = Deck(cards(("artifact",)))
    for name, ids in content.decks.items():
        deck = list(ids)
        rng.shuffle(deck)
        game.encounter_decks[name] = Deck(deck)

    by_color: dict[str, list[str]] = {c: [] for c in MYTHOS_COLORS}
    for mdef in content.mythos.values():
        by_color[mdef.color].append(mdef.id)
    for c in MYTHOS_COLORS:
        rng.shuffle(by_color[c])
    mythos_deck: list[str] = []
    for stage in old.stages:
        stage_cards: list[str] = []
        for color, count in (("green", stage.green), ("yellow", stage.yellow), ("blue", stage.blue)):
            stage_cards.extend(by_color[color][:count])
            del by_color[color][:count]
        rng.shuffle(stage_cards)
        mythos_deck.extend(stage_cards)
    game.mythos_deck = mythos_deck

    mysteries = [m.id for m in old.mysteries]
    rng.shuffle(mysteries)
    game.mystery_deck = mysteries

    gates = [loc.id for loc in content.locations.values() if loc.gate_color]
    rng.shuffle(gates)
    game.gate_deck = Deck(gates)

    clues = list(content.locations)
    rng.shuffle(clues)
    game.clue_deck = Deck(clues)

    other_worlds = list(content.other_worlds)
    rng.shuffle(other_worlds)
    game.other_world_deck = Deck(other_worlds)

    cup = []
    for mon_def in content.monsters.values():
        if not mon_def.epic:
            cup.extend([mon_def.id] * mon_def.count)
    for mon_id in old.set_aside:
        cup.remove(mon_id)
    game.set_aside = list(old.set_aside)
    game.monster_cup = sorted(cup)


def create_investigator(game: Game, def_id: str, seat: int) -> Investigator:
    content = game.content
    d = content.investigators[def_id]
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
        clues=d.clues,
        tickets=list(d.tickets)[: content.rules.max_tickets],
    )
    inv.assets = [rules.take_starting_card(game, a) for a in d.assets]
    inv.conditions = [ConditionInst(game.uid(), c) for c in d.conditions]
    return inv

