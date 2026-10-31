"""Load and check every content file in `pursuit/data`.

`load_content()` either returns a complete, consistent `Content` or raises `ContentError`
with the JSON path of the first problem. Set PURSUIT_DATA to load another data folder.
"""

from __future__ import annotations

import json
import os
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import pursuit.effects.library  # noqa: F401  (registers every effect type)
from pursuit.content.defs import (
    ASSET_KINDS,
    BLOCKABLE_ACTIONS,
    CONDITION_TRIGGERS,
    MARKET_KINDS,
    MONSTER_FORMS,
    REGIONS,
    RITE_KINDS,
    RITE_RESOURCES,
    ROUTE_KINDS,
    SKILLS,
    TERRAINS,
    ActionAbility,
    AssetDef,
    AwakeningDef,
    Boost,
    ConditionDef,
    Cure,
    DifficultyDef,
    EncounterDef,
    InvestigatorDef,
    LocationDef,
    MonsterDef,
    OldOneDef,
    Outcome,
    PortentDef,
    PortentTier,
    RiteDef,
    RouteDef,
    RulesDef,
    read_action,
    read_cost,
    read_location_filter,
    read_modifiers,
    read_perks,
)
from pursuit.content.reader import ContentError, Reader
from pursuit.effects.base import Effect, read_effects, walk

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SPECIAL_DECKS = ("rift",)


@dataclass(frozen=True)
class Content:
    rules: RulesDef
    locations: dict[str, LocationDef]
    routes: tuple[RouteDef, ...]
    adjacency: dict[str, list[tuple[str, str]]]
    investigators: dict[str, InvestigatorDef]
    old_ones: dict[str, OldOneDef]
    monsters: dict[str, MonsterDef]
    assets: dict[str, AssetDef]
    conditions: dict[str, ConditionDef]
    portents: dict[str, PortentDef]
    encounters: dict[str, EncounterDef]
    decks: dict[str, tuple[str, ...]]

    def deck_for_location(self, loc_id: str) -> str:
        loc = self.locations[loc_id]
        return loc.id if loc.hub else loc.terrain


def data_dir() -> Path:
    override = os.environ.get("PURSUIT_DATA")
    return Path(override) if override else DEFAULT_DATA_DIR


@cache
def load_content(path: str | None = None) -> Content:
    root = Path(path) if path else data_dir()
    return _Loader(root).load()


def _read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise ContentError(f"{path}: file not found") from None
    except json.JSONDecodeError as exc:
        raise ContentError(f"{path}: invalid JSON at line {exc.lineno}: {exc.msg}") from None


def _list_of_objects(data: Any, path: str) -> list[Reader]:
    if not isinstance(data, list):
        raise ContentError(f"{path}: expected a list")
    return [Reader(item, f"{path}[{i}]") for i, item in enumerate(data)]


def _index[T](items: Iterable[T], key: Callable[[T], str], what: str) -> dict[str, T]:
    out: dict[str, T] = {}
    for item in items:
        k = key(item)
        if k in out:
            raise ContentError(f"duplicate {what} id '{k}'")
        out[k] = item
    return out


def _id(r: Reader) -> str:
    value: str = r.get_str("id")
    if not value or not value.replace("_", "").isalnum() or value != value.lower():
        raise ContentError(f"{r.at('id')}: ids must be lowercase letters, digits, and underscores")
    return value


class _Loader:
    def __init__(self, root: Path) -> None:
        self.root = root

    def file(self, name: str) -> Any:
        return _read_json(self.root / name)

    def load(self) -> Content:
        rules = self.rules()
        locations, routes = self.map()
        content = Content(
            rules=rules,
            locations=locations,
            routes=routes,
            adjacency=_adjacency(locations, routes),
            investigators=_index(self.investigators(), lambda d: d.id, "investigator"),
            old_ones=_index(self.old_ones(), lambda d: d.id, "old one"),
            monsters=_index(self.monsters(), lambda d: d.id, "monster"),
            assets=_index(self.assets(), lambda d: d.id, "asset"),
            conditions=_index(self.conditions(), lambda d: d.id, "condition"),
            portents=_index(self.portents(), lambda d: d.id, "portent"),
            encounters={},
            decks={},
        )
        encounters, decks = self.encounters(locations)
        content.encounters.update(encounters)
        content.decks.update(decks)
        _Checker(content).check()
        return content

    # --- files ------------------------------------------------------------------------

    def rules(self) -> RulesDef:
        r = Reader(self.file("rules.json"), "rules.json")
        diffs = {}
        for d in r.objects("difficulties"):
            diff = DifficultyDef(
                id=_id(d),
                label=d.get_str("label"),
                text=d.get_str("text"),
                doom_mod=d.get_int("doom_mod", 0),
                funds_mod=d.get_int("funds_mod", 0),
                start_rifts_mod=d.get_int("start_rifts_mod", 0),
            )
            d.done()
            diffs[diff.id] = diff
        rules = RulesDef(
            actions_per_turn=r.get_int("actions_per_turn"),
            success_on=r.get_int("success_on"),
            market_size=r.get_int("market_size"),
            max_paid_steps=r.get_int("max_paid_steps"),
            step_cost=r.get_int("step_cost"),
            start_rifts=r.get_int("start_rifts"),
            start_clues=r.get_int("start_clues"),
            night_doom=r.get_int("night_doom"),
            max_improvement=r.get_int("max_improvement"),
            max_investigators=r.get_int("max_investigators"),
            defeat_doom=r.get_int("defeat_doom"),
            difficulties=diffs,
        )
        r.done()
        if "normal" not in diffs:
            raise ContentError("rules.json: difficulties must include 'normal'")
        if not 2 <= rules.success_on <= 6:
            raise ContentError("rules.json: success_on must be 2 to 6")
        return rules

    def map(self) -> tuple[dict[str, LocationDef], tuple[RouteDef, ...]]:
        r = Reader(self.file("map.json"), "map.json")
        locs = []
        for lr in r.objects("locations"):
            pos = lr.get_list("pos")
            if len(pos) != 2 or not all(isinstance(p, int) for p in pos):
                raise ContentError(f"{lr.at('pos')}: expected [x, y]")
            loc = LocationDef(
                id=_id(lr),
                name=lr.get_str("name"),
                code=lr.get_str("code"),
                terrain=lr.get_enum("terrain", TERRAINS),
                region=lr.get_enum("region", REGIONS),
                hub=lr.get_bool("hub", False),
                rift_site=lr.get_bool("rift_site", False),
                text=lr.get_str("text"),
                pos=(pos[0], pos[1]),
            )
            lr.done()
            locs.append(loc)
        locations = _index(locs, lambda d: d.id, "location")
        routes = []
        for i, raw in enumerate(r.get_list("routes")):
            path = f"map.json.routes[{i}]"
            if not (isinstance(raw, list) and len(raw) == 3 and all(isinstance(x, str) for x in raw)):
                raise ContentError(f"{path}: expected [from, to, kind]")
            a, b, kind = raw
            if kind not in ROUTE_KINDS:
                raise ContentError(f"{path}: route kind '{kind}' is not one of {', '.join(ROUTE_KINDS)}")
            for end in (a, b):
                if end not in locations:
                    raise ContentError(f"{path}: unknown location '{end}'")
            if a == b:
                raise ContentError(f"{path}: a route cannot loop to the same location")
            routes.append(RouteDef(a, b, kind))
        r.done()
        seen: set[frozenset[str]] = set()
        for route in routes:
            pair = frozenset((route.a, route.b))
            if pair in seen:
                raise ContentError(f"map.json: two routes join {route.a} and {route.b}")
            seen.add(pair)
        return locations, tuple(routes)

    def investigators(self) -> list[InvestigatorDef]:
        out = []
        for r in _list_of_objects(self.file("investigators.json"), "investigators.json"):
            skills_r = r.get_obj("skills")
            skills = {s: skills_r.get_int(s) for s in SKILLS}
            skills_r.done()
            inv = InvestigatorDef(
                id=_id(r),
                name=r.get_str("name"),
                occupation=r.get_str("occupation"),
                bio=r.get_str("bio"),
                quote=r.get_str("quote"),
                health=r.get_int("health"),
                sanity=r.get_int("sanity"),
                skills=skills,
                start=r.get_str("start"),
                funds=r.get_int("funds", 0),
                clues=r.get_int("clues", 0),
                assets=r.get_str_tuple("assets"),
                conditions=r.get_str_tuple("conditions"),
                passive_text=r.get_str("passive_text", ""),
                perks=read_perks(r, "perks"),
                modifiers=read_modifiers(r, "modifiers"),
                action=read_action(r, "action"),
            )
            r.done()
            out.append(inv)
        return out

    def monsters(self) -> list[MonsterDef]:
        out = []
        for r in _list_of_objects(self.file("monsters.json"), "monsters.json"):
            m = MonsterDef(
                id=_id(r),
                name=r.get_str("name"),
                form=r.get_enum("form", MONSTER_FORMS),
                count=r.get_int("count", 1),
                text=r.get_str("text"),
                horror=r.get_int("horror"),
                horror_mod=r.get_int("horror_mod", 0),
                damage=r.get_int("damage"),
                fight_mod=r.get_int("fight_mod", 0),
                evade_mod=r.get_int("evade_mod", 0),
                toughness=r.get_int("toughness"),
                toughness_per_investigator=r.get_int("toughness_per_investigator", 0),
                roams=r.get_bool("roams", False),
                epic=r.get_bool("epic", False),
                on_defeat=read_effects(r, "on_defeat"),
                art=r.get_str("art", ""),
            )
            r.done()
            if m.toughness < 1 or m.damage < 0 or m.horror < 0 or m.count < 1:
                raise ContentError(f"{r.path}: toughness and count must be at least 1, damage and horror at least 0")
            out.append(m)
        return out

    def assets(self) -> list[AssetDef]:
        out = []
        for name, default_kind in (("assets.json", None), ("spells.json", "spell"), ("relics.json", "relic")):
            for r in _list_of_objects(self.file(name), name):
                kind = r.get_enum("kind", ASSET_KINDS, default_kind)
                if kind is None:
                    raise ContentError(f"{r.path}: missing required field 'kind'")
                a = AssetDef(
                    id=_id(r),
                    name=r.get_str("name"),
                    kind=kind,
                    traits=r.get_str_tuple("traits"),
                    cost=r.get_int("cost", 0),
                    count=r.get_int("count", 1),
                    text=r.get_str("text"),
                    flavor=r.get_str("flavor", ""),
                    modifiers=read_modifiers(r, "modifiers"),
                    boosts=tuple(Boost.parse(b) for b in r.objects("boosts", [])),
                    action=read_action(r, "action"),
                    on_gain=read_effects(r, "on_gain"),
                    perks=read_perks(r, "perks"),
                )
                r.done()
                if a.count < 1 or a.cost < 0:
                    raise ContentError(f"{r.path}: count must be at least 1 and cost at least 0")
                if a.kind == "service" and not a.on_gain:
                    raise ContentError(f"{r.path}: a service needs on_gain effects")
                out.append(a)
        return out

    def conditions(self) -> list[ConditionDef]:
        out = []
        for r in _list_of_objects(self.file("conditions.json"), "conditions.json"):
            outcomes = []
            for o in r.objects("outcomes", []):
                outcomes.append(Outcome(o.get_int("weight", 1), o.get_str("text"), read_effects(o, "effects")))
                o.done()
            cure = None
            cr = r.opt_obj("cure")
            if cr is not None:
                skill = cr.get_enum("skill", SKILLS, None)
                cure = Cure(cr.get_str("text"), read_cost(cr, "cost"), skill, cr.get_int("mod", 0))
                cr.done()
            trigger = r.get_enum("trigger", CONDITION_TRIGGERS)
            c = ConditionDef(
                id=_id(r),
                name=r.get_str("name"),
                traits=r.get_str_tuple("traits"),
                text=r.get_str("text"),
                modifiers=read_modifiers(r, "modifiers"),
                blocks=r.get_str_tuple("blocks", BLOCKABLE_ACTIONS),
                trigger=trigger,
                chance=r.get_int("chance", 6 if trigger != "night" else 2),
                outcomes=tuple(outcomes),
                cure=cure,
            )
            r.done()
            if c.trigger != "never" and not c.outcomes:
                raise ContentError(f"{r.path}: a condition with a trigger needs outcomes")
            if not 1 <= c.chance <= 6:
                raise ContentError(f"{r.path}: chance must be 1 to 6")
            if any(o.weight < 1 for o in c.outcomes):
                raise ContentError(f"{r.path}: outcome weights must be at least 1")
            out.append(c)
        return out

    def portents(self) -> list[PortentDef]:
        out = []
        for r in _list_of_objects(self.file("portents.json"), "portents.json"):
            tiers = []
            for t in r.objects("tiers"):
                tiers.append(PortentTier(t.get_str("text"), read_effects(t, "effects")))
                t.done()
            p = PortentDef(_id(r), r.get_str("name"), r.get_str("flavor"), r.get_int("min_dread", 1), tuple(tiers))
            r.done()
            if not 1 <= p.min_dread <= 3:
                raise ContentError(f"{r.path}: min_dread must be 1 to 3")
            if len(p.tiers) != 4 - p.min_dread:
                raise ContentError(
                    f"{r.path}: a portent with min_dread {p.min_dread} needs {4 - p.min_dread} tier(s), "
                    f"one for each Dread level from {p.min_dread} to 3"
                )
            out.append(p)
        return out

    def rite(self, r: Reader) -> RiteDef:
        rite = RiteDef(
            id=_id(r),
            name=r.get_str("name"),
            text=r.get_str("text"),
            kind=r.get_enum("kind", RITE_KINDS),
            amount=r.get_int("amount", 1),
            per_investigator=r.get_bool("per_investigator", False),
            resource=r.get_enum("resource", RITE_RESOURCES, None),
            where=read_location_filter(r, "where"),
            skill=r.get_enum("skill", SKILLS, None),
            mod=r.get_int("mod", 0),
            monster=r.get_str("monster", None),
            spawn_at=r.get_str("spawn_at", None),
        )
        r.done()
        if rite.amount < 1:
            raise ContentError(f"{r.path}: amount must be at least 1")
        if rite.kind == "spend" and rite.resource is None:
            raise ContentError(f"{r.path}: a spend rite needs a resource")
        if rite.kind == "test" and rite.skill is None:
            raise ContentError(f"{r.path}: a test rite needs a skill")
        if rite.kind == "defeat" and rite.monster is None:
            raise ContentError(f"{r.path}: a defeat rite needs a monster")
        if rite.kind in ("spend", "test") and rite.where is None:
            raise ContentError(f"{r.path}: a {rite.kind} rite needs a 'where' location filter")
        return rite

    def old_ones(self) -> list[OldOneDef]:
        out = []
        for r in _list_of_objects(self.file("old_ones.json"), "old_ones.json"):
            aw = r.get_obj("awakening")
            awakening = AwakeningDef(
                text=aw.get_str("text"),
                effects=read_effects(aw, "effects"),
                nights=aw.get_int("nights"),
                night=read_effects(aw, "night"),
                final_rite=self.rite(aw.get_obj("final_rite")),
            )
            aw.done()
            dread = r.get_list("dread_at")
            if len(dread) != 2 or not all(isinstance(x, int) for x in dread):
                raise ContentError(f"{r.at('dread_at')}: expected two integers")
            o = OldOneDef(
                id=_id(r),
                name=r.get_str("name"),
                title=r.get_str("title"),
                difficulty=r.get_enum("difficulty", ("low", "medium", "high")),
                description=r.get_str("description"),
                art=r.get_str("art"),
                doom=r.get_int("doom"),
                dread_at=(dread[0], dread[1]),
                seal_mod=r.get_int("seal_mod", 0),
                rift_pressure=r.get_int("rift_pressure"),
                rift_limit=r.get_int("rift_limit", None),
                modifiers=read_modifiers(r, "modifiers"),
                rules_text=r.get_str_tuple("rules_text"),
                setup=read_effects(r, "setup"),
                night=read_effects(r, "night"),
                rites=tuple(self.rite(x) for x in r.objects("rites")),
                rites_needed=r.get_int("rites_needed"),
                awakening=awakening,
                monsters=r.get_str_tuple("monsters"),
            )
            r.done()
            if not o.doom > o.dread_at[0] > o.dread_at[1] > 0:
                raise ContentError(f"{r.path}: need doom > dread_at[0] > dread_at[1] > 0")
            if not 1 <= o.rites_needed <= len(o.rites):
                raise ContentError(f"{r.path}: rites_needed must be between 1 and the number of rites")
            if awakening.nights < 1:
                raise ContentError(f"{r.path}.awakening: nights must be at least 1")
            out.append(o)
        return out

    def encounters(
        self, locations: dict[str, LocationDef]
    ) -> tuple[dict[str, EncounterDef], dict[str, tuple[str, ...]]]:
        folder = self.root / "encounters"
        if not folder.is_dir():
            raise ContentError(f"{folder}: encounter folder not found")
        encounters: dict[str, EncounterDef] = {}
        decks: dict[str, tuple[str, ...]] = {}
        valid = {*TERRAINS, *SPECIAL_DECKS, *(loc.id for loc in locations.values() if loc.hub)}
        for path in sorted(folder.glob("*.json")):
            deck = path.stem
            name = f"encounters/{path.name}"
            if deck not in valid:
                raise ContentError(f"{name}: '{deck}' is not a terrain, 'rift', or a hub location id")
            ids = []
            for r in _list_of_objects(_read_json(path), name):
                e = EncounterDef(_id(r), deck, r.get_str("title"), r.get_str("text"), read_effects(r, "effects"))
                r.done()
                if e.id in encounters:
                    raise ContentError(f"{r.path}: duplicate encounter id '{e.id}'")
                encounters[e.id] = e
                ids.append(e.id)
            if not ids:
                raise ContentError(f"{name}: a deck needs at least one encounter")
            decks[deck] = tuple(ids)
        missing = sorted(valid - set(decks))
        if missing:
            raise ContentError(f"encounters: missing deck file(s) for: {', '.join(missing)}")
        return encounters, decks


def _adjacency(locations: dict[str, LocationDef], routes: Sequence[RouteDef]) -> dict[str, list[tuple[str, str]]]:
    adj: dict[str, list[tuple[str, str]]] = {loc: [] for loc in locations}
    for route in routes:
        adj[route.a].append((route.b, route.kind))
        adj[route.b].append((route.a, route.kind))
    for links in adj.values():
        links.sort(key=lambda x: locations[x[0]].name)
    return adj


class _Checker:
    """Cross-reference and consistency checks over a fully parsed `Content`."""

    def __init__(self, content: Content) -> None:
        self.c = content

    def check(self) -> None:
        self.check_map()
        self.check_investigators()
        self.check_assets()
        self.check_monsters()
        self.check_old_ones()
        self.check_portents()
        self.check_effects()

    def fail(self, msg: str) -> None:
        raise ContentError(msg)

    def check_map(self) -> None:
        c = self.c
        codes: dict[str, str] = {}
        for loc in c.locations.values():
            if len(loc.code) != 2:
                self.fail(f"map.json: location '{loc.id}' code must be 2 characters")
            if loc.code in codes:
                self.fail(f"map.json: locations '{codes[loc.code]}' and '{loc.id}' share code {loc.code}")
            codes[loc.code] = loc.id
            if not c.adjacency[loc.id]:
                self.fail(f"map.json: location '{loc.id}' has no routes")
        start = next(iter(c.locations))
        seen = {start}
        queue = deque([start])
        while queue:
            for nxt, _ in c.adjacency[queue.popleft()]:
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        unreachable = sorted(set(c.locations) - seen)
        if unreachable:
            self.fail(f"map.json: cannot reach {', '.join(unreachable)}")
        if not any(loc.rift_site for loc in c.locations.values()):
            self.fail("map.json: at least one location must be a rift_site")

    def check_investigators(self) -> None:
        c = self.c
        if len(c.investigators) < c.rules.max_investigators:
            self.fail("investigators.json: need at least max_investigators investigators")
        for inv in c.investigators.values():
            where = f"investigators.json '{inv.id}'"
            if inv.start not in c.locations:
                self.fail(f"{where}: unknown start location '{inv.start}'")
            for a in inv.assets:
                if a not in c.assets:
                    self.fail(f"{where}: unknown starting asset '{a}'")
            for cond in inv.conditions:
                if cond not in c.conditions:
                    self.fail(f"{where}: unknown starting condition '{cond}'")
            if inv.health < 1 or inv.sanity < 1:
                self.fail(f"{where}: health and sanity must be at least 1")
            if any(not 1 <= v <= 6 for v in inv.skills.values()):
                self.fail(f"{where}: skills must be 1 to 6")

    def check_assets(self) -> None:
        if not any(a.kind in MARKET_KINDS for a in self.c.assets.values()):
            self.fail("assets.json: the market needs at least one item, ally, or service")

    def check_monsters(self) -> None:
        if not any(not m.epic for m in self.c.monsters.values()):
            self.fail("monsters.json: need at least one ordinary (non-epic) monster")

    def check_old_ones(self) -> None:
        c = self.c
        for o in c.old_ones.values():
            where = f"old_ones.json '{o.id}'"
            for m in o.monsters:
                if m not in c.monsters or c.monsters[m].epic:
                    self.fail(f"{where}: '{m}' is not an ordinary monster")
            for rite in (*o.rites, o.awakening.final_rite):
                if rite.monster and (rite.monster not in c.monsters or not c.monsters[rite.monster].epic):
                    self.fail(f"{where}: rite '{rite.id}' needs an epic monster, not '{rite.monster}'")
                if rite.spawn_at and rite.spawn_at not in c.locations:
                    self.fail(f"{where}: rite '{rite.id}' spawns at unknown location '{rite.spawn_at}'")
                if rite.where:
                    for _table, ref in rite.where.refs():
                        if ref not in c.locations:
                            self.fail(f"{where}: rite '{rite.id}' refers to unknown location '{ref}'")
            ids = [r.id for r in o.rites]
            if len(ids) != len(set(ids)):
                self.fail(f"{where}: rite ids must be unique")

    def check_portents(self) -> None:
        if not any(p.min_dread == 1 for p in self.c.portents.values()):
            self.fail("portents.json: need at least one portent with min_dread 1")

    def effect_lists(self) -> Iterable[tuple[str, Sequence[Effect], bool]]:
        """Every effect list in the content, with a flag for 'runs with no investigator'."""
        c = self.c
        for e in c.encounters.values():
            yield f"encounters '{e.id}'", e.effects, False
        for p in c.portents.values():
            for i, t in enumerate(p.tiers):
                yield f"portents.json '{p.id}' tier {i + 1}", t.effects, True
        for o in c.old_ones.values():
            yield f"old_ones.json '{o.id}' setup", o.setup, True
            yield f"old_ones.json '{o.id}' night", o.night, True
            yield f"old_ones.json '{o.id}' awakening", o.awakening.effects, True
            yield f"old_ones.json '{o.id}' awakening night", o.awakening.night, True
        for m in c.monsters.values():
            yield f"monsters.json '{m.id}' on_defeat", m.on_defeat, False
        for a in c.assets.values():
            yield f"asset '{a.id}' on_gain", a.on_gain, False
            if a.action:
                yield f"asset '{a.id}' action", a.action.effects, False
        for cond in c.conditions.values():
            for i, out in enumerate(cond.outcomes):
                yield f"conditions.json '{cond.id}' outcome {i}", out.effects, False
        for inv in c.investigators.values():
            if inv.action:
                yield f"investigators.json '{inv.id}' action", inv.action.effects, False

    def check_effects(self) -> None:
        tables: dict[str, dict[str, Any]] = {
            "asset": self.c.assets,
            "condition": self.c.conditions,
            "monster": self.c.monsters,
            "location": self.c.locations,
        }
        for where, effects, world in self.effect_lists():
            for effect in walk(effects):
                for table, ref in effect.refs():
                    if ref not in tables[table]:
                        self.fail(f"{where}: effect '{effect.kind}' refers to unknown {table} '{ref}'")
            if world:
                self.check_world(where, effects)
        for a in self.c.assets.values():
            self.check_ability_refs(f"asset '{a.id}'", a.action)
        for inv in self.c.investigators.values():
            self.check_ability_refs(f"investigator '{inv.id}'", inv.action)

    def check_ability_refs(self, where: str, ability: ActionAbility | None) -> None:
        if ability and ability.requires:
            for table, ref in ability.requires.refs():
                pools: dict[str, Mapping[str, object]] = {
                    "asset": self.c.assets,
                    "condition": self.c.conditions,
                    "location": self.c.locations,
                }
                pool = pools[table]
                if ref not in pool:
                    self.fail(f"{where}: requirement refers to unknown {table} '{ref}'")

    def check_world(self, where: str, effects: Sequence[Effect]) -> None:
        for effect in effects:
            if getattr(effect, "provides_investigator", False):
                continue
            if effect.needs_investigator():
                self.fail(
                    f"{where}: effect '{effect.kind}' needs an investigator here. "
                    "Wrap it in each_investigator or one_investigator."
                )
            for child in effect.children():
                self.check_world(where, child)
