"""Load and check every content file in `pursuit/data`.

`load_content()` either returns a complete, consistent `Content` or raises `ContentError`
with the JSON path of the first problem. Set PURSUIT_DATA to load another data folder.
"""

from __future__ import annotations

import json
import os
from collections import Counter, deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import pursuit.effects.library  # noqa: F401  (registers every effect type)
from pursuit.content.defs import (
    ACTIVE_EXPEDITION,
    ASSET_KINDS,
    BLOCKABLE_ACTIONS,
    EXPANSIONS,
    EXPEDITION_LOCATIONS,
    GATE_COLORS,
    LOCATION_DECKS,
    MONSTER_FORMS,
    MYSTERY_KINDS,
    MYTHOS_BLOCKS,
    MYTHOS_COLORS,
    MYTHOS_DIFFICULTIES,
    MYTHOS_ICONS,
    MYTHOS_TRAITS,
    REGIONS,
    RESERVE_KINDS,
    ROUTE_KINDS,
    SKILLS,
    SPECIAL_DECKS,
    TERRAINS,
    TICKET_KINDS,
    ActionAbility,
    AssetDef,
    AwakeningDef,
    Boost,
    ConditionDef,
    DefeatedEncounterDef,
    DifficultyDef,
    EncounterDef,
    EncounterSection,
    InvestigatorDef,
    LocationDef,
    MonsterDef,
    MysteryDef,
    MythosDef,
    OldOneDef,
    Prevent,
    ReferenceRow,
    RerollAbility,
    RouteDef,
    RulesDef,
    SixRule,
    StageComp,
    read_action,
    read_backs,
    read_location_filter,
    read_modifiers,
    read_perks,
)
from pursuit.content.reader import ContentError, Reader
from pursuit.effects.base import Effect, read_effects, walk

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BASE_ENCOUNTER_DECKS = (*LOCATION_DECKS, "general", "expedition", "other_world")


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
    mythos: dict[str, MythosDef]
    encounters: dict[str, EncounterDef]
    decks: dict[str, tuple[str, ...]]


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
        old_ones = _index(self.old_ones(), lambda d: d.id, "old one")
        content = Content(
            rules=rules,
            locations=locations,
            routes=routes,
            adjacency=_adjacency(locations, routes),
            investigators=_index(self.investigators(), lambda d: d.id, "investigator"),
            old_ones=old_ones,
            monsters=_index(self.monsters(), lambda d: d.id, "monster"),
            assets=_index(self.assets(), lambda d: d.id, "asset"),
            conditions=_index(self.conditions(), lambda d: d.id, "condition"),
            mythos=_index(self.mythos(), lambda d: d.id, "mythos"),
            encounters={},
            decks={},
        )
        encounters, decks = self.encounters(old_ones)
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
                removes=d.get_enum("removes", MYTHOS_DIFFICULTIES, None),
            )
            d.done()
            diffs[diff.id] = diff
        ref = {}
        for rr in r.objects("reference"):
            row = ReferenceRow(
                players=rr.get_int("players"),
                spawn_gates=rr.get_int("spawn_gates"),
                spawn_clues=rr.get_int("spawn_clues"),
                monster_surge=rr.get_int("monster_surge"),
            )
            rr.done()
            ref[row.players] = row
        rules = RulesDef(
            actions_per_turn=r.get_int("actions_per_turn"),
            success_on=r.get_int("success_on"),
            reserve_size=r.get_int("reserve_size"),
            max_tickets=r.get_int("max_tickets"),
            start_gates=r.get_int("start_gates"),
            start_clues=r.get_int("start_clues"),
            max_improvement=r.get_int("max_improvement"),
            max_investigators=r.get_int("max_investigators"),
            defeat_doom=r.get_int("defeat_doom"),
            reference=ref,
            difficulties=diffs,
        )
        r.done()
        if "normal" not in diffs:
            raise ContentError("rules.json: difficulties must include 'normal'")
        if not 2 <= rules.success_on <= 6:
            raise ContentError("rules.json: success_on must be 2 to 6")
        for p in range(1, rules.max_investigators + 1):
            if p not in ref:
                raise ContentError(f"rules.json: reference missing entry for {p} player(s)")
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
                expansion=lr.get_enum("expansion", EXPANSIONS),
                code=lr.get_str("code"),
                terrain=lr.get_enum("terrain", TERRAINS),
                region=lr.get_enum("region", REGIONS),
                gate_color=lr.get_enum("gate_color", GATE_COLORS, None),
                expedition=lr.get_bool("expedition", False),
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

    def _defeated_encounter(self, r: Reader) -> DefeatedEncounterDef:
        e = DefeatedEncounterDef(
            text=r.get_str("text"),
            skill=r.get_enum("skill", SKILLS),
            mod=r.get_int("mod", 0),
            pass_text=r.get_str("pass_text"),
            fail_text=r.get_str("fail_text"),
        )
        r.done()
        return e

    def investigators(self) -> list[InvestigatorDef]:
        out = []
        for r in _list_of_objects(self.file("investigators.json"), "investigators.json"):
            skills_r = r.get_obj("skills")
            skills = {s: skills_r.get_int(s) for s in SKILLS}
            skills_r.done()
            inv = InvestigatorDef(
                id=_id(r),
                name=r.get_str("name"),
                expansion=r.get_enum("expansion", EXPANSIONS),
                occupation=r.get_str("occupation"),
                bio=r.get_str("bio"),
                quote=r.get_str("quote"),
                health=r.get_int("health"),
                sanity=r.get_int("sanity"),
                skills=skills,
                start=r.get_str("start"),
                clues=r.get_int("clues", 0),
                tickets=r.get_str_tuple("tickets", TICKET_KINDS),
                assets=r.get_str_tuple("assets"),
                conditions=r.get_str_tuple("conditions"),
                passive_text=r.get_str("passive_text", ""),
                perks=read_perks(r, "perks"),
                modifiers=read_modifiers(r, "modifiers"),
                rerolls=tuple(RerollAbility.parse(rr) for rr in r.objects("rerolls", [])),
                action=read_action(r, "action"),
                crippled=self._defeated_encounter(r.get_obj("crippled")),
                insane=self._defeated_encounter(r.get_obj("insane")),
                on_start=read_effects(r, "on_start"),
            )
            r.done()
            out.append(inv)
        return out

    def monster(self, r: Reader, *, cultist: bool = False) -> MonsterDef:
        m = MonsterDef(
            id="cultist" if cultist else _id(r),
            name="Cultist" if cultist else r.get_str("name"),
            expansion=r.get_enum("expansion", EXPANSIONS),
            form="humanoid" if cultist else r.get_enum("form", MONSTER_FORMS),
            count=5 if cultist else r.get_int("count", 1),
            text=r.get_str("text", ""),
            horror=r.get_int("horror", 0),
            horror_mod=r.get_int("horror_mod", 0),
            damage=r.get_int("damage", 0),
            fight_mod=r.get_int("fight_mod", 0),
            toughness=r.get_int("toughness"),
            toughness_per_investigator=r.get_int("toughness_per_investigator", 0),
            roams=r.get_bool("roams", False),
            epic=r.get_bool("epic", False),
            on_spawn=read_effects(r, "on_spawn"),
            reckoning=read_effects(r, "reckoning"),
            on_defeat=read_effects(r, "on_defeat"),
            art=r.get_str("art", ""),
            horror_test=r.get_bool("horror_test", True),
            damage_test=r.get_bool("damage_test", True),
            before_will=read_effects(r, "before_will"),
            will_passed=read_effects(r, "will_passed"),
            will_failed=read_effects(r, "will_failed"),
            after_will=read_effects(r, "after_will"),
            before_strength=read_effects(r, "before_strength"),
            lost_health=read_effects(r, "lost_health"),
            after_hit=read_effects(r, "after_hit"),
            on_combat_defeat=read_effects(r, "on_combat_defeat"),
            replace_encounter=read_action(r, "replace_encounter"),
            skip_strength_on_will_fail=r.get_bool("skip_strength_on_will_fail", False),
            no_clue_rerolls=r.get_bool("no_clue_rerolls", False),
            ally_shield=r.get_bool("ally_shield", False),
            blocks_encounter=r.get_bool("blocks_encounter", False),
            needs_mysteries=r.get_bool("needs_mysteries", False),
            sanity_to_sheet=r.get_bool("sanity_to_sheet", False),
        )
        r.done()
        if m.toughness < 1 or m.damage < 0 or m.horror < 0 or m.count < 1:
            raise ContentError(f"{r.path}: toughness and count must be at least 1, damage and horror at least 0")
        return m

    def monsters(self) -> list[MonsterDef]:
        return [self.monster(r) for r in _list_of_objects(self.file("monsters.json"), "monsters.json")]

    def assets(self) -> list[AssetDef]:
        out = []
        files = (("assets.json", None), ("spells.json", "spell"), ("artifacts.json", "artifact"))
        for name, default_kind in files:
            for r in _list_of_objects(self.file(name), name):
                kind = r.get_enum("kind", ASSET_KINDS, default_kind)
                if kind is None:
                    raise ContentError(f"{r.path}: missing required field 'kind'")
                a = AssetDef(
                    id=_id(r),
                    name=r.get_str("name"),
                    expansion=r.get_enum("expansion", EXPANSIONS),
                    kind=kind,
                    traits=r.get_str_tuple("traits"),
                    cost=r.get_int("cost", 0),
                    count=r.get_int("count", 1),
                    text=r.get_str("text"),
                    flavor=r.get_str("flavor", ""),
                    modifiers=read_modifiers(r, "modifiers"),
                    rerolls=tuple(RerollAbility.parse(rr) for rr in r.objects("rerolls", [])),
                    action=read_action(r, "action"),
                    on_gain=read_effects(r, "on_gain"),
                    reckoning=read_effects(r, "reckoning"),
                    backs=read_backs(r, "backs"),
                    damage_reduction=r.get_int("damage_reduction", 0),
                    sanity_reduction=r.get_int("sanity_reduction", 0),
                    perks=read_perks(r, "perks"),
                    boosts=tuple(Boost.parse(b) for b in r.objects("boosts", [])),
                    prevents=tuple(Prevent.parse(p) for p in r.objects("prevents", [])),
                    double_sixes=tuple(SixRule.parse(d) for d in r.objects("double_sixes", [])),
                    rest_prompt=r.get_str("rest_prompt", ""),
                    on_rest=read_effects(r, "on_rest"),
                    rest_aura=read_effects(r, "rest_aura"),
                    on_close_gate=read_effects(r, "on_close_gate"),
                    on_combat_win=read_effects(r, "on_combat_win"),
                    trigger_prompt=r.get_str("trigger_prompt", ""),
                    on_combat=read_effects(r, "on_combat"),
                    on_encounter=read_effects(r, "on_encounter"),
                    encounter_when=r.get_enum("encounter_when", ("monsters", "clue"), None),
                    on_ward=read_effects(r, "on_ward"),
                    ward_stat=r.get_enum("ward_stat", ("health", "sanity"), None),
                )
                r.done()
                if bool(a.on_rest) != bool(a.rest_prompt):
                    raise ContentError(f"{r.path}: on_rest and rest_prompt go together")
                if a.count < 1 or a.cost < 0:
                    raise ContentError(f"{r.path}: count must be at least 1 and cost at least 0")
                if a.kind == "service" and not a.on_gain and a.action is None and a.id != "bank_loan":
                    raise ContentError(f"{r.path}: a service needs on_gain effects or an action")
                if bool(a.on_ward) != bool(a.ward_stat) or bool(a.on_encounter) != bool(a.encounter_when):
                    raise ContentError(f"{r.path}: a trigger needs its condition field")
                if (a.on_combat or a.on_encounter or a.on_ward) and not a.trigger_prompt:
                    raise ContentError(f"{r.path}: a trigger needs 'trigger_prompt'")
                if a.kind == "spell" and not a.backs:
                    raise ContentError(f"{r.path}: a spell needs at least one back")
                out.append(a)
        return out

    def conditions(self) -> list[ConditionDef]:
        out = []
        for r in _list_of_objects(self.file("conditions.json"), "conditions.json"):
            c = ConditionDef(
                id=_id(r),
                name=r.get_str("name"),
                expansion=r.get_enum("expansion", EXPANSIONS),
                traits=r.get_str_tuple("traits"),
                text=r.get_str("text"),
                modifiers=read_modifiers(r, "modifiers"),
                blocks=r.get_str_tuple("blocks", BLOCKABLE_ACTIONS),
                action=read_action(r, "action"),
                reckoning=read_effects(r, "reckoning"),
                backs=read_backs(r, "backs"),
                rest_roll=r.get_bool("rest_roll", False),
                replaces_encounter=r.get_bool("replaces_encounter", False),
            )
            r.done()
            if not c.backs:
                raise ContentError(f"{r.path}: a condition needs at least one back")
            out.append(c)
        return out

    def mythos(self) -> list[MythosDef]:
        out = []
        for r in _list_of_objects(self.file("mythos.json"), "mythos.json"):
            m = MythosDef(
                id=_id(r),
                name=r.get_str("name"),
                expansion=r.get_enum("expansion", EXPANSIONS),
                color=r.get_enum("color", MYTHOS_COLORS),
                traits=r.get_str_tuple("traits", MYTHOS_TRAITS),
                icons=r.get_str_tuple("icons", MYTHOS_ICONS),
                flavor=r.get_str("flavor", ""),
                text=r.get_str("text"),
                effects=read_effects(r, "effects"),
                reckoning=read_effects(r, "reckoning"),
                rumor_space=r.get_str("rumor_space", None),
                eldritch=r.get_int("eldritch", 0),
                encounter_text=r.get_str("encounter_text", ""),
                encounter_effects=read_effects(r, "encounter_effects"),
                on_zero_eldritch=read_effects(r, "on_zero_eldritch"),
                difficulty=r.get_enum("difficulty", MYTHOS_DIFFICULTIES),
                blocks=r.get_str_tuple("blocks", MYTHOS_BLOCKS),
                rumor_monster=r.get_str("rumor_monster", None),
                trophy_space=r.get_str("trophy_space", None),
            )
            r.done()
            if not m.traits:
                raise ContentError(f"{r.path}: mythos card needs at least one trait")
            out.append(m)
        return out

    def mystery(self, r: Reader) -> MysteryDef:
        m = MysteryDef(
            id=_id(r),
            name=r.get_str("name"),
            expansion=r.get_enum("expansion", EXPANSIONS),
            flavor=r.get_str("flavor", ""),
            text=r.get_str("text"),
            kind=r.get_enum("kind", MYSTERY_KINDS),
            amount=r.get_int("amount", 1),
            half_players=r.get_bool("half_players", False),
            per_investigator=r.get_bool("per_investigator", False),
            where=read_location_filter(r, "where"),
            skill=r.get_enum("skill", SKILLS, None),
            mod=r.get_int("mod", 0),
            clue_cost=r.get_int("clue_cost", 0),
            monster=r.get_str("monster", None),
            spawn_at=r.get_str("spawn_at", None),
            on_enter=read_effects(r, "on_enter"),
            on_solve=read_effects(r, "on_solve"),
            deck=r.get_enum("deck", SPECIAL_DECKS, None),
            omen_match=r.get_bool("omen_match", False),
            spell_cost=r.get_int("spell_cost", 0),
            remove_gate=r.get_bool("remove_gate", False),
            token=r.get_bool("token", False),
            needs_solved=r.get_bool("needs_solved", False),
            spawn_when_solved=r.get_bool("spawn_when_solved", False),
        )
        r.done()
        if m.amount < 1:
            raise ContentError(f"{r.path}: amount must be at least 1")
        if m.kind in ("defeat", "ambush") and m.monster is None:
            raise ContentError(f"{r.path}: a {m.kind} mystery needs a monster")
        if m.kind == "special" and m.deck is None:
            raise ContentError(f"{r.path}: a special mystery needs a deck")
        return m

    def _stage(self, r: Reader) -> StageComp:
        s = StageComp(r.get_int("green"), r.get_int("yellow"), r.get_int("blue"))
        r.done()
        return s

    def old_ones(self) -> list[OldOneDef]:
        out = []
        for r in _list_of_objects(self.file("old_ones.json"), "old_ones.json"):
            aw = r.get_obj("awakening")
            fm_r = aw.opt_obj("final_mystery")
            cult_back = aw.opt_obj("cultist")
            awakening = AwakeningDef(
                text=aw.get_str("text"),
                effects=read_effects(aw, "effects"),
                reckoning=read_effects(aw, "reckoning"),
                doom_advance_effects=read_effects(aw, "doom_advance_effects"),
                lose_immediately=aw.get_bool("lose_immediately", False),
                final_mystery=self.mystery(fm_r) if fm_r is not None else None,
                cultist=self.monster(cult_back, cultist=True) if cult_back is not None else None,
                on_eldritch_move=read_effects(aw, "on_eldritch_move"),
            )
            aw.done()
            stages_list = [self._stage(sr) for sr in r.objects("stages")]
            if len(stages_list) != 3:
                raise ContentError(f"{r.at('stages')}: expected 3 stages")
            o = OldOneDef(
                id=_id(r),
                name=r.get_str("name"),
                expansion=r.get_enum("expansion", EXPANSIONS),
                title=r.get_str("title"),
                difficulty=r.get_enum("difficulty", ("low", "medium", "high")),
                description=r.get_str("description"),
                art=r.get_str("art"),
                doom=r.get_int("doom"),
                stages=(stages_list[0], stages_list[1], stages_list[2]),
                modifiers=read_modifiers(r, "modifiers"),
                rules_text=r.get_str_tuple("rules_text"),
                setup=read_effects(r, "setup"),
                reckoning=read_effects(r, "reckoning"),
                omen_green_eldritch_doom=r.get_bool("omen_green_eldritch_doom", False),
                mysteries=tuple(self.mystery(x) for x in r.objects("mysteries")),
                mysteries_needed=r.get_int("mysteries_needed", 3),
                awakening=awakening,
                cultist=self.monster(r.get_obj("cultist"), cultist=True),
                set_aside=r.get_str_tuple("set_aside"),
                on_eldritch_move=read_effects(r, "on_eldritch_move"),
            )
            r.done()
            if o.doom < 1:
                raise ContentError(f"{r.path}: doom must be at least 1")
            if not 1 <= o.mysteries_needed <= len(o.mysteries):
                raise ContentError(f"{r.path}: mysteries_needed must be between 1 and the number of mysteries")
            if not awakening.lose_immediately and awakening.final_mystery is None:
                raise ContentError(f"{r.path}.awakening: needs final_mystery unless lose_immediately is true")
            out.append(o)
        return out

    def _section(self, r: Reader) -> EncounterSection:
        section = EncounterSection(
            text=r.get_str("text"),
            effects=read_effects(r, "effects"),
            location=r.get_str("location", None),
            terrain=r.get_enum("terrain", TERRAINS, None),
        )
        r.done()
        if bool(section.location) == bool(section.terrain):
            raise ContentError(f"{r.path}: a section needs exactly one of 'location' or 'terrain'")
        return section

    def encounters(
        self, old_ones: dict[str, OldOneDef]
    ) -> tuple[dict[str, EncounterDef], dict[str, tuple[str, ...]]]:
        folder = self.root / "encounters"
        if not folder.is_dir():
            raise ContentError(f"{folder}: encounter folder not found")
        encounters: dict[str, EncounterDef] = {}
        decks: dict[str, tuple[str, ...]] = {}
        research_decks = {f"research_{oid}" for oid in old_ones}
        valid = {*BASE_ENCOUNTER_DECKS, *research_decks, *SPECIAL_DECKS}
        for path in sorted(folder.glob("*.json")):
            deck = path.stem
            name = f"encounters/{path.name}"
            if deck not in valid:
                raise ContentError(f"{name}: '{deck}' is not a valid encounter deck")
            ids = []
            for r in _list_of_objects(_read_json(path), name):
                e = EncounterDef(
                    id=_id(r),
                    deck=deck,
                    title=r.get_str("title"),
                    expansion=r.get_enum("expansion", EXPANSIONS),
                    text=r.get_str("text", ""),
                    effects=read_effects(r, "effects"),
                    terrain=r.get_enum("terrain", TERRAINS, None),
                    location=r.get_str("location", None),
                    sections=tuple(self._section(sr) for sr in r.objects("sections", [])),
                )
                if e.sections and (e.text or e.effects or e.terrain or e.location):
                    raise ContentError(f"{r.path}: use either 'sections' or a single-section card, not both")
                if not e.sections and not e.text:
                    raise ContentError(f"{r.path}: missing required field 'text'")
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
        self.check_mythos()
        self.check_encounters()
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
        if not any(loc.gate_color for loc in c.locations.values()):
            self.fail("map.json: at least one location must have a gate_color")
        for exp in EXPEDITION_LOCATIONS:
            if exp not in c.locations or not c.locations[exp].expedition:
                self.fail(f"map.json: expedition location '{exp}' is missing or not marked expedition")

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
        if not any(a.kind in RESERVE_KINDS for a in self.c.assets.values()):
            self.fail("assets.json: the reserve needs at least one item, ally, trinket, or service")

    def check_monsters(self) -> None:
        if not any(not m.epic for m in self.c.monsters.values()):
            self.fail("monsters.json: need at least one ordinary (non-epic) monster")
        if "cultist" not in self.c.monsters:
            self.fail("monsters.json: must define 'cultist'")

    def check_old_ones(self) -> None:
        c = self.c
        by_color = {
            color: sum(1 for m in c.mythos.values() if m.color == color) for color in MYTHOS_COLORS
        }
        for o in c.old_ones.values():
            where = f"old_ones.json '{o.id}'"
            for m in o.set_aside:
                if m not in c.monsters or c.monsters[m].epic:
                    self.fail(f"{where}: '{m}' is not an ordinary monster")
            for name, count in Counter(o.set_aside).items():
                if count > c.monsters[name].count:
                    self.fail(f"{where}: sets aside more '{name}' tokens than the cup holds")
            need_green = sum(s.green for s in o.stages)
            need_yellow = sum(s.yellow for s in o.stages)
            need_blue = sum(s.blue for s in o.stages)
            if need_green > by_color["green"] or need_yellow > by_color["yellow"] or need_blue > by_color["blue"]:
                self.fail(f"{where}: not enough mythos cards to build stages")
            mysteries = list(o.mysteries)
            if o.awakening.final_mystery is not None:
                mysteries.append(o.awakening.final_mystery)
            for mys in mysteries:
                if mys.kind == "ambush" and mys.monster not in c.monsters:
                    self.fail(f"{where}: mystery '{mys.id}' ambushes with unknown monster '{mys.monster}'")
                if mys.kind == "defeat" and (mys.monster not in c.monsters or not c.monsters[mys.monster].epic):
                    self.fail(f"{where}: mystery '{mys.id}' needs an epic monster, not '{mys.monster}'")
                if mys.spawn_at and mys.spawn_at != "random" and mys.spawn_at not in c.locations:
                    self.fail(f"{where}: mystery '{mys.id}' spawns at unknown location '{mys.spawn_at}'")
                if mys.where:
                    for _table, ref in mys.where.refs():
                        if ref not in c.locations:
                            self.fail(f"{where}: mystery '{mys.id}' refers to unknown location '{ref}'")
            ids = [m.id for m in o.mysteries]
            if len(ids) != len(set(ids)):
                self.fail(f"{where}: mystery ids must be unique")

    def check_mythos(self) -> None:
        c = self.c
        for m in c.mythos.values():
            if m.rumor_space and m.rumor_space != ACTIVE_EXPEDITION and m.rumor_space not in c.locations:
                self.fail(f"mythos.json '{m.id}': unknown rumor_space '{m.rumor_space}'")
            if m.trophy_space and m.trophy_space not in c.locations:
                self.fail(f"mythos.json '{m.id}': unknown trophy_space '{m.trophy_space}'")
            if m.rumor_monster and m.rumor_monster not in c.monsters:
                self.fail(f"mythos.json '{m.id}': unknown rumor_monster '{m.rumor_monster}'")

    def check_encounters(self) -> None:
        c = self.c
        cities = {
            region: {loc.id for loc in c.locations.values() if loc.region == region and loc.terrain == "city"}
            for region in LOCATION_DECKS
        }
        named_cities = {
            loc.id for loc in c.locations.values() if loc.terrain == "city" and not loc.id.startswith("space_")
        }
        for e in c.encounters.values():
            if e.location and e.location not in c.locations:
                self.fail(f"encounters '{e.id}': unknown location '{e.location}'")
            if e.deck == "expedition" and (e.location not in EXPEDITION_LOCATIONS):
                self.fail(f"encounters '{e.id}': expedition card needs an expedition location")
            if e.deck in LOCATION_DECKS:
                expected = cities[e.deck] & named_cities
                actual = {s.location for s in e.sections}
                if actual != expected:
                    self.fail(
                        f"encounters '{e.id}': {e.deck} sections must cover {', '.join(sorted(expected))}"
                    )
            elif e.deck == "general":
                actual_terrains = {s.terrain for s in e.sections}
                if actual_terrains != set(TERRAINS):
                    self.fail(f"encounters '{e.id}': general sections must cover every terrain")
            elif e.sections:
                self.fail(f"encounters '{e.id}': deck '{e.deck}' does not use sections")
            for s in e.sections:
                if s.location and s.location not in c.locations:
                    self.fail(f"encounters '{e.id}': unknown section location '{s.location}'")

    def monster_lists(self, where: str, mon: MonsterDef) -> Iterable[tuple[str, Sequence[Effect], bool]]:
        yield f"{where} on_spawn", mon.on_spawn, True
        yield f"{where} reckoning", mon.reckoning, True
        for name, effects in mon.combat_hooks().items():
            yield f"{where} {name}", effects, False
        if mon.replace_encounter:
            yield f"{where} replace_encounter", mon.replace_encounter.effects, False

    def effect_lists(self) -> Iterable[tuple[str, Sequence[Effect], bool]]:
        """Every effect list in the content, with a flag for 'runs with no investigator'."""
        c = self.c
        for e in c.encounters.values():
            yield f"encounters '{e.id}'", e.effects, False
            for i, section in enumerate(e.sections):
                yield f"encounters '{e.id}' section {i}", section.effects, False
        for m in c.mythos.values():
            yield f"mythos.json '{m.id}' effects", m.effects, True
            yield f"mythos.json '{m.id}' reckoning", m.reckoning, True
            yield f"mythos.json '{m.id}' encounter_effects", m.encounter_effects, False
            yield f"mythos.json '{m.id}' on_zero_eldritch", m.on_zero_eldritch, True
        for o in c.old_ones.values():
            yield f"old_ones.json '{o.id}' setup", o.setup, True
            yield f"old_ones.json '{o.id}' reckoning", o.reckoning, True
            yield f"old_ones.json '{o.id}' awakening", o.awakening.effects, True
            yield f"old_ones.json '{o.id}' awakening reckoning", o.awakening.reckoning, True
            yield f"old_ones.json '{o.id}' awakening doom_advance", o.awakening.doom_advance_effects, True
            cultists = [o.cultist] if o.awakening.cultist is None else [o.cultist, o.awakening.cultist]
            for cultist in cultists:
                yield from self.monster_lists(f"old_ones.json '{o.id}' cultist", cultist)
            yield f"old_ones.json '{o.id}' on_eldritch_move", o.on_eldritch_move, False
            yield f"old_ones.json '{o.id}' awakening on_eldritch_move", o.awakening.on_eldritch_move, False
            for mys in o.mysteries:
                yield f"old_ones.json '{o.id}' mystery '{mys.id}' on_enter", mys.on_enter, True
                yield f"old_ones.json '{o.id}' mystery '{mys.id}' on_solve", mys.on_solve, True
            if o.awakening.final_mystery:
                yield (
                    f"old_ones.json '{o.id}' final_mystery on_enter",
                    o.awakening.final_mystery.on_enter,
                    True,
                )
        for mon in c.monsters.values():
            yield from self.monster_lists(f"monsters.json '{mon.id}'", mon)
        for a in c.assets.values():
            yield f"asset '{a.id}' on_gain", a.on_gain, False
            yield f"asset '{a.id}' reckoning", a.reckoning, False
            yield f"asset '{a.id}' on_rest", a.on_rest, False
            yield f"asset '{a.id}' rest_aura", a.rest_aura, False
            yield f"asset '{a.id}' on_close_gate", a.on_close_gate, False
            yield f"asset '{a.id}' on_combat_win", a.on_combat_win, False
            yield f"asset '{a.id}' on_combat", a.on_combat, False
            yield f"asset '{a.id}' on_encounter", a.on_encounter, False
            yield f"asset '{a.id}' on_ward", a.on_ward, False
            if a.action:
                yield f"asset '{a.id}' action", a.action.effects, False
            for i, back in enumerate(a.backs):
                yield f"asset '{a.id}' back {i}", back.effects, False
        for cond in c.conditions.values():
            yield f"conditions.json '{cond.id}' reckoning", cond.reckoning, False
            if cond.action:
                yield f"conditions.json '{cond.id}' action", cond.action.effects, False
            for i, back in enumerate(cond.backs):
                yield f"conditions.json '{cond.id}' back {i}", back.effects, False
        for inv in c.investigators.values():
            yield f"investigators.json '{inv.id}' on_start", inv.on_start, False
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
        for cond in self.c.conditions.values():
            self.check_ability_refs(f"condition '{cond.id}'", cond.action)
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

