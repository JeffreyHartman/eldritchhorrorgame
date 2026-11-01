"""Mutable game state. Everything here is saved and loaded by `pursuit.engine.save`."""

from __future__ import annotations

import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pursuit.content.defs import OMEN_COLORS, OMEN_TRACK

if TYPE_CHECKING:
    from pursuit.content.defs import AssetDef, LocationDef, Modifier, MonsterDef, MysteryDef, OldOneDef, ReferenceRow
    from pursuit.content.loader import Content
    from pursuit.controller import Controller


class Phase(StrEnum):
    ACTION = "action"
    ENCOUNTER = "encounter"
    MYTHOS = "mythos"


@dataclass
class AssetCard:
    uid: int
    def_id: str
    exhausted: bool = False
    back: int = 0


@dataclass
class ConditionInst:
    uid: int
    def_id: str
    back: int | None = None


@dataclass
class MonsterInst:
    uid: int
    def_id: str
    wounds: int = 0


@dataclass
class FallenInvestigator:
    def_id: str
    name: str
    cause: str  # "health" or "sanity"
    clues: int = 0
    tickets: list[str] = field(default_factory=list)
    assets: list[AssetCard] = field(default_factory=list)


@dataclass
class ActiveMythos:
    def_id: str
    eldritch: int = 0
    rumor_space: str | None = None
    health_tokens: int = 0
    trophies: list[str] = field(default_factory=list)


@dataclass
class LocationState:
    id: str
    clues: list[str] = field(default_factory=list)
    eldritch: int = 0
    gate: bool = False
    monsters: list[MonsterInst] = field(default_factory=list)
    fallen: list[FallenInvestigator] = field(default_factory=list)


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
    clues: int = 0
    tickets: list[str] = field(default_factory=list)
    improvements: dict[str, int] = field(default_factory=dict)
    assets: list[AssetCard] = field(default_factory=list)
    conditions: list[ConditionInst] = field(default_factory=list)
    delayed: bool = False
    actions_taken: list[str] = field(default_factory=list)
    used_this_round: list[str] = field(default_factory=list)
    bonus_actions: int = 0
    defeated: bool = False
    defeated_awake: bool = False
    devoured: bool = False
    eliminated: bool = False

    def skill(self, name: str) -> int:
        return self.skills[name] + self.improvements.get(name, 0)


@dataclass
class Deck[T]:
    """A draw pile and a discard pile. An empty draw pile reshuffles the discards."""

    cards: list[T] = field(default_factory=list)
    discards: list[T] = field(default_factory=list)

    def draw(self, rng: random.Random, *, reshuffle: bool = True) -> T | None:
        if not self.cards and self.discards and reshuffle:
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
class MysteryState:
    def_id: str
    required: int
    progress: int = 0
    final: bool = False
    solved: bool = False

    @property
    def ready(self) -> bool:
        return self.progress >= self.required

    @property
    def done(self) -> bool:
        return self.solved


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
    omen_index: int = 0
    green_eldritch: int = 0
    sheet_tokens: int = 0
    round: int = 1
    phase: Phase = Phase.ACTION
    turn_index: int = 0
    lead_seat: int = 0
    awakened: bool = False
    active_expedition: str | None = None
    mystery_deck: list[str] = field(default_factory=list)
    active_mystery: MysteryState | None = None
    solved_mysteries: list[str] = field(default_factory=list)
    final_mystery: MysteryState | None = None
    reserve: list[AssetCard] = field(default_factory=list)
    asset_deck: Deck[AssetCard] = field(default_factory=Deck)
    spell_deck: Deck[AssetCard] = field(default_factory=Deck)
    artifact_deck: Deck[AssetCard] = field(default_factory=Deck)
    encounter_decks: dict[str, Deck[str]] = field(default_factory=dict)
    mythos_deck: list[str] = field(default_factory=list)
    mythos_discards: list[str] = field(default_factory=list)
    mythos_box: list[str] = field(default_factory=list)
    active_mythos: list[ActiveMythos] = field(default_factory=list)
    gate_deck: Deck[str] = field(default_factory=Deck)
    clue_deck: Deck[str] = field(default_factory=Deck)
    monster_cup: list[str] = field(default_factory=list)
    set_aside: list[str] = field(default_factory=list)
    epics_gone: list[str] = field(default_factory=list)
    unused_investigators: list[str] = field(default_factory=list)
    next_uid: int = 1
    outcome: str | None = None
    outcome_reason: str = ""
    log: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    # Not saved, because none of these outlast a decision point that saves. `spell_lore_passed`
    # lasts for one Spell action, `casting` is True while a Spell resolves, and `boosts` lasts
    # for one Combat Encounter. `ctl` receives every decision and event. `roll` makes dice
    # scriptable in tests.
    spell_lore_passed: bool = field(default=False, repr=False, compare=False)
    casting: bool = field(default=False, repr=False, compare=False)
    force_ones: bool = field(default=False, repr=False, compare=False)
    boosts: list[tuple[str, Modifier]] = field(default_factory=list, repr=False, compare=False)
    free_rerolls: int = field(default=0, repr=False, compare=False)
    free_reroll_source: str = field(default="", repr=False, compare=False)
    prevented: int = field(default=0, repr=False, compare=False)
    ignore_monsters: bool = field(default=False, repr=False, compare=False)
    remote_clue: str | None = field(default=None, repr=False, compare=False)
    ctl: Controller = field(default_factory=NullController, repr=False, compare=False)
    roll: Callable[[], int] | None = field(default=None, repr=False, compare=False)

    LOG_LIMIT = 300

    def uid(self) -> int:
        value = self.next_uid
        self.next_uid += 1
        return value

    def roll_die(self) -> int:
        if self.force_ones:
            return 1
        return self.roll() if self.roll else self.rng.randint(1, 6)

    @property
    def old_one(self) -> OldOneDef:
        return self.content.old_ones[self.old_one_id]

    @property
    def omen_space(self) -> str:
        return OMEN_TRACK[self.omen_index % len(OMEN_TRACK)]

    @property
    def omen_color(self) -> str:
        return OMEN_COLORS[self.omen_space]

    @property
    def reference(self) -> ReferenceRow:
        n = max(1, min(self.content.rules.max_investigators, len(self.investigators)))
        return self.content.rules.reference[n]

    def lead_investigator(self) -> Investigator:
        for inv in self.investigators:
            if inv.seat == self.lead_seat and not inv.eliminated and not inv.defeated:
                return inv
        active = [i for i in self.investigators if not i.eliminated and not i.defeated]
        return active[0] if active else self.investigators[0]

    def turn_order(self) -> list[Investigator]:
        n = len(self.investigators)
        if n == 0:
            return []
        start = next((idx for idx, inv in enumerate(self.investigators) if inv.seat == self.lead_seat), 0)
        return [self.investigators[(start + i) % n] for i in range(n)]

    def location_def(self, loc_id: str) -> LocationDef:
        return self.content.locations[loc_id]

    def monster_def(self, def_id: str) -> MonsterDef:
        """The Cultist's stats come from the sheet side of the Ancient One that is faceup."""
        if def_id != "cultist":
            return self.content.monsters[def_id]
        old = self.old_one
        return (old.awakening.cultist if self.awakened else None) or old.cultist

    def asset_def(self, card: AssetCard) -> AssetDef:
        return self.content.assets[card.def_id]

    def mystery_def(self, mys: MysteryState) -> MysteryDef:
        if mys.final:
            assert self.old_one.awakening.final_mystery is not None
            return self.old_one.awakening.final_mystery
        return next(m for m in self.old_one.mysteries if m.id == mys.def_id)

    def active_investigators(self) -> list[Investigator]:
        return [i for i in self.investigators if not i.eliminated]

    def investigators_at(self, loc_id: str) -> list[Investigator]:
        return [i for i in self.active_investigators() if i.location == loc_id and not i.defeated]

    def open_gates(self) -> list[str]:
        return [loc for loc, state in self.locations.items() if state.gate]

    def matching_gates(self) -> list[str]:
        color = self.omen_color
        return [loc for loc in self.open_gates() if self.content.locations[loc].gate_color == color]

    def all_monsters(self) -> Iterator[tuple[str, MonsterInst]]:
        for loc, state in self.locations.items():
            for monster in state.monsters:
                yield loc, monster

    def active_mysteries(self) -> list[MysteryState]:
        out: list[MysteryState] = []
        if self.active_mystery and not self.active_mystery.done:
            out.append(self.active_mystery)
        if self.awakened and self.final_mystery and not self.final_mystery.done:
            out.append(self.final_mystery)
        return out

    def bump(self, stat: str, amount: int = 1) -> None:
        self.stats[stat] = self.stats.get(stat, 0) + amount

