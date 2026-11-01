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

SKILLS = ("lore", "influence", "observation", "strength", "will")
TERRAINS = ("city", "wilderness", "sea")
REGIONS = (
    "americas",
    "europe",
    "asia_australia",
    "general",
)
ROUTE_KINDS = ("uncharted", "train", "ship")
TICKET_KINDS = ("train", "ship")
OMEN_TRACK = ("green", "blue_a", "red", "blue_b")
OMEN_COLORS = {"green": "green", "blue_a": "blue", "red": "red", "blue_b": "blue"}
GATE_COLORS = ("green", "blue", "red")
MYTHOS_COLORS = ("green", "yellow", "blue")
MYTHOS_TRAITS = ("event", "ongoing", "rumor")
MYTHOS_ICONS = (
    "advance_omen",
    "reckoning",
    "spawn_gates",
    "monster_surge",
    "spawn_clues",
    "place_rumor",
    "place_eldritch",
)
EXPEDITION_LOCATIONS = (
    "the_amazon",
    "the_heart_of_africa",
    "the_himalayas",
    "the_pyramids",
    "tunguska",
    "antarctica",
)
LOCATION_DECKS = ("americas", "europe", "asia_australia")
CONTEXTS = (
    "any",
    "encounter",
    "combat",
    "horror",
    "fight",
    "acquire",
    "cast",
    "mystery",
    "other_world",
)
ASSET_KINDS = ("item", "ally", "service", "trinket", "spell", "artifact")
RESERVE_KINDS = ("item", "ally", "service", "trinket")
PERKS = (
    "rest_sanity",
    "double_improve",
    "no_delay",
    "clue_discount",
    "ignore_monsters",
    "horror_to_one",
    "watch_conditions",
    "lend_die",
    "no_detained",
    "sanity_for_clue",
    "clue_two_dice",
)
BLOCKABLE_ACTIONS = ("travel", "rest", "trade", "prepare", "acquire", "component", "move")
MYTHOS_BLOCKS = ("reserve", "close_gate", "rest", "expedition")
MYTHOS_DIFFICULTIES = ("easy", "normal", "hard")
ACTIVE_EXPEDITION = "active_expedition"
MONSTER_FORMS = ("beast", "humanoid", "horror", "swarm", "spirit")
MYSTERY_KINDS = ("encounter", "research", "gate", "trophy", "defeat", "spend", "spell", "ambush", "special")
SPECIAL_DECKS = ("special_cthulhu", "special_yog_sothoth")


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
    gate: bool | None = None
    clue: bool | None = None
    monsters: bool | None = None
    expedition: bool | None = None
    eldritch: bool | None = None
    monster: str | None = None

    @classmethod
    def parse(cls, r: Reader) -> LocationFilter:
        f = cls(
            ids=r.get_str_tuple("id"),
            terrain=r.get_str_tuple("terrain", TERRAINS),
            region=r.get_str_tuple("region", REGIONS),
            gate=r.get_bool("gate", None),
            clue=r.get_bool("clue", None),
            monsters=r.get_bool("monsters", None),
            expedition=r.get_bool("expedition", None),
            eldritch=r.get_bool("eldritch", None),
            monster=r.get_str("monster", None),
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
            self.gate is None or state.gate == self.gate,
            self.clue is None or state.clue == self.clue,
            self.monsters is None or bool(state.monsters) == self.monsters,
            self.expedition is None or (game.active_expedition == loc_id) == self.expedition,
            self.eldritch is None or (state.eldritch > 0) == self.eldritch,
            self.monster is None or any(m.def_id == self.monster for m in state.monsters),
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
        if self.gate:
            parts.append("with a gate")
        if self.clue:
            parts.append("with a clue")
        if self.expedition:
            parts.append("at the Active Expedition")
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
    clues_at_least: int | None = None
    tickets_at_least: int | None = None
    sanity_at_most: int | None = None
    health_at_most: int | None = None
    at: LocationFilter | None = None
    alone: bool | None = None
    lead: bool | None = None
    lacks_condition: str | None = None
    clues_at_most: int | None = None
    has_improvement: bool | None = None
    monster_at_gate: bool | None = None

    @classmethod
    def parse(cls, r: Reader) -> InvestigatorFilter:
        f = cls(
            condition=r.get_str("condition", None),
            condition_trait=r.get_str("condition_trait", None),
            asset=r.get_str("asset", None),
            asset_kind=r.get_enum("asset_kind", ASSET_KINDS, None),
            asset_trait=r.get_str("asset_trait", None),
            clues_at_least=r.get_int("clues_at_least", None),
            tickets_at_least=r.get_int("tickets_at_least", None),
            sanity_at_most=r.get_int("sanity_at_most", None),
            health_at_most=r.get_int("health_at_most", None),
            at=read_location_filter(r, "at"),
            alone=r.get_bool("alone", None),
            lead=r.get_bool("lead", None),
            lacks_condition=r.get_str("lacks_condition", None),
            clues_at_most=r.get_int("clues_at_most", None),
            has_improvement=r.get_bool("has_improvement", None),
            monster_at_gate=r.get_bool("monster_at_gate", None),
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
        if self.asset_kind is not None and not any(a.is_a(self.asset_kind) for a in assets):
            return False
        if self.asset_trait is not None and all(self.asset_trait not in a.traits for a in assets):
            return False
        if self.clues_at_least is not None and inv.clues < self.clues_at_least:
            return False
        if self.tickets_at_least is not None and len(inv.tickets) < self.tickets_at_least:
            return False
        if self.sanity_at_most is not None and inv.sanity > self.sanity_at_most:
            return False
        if self.health_at_most is not None and inv.health > self.health_at_most:
            return False
        if self.at is not None and not self.at.matches(game, inv.location):
            return False
        if self.lacks_condition is not None and any(c.id == self.lacks_condition for c in conds):
            return False
        if self.clues_at_most is not None and inv.clues > self.clues_at_most:
            return False
        if self.has_improvement is not None and any(v > 0 for v in inv.improvements.values()) != self.has_improvement:
            return False
        if self.monster_at_gate is not None:
            found = any(st.gate and st.monsters for st in game.locations.values())
            if found != self.monster_at_gate:
                return False
        if self.alone is not None:
            others = [o for o in game.active_investigators() if o is not inv and o.location == inv.location]
            if (not others) != self.alone:
                return False
        return self.lead is None or (game.lead_seat == inv.seat) == self.lead

    def refs(self) -> Iterable[tuple[str, str]]:
        if self.condition:
            yield ("condition", self.condition)
        if self.lacks_condition:
            yield ("condition", self.lacks_condition)
        if self.asset:
            yield ("asset", self.asset)
        if self.at:
            yield from self.at.refs()


def read_investigator_filter(r: Reader, key: str) -> InvestigatorFilter | None:
    sub = r.opt_obj(key)
    return None if sub is None else InvestigatorFilter.parse(sub)


@dataclass(frozen=True)
class Cost:
    clues: int = 0
    sanity: int = 0
    health: int = 0
    tickets: int = 0

    @classmethod
    def parse(cls, r: Reader) -> Cost:
        c = cls(
            clues=r.get_int("clues", 0),
            sanity=r.get_int("sanity", 0),
            health=r.get_int("health", 0),
            tickets=r.get_int("tickets", 0),
        )
        r.done()
        if min(c.clues, c.sanity, c.health, c.tickets) < 0:
            raise ContentError(f"{r.path}: costs cannot be negative")
        return c

    def is_free(self) -> bool:
        return not (self.clues or self.sanity or self.health or self.tickets)

    def can_pay(self, inv: Investigator) -> bool:
        # Health and sanity costs never let a payment defeat the payer.
        return (
            inv.clues >= self.clues
            and len(inv.tickets) >= self.tickets
            and (self.sanity == 0 or inv.sanity > self.sanity)
            and (self.health == 0 or inv.health > self.health)
        )

    def describe(self) -> str:
        parts = []
        for name, value in (
            ("Clue", self.clues),
            ("Sanity", self.sanity),
            ("Health", self.health),
            ("Ticket", self.tickets),
        ):
            if value:
                parts.append(f"{value} {name}")
        return ", ".join(parts) or "free"


def read_cost(r: Reader, key: str) -> Cost:
    sub = r.opt_obj(key)
    return Cost() if sub is None else Cost.parse(sub)


@dataclass(frozen=True)
class Modifier:
    """Skill bonus/penalty or additional dice for tests matching `skill` and `context`.

    In Eldritch Horror, an investigator uses only their highest positive card skill
    bonus (`additional=False`), while penalties and "roll additional dice" effects
    (`additional=True`) stack with everything.
    """

    amount: int
    skill: str | None = None
    context: str = "any"
    where: LocationFilter | None = None
    additional: bool = False
    aura: bool = False
    except_context: str | None = None

    @classmethod
    def parse(cls, r: Reader) -> Modifier:
        m = cls(
            amount=r.get_int("amount"),
            skill=_skill_or_none(r, "skill"),
            context=r.get_enum("context", CONTEXTS, "any"),
            where=read_location_filter(r, "where"),
            additional=r.get_bool("additional", False),
            aura=r.get_bool("aura", False),
            except_context=r.get_enum("except_context", CONTEXTS, None),
        )
        r.done()
        return m

    def applies(self, skill: str, contexts: tuple[str, ...]) -> bool:
        if self.except_context in contexts:
            return False
        return (self.skill is None or self.skill == skill) and (self.context == "any" or self.context in contexts)

    def describe(self) -> str:
        what = self.skill.title() if self.skill else "all tests"
        when = "" if self.context == "any" else f" ({self.context})"
        if self.additional:
            return f"+{self.amount} extra dice on {what}{when}"
        sign = "+" if self.amount >= 0 else ""
        return f"{sign}{self.amount} {what}{when}"


def read_modifiers(r: Reader, key: str) -> tuple[Modifier, ...]:
    return tuple(Modifier.parse(m) for m in r.objects(key, []))


@dataclass(frozen=True)
class Boost:
    """A bonus the investigator chooses before rolling. It lasts for the Combat Encounter."""

    text: str
    modifiers: tuple[Modifier, ...]
    discard: bool = False
    once_per_round: bool = False

    @classmethod
    def parse(cls, r: Reader) -> Boost:
        b = cls(
            text=r.get_str("text"),
            modifiers=read_modifiers(r, "modifiers"),
            discard=r.get_bool("discard", False),
            once_per_round=r.get_bool("once_per_round", False),
        )
        r.done()
        return b


@dataclass(frozen=True)
class Prevent:
    """Prevent loss of `stat`. An `amount` of 0 prevents all of the loss."""

    stat: str
    amount: int
    discard: bool = False
    local: bool = False
    clue_cost: int = 0
    once_per_round: bool = False
    spell_only: bool = False

    @classmethod
    def parse(cls, r: Reader) -> Prevent:
        p = cls(
            stat=r.get_enum("stat", ("health", "sanity")),
            amount=r.get_int("amount", 0),
            discard=r.get_bool("discard", False),
            local=r.get_bool("local", False),
            clue_cost=r.get_int("clue_cost", 0),
            once_per_round=r.get_bool("once_per_round", False),
            spell_only=r.get_bool("spell_only", False),
        )
        r.done()
        return p


@dataclass(frozen=True)
class SixRule:
    """Each 6 rolled on a matching test counts as 2 successes."""

    skill: str | None = None
    context: str = "any"

    @classmethod
    def parse(cls, r: Reader) -> SixRule:
        s = cls(_skill_or_none(r, "skill"), r.get_enum("context", CONTEXTS, "any"))
        r.done()
        return s

    def applies(self, skill: str, contexts: tuple[str, ...]) -> bool:
        return (self.skill is None or self.skill == skill) and (self.context == "any" or self.context in contexts)


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
class RerollAbility:
    """Reroll 1 die or any number of dice on a matching test, or add 1 to 1 die."""

    text: str
    skill: str | None = None
    context: str = "any"
    any_dice: bool = False
    once_per_round: bool = False
    discard: bool = False
    sanity_cost: int = 0
    add_one: bool = False

    @classmethod
    def parse(cls, r: Reader) -> RerollAbility:
        a = cls(
            text=r.get_str("text"),
            skill=_skill_or_none(r, "skill"),
            context=r.get_enum("context", CONTEXTS, "any"),
            any_dice=r.get_bool("any_dice", False),
            once_per_round=r.get_bool("once_per_round", False),
            discard=r.get_bool("discard", False),
            sanity_cost=r.get_int("sanity_cost", 0),
            add_one=r.get_bool("add_one", False),
        )
        r.done()
        return a

    def applies(self, skill: str, contexts: tuple[str, ...]) -> bool:
        return (self.skill is None or self.skill == skill) and (self.context == "any" or self.context in contexts)


@dataclass(frozen=True)
class ActionAbility:
    """A component action (`Action:` or `Local Action:`). Each component works once per round."""

    text: str
    effects: tuple[Effect, ...]
    cost: Cost
    discard: bool
    target: str
    local: bool
    requires: InvestigatorFilter | None
    free: bool = False

    @classmethod
    def parse(cls, r: Reader) -> ActionAbility:
        a = cls(
            text=r.get_str("text"),
            effects=read_effects(r, "effects"),
            cost=read_cost(r, "cost"),
            discard=r.get_bool("discard", False),
            target=r.get_enum("target", ("self", "investigator_here", "any_investigator", "anyone"), "self"),
            local=r.get_bool("local", False),
            requires=read_investigator_filter(r, "requires"),
            free=r.get_bool("free", False),
        )
        r.done()
        if not a.effects:
            raise ContentError(f"{r.path}: an action needs at least one effect")
        return a


def read_action(r: Reader, key: str) -> ActionAbility | None:
    sub = r.opt_obj(key)
    return None if sub is None else ActionAbility.parse(sub)


@dataclass(frozen=True)
class CardBack:
    """A hidden back variant on a double-sided Spell or Condition card."""

    text: str
    effects: tuple[Effect, ...]
    weight: int = 1
    min_successes: int | None = None
    max_successes: int | None = None
    keep: bool = False
    face: int = 0

    @classmethod
    def parse(cls, r: Reader) -> CardBack:
        b = cls(
            text=r.get_str("text"),
            effects=read_effects(r, "effects"),
            weight=r.get_int("weight", 1),
            min_successes=r.get_int("min_successes", None),
            max_successes=r.get_int("max_successes", None),
            keep=r.get_bool("keep", False),
            face=r.get_int("face", 0),
        )
        r.done()
        if b.weight < 1:
            raise ContentError(f"{r.path}: back weight must be at least 1")
        return b


def read_backs(r: Reader, key: str = "backs") -> tuple[CardBack, ...]:
    return tuple(CardBack.parse(b) for b in r.objects(key, []))


@dataclass(frozen=True)
class LocationDef:
    id: str
    name: str
    code: str
    terrain: str
    region: str
    gate_color: str | None
    expedition: bool
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
    rerolls: tuple[RerollAbility, ...]
    action: ActionAbility | None
    on_gain: tuple[Effect, ...]
    reckoning: tuple[Effect, ...]
    backs: tuple[CardBack, ...]
    damage_reduction: int = 0
    sanity_reduction: int = 0
    perks: dict[str, int] = field(default_factory=dict)
    boosts: tuple[Boost, ...] = ()
    prevents: tuple[Prevent, ...] = ()
    double_sixes: tuple[SixRule, ...] = ()
    rest_prompt: str = ""
    on_rest: tuple[Effect, ...] = ()
    rest_aura: tuple[Effect, ...] = ()
    on_close_gate: tuple[Effect, ...] = ()
    on_combat_win: tuple[Effect, ...] = ()
    trigger_prompt: str = ""
    on_combat: tuple[Effect, ...] = ()
    on_encounter: tuple[Effect, ...] = ()
    encounter_when: str | None = None
    on_ward: tuple[Effect, ...] = ()
    ward_stat: str | None = None

    def is_a(self, kind: str) -> bool:
        return self.kind == kind or kind in self.traits


@dataclass(frozen=True)
class ConditionDef:
    """A double-sided condition card. The front is visible; the back is hidden until flipped."""

    id: str
    name: str
    traits: tuple[str, ...]
    text: str
    modifiers: tuple[Modifier, ...]
    blocks: tuple[str, ...]
    action: ActionAbility | None
    reckoning: tuple[Effect, ...]
    backs: tuple[CardBack, ...]
    rest_roll: bool = False
    replaces_encounter: bool = False


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
    toughness: int
    toughness_per_investigator: int
    roams: bool
    epic: bool
    on_spawn: tuple[Effect, ...]
    reckoning: tuple[Effect, ...]
    on_defeat: tuple[Effect, ...]
    art: str
    horror_test: bool = True
    damage_test: bool = True
    before_will: tuple[Effect, ...] = ()
    will_passed: tuple[Effect, ...] = ()
    will_failed: tuple[Effect, ...] = ()
    after_will: tuple[Effect, ...] = ()
    before_strength: tuple[Effect, ...] = ()
    lost_health: tuple[Effect, ...] = ()
    after_hit: tuple[Effect, ...] = ()
    on_combat_defeat: tuple[Effect, ...] = ()
    replace_encounter: ActionAbility | None = None
    skip_strength_on_will_fail: bool = False
    no_clue_rerolls: bool = False
    ally_shield: bool = False
    blocks_encounter: bool = False
    needs_mysteries: bool = False
    sanity_to_sheet: bool = False

    def combat_hooks(self) -> dict[str, tuple[Effect, ...]]:
        return {
            "before_will": self.before_will,
            "will_passed": self.will_passed,
            "will_failed": self.will_failed,
            "after_will": self.after_will,
            "before_strength": self.before_strength,
            "lost_health": self.lost_health,
            "after_hit": self.after_hit,
            "on_combat_defeat": self.on_combat_defeat,
            "on_defeat": self.on_defeat,
        }


@dataclass(frozen=True)
class EncounterSection:
    text: str
    effects: tuple[Effect, ...]
    location: str | None = None
    terrain: str | None = None


@dataclass(frozen=True)
class EncounterDef:
    id: str
    deck: str
    title: str
    text: str
    effects: tuple[Effect, ...]
    terrain: str | None = None
    location: str | None = None
    sections: tuple[EncounterSection, ...] = ()


@dataclass(frozen=True)
class MythosDef:
    id: str
    name: str
    color: str
    traits: tuple[str, ...]
    icons: tuple[str, ...]
    flavor: str
    text: str
    effects: tuple[Effect, ...]
    reckoning: tuple[Effect, ...]
    rumor_space: str | None = None
    eldritch: int = 0
    encounter_text: str = ""
    encounter_effects: tuple[Effect, ...] = ()
    on_zero_eldritch: tuple[Effect, ...] = ()
    difficulty: str = "normal"
    blocks: tuple[str, ...] = ()
    rumor_monster: str | None = None
    trophy_space: str | None = None


@dataclass(frozen=True)
class MysteryDef:
    id: str
    name: str
    flavor: str
    text: str
    kind: str
    amount: int
    half_players: bool
    per_investigator: bool
    where: LocationFilter | None
    skill: str | None
    mod: int
    clue_cost: int
    monster: str | None
    spawn_at: str | None
    on_enter: tuple[Effect, ...]
    on_solve: tuple[Effect, ...] = ()
    deck: str | None = None
    omen_match: bool = False
    spell_cost: int = 0
    remove_gate: bool = False
    token: bool = False
    needs_solved: bool = False
    spawn_when_solved: bool = False

    def required(self, investigators: int) -> int:
        if self.half_players:
            return max(1, (investigators + 1) // 2) * self.amount
        if self.per_investigator:
            return self.amount * investigators
        return self.amount


@dataclass(frozen=True)
class StageComp:
    green: int
    yellow: int
    blue: int


@dataclass(frozen=True)
class AwakeningDef:
    text: str
    effects: tuple[Effect, ...]
    reckoning: tuple[Effect, ...]
    doom_advance_effects: tuple[Effect, ...]
    lose_immediately: bool
    final_mystery: MysteryDef | None
    cultist: MonsterDef | None = None
    on_eldritch_move: tuple[Effect, ...] = ()


@dataclass(frozen=True)
class OldOneDef:
    id: str
    name: str
    title: str
    difficulty: str
    description: str
    art: str
    doom: int
    stages: tuple[StageComp, StageComp, StageComp]
    modifiers: tuple[Modifier, ...]
    rules_text: tuple[str, ...]
    setup: tuple[Effect, ...]
    reckoning: tuple[Effect, ...]
    omen_green_eldritch_doom: bool
    mysteries: tuple[MysteryDef, ...]
    mysteries_needed: int
    awakening: AwakeningDef
    cultist: MonsterDef
    set_aside: tuple[str, ...]
    on_eldritch_move: tuple[Effect, ...] = ()


@dataclass(frozen=True)
class DefeatedEncounterDef:
    text: str
    skill: str
    mod: int
    pass_text: str
    fail_text: str


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
    clues: int
    tickets: tuple[str, ...]
    assets: tuple[str, ...]
    conditions: tuple[str, ...]
    passive_text: str
    perks: dict[str, int]
    modifiers: tuple[Modifier, ...]
    rerolls: tuple[RerollAbility, ...]
    action: ActionAbility | None
    crippled: DefeatedEncounterDef
    insane: DefeatedEncounterDef
    on_start: tuple[Effect, ...] = ()


@dataclass(frozen=True)
class ReferenceRow:
    players: int
    spawn_gates: int
    spawn_clues: int
    monster_surge: int


@dataclass(frozen=True)
class DifficultyDef:
    id: str
    label: str
    text: str
    removes: str | None


@dataclass(frozen=True)
class RulesDef:
    actions_per_turn: int
    success_on: int
    reserve_size: int
    max_tickets: int
    start_gates: int
    start_clues: int
    max_improvement: int
    max_investigators: int
    defeat_doom: int
    reference: dict[int, ReferenceRow]
    difficulties: dict[str, DifficultyDef]

