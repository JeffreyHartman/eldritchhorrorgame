"""Immutable definitions parsed from the JSON content files.

Definitions never change during play. Mutable game state lives in `pursuit.engine.state`
and refers to these records by id.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pursuit.content.reader import ContentError, Reader
from pursuit.effects.base import Effect, read_effects

if TYPE_CHECKING:
    from pursuit.engine.state import Game, Investigator

SKILLS = ("lore", "charm", "wits", "brawn", "nerve")
TERRAINS = ("city", "wilderness", "sea")
REGIONS = (
    "north_america",
    "south_america",
    "europe",
    "africa",
    "middle_east",
    "asia",
    "oceania",
    "ocean",
)
ROUTE_KINDS = ("road", "rail", "sea")
CONTEXTS = (
    "any",
    "encounter",
    "combat",
    "horror",
    "evade",
    "seal",
    "investigate",
    "funds",
    "cast",
    "rite",
)
ASSET_KINDS = ("item", "ally", "service", "spell", "relic")
MARKET_KINDS = ("item", "ally", "service")
PERKS = (
    "market_discount",
    "free_travel_steps",
    "earn_bonus",
    "rest_bonus",
    "investigate_bonus",
    "seal_bonus",
)
BLOCKABLE_ACTIONS = ("travel", "rest", "investigate", "seal", "earn", "rite", "buy")
CONDITION_TRIGGERS = ("night", "rest", "encounter", "never")
MONSTER_FORMS = ("beast", "humanoid", "horror", "swarm", "spirit")
RITE_KINDS = ("spend", "test", "seal", "defeat")
RITE_RESOURCES = ("clues", "funds", "trophies", "relic")


def _skill_or_none(r: Reader, key: str) -> str | None:
    value: str | None = r.get_str(key, None)
    if value is not None and value not in SKILLS:
        raise ContentError(f"{r.at(key)}: '{value}' is not a skill ({', '.join(SKILLS)})")
    return value


@dataclass(frozen=True)
class LocationFilter:
    ids: tuple[str, ...] = ()
    terrain: tuple[str, ...] = ()
    region: tuple[str, ...] = ()
    hub: bool | None = None
    rift: bool | None = None
    clue: bool | None = None
    monsters: bool | None = None

    @classmethod
    def parse(cls, r: Reader) -> LocationFilter:
        f = cls(
            ids=r.get_str_tuple("id"),
            terrain=r.get_str_tuple("terrain", TERRAINS),
            region=r.get_str_tuple("region", REGIONS),
            hub=r.get_bool("hub", None),
            rift=r.get_bool("rift", None),
            clue=r.get_bool("clue", None),
            monsters=r.get_bool("monsters", None),
        )
        r.done()
        return f

    def matches(self, game: Game, loc_id: str) -> bool:
        ldef = game.content.locations[loc_id]
        state = game.locations[loc_id]
        checks = (
            not self.ids or loc_id in self.ids,
            not self.terrain or ldef.terrain in self.terrain,
            not self.region or ldef.region in self.region,
            self.hub is None or ldef.hub == self.hub,
            self.rift is None or state.rift == self.rift,
            self.clue is None or state.clue == self.clue,
            self.monsters is None or bool(state.monsters) == self.monsters,
        )
        return all(checks)

    def describe(self, names: dict[str, str]) -> str:
        parts: list[str] = []
        if self.ids:
            parts.append(" or ".join(names.get(i, i) for i in self.ids))
        if self.terrain:
            parts.append("any " + " or ".join(self.terrain))
        if self.region:
            parts.append("in " + " or ".join(r.replace("_", " ").title() for r in self.region))
        if self.rift:
            parts.append("with a rift")
        if self.clue:
            parts.append("with a clue")
        return ", ".join(parts) or "anywhere"

    def refs(self) -> Iterable[tuple[str, str]]:
        return (("location", i) for i in self.ids)


def read_location_filter(r: Reader, key: str) -> LocationFilter | None:
    sub = r.opt_obj(key)
    return None if sub is None else LocationFilter.parse(sub)


@dataclass(frozen=True)
class InvestigatorFilter:
    condition: str | None = None
    condition_trait: str | None = None
    asset: str | None = None
    asset_kind: str | None = None
    asset_trait: str | None = None
    funds_at_least: int | None = None
    clues_at_least: int | None = None
    trophies_at_least: int | None = None
    sanity_at_most: int | None = None
    health_at_most: int | None = None
    at: LocationFilter | None = None
    alone: bool | None = None

    @classmethod
    def parse(cls, r: Reader) -> InvestigatorFilter:
        f = cls(
            condition=r.get_str("condition", None),
            condition_trait=r.get_str("condition_trait", None),
            asset=r.get_str("asset", None),
            asset_kind=r.get_enum("asset_kind", ASSET_KINDS, None),
            asset_trait=r.get_str("asset_trait", None),
            funds_at_least=r.get_int("funds_at_least", None),
            clues_at_least=r.get_int("clues_at_least", None),
            trophies_at_least=r.get_int("trophies_at_least", None),
            sanity_at_most=r.get_int("sanity_at_most", None),
            health_at_most=r.get_int("health_at_most", None),
            at=read_location_filter(r, "at"),
            alone=r.get_bool("alone", None),
        )
        r.done()
        return f

    def matches(self, game: Game, inv: Investigator) -> bool:
        content = game.content
        conds = [content.conditions[c.def_id] for c in inv.conditions]
        assets = [content.assets[a.def_id] for a in inv.assets]
        if self.condition is not None and all(c.id != self.condition for c in conds):
            return False
        if self.condition_trait is not None and all(self.condition_trait not in c.traits for c in conds):
            return False
        if self.asset is not None and all(a.id != self.asset for a in assets):
            return False
        if self.asset_kind is not None and all(a.kind != self.asset_kind for a in assets):
            return False
        if self.asset_trait is not None and all(self.asset_trait not in a.traits for a in assets):
            return False
        if self.funds_at_least is not None and inv.funds < self.funds_at_least:
            return False
        if self.clues_at_least is not None and inv.clues < self.clues_at_least:
            return False
        if self.trophies_at_least is not None and inv.trophies < self.trophies_at_least:
            return False
        if self.sanity_at_most is not None and inv.sanity > self.sanity_at_most:
            return False
        if self.health_at_most is not None and inv.health > self.health_at_most:
            return False
        if self.at is not None and not self.at.matches(game, inv.location):
            return False
        if self.alone is not None:
            others = [o for o in game.active_investigators() if o is not inv and o.location == inv.location]
            if (not others) != self.alone:
                return False
        return True

    def refs(self) -> Iterable[tuple[str, str]]:
        if self.condition:
            yield ("condition", self.condition)
        if self.asset:
            yield ("asset", self.asset)
        if self.at:
            yield from self.at.refs()


def read_investigator_filter(r: Reader, key: str) -> InvestigatorFilter | None:
    sub = r.opt_obj(key)
    return None if sub is None else InvestigatorFilter.parse(sub)


@dataclass(frozen=True)
class Cost:
    funds: int = 0
    clues: int = 0
    sanity: int = 0
    health: int = 0
    trophies: int = 0

    @classmethod
    def parse(cls, r: Reader) -> Cost:
        c = cls(
            funds=r.get_int("funds", 0),
            clues=r.get_int("clues", 0),
            sanity=r.get_int("sanity", 0),
            health=r.get_int("health", 0),
            trophies=r.get_int("trophies", 0),
        )
        r.done()
        if min(c.funds, c.clues, c.sanity, c.health, c.trophies) < 0:
            raise ContentError(f"{r.path}: costs cannot be negative")
        return c

    def is_free(self) -> bool:
        return not (self.funds or self.clues or self.sanity or self.health or self.trophies)

    def can_pay(self, inv: Investigator) -> bool:
        # Health and sanity costs never let a payment defeat the payer.
        return (
            inv.funds >= self.funds
            and inv.clues >= self.clues
            and inv.trophies >= self.trophies
            and (self.sanity == 0 or inv.sanity > self.sanity)
            and (self.health == 0 or inv.health > self.health)
        )

    def describe(self) -> str:
        parts = []
        for name, value in (
            ("Funds", self.funds),
            ("Clue", self.clues),
            ("Sanity", self.sanity),
            ("Health", self.health),
            ("Trophy", self.trophies),
        ):
            if value:
                parts.append(f"{value} {name}")
        return ", ".join(parts) or "free"


def read_cost(r: Reader, key: str) -> Cost:
    sub = r.opt_obj(key)
    return Cost() if sub is None else Cost.parse(sub)


@dataclass(frozen=True)
class Modifier:
    """Extra dice (or fewer) for tests that match `skill` and `context`."""

    amount: int
    skill: str | None = None
    context: str = "any"
    where: LocationFilter | None = None

    @classmethod
    def parse(cls, r: Reader) -> Modifier:
        m = cls(
            amount=r.get_int("amount"),
            skill=_skill_or_none(r, "skill"),
            context=r.get_enum("context", CONTEXTS, "any"),
            where=read_location_filter(r, "where"),
        )
        r.done()
        return m

    def applies(self, skill: str, contexts: tuple[str, ...]) -> bool:
        return (self.skill is None or self.skill == skill) and (self.context == "any" or self.context in contexts)

    def describe(self) -> str:
        sign = "+" if self.amount >= 0 else ""
        what = self.skill.title() if self.skill else "all tests"
        when = "" if self.context == "any" else f" ({self.context})"
        return f"{sign}{self.amount} {what}{when}"


def read_modifiers(r: Reader, key: str) -> tuple[Modifier, ...]:
    return tuple(Modifier.parse(m) for m in r.objects(key, []))


def read_perks(r: Reader, key: str) -> dict[str, int]:
    raw = r.get_dict(key, {})
    perks: dict[str, int] = {}
    for name, value in raw.items():
        if name not in PERKS:
            raise ContentError(f"{r.at(key)}: unknown perk '{name}' (known: {', '.join(PERKS)})")
        if not isinstance(value, int) or isinstance(value, bool):
            raise ContentError(f"{r.at(key)}.{name}: expected an integer")
        perks[name] = value
    return perks


@dataclass(frozen=True)
class Boost:
    """An optional, paid bonus that the owner may add to a matching test."""

    text: str
    amount: int
    context: str
    skill: str | None
    cost: Cost
    exhaust: bool
    discard: bool

    @classmethod
    def parse(cls, r: Reader) -> Boost:
        b = cls(
            text=r.get_str("text"),
            amount=r.get_int("amount"),
            context=r.get_enum("context", CONTEXTS),
            skill=_skill_or_none(r, "skill"),
            cost=read_cost(r, "cost"),
            exhaust=r.get_bool("exhaust", True),
            discard=r.get_bool("discard", False),
        )
        r.done()
        return b

    def applies(self, skill: str, contexts: tuple[str, ...]) -> bool:
        return (self.skill is None or self.skill == skill) and (self.context == "any" or self.context in contexts)


@dataclass(frozen=True)
class ActionAbility:
    """An ability that costs one action. Each one works once per round."""

    text: str
    effects: tuple[Effect, ...]
    cost: Cost
    discard: bool
    target: str
    requires: InvestigatorFilter | None

    @classmethod
    def parse(cls, r: Reader) -> ActionAbility:
        a = cls(
            text=r.get_str("text"),
            effects=read_effects(r, "effects"),
            cost=read_cost(r, "cost"),
            discard=r.get_bool("discard", False),
            target=r.get_enum("target", ("self", "investigator_here"), "self"),
            requires=read_investigator_filter(r, "requires"),
        )
        r.done()
        if not a.effects:
            raise ContentError(f"{r.path}: an action needs at least one effect")
        return a


def read_action(r: Reader, key: str) -> ActionAbility | None:
    sub = r.opt_obj(key)
    return None if sub is None else ActionAbility.parse(sub)


@dataclass(frozen=True)
class LocationDef:
    id: str
    name: str
    code: str
    terrain: str
    region: str
    hub: bool
    rift_site: bool
    text: str
    pos: tuple[int, int]


@dataclass(frozen=True)
class RouteDef:
    a: str
    b: str
    kind: str


@dataclass(frozen=True)
class AssetDef:
    id: str
    name: str
    kind: str
    traits: tuple[str, ...]
    cost: int
    count: int
    text: str
    flavor: str
    modifiers: tuple[Modifier, ...]
    boosts: tuple[Boost, ...]
    action: ActionAbility | None
    on_gain: tuple[Effect, ...]
    perks: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Outcome:
    weight: int
    text: str
    effects: tuple[Effect, ...]


@dataclass(frozen=True)
class Cure:
    text: str
    cost: Cost
    skill: str | None
    mod: int


@dataclass(frozen=True)
class ConditionDef:
    """A condition. Players see `text` and `modifiers`. The outcomes stay hidden
    until the trigger fires and one outcome is drawn at random by weight."""

    id: str
    name: str
    traits: tuple[str, ...]
    text: str
    modifiers: tuple[Modifier, ...]
    blocks: tuple[str, ...]
    trigger: str
    chance: int
    outcomes: tuple[Outcome, ...]
    cure: Cure | None


@dataclass(frozen=True)
class MonsterDef:
    id: str
    name: str
    form: str
    count: int
    text: str
    horror: int
    horror_mod: int
    damage: int
    fight_mod: int
    evade_mod: int
    toughness: int
    toughness_per_investigator: int
    roams: bool
    epic: bool
    on_defeat: tuple[Effect, ...]
    art: str


@dataclass(frozen=True)
class EncounterDef:
    id: str
    deck: str
    title: str
    text: str
    effects: tuple[Effect, ...]


@dataclass(frozen=True)
class PortentTier:
    text: str
    effects: tuple[Effect, ...]


@dataclass(frozen=True)
class PortentDef:
    """A Night card. `tiers[0]` resolves at Dread `min_dread`, `tiers[1]` one level higher,
    and so on. At a Dread above the last tier, the last tier resolves."""

    id: str
    name: str
    flavor: str
    min_dread: int
    tiers: tuple[PortentTier, ...]

    def tier(self, dread: int) -> PortentTier:
        index = max(0, min(dread - self.min_dread, len(self.tiers) - 1))
        return self.tiers[index]


@dataclass(frozen=True)
class RiteDef:
    id: str
    name: str
    text: str
    kind: str
    amount: int
    per_investigator: bool
    resource: str | None
    where: LocationFilter | None
    skill: str | None
    mod: int
    monster: str | None
    spawn_at: str | None

    def required(self, investigators: int) -> int:
        return self.amount * investigators if self.per_investigator else self.amount


@dataclass(frozen=True)
class AwakeningDef:
    text: str
    effects: tuple[Effect, ...]
    nights: int
    night: tuple[Effect, ...]
    final_rite: RiteDef


@dataclass(frozen=True)
class OldOneDef:
    id: str
    name: str
    title: str
    difficulty: str
    description: str
    art: str
    doom: int
    dread_at: tuple[int, int]
    seal_mod: int
    rift_pressure: int
    rift_limit: int | None
    modifiers: tuple[Modifier, ...]
    rules_text: tuple[str, ...]
    setup: tuple[Effect, ...]
    night: tuple[Effect, ...]
    rites: tuple[RiteDef, ...]
    rites_needed: int
    awakening: AwakeningDef
    monsters: tuple[str, ...]


@dataclass(frozen=True)
class InvestigatorDef:
    id: str
    name: str
    occupation: str
    bio: str
    quote: str
    health: int
    sanity: int
    skills: dict[str, int]
    start: str
    funds: int
    clues: int
    assets: tuple[str, ...]
    conditions: tuple[str, ...]
    passive_text: str
    perks: dict[str, int]
    modifiers: tuple[Modifier, ...]
    action: ActionAbility | None


@dataclass(frozen=True)
class DifficultyDef:
    id: str
    label: str
    text: str
    doom_mod: int
    funds_mod: int
    start_rifts_mod: int


@dataclass(frozen=True)
class RulesDef:
    actions_per_turn: int
    success_on: int
    market_size: int
    max_paid_steps: int
    step_cost: int
    start_rifts: int
    start_clues: int
    night_doom: int
    max_improvement: int
    max_investigators: int
    defeat_doom: int
    difficulties: dict[str, DifficultyDef]
