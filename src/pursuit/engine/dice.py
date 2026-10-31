"""Skill tests: build a dice pool, offer boosts, roll, and offer Clue rerolls."""

from __future__ import annotations

from dataclasses import dataclass

from pursuit.engine import rules
from pursuit.engine.state import Game, Investigator


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
    """Every passive modifier that applies to this test, as (source name, amount)."""
    content = game.content
    found: list[tuple[str, int]] = []

    def add(name: str, mods: tuple) -> None:
        for m in mods:
            if m.applies(skill, contexts) and (m.where is None or m.where.matches(game, inv.location)):
                found.append((name, m.amount))

    idef = content.investigators[inv.def_id]
    add(idef.name, idef.modifiers)
    for card in inv.assets:
        adef = content.assets[card.def_id]
        add(adef.name, adef.modifiers)
    for inst in inv.conditions:
        cdef = content.conditions[inst.def_id]
        add(cdef.name, cdef.modifiers)
    add(game.old_one.name, game.old_one.modifiers)
    return found


def dice_pool(game: Game, inv: Investigator, skill: str, mod: int, contexts: tuple[str, ...]) -> int:
    return inv.skill(skill) + mod + sum(a for _, a in modifier_sources(game, inv, skill, contexts))


def _offer_boosts(game: Game, inv: Investigator, skill: str, contexts: tuple[str, ...]) -> int:
    bonus = 0
    for card in list(inv.assets):
        adef = game.asset_def(card)
        for boost in adef.boosts:
            if card not in inv.assets or (boost.exhaust and card.exhausted):
                break
            if not boost.applies(skill, contexts) or not boost.cost.can_pay(inv):
                continue
            prompt = f"Use {adef.name}? {boost.text}"
            if not rules.confirm(game, prompt, kind="boost", inv=inv):
                continue
            rules.pay_cost(game, inv, boost.cost)
            bonus += boost.amount
            rules.emit(game, "info", f"{inv.name} uses {adef.name} (+{boost.amount} dice).")
            if boost.exhaust:
                card.exhausted = True
            if boost.discard:
                rules.discard_asset(game, inv, card)
    return bonus


def run_test(
    game: Game,
    inv: Investigator,
    skill: str,
    mod: int = 0,
    *,
    contexts: tuple[str, ...] = ("encounter",),
    needed: int = 1,
    label: str = "",
) -> TestResult:
    success_on = game.content.rules.success_on
    pool = dice_pool(game, inv, skill, mod, contexts) + _offer_boosts(game, inv, skill, contexts)
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
    while successes < needed and inv.clues > 0 and any(r < success_on for r in rolls):
        prompt = f"{successes}/{needed} successes. Spend 1 Clue to reroll every failed die?"
        if not rules.confirm(game, prompt, kind="reroll", inv=inv):
            break
        inv.clues -= 1
        game.bump("clues_spent_rerolls")
        rolls = [r if r >= success_on else game.roll_die() for r in rolls]
        successes = sum(r >= success_on for r in rolls)
        rules.emit(
            game,
            "dice",
            f"{inv.name} spends a Clue and rerolls: {successes} success(es).",
            rolls=list(rolls),
            successes=successes,
            needed=needed,
            skill=skill,
            success_on=success_on,
            reroll=True,
        )
    return TestResult(skill, count, tuple(rolls), successes, needed)
