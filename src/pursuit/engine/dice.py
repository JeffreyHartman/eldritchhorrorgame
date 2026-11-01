"""Skill tests: build a dice pool, roll, and offer card and Clue rerolls."""

from __future__ import annotations

from dataclasses import dataclass

from pursuit.engine import rules
from pursuit.engine.state import AssetCard, Game, Investigator


@dataclass(frozen=True)
class TestResult:
    skill: str
    pool: int
    rolls: tuple[int, ...]
    successes: int
    needed: int

    @property
    def passed(self) -> bool:
        return self.successes >= self.needed


def modifier_sources(game: Game, inv: Investigator, skill: str, contexts: tuple[str, ...]) -> list[tuple[str, int]]:
    """Every passive modifier that applies to this test, as (source name, amount).

    In Eldritch Horror, an investigator uses only their single highest positive skill
    bonus (`additional=False`), while penalties and "roll additional dice" effects
    (`additional=True`) stack with everything.
    """
    content = game.content
    bonuses: list[tuple[str, int]] = []
    other: list[tuple[str, int]] = []

    def add(name: str, mods: tuple, *, allow_where: bool = True) -> None:
        for m in mods:
            if not m.applies(skill, contexts):
                continue
            if allow_where and m.where is not None and not m.where.matches(game, inv.location):
                continue
            if m.amount > 0 and not m.additional:
                bonuses.append((name, m.amount))
            else:
                other.append((name, m.amount))

    for person in game.investigators_at(inv.location):
        idef = content.investigators[person.def_id]
        if person is inv:
            add(idef.name, idef.modifiers)
        else:
            # Local investigator auras (e.g. Jim Culver, Silas Marsh) use additional=True
            aura = tuple(m for m in idef.modifiers if m.additional)
            add(idef.name, aura)

    for card in inv.assets:
        adef = content.assets[card.def_id]
        add(adef.name, adef.modifiers)
    for inst in inv.conditions:
        cdef = content.conditions[inst.def_id]
        add(cdef.name, cdef.modifiers)
    add(game.old_one.name, game.old_one.modifiers)

    found: list[tuple[str, int]] = []
    if bonuses:
        best = max(bonuses, key=lambda item: item[1])
        found.append(best)
    found.extend(other)
    return found


def dice_pool(game: Game, inv: Investigator, skill: str, mod: int, contexts: tuple[str, ...]) -> int:
    return inv.skill(skill) + mod + sum(a for _, a in modifier_sources(game, inv, skill, contexts))


def _offer_card_rerolls(
    game: Game,
    inv: Investigator,
    skill: str,
    contexts: tuple[str, ...],
    rolls: list[int],
    success_on: int,
    needed: int,
) -> list[int]:
    from pursuit.content.defs import RerollAbility

    content = game.content
    idef = content.investigators[inv.def_id]
    sources: list[tuple[str, AssetCard | None, RerollAbility]] = []
    for rr in idef.rerolls:
        sources.append((idef.name, None, rr))
    for card in list(inv.assets):
        adef = content.assets[card.def_id]
        for rr in adef.rerolls:
            sources.append((adef.name, card, rr))

    for name, src_card, rr in sources:
        if src_card is not None and (src_card not in inv.assets or (rr.once_per_round and src_card.exhausted)):
            continue
        if not rr.applies(skill, contexts) or inv.sanity <= rr.sanity_cost:
            continue
        failed = [i for i, r in enumerate(rolls) if r < success_on]
        if not failed:
            break
        prompt = f"Use {name} to reroll ({rr.text})?"
        if not rules.confirm(game, prompt, kind="reroll_card", inv=inv):
            continue
        if rr.sanity_cost:
            rules.change_sanity(game, inv, -rr.sanity_cost)
        if rr.once_per_round and src_card is not None:
            src_card.exhausted = True
        if rr.discard and src_card is not None:
            rules.discard_asset(game, inv, src_card)
        if rr.all_dice:
            rolls = [r if r >= success_on else game.roll_die() for r in rolls]
        else:
            idx = min(failed, key=lambda i: rolls[i])
            rolls[idx] = game.roll_die()
        successes = sum(r >= success_on for r in rolls)
        rules.emit(
            game,
            "dice",
            f"{inv.name} uses {name} and rerolls: {successes} success(es).",
            rolls=list(rolls),
            successes=successes,
            needed=needed,
            skill=skill,
            success_on=success_on,
            reroll=True,
        )
    return rolls


def run_test(
    game: Game,
    inv: Investigator,
    skill: str,
    mod: int = 0,
    *,
    contexts: tuple[str, ...] = ("encounter",),
    needed: int = 1,
    label: str = "",
    open_ended: bool = False,
    allow_clues: bool = True,
) -> TestResult:
    """Roll a test. Set `open_ended` when successes past `needed` still count."""
    success_on = game.content.rules.success_on
    blessed = rules.has_condition(inv, "blessed")
    cursed = rules.has_condition(inv, "cursed")
    if blessed and not cursed:
        success_on = max(2, success_on - 1)
    elif cursed and not blessed:
        success_on = min(6, success_on + 1)

    pool = dice_pool(game, inv, skill, mod, contexts)
    count = max(1, pool)
    rolls = [game.roll_die() for _ in range(count)]
    successes = sum(r >= success_on for r in rolls)
    what = f"{skill.title()} ({label})" if label else skill.title()
    rules.emit(
        game,
        "dice",
        f"{inv.name} tests {what} with {count} dice: {successes} success(es), {needed} needed.",
        rolls=list(rolls),
        successes=successes,
        needed=needed,
        skill=skill,
        success_on=success_on,
    )

    if any(r < success_on for r in rolls):
        rolls = _offer_card_rerolls(game, inv, skill, contexts, rolls, success_on, needed)
        successes = sum(r >= success_on for r in rolls)

    while allow_clues and inv.clues > 0 and any(r < success_on for r in rolls):
        short = successes < needed
        if not short and not open_ended:
            break
        prompt = f"{successes}/{needed} successes. Spend 1 Clue to reroll 1 failed die?"
        if not rules.confirm(game, prompt, kind="reroll" if short else "reroll_extra", inv=inv):
            break
        inv.clues -= 1
        game.bump("clues_spent_rerolls")
        failed = [i for i, r in enumerate(rolls) if r < success_on]
        idx = min(failed, key=lambda i: rolls[i])
        rolls[idx] = game.roll_die()
        successes = sum(r >= success_on for r in rolls)
        rules.emit(
            game,
            "dice",
            f"{inv.name} spends a Clue and rerolls 1 die: {successes} success(es).",
            rolls=list(rolls),
            successes=successes,
            needed=needed,
            skill=skill,
            success_on=success_on,
            reroll=True,
        )

    if (
        contexts == ("acquire",)
        and inv.location in game.locations
        and not rules.has_condition(inv, "debt")
        and "bank_loan" in game.content.assets
    ):
        prompt = "Take a Bank Loan (gain Debt Condition to add 2 successes)?"
        if rules.confirm(game, prompt, kind="bank_loan", inv=inv):
            rules.gain_condition(game, inv, "debt")
            successes += 2
            rules.emit(game, "info", f"{inv.name} takes a Bank Loan (+2 successes).")

    return TestResult(skill, count, tuple(rolls), successes, needed)

