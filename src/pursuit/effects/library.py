"""Every effect type that content JSON can use. Importing this module registers them."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import ClassVar

from pursuit.content.defs import (
    ASSET_KINDS,
    CONTEXTS,
    OMEN_TRACK,
    RESERVE_KINDS,
    SKILLS,
    TERRAINS,
    TICKET_KINDS,
    Cost,
    InvestigatorFilter,
    read_cost,
    read_investigator_filter,
)
from pursuit.content.reader import ContentError, Reader
from pursuit.controller import Option
from pursuit.effects.base import Ctx, Effect, read_effects, register, run_effects, walk
from pursuit.engine import actions, combat, phases, rules
from pursuit.engine.dice import run_test
from pursuit.engine.state import AssetCard, Investigator


def _nonzero(r: Reader, key: str) -> int:
    value: int = r.get_int(key)
    if value == 0:
        raise ContentError(f"{r.at(key)}: amount cannot be 0")
    return value


def _positive(r: Reader, key: str, default: int = 1) -> int:
    value: int = r.get_int(key, default)
    if value < 1:
        raise ContentError(f"{r.at(key)}: must be at least 1")
    return value


OPEN_ENDED = ("flip_self", "clues_per_success")


# --- narrative and tests --------------------------------------------------------------


@register("text")
@dataclass(frozen=True)
class Text(Effect):
    text: str

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_str("text"))

    def apply(self, ctx: Ctx) -> None:
        rules.emit(ctx.game, "info", self.text)

    def needs_investigator(self) -> bool:
        return False


@register("test")
@dataclass(frozen=True)
class Test(Effect):
    skill: str
    mod: int
    needed: int
    context: str
    passed: tuple[Effect, ...]
    failed: tuple[Effect, ...]
    after: tuple[Effect, ...]
    clue_bonus: bool
    sanity_dice: bool
    minus_per: str | None

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(
            skill=r.get_enum("skill", SKILLS),
            mod=r.get_int("mod", 0),
            needed=_positive(r, "needed"),
            context=r.get_enum("context", CONTEXTS, "encounter"),
            passed=read_effects(r, "pass"),
            failed=read_effects(r, "fail"),
            after=read_effects(r, "after"),
            clue_bonus=r.get_bool("clue_bonus", False),
            sanity_dice=r.get_bool("sanity_dice", False),
            minus_per=r.get_enum("minus_per", ("spell", "cultist"), None),
        )

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        counts_successes = any(e.kind in OPEN_ENDED for lst in self.children() for e in walk(lst))
        mod = self.mod - self._penalty(ctx, inv) + self._buy_dice(ctx, inv)
        result = run_test(
            ctx.game,
            inv,
            self.skill,
            mod,
            contexts=(self.context, ctx.tag) if ctx.tag else (self.context,),
            needed=self.needed,
            open_ended=counts_successes,
        )
        successes = result.successes + self._spend_clues(ctx, inv, result.successes)
        if ctx.asset is not None and self.skill == "lore" and successes >= self.needed:
            ctx.game.spell_lore_passed = True
        sub_ctx = replace(ctx, test_successes=successes)
        run_effects(self.passed if successes >= self.needed else self.failed, sub_ctx)
        if self.after:
            run_effects(self.after, sub_ctx)

    def _penalty(self, ctx: Ctx, inv: Investigator) -> int:
        game = ctx.game
        if self.minus_per == "spell":
            return sum(game.asset_def(c).kind == "spell" for c in inv.assets)
        if self.minus_per == "cultist":
            return sum(m.def_id == "cultist" for _loc, m in game.all_monsters())
        return 0

    def _buy_dice(self, ctx: Ctx, inv: Investigator) -> int:
        bought = 0
        while self.sanity_dice and inv.sanity - bought > 1:
            prompt = "Spend 1 Sanity to roll 1 additional die?"
            if not rules.confirm(ctx.game, prompt, kind="spend_for_test", inv=inv):
                break
            bought += 1
        if bought:
            rules.change_sanity(ctx.game, inv, -bought, preventable=False)
        return bought

    def _spend_clues(self, ctx: Ctx, inv: Investigator, successes: int) -> int:
        added = 0
        while self.clue_bonus and inv.clues > 0 and successes + added < self.needed:
            prompt = f"{successes + added}/{self.needed} successes. Spend 1 Clue to add 1 success?"
            if not rules.confirm(ctx.game, prompt, kind="spend_for_test", inv=inv):
                break
            rules.change_clues(ctx.game, inv, -1)
            added += 1
        return added

    def children(self) -> Iterable[Sequence[Effect]]:
        return (self.passed, self.failed, self.after)


# --- investigator resources -----------------------------------------------------------


@register("health")
@dataclass(frozen=True)
class Health(Effect):
    amount: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_nonzero(r, "amount"))

    def apply(self, ctx: Ctx) -> None:
        rules.change_health(ctx.game, ctx.need_inv(self.kind), self.amount)


@register("sanity")
@dataclass(frozen=True)
class Sanity(Effect):
    amount: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_nonzero(r, "amount"))

    def apply(self, ctx: Ctx) -> None:
        rules.change_sanity(ctx.game, ctx.need_inv(self.kind), self.amount)


@register("recover_all")
@dataclass(frozen=True)
class RecoverAll(Effect):
    health: bool
    sanity: bool

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_bool("health", True), r.get_bool("sanity", True))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        if self.health and inv.health < inv.max_health:
            rules.change_health(game, inv, inv.max_health - inv.health)
        if self.sanity and not inv.defeated and inv.sanity < inv.max_sanity:
            rules.change_sanity(game, inv, inv.max_sanity - inv.sanity)


@register("clues")
@dataclass(frozen=True)
class Clues(Effect):
    amount: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_nonzero(r, "amount"))

    def apply(self, ctx: Ctx) -> None:
        rules.change_clues(ctx.game, ctx.need_inv(self.kind), self.amount)


@register("clues_per_success")
@dataclass(frozen=True)
class CluesPerSuccess(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        rules.change_clues(ctx.game, ctx.need_inv(self.kind), ctx.test_successes or 0)


@register("claim_clue")
@dataclass(frozen=True)
class ClaimClue(Effect):
    bonus: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_int("bonus", 0))

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        state = ctx.game.locations[inv.location]
        if state.clue:
            state.clue = False
            rules.change_clues(ctx.game, inv, 1 + self.bonus)
        elif self.bonus > 0:
            rules.change_clues(ctx.game, inv, self.bonus)


@register("gain_ticket")
@dataclass(frozen=True)
class GainTicket(Effect):
    ticket_kind: str

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_enum("kind", (*TICKET_KINDS, "choose"), "choose"))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        kind = self.ticket_kind
        if kind == "choose":
            options = [Option("Train Ticket", "train"), Option("Ship Ticket", "ship")]
            pick = rules.choose(game, "Gain which travel ticket?", options, kind="prepare_ticket", inv=inv)
            kind = options[pick].value
        rules.gain_ticket(game, inv, kind)


@register("improve_skill")
@dataclass(frozen=True)
class ImproveSkill(Effect):
    skill: str
    amount: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_enum("skill", (*SKILLS, "choose")), _nonzero(r, "amount") if r.has("amount") else 1)

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        cap = game.content.rules.max_improvement
        skill = self.skill
        if skill == "choose":
            options = [
                Option(s.title(), s, f"now {inv.skill(s)}", enabled=inv.improvements.get(s, 0) < cap) for s in SKILLS
            ]
            if not any(o.enabled for o in options):
                return
            skill = SKILLS[rules.choose(game, "Improve which skill?", options, kind="improve", inv=inv)]
        current = inv.improvements.get(skill, 0)
        delta = self.amount
        if delta > 0 and rules.perk(game, inv, "double_improve") > 0:
            delta += 1
        new = max(-inv.skills[skill] + 1, min(cap, current + delta))
        if new == current:
            return
        inv.improvements[skill] = new
        word = "improves" if new > current else "impairs"
        rules.emit(
            game, "gain" if new > current else "loss", f"{inv.name}'s {skill.title()} {word} to {inv.skill(skill)}."
        )


@register("extra_action")
@dataclass(frozen=True)
class ExtraAction(Effect):
    immediate: bool

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_bool("immediate", False))

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        rules.emit(ctx.game, "gain", f"{inv.name} may perform 1 additional action.")
        if self.immediate:
            actions.additional_action(ctx.game, inv)
        else:
            inv.bonus_actions += 1


# --- assets and conditions ------------------------------------------------------------


@register("gain_asset")
@dataclass(frozen=True)
class GainAsset(Effect):
    asset_id: str | None
    asset_kind: str | None
    trait: str | None
    source: str
    count: int
    any_of: tuple[str, ...]

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        e = cls(
            asset_id=r.get_str("id", None),
            asset_kind=r.get_enum("kind", ASSET_KINDS, None),
            trait=r.get_str("trait", None),
            source=r.get_enum("source", ("deck", "reserve", "choice"), "deck"),
            count=_positive(r, "count"),
            any_of=r.get_str_tuple("any_of"),
        )
        if e.source == "reserve" and (e.asset_id or (e.asset_kind and e.asset_kind not in RESERVE_KINDS)):
            raise ContentError(f"{r.path}: a reserve gain can only filter by a reserve kind and a trait")
        return e

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        for _ in range(self.count):
            src = self.source
            if src == "choice":
                matching_res = [
                    c
                    for c in game.reserve
                    if (self.asset_kind is None or game.asset_def(c).kind == self.asset_kind)
                    and (self.trait is None or self.trait in game.asset_def(c).traits)
                ]
                if matching_res:
                    opts = [Option("Take from the reserve", "reserve"), Option("Draw from the deck", "deck")]
                    src = opts[rules.choose(game, "Gain asset from where?", opts, kind="gain_source", inv=inv)].value
                else:
                    src = "deck"

            if src == "reserve":
                cards = [
                    c
                    for c in game.reserve
                    if (self.asset_kind is None or game.asset_def(c).kind == self.asset_kind)
                    and (self.trait is None or self.trait in game.asset_def(c).traits)
                    and (not self.any_of or any(game.asset_def(c).is_a(k) for k in self.any_of))
                ]
                if not cards:
                    rules.emit(game, "info", "No matching Asset is in the reserve.")
                    return
                options = [Option(game.asset_def(c).name, c.uid, game.asset_def(c).text) for c in cards]
                card = cards[
                    rules.choose(game, "Take one Asset from the reserve.", options, kind="gain_reserve", inv=inv)
                ]
                game.reserve.remove(card)
                rules.refill_reserve(game)
            else:
                found = rules.draw_matching(game, asset_id=self.asset_id, kind=self.asset_kind, trait=self.trait)
                if found is None:
                    rules.emit(game, "info", "There are no matching cards left.")
                    return
                card = found
            rules.gain_card(game, inv, card)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("asset", self.asset_id)] if self.asset_id else []


@register("lose_asset")
@dataclass(frozen=True)
class LoseAsset(Effect):
    asset_id: str | None
    asset_kind: str | None
    trait: str | None
    count: int
    every: bool

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(
            asset_id=r.get_str("id", None),
            asset_kind=r.get_enum("kind", ASSET_KINDS, None),
            trait=r.get_str("trait", None),
            count=_positive(r, "count"),
            every=r.get_bool("all", False),
        )

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)

        def matching() -> list:
            return [
                c
                for c in inv.assets
                if (self.asset_id is None or c.def_id == self.asset_id)
                and (self.asset_kind is None or game.asset_def(c).is_a(self.asset_kind))
                and (self.trait is None or self.trait in game.asset_def(c).traits)
            ]

        times = len(inv.assets) if self.every else self.count
        for _ in range(times):
            cards = matching()
            if not cards:
                return
            if self.every:
                card = cards[0]
            else:
                options = [Option(game.asset_def(c).name, c.uid) for c in cards]
                card = cards[
                    rules.choose(
                        game, "Choose a possession to discard.", options, kind="lose_asset", inv=inv, auto_single=True
                    )
                ]
            rules.discard_asset(game, inv, card)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("asset", self.asset_id)] if self.asset_id else []


@register("gain_condition")
@dataclass(frozen=True)
class GainCondition(Effect):
    condition: str | None
    trait: str | None

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        e = cls(r.get_str("id", None), r.get_str("trait", None))
        if bool(e.condition) == bool(e.trait):
            raise ContentError(f"{r.path}: gain_condition needs exactly one of 'id' or 'trait'")
        return e

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        if self.condition:
            rules.gain_condition(ctx.game, inv, self.condition)
        elif self.trait:
            rules.gain_condition_trait(ctx.game, inv, self.trait)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("condition", self.condition)] if self.condition else []


@register("remove_condition")
@dataclass(frozen=True)
class RemoveCondition(Effect):
    condition: str | None
    trait: str | None

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        e = cls(r.get_str("id", None), r.get_str("trait", None))
        if not e.condition and not e.trait:
            raise ContentError(f"{r.path}: remove_condition needs 'id' or 'trait'")
        return e

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        for inst in list(inv.conditions):
            cdef = game.content.conditions[inst.def_id]
            if (self.condition and cdef.id == self.condition) or (self.trait and self.trait in cdef.traits):
                rules.remove_condition(game, inv, inst)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("condition", self.condition)] if self.condition else []


@register("remove_any_condition")
@dataclass(frozen=True)
class RemoveAnyCondition(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        if not inv.conditions:
            return
        options = [Option(game.content.conditions[c.def_id].name, c.uid) for c in inv.conditions]
        pick = rules.choose(
            game, "Discard which Condition?", options, kind="remove_condition", inv=inv, auto_single=True
        )
        inst = next(c for c in inv.conditions if c.uid == options[pick].value)
        rules.remove_condition(game, inv, inst)


@register("remove_self")
@dataclass(frozen=True)
class RemoveSelf(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        if ctx.condition is not None:
            for person in ctx.game.investigators:
                if ctx.condition in person.conditions:
                    rules.remove_condition(ctx.game, person, ctx.condition)
                    return
        elif ctx.asset is not None:
            owner = next((i for i in ctx.game.investigators if ctx.asset in i.assets), ctx.inv)
            if owner is not None:
                rules.discard_asset(ctx.game, owner, ctx.asset)
        elif ctx.mythos is not None:
            rules.solve_rumor(ctx.game, ctx.mythos)


@register("flip_self")
@dataclass(frozen=True)
class FlipSelf(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        if ctx.condition is not None:
            rules.flip_condition(ctx.game, inv, ctx.condition, ctx.test_successes)
        elif ctx.asset is not None:
            owner = next((i for i in ctx.game.investigators if ctx.asset in i.assets), inv)
            rules.flip_asset(ctx.game, owner, ctx.asset, ctx.test_successes)


@register("flip_conditions")
@dataclass(frozen=True)
class FlipConditions(Effect):
    condition_id: str | None
    trait: str | None

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_str("id", None), r.get_str("trait", None))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        for inst in list(inv.conditions):
            cdef = game.content.conditions[inst.def_id]
            if (self.condition_id is None or cdef.id == self.condition_id) and (
                self.trait is None or self.trait in cdef.traits
            ):
                rules.flip_condition(game, inv, inst)
                if inv.defeated or game.outcome:
                    return


# --- movement and status --------------------------------------------------------------


MOVE_KEYWORDS = (
    "nearest_city",
    "random_city",
    "start",
    "choose_adjacent",
    "nearest_gate",
    "choose_within",
    "ship_path",
)


@register("move")
@dataclass(frozen=True)
class Move(Effect):
    to: str
    range: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        e = cls(r.get_str("to"), r.get_int("range", 0))
        if (e.to == "choose_within") != (e.range > 0):
            raise ContentError(f'{r.path}: use \'range\' with "to": "choose_within", and only there')
        return e

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        content = game.content
        dest: str | None
        if self.to == "start":
            dest = content.investigators[inv.def_id].start
        elif self.to == "random_city":
            dest = game.rng.choice(sorted(loc.id for loc in content.locations.values() if loc.terrain == "city"))
        elif self.to == "nearest_city":
            dest = rules.nearest_city(game, inv.location)
        elif self.to == "nearest_gate":
            dist = rules.distances(game, inv.location)
            gates = [loc for loc in game.open_gates() if loc in dist]
            dest = min(gates, key=lambda loc: (dist[loc], loc)) if gates else None
        elif self.to == "choose_adjacent":
            near = rules.neighbors(game, inv.location)
            options = [Option(rules.loc_name(game, loc), loc, k) for loc, k in near]
            dest = near[rules.choose(game, "Where do you move?", options, kind="move", inv=inv)][0]
        elif self.to == "ship_path":
            near = [(loc, k) for loc, k in rules.neighbors(game, inv.location) if k == "ship"]
            if not near:
                return
            options = [Option(rules.loc_name(game, loc), loc, "ship path") for loc, _ in near]
            pick = rules.choose(game, "Move along which Ship path?", options, kind="move", inv=inv, auto_single=True)
            dest = near[pick][0]
        elif self.to == "choose_within":
            dist = rules.distances(game, inv.location)
            places = sorted(
                (loc for loc, d in dist.items() if 0 < d <= self.range),
                key=lambda loc: (dist[loc], rules.loc_name(game, loc)),
            )
            options = [Option(rules.loc_name(game, loc), loc, f"{dist[loc]} space(s)") for loc in places]
            options.append(Option("Stay here", None))
            dest = options[rules.choose(game, "Where do you move?", options, kind="move", inv=inv)].value
        else:
            dest = self.to
        if dest:
            rules.move_investigator(game, inv, dest)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [] if self.to in MOVE_KEYWORDS else [("location", self.to)]


@register("nearest_terrain")
@dataclass(frozen=True)
class NearestTerrain(Effect):
    terrain: str

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_enum("terrain", TERRAINS))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        dist = rules.distances(game, inv.location)
        places = [
            loc
            for loc in game.content.locations.values()
            if loc.terrain == self.terrain and loc.id in dist and loc.id != inv.location
        ]
        if not places:
            return
        dest = min(places, key=lambda loc: (dist[loc.id], loc.name)).id
        rules.move_investigator(game, inv, dest)

    def needs_investigator(self) -> bool:
        return True


@register("delay")
@dataclass(frozen=True)
class Delay(Effect):
    chosen: bool

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_bool("chosen", False))

    def apply(self, ctx: Ctx) -> None:
        rules.delay(ctx.game, ctx.need_inv(self.kind), chosen=self.chosen)


@register("devour")
@dataclass(frozen=True)
class Devour(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        rules.devour_investigator(ctx.game, inv)


@register("swap_health_sanity")
@dataclass(frozen=True)
class SwapHealthSanity(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        most_h_to_s = min(inv.health - 1, inv.max_sanity - inv.sanity)
        most_s_to_h = min(inv.sanity - 1, inv.max_health - inv.health)
        options = [
            Option("Spend Health to recover Sanity", "h_to_s", enabled=most_h_to_s > 0),
            Option("Spend Sanity to recover Health", "s_to_h", enabled=most_s_to_h > 0),
            Option("Done", None),
        ]
        way = options[rules.choose(game, "Martial Arts focus:", options, kind="effect_choice", inv=inv)].value
        if way is None:
            return
        most = most_h_to_s if way == "h_to_s" else most_s_to_h
        amounts = [Option(str(n), n) for n in range(1, most + 1)]
        pick = rules.choose(game, "Spend how many?", amounts, kind="amount", inv=inv, auto_single=True)
        amount = amounts[pick].value
        if way == "h_to_s":
            rules.change_health(game, inv, -amount, preventable=False)
            rules.change_sanity(game, inv, amount)
        else:
            rules.change_sanity(game, inv, -amount, preventable=False)
            rules.change_health(game, inv, amount)


@register("condition_penalty")
@dataclass(frozen=True)
class ConditionPenalty(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        traits = [t for inst in inv.conditions for t in game.content.conditions[inst.def_id].traits]
        injuries = traits.count("injury")
        madness = traits.count("madness")
        deals = traits.count("deal")
        if injuries:
            rules.change_health(game, inv, -injuries)
        if madness and not inv.defeated:
            rules.change_sanity(game, inv, -madness)
        if deals and not inv.defeated:
            rules.change_clues(game, inv, -deals)


# --- doom, omen, eldritch tokens ------------------------------------------------------


@register("advance_doom")
@dataclass(frozen=True)
class AdvanceDoom(Effect):
    amount: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_positive(r, "amount"))

    def apply(self, ctx: Ctx) -> None:
        rules.advance_doom(ctx.game, self.amount)

    def needs_investigator(self) -> bool:
        return False


@register("retreat_doom")
@dataclass(frozen=True)
class RetreatDoom(Effect):
    amount: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_positive(r, "amount"))

    def apply(self, ctx: Ctx) -> None:
        rules.retreat_doom(ctx.game, self.amount)

    def needs_investigator(self) -> bool:
        return False


@register("advance_omen")
@dataclass(frozen=True)
class AdvanceOmen(Effect):
    amount: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_positive(r, "amount"))

    def apply(self, ctx: Ctx) -> None:
        rules.advance_omen(ctx.game, self.amount)

    def needs_investigator(self) -> bool:
        return False


@register("green_omen_eldritch")
@dataclass(frozen=True)
class GreenOmenEldritch(Effect):
    amount: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_nonzero(r, "amount"))

    def apply(self, ctx: Ctx) -> None:
        ctx.game.green_eldritch = max(0, ctx.game.green_eldritch + self.amount)
        rules.emit(
            ctx.game,
            "info",
            f"Eldritch tokens on the green Omen space: {ctx.game.green_eldritch}.",
        )

    def needs_investigator(self) -> bool:
        return False


@register("sheet_token")
@dataclass(frozen=True)
class SheetToken(Effect):
    amount: int
    lose_at: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_nonzero(r, "amount"), r.get_int("lose_at", 0))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        game.sheet_tokens = max(0, game.sheet_tokens + self.amount)
        rules.emit(game, "info", f"Tokens on {game.old_one.name}: {game.sheet_tokens}.")
        if self.lose_at > 0 and game.sheet_tokens >= self.lose_at:
            rules.lose(game, f"There are {game.sheet_tokens} tokens on {game.old_one.name}! The world is lost.")

    def needs_investigator(self) -> bool:
        return False


@register("mythos_eldritch")
@dataclass(frozen=True)
class MythosEldritch(Effect):
    """Change the Eldritch tokens on this card. `per` scales a discard: half the Gates on the
    board, or the Madness Conditions of the Lead Investigator."""

    amount: int
    per: str | None

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_nonzero(r, "amount"), r.get_enum("per", ("half_gates", "lead_madness"), None))

    def _scale(self, ctx: Ctx) -> int:
        game = ctx.game
        if self.per == "half_gates":
            return (len(game.open_gates()) + 1) // 2
        if self.per == "lead_madness":
            lead = game.lead_investigator()
            return sum("madness" in game.content.conditions[c.def_id].traits for c in lead.conditions)
        return 1

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        active = ctx.mythos
        if active is None or active not in game.active_mythos:
            return
        active.eldritch = max(0, active.eldritch + self.amount * self._scale(ctx))
        mdef = game.content.mythos[active.def_id]
        rules.emit(game, "mythos", f"'{mdef.name}' now has {active.eldritch} Eldritch token(s).")
        if active.eldritch == 0 and mdef.on_zero_eldritch:
            run_effects(mdef.on_zero_eldritch, Ctx(game, None, f"mythos_zero:{mdef.id}", mythos=active))

    def needs_investigator(self) -> bool:
        return False


@register("solve_rumor")
@dataclass(frozen=True)
class SolveRumor(Effect):
    solved: bool

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_bool("solved", True))

    def apply(self, ctx: Ctx) -> None:
        if ctx.mythos is not None:
            rules.solve_rumor(ctx.game, ctx.mythos, solved=self.solved)

    def needs_investigator(self) -> bool:
        return False


@register("solve_rumor_in_play")
@dataclass(frozen=True)
class SolveRumorInPlay(Effect):
    """Solve one Rumor Mythos card that is already in play."""

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        rumors = [a for a in game.active_mythos if "rumor" in game.content.mythos[a.def_id].traits]
        if rumors:
            options = [Option(game.content.mythos[a.def_id].name, a.def_id) for a in rumors]
            pick = rules.choose(game, "Solve which Rumor?", options, kind="pick_rumor", auto_single=True)
            rules.solve_rumor(game, rumors[pick])

    def needs_investigator(self) -> bool:
        return False


# --- flow control ---------------------------------------------------------------------


@dataclass(frozen=True)
class ChoiceOption:
    label: str
    effects: tuple[Effect, ...]
    requires: InvestigatorFilter | None


@register("choice")
@dataclass(frozen=True)
class Choice(Effect):
    prompt: str
    options: tuple[ChoiceOption, ...]

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        options = []
        for o in r.objects("options"):
            options.append(
                ChoiceOption(o.get_str("label"), read_effects(o, "effects"), read_investigator_filter(o, "requires"))
            )
            o.done()
        if len(options) < 2:
            raise ContentError(f"{r.path}: a choice needs at least 2 options")
        return cls(r.get_str("prompt", "What do you do?"), tuple(options))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.inv
        opts = [
            Option(o.label, i, enabled=o.requires is None or (inv is not None and o.requires.matches(game, inv)))
            for i, o in enumerate(self.options)
        ]
        if not any(o.enabled for o in opts):
            return
        pick = rules.choose(game, self.prompt, opts, kind="effect_choice", inv=inv)
        run_effects(self.options[pick].effects, ctx)

    def children(self) -> Iterable[Sequence[Effect]]:
        return [o.effects for o in self.options]

    def refs(self) -> Iterable[tuple[str, str]]:
        for o in self.options:
            if o.requires:
                yield from o.requires.refs()

    def needs_investigator(self) -> bool:
        return any(o.requires is not None for o in self.options)


@register("pay")
@dataclass(frozen=True)
class Pay(Effect):
    cost: Cost
    half_players_clues: bool
    prompt: str
    then: tuple[Effect, ...]
    otherwise: tuple[Effect, ...]

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        cost = read_cost(r, "cost")
        half = r.get_bool("half_players_clues", False)
        if cost.is_free() and not half:
            raise ContentError(f"{r.path}: a pay effect needs a cost")
        return cls(cost, half, r.get_str("prompt", ""), read_effects(r, "then"), read_effects(r, "else"))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        actual = self.cost
        if self.half_players_clues:
            half_n = max(1, (len(game.investigators) + 1) // 2)
            actual = Cost(clues=half_n, sanity=actual.sanity, health=actual.health, tickets=actual.tickets)
        prompt = self.prompt or f"Pay {actual.describe()}?"
        full_prompt = f"{prompt} ({actual.describe()})"
        if rules.can_pay(game, inv, actual) and rules.confirm(game, full_prompt, kind="pay", inv=inv):
            rules.pay_cost(game, inv, actual)
            run_effects(self.then, ctx)
        else:
            run_effects(self.otherwise, ctx)

    def children(self) -> Iterable[Sequence[Effect]]:
        return (self.then, self.otherwise)


@register("if")
@dataclass(frozen=True)
class If(Effect):
    has: InvestigatorFilter
    then: tuple[Effect, ...]
    otherwise: tuple[Effect, ...]

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        has = read_investigator_filter(r, "has")
        if has is None:
            raise ContentError(f"{r.path}: missing required field 'has'")
        return cls(has, read_effects(r, "then"), read_effects(r, "else"))

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        run_effects(self.then if self.has.matches(ctx.game, inv) else self.otherwise, ctx)

    def children(self) -> Iterable[Sequence[Effect]]:
        return (self.then, self.otherwise)

    def refs(self) -> Iterable[tuple[str, str]]:
        return self.has.refs()


@dataclass(frozen=True)
class RandomOutcome:
    weight: int
    text: str
    effects: tuple[Effect, ...]


@register("random")
@dataclass(frozen=True)
class Random(Effect):
    outcomes: tuple[RandomOutcome, ...]

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        outcomes = []
        for o in r.objects("outcomes"):
            outcomes.append(RandomOutcome(_positive(o, "weight"), o.get_str("text", ""), read_effects(o, "effects")))
            o.done()
        if len(outcomes) < 2:
            raise ContentError(f"{r.path}: random needs at least 2 outcomes")
        return cls(tuple(outcomes))

    def apply(self, ctx: Ctx) -> None:
        pick = ctx.game.rng.choices(self.outcomes, weights=[o.weight for o in self.outcomes])[0]
        if pick.text:
            rules.emit(ctx.game, "info", pick.text)
        run_effects(pick.effects, ctx)

    def children(self) -> Iterable[Sequence[Effect]]:
        return [o.effects for o in self.outcomes]

    def needs_investigator(self) -> bool:
        return False


@register("each_investigator")
@dataclass(frozen=True)
class EachInvestigator(Effect):
    provides_investigator: ClassVar[bool] = True
    where: InvestigatorFilter | None
    here: bool
    near_monster: int | None
    effects: tuple[Effect, ...]
    near_expedition: int | None = None
    others: bool = False

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(
            read_investigator_filter(r, "where"),
            r.get_bool("here", False),
            r.get_int("near_monster", None),
            read_effects(r, "effects"),
            r.get_int("near_expedition", None),
            r.get_bool("others", False),
        )

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        if self.here and ctx.inv is None:
            raise RuntimeError(f"each_investigator with here=true from {ctx.source} needs an investigator")
        spaces: set[str] = set()
        if self.near_monster is not None:
            center = rules.monster_location(game, ctx.need_monster(self.kind))
            if center is not None:
                dist = rules.distances(game, center)
                spaces = {loc for loc, d in dist.items() if d <= self.near_monster}
        near_exp: set[str] = set()
        if self.near_expedition is not None and game.active_expedition:
            dist = rules.distances(game, game.active_expedition)
            near_exp = {loc for loc, d in dist.items() if d <= self.near_expedition}
        targets = [
            i
            for i in game.turn_order()
            if not i.eliminated
            and not i.defeated
            and (not self.here or (ctx.inv is not None and i.location == ctx.inv.location))
            and (self.near_monster is None or i.location in spaces)
            and (self.near_expedition is None or i.location in near_exp)
            and (not self.others or i is not ctx.inv)
            and (self.where is None or self.where.matches(game, i))
        ]
        for inv in targets:
            if game.outcome:
                return
            run_effects(self.effects, ctx.for_inv(inv))

    def children(self) -> Iterable[Sequence[Effect]]:
        return (self.effects,)

    def refs(self) -> Iterable[tuple[str, str]]:
        return self.where.refs() if self.where else []

    def needs_investigator(self) -> bool:
        return self.here


PICKS = ("lead", "lowest_sanity", "lowest_health", "most_clues", "random", "choose")


@register("one_investigator")
@dataclass(frozen=True)
class OneInvestigator(Effect):
    provides_investigator: ClassVar[bool] = True
    pick: str
    where: InvestigatorFilter | None
    effects: tuple[Effect, ...]
    others: bool = False

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(
            r.get_enum("pick", PICKS),
            read_investigator_filter(r, "where"),
            read_effects(r, "effects"),
            r.get_bool("others", False),
        )

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        pool = [
            i
            for i in game.turn_order()
            if not i.eliminated
            and not i.defeated
            and (not self.others or i is not ctx.inv)
            and (self.where is None or self.where.matches(game, i))
        ]
        if not pool:
            return
        if self.pick == "lead":
            lead = game.lead_investigator()
            target = lead if lead in pool else pool[0]
        elif self.pick == "random":
            target = game.rng.choice(pool)
        elif self.pick == "choose":
            options = [Option(i.name, i.seat, rules.loc_name(game, i.location)) for i in pool]
            target = pool[rules.choose(game, "Choose an investigator.", options, kind="pick_investigator")]
        else:
            key = {
                "lowest_sanity": lambda i: (i.sanity, i.seat),
                "lowest_health": lambda i: (i.health, i.seat),
                "most_clues": lambda i: (-i.clues, i.seat),
            }[self.pick]
            target = min(pool, key=key)
        run_effects(self.effects, ctx.for_inv(target))

    def children(self) -> Iterable[Sequence[Effect]]:
        return (self.effects,)

    def refs(self) -> Iterable[tuple[str, str]]:
        return self.where.refs() if self.where else []

    def needs_investigator(self) -> bool:
        return False


# --- the world ------------------------------------------------------------------------


@register("spawn_gate")
@dataclass(frozen=True)
class SpawnGate(Effect):
    count: int
    location: str | None

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_positive(r, "count"), r.get_str("at", None))

    def apply(self, ctx: Ctx) -> None:
        for _ in range(self.count):
            if ctx.game.outcome:
                return
            rules.spawn_gate(ctx.game, self.location)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("location", self.location)] if self.location else []

    def needs_investigator(self) -> bool:
        return False


@register("close_gate")
@dataclass(frozen=True)
class CloseGate(Effect):
    """Close the Gate here. An Other World Encounter run from a Rumor solves that Rumor instead."""

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        if ctx.tag == "other_world" and ctx.mythos is not None:
            rules.solve_rumor(game, ctx.mythos)
            return
        had_gate = game.locations[inv.location].gate
        rules.close_gate(game, inv, inv.location)
        if ctx.tag == "other_world" and had_gate and not game.locations[inv.location].gate:
            for card in list(inv.assets):
                run_effects(game.asset_def(card).on_close_gate, replace(ctx, asset=card))


@register("discard_matching_gates")
@dataclass(frozen=True)
class DiscardMatchingGates(Effect):
    doom_per_gate: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_int("doom_per_gate", 1))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        matching = list(game.matching_gates())
        for loc in matching:
            rules.discard_gate(game, loc)
        if matching and self.doom_per_gate > 0:
            rules.advance_doom(game, len(matching) * self.doom_per_gate, "discarded matching Gates")

    def needs_investigator(self) -> bool:
        return False


@register("peek_gates")
@dataclass(frozen=True)
class PeekGates(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        cards = game.gate_deck.cards
        if len(cards) < 2:
            if cards:
                rules.emit(game, "info", f"Top Gate in the stack: {rules.loc_name(game, cards[0])}.")
            return
        top_two = [cards[0], cards[1]]
        options = [
            Option(f"Keep {rules.loc_name(game, top_two[0])} on top", 0),
            Option(f"Keep {rules.loc_name(game, top_two[1])} on top", 1),
        ]
        prompt = "Top 2 Gates in the stack. Put which on top (the other on the bottom)?"
        pick = rules.choose(game, prompt, options, kind="peek_gates", inv=inv)
        kept = top_two[pick]
        bottom = top_two[1 - pick]
        cards[:2] = [kept]
        cards.append(bottom)


@register("monster_surge")
@dataclass(frozen=True)
class MonsterSurge(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        rules.monster_surge(ctx.game)

    def needs_investigator(self) -> bool:
        return False


SPAWN_AT = ("here", "gates", "random_space", "active_expedition", "cultist_spaces", "monster_space")


@register("spawn_monster")
@dataclass(frozen=True)
class SpawnMonster(Effect):
    count: int
    monster: str | None
    at: str

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_positive(r, "count"), r.get_str("id", None), r.get_str("at", "random_space"))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        for _ in range(self.count):
            if self.at == "here":
                places = [ctx.need_inv(self.kind).location]
            elif self.at == "gates":
                places = game.open_gates()
            elif self.at == "active_expedition":
                places = [game.active_expedition] if game.active_expedition else [rules.random_space(game)]
            elif self.at == "monster_space":
                found = rules.monster_location(game, ctx.need_monster(self.kind))
                places = [found] if found else []
            elif self.at == "cultist_spaces":
                places = [
                    loc
                    for loc, st in game.locations.items()
                    if any(m.def_id == "cultist" for m in st.monsters)
                ]
            elif self.at == "random_space":
                places = [rules.random_space(game)]
            else:
                places = [self.at]
            for place in places:
                rules.spawn_monster(game, place, self.monster)

    def refs(self) -> Iterable[tuple[str, str]]:
        found = [("monster", self.monster)] if self.monster else []
        if self.at not in SPAWN_AT:
            found.append(("location", self.at))
        return found

    def needs_investigator(self) -> bool:
        return self.at == "here"


@register("ambush")
@dataclass(frozen=True)
class Ambush(Effect):
    monster: str | None

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_str("id", None))

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        combat.ambush(ctx.game, inv, self.monster)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("monster", self.monster)] if self.monster else []


@register("encounter_monsters")
@dataclass(frozen=True)
class EncounterMonsters(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        combat.resolve_monsters(ctx.game, inv)


@register("discard_monster")
@dataclass(frozen=True)
class DiscardMonster(Effect):
    where: str
    all_monsters: bool

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_enum("where", ("here", "choose_space"), "here"), r.get_bool("all", False))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        if self.where == "here":
            loc_id = ctx.need_inv(self.kind).location
        else:
            with_monsters = [
                loc
                for loc, st in game.locations.items()
                if any(not game.monster_def(m.def_id).epic for m in st.monsters)
            ]
            if not with_monsters:
                return
            options = [Option(rules.loc_name(game, loc), loc) for loc in with_monsters]
            pick = rules.choose(
                game, "Choose a space with Monsters:", options, kind="choose_space", inv=ctx.inv, auto_single=True
            )
            loc_id = with_monsters[pick]
        monsters = [m for m in game.locations[loc_id].monsters if not game.monster_def(m.def_id).epic]
        if not monsters:
            return
        if self.all_monsters:
            for monster in monsters:
                rules.discard_monster(game, loc_id, monster)
            return
        options = [Option(game.content.monsters[m.def_id].name, m.uid) for m in monsters]
        pick = rules.choose(
            game, "Discard which Monster?", options, kind="discard_monster", inv=ctx.inv, auto_single=True
        )
        monster = next(m for m in monsters if m.uid == options[pick].value)
        rules.discard_monster(game, loc_id, monster)

    def needs_investigator(self) -> bool:
        return self.where == "here"


@register("move_monster_here")
@dataclass(frozen=True)
class MoveMonsterHere(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        candidates = [
            (loc, monster)
            for loc, monster in game.all_monsters()
            if not game.content.monsters[monster.def_id].epic and loc != inv.location
        ]
        if not candidates:
            return
        options = [
            Option(f"{game.content.monsters[m.def_id].name} at {rules.loc_name(game, loc)}", i)
            for i, (loc, m) in enumerate(candidates)
        ]
        pick = rules.choose(
            game, "Move which Monster here?", options, kind="move_monster", inv=inv, auto_single=True
        )
        source, monster = candidates[pick]
        game.locations[source].monsters.remove(monster)
        game.locations[inv.location].monsters.append(monster)
        rules.emit(
            game,
            "monster",
            f"The {game.content.monsters[monster.def_id].name} moves to {rules.loc_name(game, inv.location)}.",
            monster=monster.def_id,
            location=inv.location,
        )
        combat.combat(game, inv, monster)


@register("damage_monsters")
@dataclass(frozen=True)
class DamageMonsters(Effect):
    amount: int
    where: str
    one: bool = False

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(
            _positive(r, "amount"), r.get_enum("where", ("here", "choose_space"), "here"), r.get_bool("one", False)
        )

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        if self.where == "here":
            loc_id = ctx.need_inv(self.kind).location
        else:
            with_monsters = [loc for loc, st in game.locations.items() if st.monsters]
            if not with_monsters:
                return
            options = [Option(rules.loc_name(game, loc), loc) for loc in with_monsters]
            pick = rules.choose(
                game, "Choose a space to damage Monsters:", options, kind="choose_space", inv=ctx.inv, auto_single=True
            )
            loc_id = with_monsters[pick]
        targets = list(game.locations[loc_id].monsters)
        if self.one and targets:
            options = [Option(game.monster_def(m.def_id).name, m.uid) for m in targets]
            pick = rules.choose(game, "Choose a Monster.", options, kind="pick_monster", inv=ctx.inv, auto_single=True)
            targets = [targets[pick]]
        for monster in targets:
            mdef = game.monster_def(monster.def_id)
            if not rules.wound_monster(game, ctx.inv, monster, self.amount):
                rules.emit(game, "combat", f"The {mdef.name} loses {self.amount} Health.")

    def needs_investigator(self) -> bool:
        return self.where == "here"


@register("spawn_clue")
@dataclass(frozen=True)
class SpawnClue(Effect):
    count: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_positive(r, "count"))

    def apply(self, ctx: Ctx) -> None:
        for _ in range(self.count):
            rules.spawn_clue(ctx.game)

    def needs_investigator(self) -> bool:
        return False


@register("discard_all_clues")
@dataclass(frozen=True)
class DiscardAllClues(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        for state in game.locations.values():
            state.clue = False
        for inv in game.active_investigators():
            inv.clues = 0
        rules.emit(game, "loss", "All Clues on the board and held by investigators are discarded!")

    def needs_investigator(self) -> bool:
        return False


@register("monsters_move")
@dataclass(frozen=True)
class MonstersMove(Effect):
    monster: str | None
    toward: str

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_str("id", None), r.get_str("toward", "investigator"))

    def apply(self, ctx: Ctx) -> None:
        rules.move_monsters(ctx.game, self.monster, self.toward)

    def refs(self) -> Iterable[tuple[str, str]]:
        out = []
        if self.monster:
            out.append(("monster", self.monster))
        if self.toward != "investigator":
            out.append(("monster", self.toward))
        return out

    def needs_investigator(self) -> bool:
        return False


@register("monsters_heal")
@dataclass(frozen=True)
class MonstersHeal(Effect):
    amount: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_int("amount", 99))

    def apply(self, ctx: Ctx) -> None:
        rules.heal_monsters(ctx.game, self.amount)

    def needs_investigator(self) -> bool:
        return False


@register("clear_reserve")
@dataclass(frozen=True)
class ClearReserve(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        for card in game.reserve:
            game.asset_deck.discard(card)
        game.reserve = []
        rules.emit(game, "info", "All cards in the reserve are discarded.")

    def needs_investigator(self) -> bool:
        return False


@register("refill_reserve")
@dataclass(frozen=True)
class RefillReserve(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        rules.refill_reserve(ctx.game)

    def needs_investigator(self) -> bool:
        return False


@register("mystery_progress")
@dataclass(frozen=True)
class MysteryProgress(Effect):
    amount: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_positive(r, "amount"))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        open_mys = [m for m in game.active_mysteries() if not m.done]
        if not open_mys:
            return
        rules.add_mystery_progress(game, open_mys[0], self.amount)

    def needs_investigator(self) -> bool:
        return False



# --- this Monster: effects on `ctx.monster` -------------------------------------------


@register("defeat_this")
@dataclass(frozen=True)
class DefeatThis(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        monster = ctx.need_monster(self.kind)
        loc_id = rules.monster_location(ctx.game, monster)
        if loc_id is not None:
            rules.defeat_monster(ctx.game, ctx.inv, loc_id, monster)

    def needs_investigator(self) -> bool:
        return False


@register("sanity_per_spell")
@dataclass(frozen=True)
class SanityPerSpell(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        spells = sum(ctx.game.asset_def(c).kind == "spell" for c in inv.assets)
        rules.change_sanity(ctx.game, inv, -spells)


@register("heal_this")
@dataclass(frozen=True)
class HealThis(Effect):
    amount: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_int("amount", 99))

    def apply(self, ctx: Ctx) -> None:
        monster = ctx.need_monster(self.kind)
        monster.wounds = max(0, monster.wounds - self.amount)

    def needs_investigator(self) -> bool:
        return False


@register("wound_this_by_test")
@dataclass(frozen=True)
class WoundThisByTest(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        rules.wound_monster(ctx.game, ctx.inv, ctx.need_monster(self.kind), ctx.test_successes or 0)

    def needs_investigator(self) -> bool:
        return False


@register("move_this")
@dataclass(frozen=True)
class MoveThis(Effect):
    to: str

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_str("to"))

    def apply(self, ctx: Ctx) -> None:
        rules.move_monster(ctx.game, ctx.need_monster(self.kind), self.to)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("location", self.to)]

    def needs_investigator(self) -> bool:
        return False


@register("move_this_toward")
@dataclass(frozen=True)
class MoveThisToward(Effect):
    monster: str

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_str("id"))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        monster = ctx.need_monster(self.kind)
        src = rules.monster_location(game, monster)
        goal = next((loc for loc, m in game.all_monsters() if m.def_id == self.monster), None)
        if src is not None and goal is not None:
            rules.move_monster(game, monster, rules.step_toward(game, src, goal))

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("monster", self.monster)]

    def needs_investigator(self) -> bool:
        return False


@register("replace_this")
@dataclass(frozen=True)
class ReplaceThis(Effect):
    """Spawn one of `ids` on this Monster's space. If that works, discard this Monster."""

    ids: tuple[str, ...]

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_str_tuple("ids"))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        monster = ctx.need_monster(self.kind)
        loc_id = rules.monster_location(game, monster)
        choices = [i for i in self.ids if rules.monster_available(game, i)]
        if loc_id is None or not choices:
            return
        options = [Option(game.content.monsters[i].name, i) for i in choices]
        pick = rules.choose(game, "Spawn which Monster?", options, kind="spawn_choice", auto_single=True)
        rules.spawn_monster(game, loc_id, choices[pick])
        rules.discard_monster(game, loc_id, monster)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("monster", i) for i in self.ids]

    def needs_investigator(self) -> bool:
        return False


@register("hunt_nearest")
@dataclass(frozen=True)
class HuntNearest(Effect):
    """Move this Monster to the nearest investigator, who then encounters it."""

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        monster = ctx.need_monster(self.kind)
        loc_id = rules.monster_location(game, monster)
        target = rules.nearest_investigator(game, loc_id) if loc_id else None
        if target is not None:
            rules.move_monster(game, monster, target.location)
            combat.combat(game, target, monster)

    def needs_investigator(self) -> bool:
        return False


@register("take_nearest_clue")
@dataclass(frozen=True)
class TakeNearestClue(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        monster = ctx.need_monster(self.kind)
        loc_id = rules.monster_location(game, monster)
        if loc_id is None:
            return
        dist = rules.distances(game, loc_id)
        clues = [loc for loc, st in game.locations.items() if st.clue and loc in dist]
        if clues:
            dest = min(clues, key=lambda loc: (dist[loc], loc))
            game.locations[dest].clue = False
            rules.emit(game, "clue", f"The Clue at {rules.loc_name(game, dest)} is discarded.", location=dest)
            rules.move_monster(game, monster, dest)

    def needs_investigator(self) -> bool:
        return False


@register("carry_or_chase")
@dataclass(frozen=True)
class CarryOrChase(Effect):
    """Nightgaunt: carry an investigator 1 space, or else fly 2 spaces toward the nearest one."""

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        monster = ctx.need_monster(self.kind)
        loc_id = rules.monster_location(game, monster)
        if loc_id is None:
            return
        here = game.investigators_at(loc_id)
        if here:
            victim = here[0]
            near = rules.neighbors(game, loc_id)
            options = [Option(rules.loc_name(game, loc), loc, k) for loc, k in near]
            dest = near[rules.choose(game, "Move where?", options, kind="move", inv=victim, auto_single=True)][0]
            rules.move_investigator(game, victim, dest)
            rules.move_monster(game, monster, dest)
            rules.delay(game, victim)
            return
        target = rules.nearest_investigator(game, loc_id)
        if target is not None:
            rules.move_monster(game, monster, rules.step_toward(game, loc_id, target.location, 2))

    def needs_investigator(self) -> bool:
        return False


@register("pull_nearest")
@dataclass(frozen=True)
class PullNearest(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        loc_id = rules.monster_location(game, ctx.need_monster(self.kind))
        target = rules.nearest_investigator(game, loc_id) if loc_id else None
        if target is not None and loc_id is not None:
            rules.move_investigator(game, target, rules.step_toward(game, target.location, loc_id))

    def needs_investigator(self) -> bool:
        return False


@register("nearest_investigator")
@dataclass(frozen=True)
class NearestInvestigator(Effect):
    provides_investigator: ClassVar[bool] = True
    effects: tuple[Effect, ...]

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(read_effects(r, "effects"))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        loc_id = rules.monster_location(game, ctx.need_monster(self.kind))
        target = rules.nearest_investigator(game, loc_id) if loc_id else None
        if target is not None:
            run_effects(self.effects, ctx.for_inv(target))

    def children(self) -> Iterable[Sequence[Effect]]:
        return (self.effects,)

    def needs_investigator(self) -> bool:
        return False


@register("roll_under_investigators")
@dataclass(frozen=True)
class RollUnderInvestigators(Effect):
    effects: tuple[Effect, ...]

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(read_effects(r, "effects"))

    def apply(self, ctx: Ctx) -> None:
        if ctx.game.roll_die() <= len(ctx.game.investigators):
            run_effects(self.effects, ctx)

    def children(self) -> Iterable[Sequence[Effect]]:
        return (self.effects,)

    def needs_investigator(self) -> bool:
        return False


# --- board Eldritch tokens, sheet tokens, and Ancient One sheets ----------------------


PLACE_AT = ("here", "random", "nearest_free_sea")


@register("place_eldritch")
@dataclass(frozen=True)
class PlaceEldritch(Effect):
    at: str | None
    ids: tuple[str, ...]
    half_investigators: bool

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_enum("at", PLACE_AT, None), r.get_str_tuple("ids"), r.get_bool("half_investigators", False))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        count = (len(game.investigators) + 1) // 2 if self.half_investigators else 1
        places: list[str] = list(self.ids)
        for _ in range(count if self.at else 0):
            if self.at == "random":
                places.append(rules.random_space(game))
            elif self.at == "here":
                places.append(ctx.need_inv(self.kind).location)
            else:
                dist = rules.distances(game, ctx.need_inv(self.kind).location)
                seas = [
                    loc.id
                    for loc in game.content.locations.values()
                    if loc.terrain == "sea" and not game.locations[loc.id].eldritch
                ]
                if seas:
                    places.append(min(seas, key=lambda loc: (dist.get(loc, 999), loc)))
        for loc_id in places:
            game.locations[loc_id].eldritch += 1
            rules.emit(game, "info", f"An Eldritch token is placed on {rules.loc_name(game, loc_id)}.")

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("location", i) for i in self.ids]

    def needs_investigator(self) -> bool:
        return self.at in ("here", "nearest_free_sea")


@register("clear_eldritch")
@dataclass(frozen=True)
class ClearEldritch(Effect):
    ids: tuple[str, ...]

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_str_tuple("ids"))

    def apply(self, ctx: Ctx) -> None:
        for loc_id in self.ids:
            ctx.game.locations[loc_id].eldritch = 0

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("location", i) for i in self.ids]

    def needs_investigator(self) -> bool:
        return False


@register("move_clues")
@dataclass(frozen=True)
class MoveClues(Effect):
    """Move each Clue to the nearest `terrain` space. A space holds 1 Clue token here, so
    each Clue goes to the nearest such space that has no Clue yet."""

    terrain: str

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_enum("terrain", TERRAINS))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        terrain_ids = [loc.id for loc in game.content.locations.values() if loc.terrain == self.terrain]
        clues = [loc for loc in sorted(game.locations) if game.locations[loc].clue and loc not in terrain_ids]
        for loc_id in clues:
            dist = rules.distances(game, loc_id)
            free = [t for t in terrain_ids if not game.locations[t].clue]
            if free:
                game.locations[loc_id].clue = False
                game.locations[min(free, key=lambda t: (dist.get(t, 999), t))].clue = True

    def needs_investigator(self) -> bool:
        return False


@register("sheet_gate")
@dataclass(frozen=True)
class SheetGate(Effect):
    """Yog-Sothoth: put a Gate on the sheet, from the space of `ctx.gate`, the investigator's
    space with `here`, or else the Gate stack."""

    here: bool
    lose_at: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_bool("here", False), r.get_int("lose_at", 3))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        loc_id = ctx.need_inv(self.kind).location if self.here else ctx.gate
        if loc_id is not None:
            rules.discard_gate(game, loc_id, to_stack=False)
        elif game.gate_deck.draw(game.rng) is None:
            return
        game.sheet_tokens += 1
        rules.emit(game, "info", f"Gates on {game.old_one.name}: {game.sheet_tokens}.")
        if game.sheet_tokens >= self.lose_at:
            rules.lose(game, f"There are {game.sheet_tokens} Gates on {game.old_one.name}! The world is lost.")

    def needs_investigator(self) -> bool:
        return self.here


@register("monsters_on_board_at_least")
@dataclass(frozen=True)
class MonstersOnBoardAtLeast(Effect):
    count: int
    then: tuple[Effect, ...]

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_positive(r, "count"), read_effects(r, "then"))

    def apply(self, ctx: Ctx) -> None:
        if sum(1 for _ in ctx.game.all_monsters()) >= self.count:
            run_effects(self.then, ctx)

    def children(self) -> Iterable[Sequence[Effect]]:
        return (self.then,)

    def needs_investigator(self) -> bool:
        return False


def _monster_space(ctx: Ctx, monster_id: str) -> str | None:
    return next((loc for loc, m in ctx.game.all_monsters() if m.def_id == monster_id), None)


@register("spawn_at_monster")
@dataclass(frozen=True)
class SpawnAtMonster(Effect):
    monster: str

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_str("id"))

    def apply(self, ctx: Ctx) -> None:
        loc_id = _monster_space(ctx, self.monster)
        if loc_id is not None:
            rules.spawn_monster(ctx.game, loc_id)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("monster", self.monster)]

    def needs_investigator(self) -> bool:
        return False


@register("lose_if_crowded")
@dataclass(frozen=True)
class LoseIfCrowded(Effect):
    monster: str
    count: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_str("id"), _positive(r, "count"))

    def apply(self, ctx: Ctx) -> None:
        loc_id = _monster_space(ctx, self.monster)
        if loc_id is not None and len(ctx.game.locations[loc_id].monsters) >= self.count:
            name = rules.loc_name(ctx.game, loc_id)
            rules.lose(ctx.game, f"{self.count} Monsters gather at {name}. The world is lost.")

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("monster", self.monster)]

    def needs_investigator(self) -> bool:
        return False


@register("gather_monsters")
@dataclass(frozen=True)
class GatherMonsters(Effect):
    ids: tuple[str, ...]
    monster: str

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_str_tuple("ids"), r.get_str("to_monster"))

    def apply(self, ctx: Ctx) -> None:
        dest = _monster_space(ctx, self.monster)
        if dest is None:
            return
        for _loc, monster in list(ctx.game.all_monsters()):
            if monster.def_id in self.ids:
                rules.move_monster(ctx.game, monster, dest)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("monster", i) for i in (*self.ids, self.monster)]

    def needs_investigator(self) -> bool:
        return False


@register("encounter_monster")
@dataclass(frozen=True)
class EncounterMonster(Effect):
    monster: str

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_str("id"))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        loc_id = _monster_space(ctx, self.monster)
        if loc_id is None:
            return
        for inv in game.investigators_at(loc_id):
            target = next((m for m in game.locations[loc_id].monsters if m.def_id == self.monster), None)
            if target is None or game.outcome:
                return
            combat.combat(game, inv, target)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("monster", self.monster)]

    def needs_investigator(self) -> bool:
        return False


@register("sanity_per_sheet_token")
@dataclass(frozen=True)
class SanityPerSheetToken(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        rules.change_sanity(ctx.game, ctx.need_inv(self.kind), -ctx.game.sheet_tokens)


@dataclass(frozen=True)
class RollOutcome:
    low: int
    high: int
    text: str
    effects: tuple[Effect, ...]


@register("roll")
@dataclass(frozen=True)
class Roll(Effect):
    """Roll 1 die that is not a test, so Clues and card rerolls cannot change it."""

    outcomes: tuple[RollOutcome, ...]

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        outcomes = []
        for o in r.objects("outcomes"):
            outcomes.append(
                RollOutcome(o.get_int("low"), o.get_int("high"), o.get_str("text", ""), read_effects(o, "effects"))
            )
            o.done()
        return cls(tuple(outcomes))

    def apply(self, ctx: Ctx) -> None:
        die = ctx.game.roll_die()
        rules.emit(ctx.game, "info", f"The die shows {die}.")
        for outcome in self.outcomes:
            if outcome.low <= die <= outcome.high:
                if outcome.text:
                    rules.emit(ctx.game, "info", outcome.text)
                run_effects(outcome.effects, ctx)
                return

    def children(self) -> Iterable[Sequence[Effect]]:
        return [o.effects for o in self.outcomes]

    def needs_investigator(self) -> bool:
        return False


@register("group_spend")
@dataclass(frozen=True)
class GroupSpend(Effect):
    """Investigators, as a group, spend Clues equal to half the investigators, or take `else`."""

    then: tuple[Effect, ...]
    otherwise: tuple[Effect, ...]

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(read_effects(r, "then"), read_effects(r, "else"))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        need = (len(game.investigators) + 1) // 2
        people = [i for i in game.turn_order() if not i.eliminated and not i.defeated]
        lead = game.lead_investigator()
        prompt = f"Spend {need} Clue(s) as a group?"
        if sum(i.clues for i in people) < need or not rules.confirm(game, prompt, kind="group_spend", inv=lead):
            run_effects(self.otherwise, ctx)
            return
        for _ in range(need):
            payers = [i for i in people if i.clues > 0]
            options = [Option(i.name, i.seat, f"{i.clues} Clue(s)") for i in payers]
            pick = rules.choose(
                game, "Who spends the next Clue?", options, kind="group_payer", inv=lead, auto_single=True
            )
            rules.change_clues(game, payers[pick], -1)
        run_effects(self.then, ctx)

    def children(self) -> Iterable[Sequence[Effect]]:
        return (self.then, self.otherwise)

    def needs_investigator(self) -> bool:
        return False


@register("reckon_twice")
@dataclass(frozen=True)
class ReckonTwice(Effect):
    """Resolve the Reckoning of each Monster or Mythos card twice, or else advance Doom by 1."""

    what: str

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_enum("what", ("monsters", "mythos")))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        if self.what == "monsters":
            found = any(game.monster_def(m.def_id).reckoning for _loc, m in game.all_monsters())
            reckon = rules.reckon_monsters
        else:
            found = any(game.content.mythos[a.def_id].reckoning for a in game.active_mythos)
            reckon = rules.reckon_mythos
        if not found:
            rules.advance_doom(game, 1, f"no {self.what} have a Reckoning effect")
            return
        reckon(game)
        reckon(game)

    def needs_investigator(self) -> bool:
        return False


@register("reckon_conditions")
@dataclass(frozen=True)
class ReckonConditions(Effect):
    """Resolve the Reckoning on this investigator's Conditions, treating all die rolls as 1's."""

    condition: str | None

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_str("id", None))

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        for inst in list(inv.conditions):
            if self.condition is None or inst.def_id == self.condition:
                rules.reckon_condition(ctx.game, inv, inst, ones=True)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("condition", self.condition)] if self.condition else []


@register("clear_fallen")
@dataclass(frozen=True)
class ClearFallen(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        for state in game.locations.values():
            for fallen in state.fallen:
                for card in fallen.assets:
                    rules.deck_for(game, game.asset_def(card).kind).discard(card)
            state.fallen = []
        rules.emit(game, "loss", "The defeated investigators and their possessions are lost.")

    def needs_investigator(self) -> bool:
        return False


@register("sacrifice_monster")
@dataclass(frozen=True)
class SacrificeMonster(Effect):
    """Discard 1 non-Epic Monster of the investigator's choice and lose Health equal to its toughness."""

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        found = [(loc, m) for loc, m in game.all_monsters() if not game.monster_def(m.def_id).epic]
        if not found:
            return
        options = [
            Option(f"{game.monster_def(m.def_id).name} at {rules.loc_name(game, loc)}", m.uid) for loc, m in found
        ]
        loc_id, monster = found[rules.choose(game, "Discard which Monster?", options, kind="discard_monster", inv=inv)]
        health = rules.toughness(game, monster.def_id)
        rules.discard_monster(game, loc_id, monster)
        rules.change_health(game, inv, -health)


@register("discard_chosen_gate")
@dataclass(frozen=True)
class DiscardChosenGate(Effect):
    """Discard 1 Gate. Advance Doom by 1 if that Gate does not match the current Omen."""

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        gates = game.open_gates()
        if not gates:
            return
        options = [Option(rules.loc_name(game, g), g, game.content.locations[g].gate_color or "") for g in gates]
        pick = rules.choose(game, "Discard which Gate?", options, kind="pick_gate", auto_single=True)
        matched = gates[pick] in game.matching_gates()
        rules.discard_gate(game, gates[pick])
        if not matched:
            rules.advance_doom(game, 1, "the discarded Gate did not match the Omen")

    def needs_investigator(self) -> bool:
        return False


@register("torn_asunder")
@dataclass(frozen=True)
class TornAsunder(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        count = len(game.matching_gates())
        if count == 0:
            rules.advance_omen(game, 1)
            return
        for inv in game.turn_order():
            if not inv.eliminated and not inv.defeated:
                rules.change_health(game, inv, -count)

    def needs_investigator(self) -> bool:
        return False


@register("choose_omen")
@dataclass(frozen=True)
class ChooseOmen(Effect):
    """Move the Omen to any space without advancing Doom."""

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        options = [Option(space.replace("_", " ").title(), i) for i, space in enumerate(OMEN_TRACK)]
        game.omen_index = rules.choose(game, "Move the Omen to which space?", options, kind="pick_omen", inv=ctx.inv)
        rules.emit(game, "omen", f"The Omen moves to {game.omen_color}.", omen=game.omen_space, color=game.omen_color)


@register("rewind_omen")
@dataclass(frozen=True)
class RewindOmen(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        rules.rewind_omen(ctx.game)

    def needs_investigator(self) -> bool:
        return False


@register("shuffle_back_mystery")
@dataclass(frozen=True)
class ShuffleBackMystery(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        solved = list(game.solved_mysteries)
        options = [Option(next(m.name for m in game.old_one.mysteries if m.id == s), s) for s in solved]
        pick = rules.choose(game, "Shuffle back which Mystery?", options, kind="pick_mystery", auto_single=True)
        rules.unsolve_mystery(game, solved[pick])

    def needs_investigator(self) -> bool:
        return False


@register("if_solved_mystery")
@dataclass(frozen=True)
class IfSolvedMystery(Effect):
    then: tuple[Effect, ...]
    otherwise: tuple[Effect, ...]

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(read_effects(r, "then"), read_effects(r, "else"))

    def apply(self, ctx: Ctx) -> None:
        run_effects(self.then if ctx.game.solved_mysteries else self.otherwise, ctx)

    def children(self) -> Iterable[Sequence[Effect]]:
        return (self.then, self.otherwise)

    def needs_investigator(self) -> bool:
        return False


@register("shed_possessions")
@dataclass(frozen=True)
class ShedPossessions(Effect):
    """Discard any number of matching possessions, then pay `each` for every one still held."""

    trait: str | None
    asset_kind: str | None
    each: tuple[Effect, ...]
    if_any: tuple[Effect, ...]

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(
            r.get_str("trait", None),
            r.get_enum("kind", ASSET_KINDS, None),
            read_effects(r, "each"),
            read_effects(r, "if_any"),
        )

    def _held(self, ctx: Ctx, inv: Investigator) -> list:
        defs = ctx.game.asset_def
        return [
            c
            for c in inv.assets
            if (self.trait is None or self.trait in defs(c).traits)
            and (self.asset_kind is None or defs(c).kind == self.asset_kind)
        ]

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        while held := self._held(ctx, inv):
            options = [Option(f"Discard {game.asset_def(c).name}", c.uid) for c in held]
            options.append(Option("Keep the rest", None))
            uid = options[rules.choose(game, "Discard a possession?", options, kind="shed", inv=inv)].value
            if uid is None:
                break
            rules.discard_asset(game, inv, next(c for c in held if c.uid == uid))
        kept = len(self._held(ctx, inv))
        for _ in range(kept):
            run_effects(self.each, ctx)
        if kept:
            run_effects(self.if_any, ctx)

    def children(self) -> Iterable[Sequence[Effect]]:
        return (self.each, self.if_any)


@register("keep_one_item")
@dataclass(frozen=True)
class KeepOneItem(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        items = [c for c in inv.assets if "item" in game.asset_def(c).traits]
        if len(items) < 2:
            return
        options = [Option(game.asset_def(c).name, c.uid) for c in items]
        keep = items[rules.choose(game, "Keep which Item?", options, kind="keep_item", inv=inv)]
        for card in items:
            if card is not keep:
                rules.discard_asset(game, inv, card)


@register("the_storm")
@dataclass(frozen=True)
class TheStorm(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        rumors = sum("rumor" in game.content.mythos[a.def_id].traits for a in game.active_mythos)
        if rumors:
            for inv in game.turn_order():
                if not inv.eliminated and not inv.defeated:
                    rules.change_clues(game, inv, -rumors)
            return
        boxed = [m for m in game.mythos_box if "rumor" in game.content.mythos[m].traits]
        if boxed:
            pick = game.rng.choice(boxed)
            game.mythos_box.remove(pick)
            phases.resolve_mythos(game, game.content.mythos[pick])

    def needs_investigator(self) -> bool:
        return False


@register("remove_expedition_cards")
@dataclass(frozen=True)
class RemoveExpeditionCards(Effect):
    """Return each card of the Active Expedition to the game box."""

    lose_if_empty: bool

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_bool("lose_if_empty", False))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        deck = game.encounter_decks["expedition"]
        target = game.active_expedition

        def other(card: str) -> bool:
            return game.content.encounters[card].location != target

        deck.cards = [c for c in deck.cards if other(c)]
        deck.discards = [c for c in deck.discards if other(c)]
        game.rng.shuffle(deck.cards)
        rules.update_expedition(game)
        if self.lose_if_empty and not len(deck):
            rules.lose(game, "The Expedition Encounter deck is empty. The secrets of the past are lost.")

    def needs_investigator(self) -> bool:
        return False


@register("lose_game")
@dataclass(frozen=True)
class LoseGame(Effect):
    text: str

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_str("text"))

    def apply(self, ctx: Ctx) -> None:
        rules.lose(ctx.game, self.text)

    def needs_investigator(self) -> bool:
        return False


@register("doom_per_gate")
@dataclass(frozen=True)
class DoomPerGate(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        rules.advance_doom(ctx.game, len(ctx.game.open_gates()), "each Gate on the game board")

    def needs_investigator(self) -> bool:
        return False


@register("purge_assets")
@dataclass(frozen=True)
class PurgeAssets(Effect):
    """Return Assets with value of at least the Eldritch tokens on this card to the game box."""

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        if ctx.mythos is None:
            return
        value = ctx.mythos.eldritch

        def stays(card: AssetCard) -> bool:
            return game.asset_def(card).cost < value

        game.asset_deck.cards = [c for c in game.asset_deck.cards if stays(c)]
        game.asset_deck.discards = [c for c in game.asset_deck.discards if stays(c)]
        game.reserve = [c for c in game.reserve if stays(c)]
        rules.refill_reserve(game)
        rules.emit(game, "loss", f"Assets of value {value} or more are returned to the game box.")

    def needs_investigator(self) -> bool:
        return False


@register("other_world_encounter")
@dataclass(frozen=True)
class OtherWorldEncounter(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        phases.other_world_encounter(ctx.game, ctx.need_inv(self.kind), ctx.mythos)


@register("sickness")
@dataclass(frozen=True)
class Sickness(Effect):
    """Place a Health token on this card. Each investigator loses 1 Health per token."""

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        if ctx.mythos is None:
            return
        ctx.mythos.health_tokens += 1
        for inv in game.turn_order():
            if not inv.eliminated and not inv.defeated:
                rules.change_health(game, inv, -ctx.mythos.health_tokens)

    def needs_investigator(self) -> bool:
        return False


@register("cure_sickness")
@dataclass(frozen=True)
class CureSickness(Effect):
    """Spend Clues equal to the investigators, less 1 per Health token, to solve this Rumor."""

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        if ctx.mythos is None:
            return
        cost = Cost(clues=max(0, len(game.investigators) - ctx.mythos.health_tokens))
        prompt = f"Spend {cost.clues} Clue(s) to solve this Rumor?"
        if rules.can_pay(game, inv, cost) and rules.confirm(game, prompt, kind="pay", inv=inv):
            rules.pay_cost(game, inv, cost)
            rules.solve_rumor(game, ctx.mythos)


@register("crowded_space")
@dataclass(frozen=True)
class CrowdedSpace(Effect):
    """With `count` or more Monsters on `at`, advance Doom to 0 and solve this Rumor."""

    at: str
    count: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_str("at"), _positive(r, "count"))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        if len(game.locations[self.at].monsters) >= self.count:
            rules.advance_doom(game, game.doom, f"{self.count} Monsters gather at {rules.loc_name(game, self.at)}")
            if ctx.mythos is not None:
                rules.solve_rumor(game, ctx.mythos)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("location", self.at)]

    def needs_investigator(self) -> bool:
        return False


@register("defeat_monsters_here")
@dataclass(frozen=True)
class DefeatMonstersHere(Effect):
    """Defeat each non-Epic Monster here. Only lost Health can defeat an Epic Monster."""

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        for monster in list(game.locations[inv.location].monsters):
            if not game.monster_def(monster.def_id).epic:
                rules.defeat_monster(game, inv, inv.location, monster)


@register("give_items")
@dataclass(frozen=True)
class GiveItems(Effect):
    """Give any number of Item possessions to another investigator on any space."""

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        others = [i for i in game.turn_order() if i is not inv and not i.eliminated and not i.defeated]
        if not others:
            return
        options = [Option(i.name, i.seat, rules.loc_name(game, i.location)) for i in others]
        target = others[rules.choose(game, "Give Items to whom?", options, kind="ability_target", inv=inv)]
        while items := [c for c in inv.assets if "item" in game.asset_def(c).traits]:
            options = [Option(game.asset_def(c).name, c.uid) for c in items]
            options.append(Option("Done giving", None))
            uid = options[rules.choose(game, "Give which Item?", options, kind="give_item", inv=inv)].value
            if uid is None:
                return
            card = next(c for c in items if c.uid == uid)
            inv.assets.remove(card)
            target.assets.append(card)
            rules.emit(game, "info", f"{inv.name} gives {game.asset_def(card).name} to {target.name}.")


@register("give_clues")
@dataclass(frozen=True)
class GiveClues(Effect):
    """Give any number of Clues to another investigator on any space."""

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        others = [i for i in game.turn_order() if i is not inv and not i.eliminated and not i.defeated]
        if not others or inv.clues == 0:
            return
        options = [Option(i.name, i.seat, rules.loc_name(game, i.location)) for i in others]
        target = others[rules.choose(game, "Give Clues to whom?", options, kind="ability_target", inv=inv)]
        amounts = [Option(str(n), n) for n in range(inv.clues + 1)]
        amount = amounts[rules.choose(game, "Give how many Clues?", amounts, kind="amount", inv=inv)].value
        inv.clues -= amount
        target.clues += amount
        if amount:
            rules.emit(game, "info", f"{inv.name} gives {amount} Clue(s) to {target.name}.")


@register("brain_case")
@dataclass(frozen=True)
class BrainCase(Effect):
    """Mi-go Brain Case: trade with another investigator on any space, who may then swap spaces."""

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        others = [i for i in game.turn_order() if i is not inv and not i.eliminated and not i.defeated]
        if not others:
            return
        options = [Option(i.name, i.seat, rules.loc_name(game, i.location)) for i in others]
        other = others[rules.choose(game, "Trade with whom?", options, kind="trade_partner", inv=inv)]
        actions.trade_with(game, inv, other)
        if rules.confirm(game, f"Move {other.name} to your space and swap?", kind="swap_spaces", inv=other):
            mine, theirs = inv.location, other.location
            rules.move_investigator(game, other, mine)
            if other.location == mine:
                rules.move_investigator(game, inv, theirs)


@register("kleptomania")
@dataclass(frozen=True)
class Kleptomania(Effect):
    """Gain 1 random Item from the deck, then test Observation against the value of that Item."""

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        card = rules.draw_matching(game, kind="item")
        if card is None:
            return
        rules.gain_card(game, inv, card)
        result = run_test(game, inv, "observation", open_ended=True, label="Kleptomania")
        if result.successes < game.asset_def(card).cost and card in inv.assets:
            rules.discard_asset(game, inv, card)
            rules.gain_condition(game, inv, "detained")


@register("gate_per_spell")
@dataclass(frozen=True)
class GatePerSpell(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        for _ in range(sum(game.asset_def(c).kind == "spell" for c in inv.assets)):
            if not game.outcome:
                rules.spawn_gate(game)
