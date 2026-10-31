"""Mutable game state. Everything here is saved and loaded by `pursuit.engine.save`."""

from __future__ import annotations

import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pursuit.content.defs import AssetDef, LocationDef, OldOneDef, RiteDef
    from pursuit.content.loader import Content
    from pursuit.controller import Controller


class Phase(StrEnum):
    DAY = "day"
    ENCOUNTER = "encounter"
    NIGHT = "night"


@dataclass
class AssetCard:
    uid: int
    def_id: str
    exhausted: bool = False


@dataclass
class ConditionInst:
    uid: int
    def_id: str


@dataclass
class MonsterInst:
    uid: int
    def_id: str
    wounds: int = 0


@dataclass
class LocationState:
    id: str
    clue: bool = False
    rift: bool = False
    monsters: list[MonsterInst] = field(default_factory=list)
    belongings: list[AssetCard] = field(default_factory=list)


@dataclass
class Investigator:
    seat: int
    def_id: str
    name: str
    health: int
    sanity: int
    max_health: int
    max_sanity: int
    skills: dict[str, int]
    location: str
    funds: int = 0
    clues: int = 0
    trophies: int = 0
    improvements: dict[str, int] = field(default_factory=dict)
    assets: list[AssetCard] = field(default_factory=list)
    conditions: list[ConditionInst] = field(default_factory=list)
    delayed: bool = False
    actions_taken: list[str] = field(default_factory=list)
    defeated: bool = False
    eliminated: bool = False

    def skill(self, name: str) -> int:
        return self.skills[name] + self.improvements.get(name, 0)


@dataclass
class Deck[T]:
    """A draw pile and a discard pile. An empty draw pile reshuffles the discards."""

    cards: list[T] = field(default_factory=list)
    discards: list[T] = field(default_factory=list)

    def draw(self, rng: random.Random) -> T | None:
        if not self.cards and self.discards:
            self.cards = self.discards
            self.discards = []
            rng.shuffle(self.cards)
        if not self.cards:
            return None
        return self.cards.pop(0)

    def draw_where(self, rng: random.Random, pred: Callable[[T], bool]) -> T | None:
        """Take the first card that matches, from the draw pile and then the discards."""
        for pile in (self.cards, self.discards):
            for i, card in enumerate(pile):
                if pred(card):
                    return pile.pop(i)
        return None

    def discard(self, card: T) -> None:
        self.discards.append(card)

    def shuffle_in(self, rng: random.Random, cards: list[T]) -> None:
        self.cards.extend(cards)
        rng.shuffle(self.cards)

    def __len__(self) -> int:
        return len(self.cards) + len(self.discards)


@dataclass
class RiteState:
    def_id: str
    required: int
    progress: int = 0
    final: bool = False

    @property
    def done(self) -> bool:
        return self.progress >= self.required


class NullController:
    """Used before a real controller is attached. It picks the first option."""

    def choose(self, game: Game, prompt: str, options: list[Any], *, kind: str, inv: Investigator | None = None) -> int:
        return 0

    def confirm(self, game: Game, prompt: str, *, kind: str, inv: Investigator | None = None) -> bool:
        return False

    def notify(self, game: Game, event: Any) -> None:
        pass

    def checkpoint(self, game: Game) -> None:
        pass


@dataclass
class Game:
    content: Content
    rng: random.Random
    seed: int
    old_one_id: str
    difficulty: str
    investigators: list[Investigator]
    locations: dict[str, LocationState]
    doom: int
    start_doom: int
    dread: int = 1
    round: int = 1
    phase: Phase = Phase.DAY
    turn_index: int = 0
    awakened: bool = False
    endgame: int = 0
    rites: list[RiteState] = field(default_factory=list)
    final_rite: RiteState | None = None
    market: list[AssetCard] = field(default_factory=list)
    asset_deck: Deck[AssetCard] = field(default_factory=Deck)
    spell_deck: Deck[AssetCard] = field(default_factory=Deck)
    relic_deck: Deck[AssetCard] = field(default_factory=Deck)
    encounter_decks: dict[str, Deck[str]] = field(default_factory=dict)
    portent_deck: Deck[str] = field(default_factory=Deck)
    rift_deck: Deck[str] = field(default_factory=Deck)
    clue_deck: Deck[str] = field(default_factory=Deck)
    monster_cup: list[str] = field(default_factory=list)
    unused_investigators: list[str] = field(default_factory=list)
    next_uid: int = 1
    outcome: str | None = None
    outcome_reason: str = ""
    log: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    # Not saved. `ctl` receives every decision and event. `roll` makes dice scriptable in tests.
    ctl: Controller = field(default_factory=NullController, repr=False, compare=False)
    roll: Callable[[], int] | None = field(default=None, repr=False, compare=False)

    LOG_LIMIT = 300

    def uid(self) -> int:
        value = self.next_uid
        self.next_uid += 1
        return value

    def roll_die(self) -> int:
        return self.roll() if self.roll else self.rng.randint(1, 6)

    @property
    def old_one(self) -> OldOneDef:
        return self.content.old_ones[self.old_one_id]

    def location_def(self, loc_id: str) -> LocationDef:
        return self.content.locations[loc_id]

    def asset_def(self, card: AssetCard) -> AssetDef:
        return self.content.assets[card.def_id]

    def rite_def(self, rite: RiteState) -> RiteDef:
        if rite.final:
            return self.old_one.awakening.final_rite
        return next(r for r in self.old_one.rites if r.id == rite.def_id)

    def active_investigators(self) -> list[Investigator]:
        return [i for i in self.investigators if not i.eliminated]

    def investigators_at(self, loc_id: str) -> list[Investigator]:
        return [i for i in self.active_investigators() if i.location == loc_id and not i.defeated]

    def open_rifts(self) -> list[str]:
        return [loc for loc, state in self.locations.items() if state.rift]

    def all_monsters(self) -> Iterator[tuple[str, MonsterInst]]:
        for loc, state in self.locations.items():
            for monster in state.monsters:
                yield loc, monster

    def active_rites(self) -> list[RiteState]:
        if self.awakened:
            return [self.final_rite] if self.final_rite else []
        return list(self.rites)

    def bump(self, stat: str, amount: int = 1) -> None:
        self.stats[stat] = self.stats.get(stat, 0) + amount
