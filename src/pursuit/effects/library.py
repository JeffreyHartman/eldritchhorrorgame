"""Every effect type that content JSON can use. Importing this module registers them."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import ClassVar

from pursuit.content.defs import (
    ASSET_KINDS,
    CONTEXTS,
    MARKET_KINDS,
    SKILLS,
    Cost,
    InvestigatorFilter,
    read_cost,
    read_investigator_filter,
)
from pursuit.content.reader import ContentError, Reader
from pursuit.controller import Option
from pursuit.effects.base import Ctx, Effect, read_effects, register, run_effects
from pursuit.engine import combat, rules
from pursuit.engine.dice import run_test


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

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(
            skill=r.get_enum("skill", SKILLS),
            mod=r.get_int("mod", 0),
            needed=_positive(r, "needed"),
            context=r.get_enum("context", CONTEXTS, "encounter"),
            passed=read_effects(r, "pass"),
            failed=read_effects(r, "fail"),
        )

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        result = run_test(ctx.game, inv, self.skill, self.mod, contexts=(self.context,), needed=self.needed)
        run_effects(self.passed if result.passed else self.failed, ctx)

    def children(self) -> Iterable[Sequence[Effect]]:
        return (self.passed, self.failed)


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


@register("funds")
@dataclass(frozen=True)
class Funds(Effect):
    amount: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_nonzero(r, "amount"))

    def apply(self, ctx: Ctx) -> None:
        rules.change_funds(ctx.game, ctx.need_inv(self.kind), self.amount)


@register("clues")
@dataclass(frozen=True)
class Clues(Effect):
    amount: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_nonzero(r, "amount"))

    def apply(self, ctx: Ctx) -> None:
        rules.change_clues(ctx.game, ctx.need_inv(self.kind), self.amount)


@register("trophies")
@dataclass(frozen=True)
class Trophies(Effect):
    amount: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_nonzero(r, "amount"))

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        inv.trophies = max(0, inv.trophies + self.amount)
        verb = "gains" if self.amount > 0 else "loses"
        rules.emit(ctx.game, "gain" if self.amount > 0 else "loss", f"{inv.name} {verb} {abs(self.amount)} Trophy.")


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
        new = max(-inv.skills[skill] + 1, min(cap, current + self.amount))
        if new == current:
            return
        inv.improvements[skill] = new
        word = "improves" if new > current else "weakens"
        rules.emit(
            game, "gain" if new > current else "loss", f"{inv.name}'s {skill.title()} {word} to {inv.skill(skill)}."
        )


# --- assets and conditions ------------------------------------------------------------


@register("gain_asset")
@dataclass(frozen=True)
class GainAsset(Effect):
    asset_id: str | None
    asset_kind: str | None
    trait: str | None
    source: str
    count: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        e = cls(
            asset_id=r.get_str("id", None),
            asset_kind=r.get_enum("kind", ASSET_KINDS, None),
            trait=r.get_str("trait", None),
            source=r.get_enum("source", ("deck", "market"), "deck"),
            count=_positive(r, "count"),
        )
        if e.source == "market" and (e.asset_id or (e.asset_kind and e.asset_kind not in MARKET_KINDS)):
            raise ContentError(f"{r.path}: a market gain can only filter by a market kind and a trait")
        return e

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        for _ in range(self.count):
            if self.source == "market":
                cards = [
                    c
                    for c in game.market
                    if (self.asset_kind is None or game.asset_def(c).kind == self.asset_kind)
                    and (self.trait is None or self.trait in game.asset_def(c).traits)
                ]
                if not cards:
                    rules.emit(game, "info", "Nothing suitable is on offer.")
                    return
                options = [Option(game.asset_def(c).name, c.uid, game.asset_def(c).text) for c in cards]
                card = cards[
                    rules.choose(game, "Take one asset from the market.", options, kind="gain_market", inv=inv)
                ]
                game.market.remove(card)
                rules.refill_market(game)
            else:
                found = rules.draw_matching(game, asset_id=self.asset_id, kind=self.asset_kind, trait=self.trait)
                if found is None:
                    rules.emit(game, "info", "There is nothing left to find.")
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
                and (self.asset_kind is None or game.asset_def(c).kind == self.asset_kind)
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
                        game, "Choose an asset to lose.", options, kind="lose_asset", inv=inv, auto_single=True
                    )
                ]
            rules.discard_asset(game, inv, card)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("asset", self.asset_id)] if self.asset_id else []


@register("gain_condition")
@dataclass(frozen=True)
class GainCondition(Effect):
    condition: str

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_str("id"))

    def apply(self, ctx: Ctx) -> None:
        rules.gain_condition(ctx.game, ctx.need_inv(self.kind), self.condition)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("condition", self.condition)]


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


@register("remove_self")
@dataclass(frozen=True)
class RemoveSelf(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        if ctx.condition is not None and ctx.inv is not None:
            rules.remove_condition(ctx.game, ctx.inv, ctx.condition)


@register("resolve_conditions")
@dataclass(frozen=True)
class ResolveConditions(Effect):
    trait: str | None

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_str("trait", None))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        for inst in list(inv.conditions):
            cdef = game.content.conditions[inst.def_id]
            if self.trait is None or self.trait in cdef.traits:
                rules.resolve_condition(game, inv, inst)
                if inv.defeated or game.outcome:
                    return


# --- movement -------------------------------------------------------------------------


MOVE_KEYWORDS = ("nearest_city", "random_city", "start", "choose_adjacent", "nearest_rift", "choose_within")


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
            dist = rules.distances(game, inv.location)
            cities = [loc for loc in dist if content.locations[loc].terrain == "city"]
            dest = min(cities, key=lambda loc: (dist[loc], loc)) if cities else None
        elif self.to == "nearest_rift":
            dist = rules.distances(game, inv.location)
            rifts = [loc for loc in game.open_rifts() if loc in dist]
            dest = min(rifts, key=lambda loc: (dist[loc], loc)) if rifts else None
        elif self.to == "choose_adjacent":
            near = rules.neighbors(game, inv.location)
            options = [Option(rules.loc_name(game, loc), loc, k) for loc, k in near]
            dest = near[rules.choose(game, "Where do you go?", options, kind="move", inv=inv)][0]
        elif self.to == "choose_within":
            dist = rules.distances(game, inv.location)
            places = sorted(
                (loc for loc, d in dist.items() if 0 < d <= self.range),
                key=lambda loc: (dist[loc], rules.loc_name(game, loc)),
            )
            options = [Option(rules.loc_name(game, loc), loc, f"{dist[loc]} step(s)") for loc in places]
            options.append(Option("Stay here", None))
            dest = options[rules.choose(game, "Where do you go?", options, kind="move", inv=inv)].value
        else:
            dest = self.to
        if dest:
            rules.move_investigator(game, inv, dest)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [] if self.to in MOVE_KEYWORDS else [("location", self.to)]


@register("delay")
@dataclass(frozen=True)
class Delay(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        inv.delayed = True
        rules.emit(ctx.game, "loss", f"{inv.name} is delayed and will lose their next Day turn.")


# --- doom -----------------------------------------------------------------------------


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
    prompt: str
    then: tuple[Effect, ...]
    otherwise: tuple[Effect, ...]

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        cost = read_cost(r, "cost")
        if cost.is_free():
            raise ContentError(f"{r.path}: a pay effect needs a cost")
        return cls(cost, r.get_str("prompt", ""), read_effects(r, "then"), read_effects(r, "else"))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        inv = ctx.need_inv(self.kind)
        prompt = self.prompt or f"Pay {self.cost.describe()}?"
        if self.cost.can_pay(inv) and rules.confirm(game, f"{prompt} ({self.cost.describe()})", kind="pay", inv=inv):
            rules.pay_cost(game, inv, self.cost)
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
    effects: tuple[Effect, ...]

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(read_investigator_filter(r, "where"), r.get_bool("here", False), read_effects(r, "effects"))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        if self.here and ctx.inv is None:
            raise RuntimeError(f"each_investigator with here=true from {ctx.source} needs an investigator")
        targets = [
            i
            for i in game.active_investigators()
            if not i.defeated
            and (not self.here or (ctx.inv is not None and i.location == ctx.inv.location))
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


PICKS = ("lowest_sanity", "lowest_health", "most_clues", "most_funds", "random", "choose")


@register("one_investigator")
@dataclass(frozen=True)
class OneInvestigator(Effect):
    provides_investigator: ClassVar[bool] = True
    pick: str
    where: InvestigatorFilter | None
    effects: tuple[Effect, ...]

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(r.get_enum("pick", PICKS), read_investigator_filter(r, "where"), read_effects(r, "effects"))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        pool = [
            i
            for i in game.active_investigators()
            if not i.defeated and (self.where is None or self.where.matches(game, i))
        ]
        if not pool:
            return
        if self.pick == "random":
            target = game.rng.choice(pool)
        elif self.pick == "choose":
            options = [Option(i.name, i.seat, rules.loc_name(game, i.location)) for i in pool]
            target = pool[rules.choose(game, "Choose an investigator.", options, kind="pick_investigator")]
        else:
            key = {
                "lowest_sanity": lambda i: (i.sanity, i.seat),
                "lowest_health": lambda i: (i.health, i.seat),
                "most_clues": lambda i: (-i.clues, i.seat),
                "most_funds": lambda i: (-i.funds, i.seat),
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


@register("open_rift")
@dataclass(frozen=True)
class OpenRift(Effect):
    count: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_positive(r, "count"))

    def apply(self, ctx: Ctx) -> None:
        for _ in range(self.count):
            if ctx.game.outcome:
                return
            rules.open_rift(ctx.game)

    def needs_investigator(self) -> bool:
        return False


SPAWN_AT = ("here", "rifts", "random_rift_site")


@register("spawn_monster")
@dataclass(frozen=True)
class SpawnMonster(Effect):
    count: int
    monster: str | None
    at: str

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_positive(r, "count"), r.get_str("id", None), r.get_str("at", "random_rift_site"))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        for _ in range(self.count):
            if self.at == "here":
                places = [ctx.need_inv(self.kind).location]
            elif self.at == "rifts":
                places = game.open_rifts()
            elif self.at == "random_rift_site":
                places = [game.rng.choice(sorted(loc.id for loc in game.content.locations.values() if loc.rift_site))]
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
        spawned = rules.spawn_monster(ctx.game, inv.location, self.monster)
        if spawned is not None:
            combat.combat(ctx.game, inv, spawned)

    def refs(self) -> Iterable[tuple[str, str]]:
        return [("monster", self.monster)] if self.monster else []


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


@register("close_rift")
@dataclass(frozen=True)
class CloseRift(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        rules.close_rift(ctx.game, inv, inv.location)


@register("monsters_move")
@dataclass(frozen=True)
class MonstersMove(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        rules.move_monsters(ctx.game)

    def needs_investigator(self) -> bool:
        return False


@register("monsters_heal")
@dataclass(frozen=True)
class MonstersHeal(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        rules.heal_monsters(ctx.game)

    def needs_investigator(self) -> bool:
        return False


@register("refresh_market")
@dataclass(frozen=True)
class RefreshMarket(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        for card in game.market:
            game.asset_deck.discard(card)
        game.market = []
        rules.refill_market(game)
        rules.emit(game, "info", "The market turns over. New goods are on offer.")

    def needs_investigator(self) -> bool:
        return False


@register("rite_progress")
@dataclass(frozen=True)
class RiteProgress(Effect):
    amount: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_positive(r, "amount"))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        open_rites = [r for r in game.active_rites() if not r.done and game.rite_def(r).kind in ("spend", "test")]
        if not open_rites:
            return
        options = [Option(game.rite_def(r).name, i, f"{r.progress}/{r.required}") for i, r in enumerate(open_rites)]
        pick = rules.choose(game, "Which rite does this insight advance?", options, kind="rite_pick", inv=ctx.inv)
        rules.add_rite_progress(game, open_rites[pick], self.amount)

    def needs_investigator(self) -> bool:
        return False
