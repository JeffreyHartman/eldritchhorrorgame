"""Every effect type that content JSON can use. Importing this module registers them."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import ClassVar

from pursuit.content.defs import (
    ASSET_KINDS,
    CONTEXTS,
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
    after: tuple[Effect, ...]

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
        )

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        result = run_test(ctx.game, inv, self.skill, self.mod, contexts=(self.context,), needed=self.needed)
        sub_ctx = replace(ctx, test_successes=result.successes)
        run_effects(self.passed if result.passed else self.failed, sub_ctx)
        if self.after:
            run_effects(self.after, sub_ctx)

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
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        if inv.actions_taken:
            inv.actions_taken.pop(0)
        rules.emit(ctx.game, "gain", f"{inv.name} may perform 1 additional action.")


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
            source=r.get_enum("source", ("deck", "reserve", "choice"), "deck"),
            count=_positive(r, "count"),
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
                        game, "Choose a possession to discard.", options, kind="lose_asset", inv=inv, auto_single=True
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
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        inv.delayed = True
        rules.emit(ctx.game, "loss", f"{inv.name} becomes Delayed.")


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
        options: list[Option] = []
        if inv.health > 1 and inv.sanity < inv.max_sanity:
            options.append(Option("Spend 1 Health to recover 1 Sanity", "h_to_s"))
        if inv.sanity > 1 and inv.health < inv.max_health:
            options.append(Option("Spend 1 Sanity to recover 1 Health", "s_to_h"))
        options.append(Option("Done", None))
        pick = rules.choose(game, "Martial Arts focus:", options, kind="effect_choice", inv=inv)
        val = options[pick].value
        if val == "h_to_s":
            rules.change_health(game, inv, -1)
            rules.change_sanity(game, inv, 1)
        elif val == "s_to_h":
            rules.change_sanity(game, inv, -1)
            rules.change_health(game, inv, 1)


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
    amount: int

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_nonzero(r, "amount"))

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        active = ctx.mythos
        if active is None or active not in game.active_mythos:
            return
        active.eldritch = max(0, active.eldritch + self.amount)
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
        active = next((a for a in ctx.game.active_mythos if a.rumor_space), None)
        if active is not None:
            rules.solve_rumor(ctx.game, active)

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
        if actual.can_pay(inv) and rules.confirm(game, f"{prompt} ({actual.describe()})", kind="pay", inv=inv):
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
            for i in game.turn_order()
            if not i.eliminated
            and not i.defeated
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


PICKS = ("lead", "lowest_sanity", "lowest_health", "most_clues", "random", "choose")


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
            for i in game.turn_order()
            if not i.eliminated and not i.defeated and (self.where is None or self.where.matches(game, i))
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
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        inv = ctx.need_inv(self.kind)
        rules.close_gate(ctx.game, inv, inv.location)


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


SPAWN_AT = ("here", "gates", "random_space", "active_expedition", "cultist_spaces")


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
        spawned = rules.spawn_monster(ctx.game, inv.location, self.monster)
        if spawned is not None:
            combat.combat(ctx.game, inv, spawned, ambush=True)

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
            with_monsters = [loc for loc, st in game.locations.items() if st.monsters]
            if not with_monsters:
                return
            options = [Option(rules.loc_name(game, loc), loc) for loc in with_monsters]
            pick = rules.choose(
                game, "Choose a space with Monsters:", options, kind="choose_space", inv=ctx.inv, auto_single=True
            )
            loc_id = with_monsters[pick]
        monsters = list(game.locations[loc_id].monsters)
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

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls(_positive(r, "amount"), r.get_enum("where", ("here", "choose_space"), "here"))

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
        for monster in list(game.locations[loc_id].monsters):
            mdef = game.content.monsters[monster.def_id]
            monster.wounds += self.amount
            full = rules.toughness(game, monster.def_id)
            if monster.wounds >= full:
                rules.defeat_monster(game, ctx.inv, loc_id, monster)
            else:
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


@register("refresh_reserve")
@dataclass(frozen=True)
class RefreshReserve(Effect):
    @classmethod
    def parse(cls, r: Reader) -> Effect:
        return cls()

    def apply(self, ctx: Ctx) -> None:
        game = ctx.game
        for card in game.reserve:
            game.asset_deck.discard(card)
        game.reserve = []
        rules.refill_reserve(game)
        rules.emit(game, "info", "The reserve is refreshed.")

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

