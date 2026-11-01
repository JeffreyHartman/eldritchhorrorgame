"""Combat Encounters: a Will test against horror, then a Strength test to fight.

Card text on a Monster runs through the hook lists on `MonsterDef`, in the order the text
gives. The Cultist uses the same path, with its stats from the Ancient One sheet.
"""

from __future__ import annotations

from dataclasses import replace

from pursuit.content.defs import MonsterDef
from pursuit.controller import Option
from pursuit.effects.base import Ctx, run_effects
from pursuit.engine import rules
from pursuit.engine.dice import run_test
from pursuit.engine.state import Game, Investigator, MonsterInst

DEFEATED = "defeated"
SURVIVED = "survived"
FELL = "fell"


def resolve_monsters(game: Game, inv: Investigator, *, encounter_phase: bool = False) -> bool:
    """Encounter every monster at the investigator's location in the order of their choice.

    Returns True if the investigator may resolve another encounter. Only the Encounter
    Phase has one to give up, so `encounter_phase` turns on the Gug and Byakhee effects.
    """
    state = game.locations[inv.location]
    fought: set[int] = set()
    blocked = False
    replacement = None
    while True:
        if inv.defeated or game.outcome:
            return False
        remaining = [m for m in state.monsters if m.uid not in fought]
        if not remaining:
            break
        if len(remaining) == 1:
            monster = remaining[0]
        else:
            options = [
                Option(
                    game.monster_def(m.def_id).name,
                    m.uid,
                    f"Health {rules.toughness(game, m.def_id) - m.wounds}/{rules.toughness(game, m.def_id)}",
                )
                for m in remaining
            ]
            pick = rules.choose(game, "Encounter which monster next?", options, kind="monster_order", inv=inv)
            monster = remaining[pick]
        fought.add(monster.uid)
        mdef = game.monster_def(monster.def_id)
        if combat(game, inv, monster) == DEFEATED:
            blocked = blocked or mdef.blocks_encounter
            replacement = replacement or mdef.replace_encounter
    if state.monsters or inv.defeated:
        return False
    if encounter_phase and blocked:
        return False
    if (
        encounter_phase
        and replacement is not None
        and replacement.cost.can_pay(inv)
        and rules.confirm(game, replacement.text, kind="replace_encounter", inv=inv)
    ):
        rules.pay_cost(game, inv, replacement.cost)
        run_effects(replacement.effects, Ctx(game, inv, "replace_encounter"))
        return False
    return True


def ambush(game: Game, inv: Investigator, def_id: str | None = None) -> str | None:
    """Draw a Monster and encounter it. Returns the combat result, or None with no Monster."""
    monster = rules.spawn_monster(game, inv.location, def_id, trigger=False)
    if monster is None:
        return None
    return combat(game, inv, monster, ambush=True)


def combat(game: Game, inv: Investigator, monster: MonsterInst, *, ambush: bool = False) -> str:
    mdef = game.monster_def(monster.def_id)
    ctx = Ctx(game, inv, f"monster:{mdef.id}", monster=monster)
    rules.emit(
        game,
        "combat",
        f"{inv.name} encounters the {mdef.name}. {mdef.text}",
        monster=mdef.id,
        start=True,
        wounds=monster.wounds,
    )

    def gone() -> bool:
        return rules.monster_location(game, monster) is None

    def finish() -> str:
        if gone():
            run_effects(mdef.on_combat_defeat, ctx)
            return FELL if inv.defeated else DEFEATED
        if ambush:
            _return_ambush_monster(game, inv.location, monster)
        return FELL if inv.defeated else SURVIVED

    run_effects(mdef.before_will, ctx)
    failed_will = _will_test(game, inv, mdef, ctx) if mdef.horror_test and not inv.defeated else False
    run_effects(mdef.after_will, ctx)
    if gone() or inv.defeated:
        return finish()

    if not mdef.damage_test or (failed_will and mdef.skip_strength_on_will_fail):
        rules.emit(game, "combat", f"{inv.name} does not resolve a Strength test.", monster=mdef.id)
        return finish()

    run_effects(mdef.before_strength, ctx)
    if gone() or inv.defeated:
        return finish()

    full = rules.toughness(game, monster.def_id)
    result = run_test(
        game,
        inv,
        "strength",
        mdef.fight_mod,
        contexts=("combat", "fight"),
        needed=max(1, full - monster.wounds, mdef.damage),
        label=f"Strength test against the {mdef.name}",
        allow_clues=not mdef.no_clue_rerolls,
    )
    reduction = sum(game.asset_def(c).damage_reduction for c in inv.assets)
    health_loss = max(0, _reduced(mdef.damage, reduction) - result.successes)
    if health_loss > 0 and result.successes == 0 and mdef.ally_shield and _spend_ally(game, inv):
        health_loss = 0
    if health_loss > 0:
        rules.change_health(game, inv, -health_loss)
        run_effects(mdef.lost_health, ctx)

    rules.wound_monster(game, inv, monster, result.successes)
    if not gone():
        if health_loss > 0:
            run_effects(mdef.after_hit, replace(ctx, inv=None))
        if not ambush:
            left = full - monster.wounds
            rules.emit(game, "combat", f"The {mdef.name} remains ({left}/{full} Health).", monster=mdef.id)
    return finish()


def _will_test(game: Game, inv: Investigator, mdef: MonsterDef, ctx: Ctx) -> bool:
    """Resolve the Will test. Returns True if the investigator failed it."""
    result = run_test(
        game,
        inv,
        "will",
        mdef.horror_mod,
        contexts=("combat", "horror"),
        needed=max(1, mdef.horror),
        label=f"Will test against the {mdef.name}",
        allow_clues=not mdef.no_clue_rerolls,
    )
    reduction = sum(game.asset_def(c).sanity_reduction for c in inv.assets)
    sanity_loss = max(0, _reduced(mdef.horror, reduction) - result.successes)
    if sanity_loss > 0:
        rules.change_sanity(game, inv, -sanity_loss)
        if mdef.sanity_to_sheet:
            game.sheet_tokens += sanity_loss
    failed = result.successes == 0
    hook = mdef.will_failed if failed else mdef.will_passed
    run_effects(hook, replace(ctx, test_successes=result.successes))
    return failed


def _spend_ally(game: Game, inv: Investigator) -> bool:
    allies = [c for c in inv.assets if game.asset_def(c).kind == "ally"]
    prompt = "Discard 1 Ally Asset instead of losing Health?"
    if not allies or not rules.confirm(game, prompt, kind="ally_shield", inv=inv):
        return False
    options = [Option(game.asset_def(c).name, c.uid) for c in allies]
    pick = rules.choose(game, "Discard which Ally?", options, kind="lose_asset", inv=inv, auto_single=True)
    rules.discard_asset(game, inv, allies[pick])
    return True


def _reduced(value: int, reduction: int) -> int:
    return max(1, value - reduction) if value > 0 and reduction else value


def _return_ambush_monster(game: Game, loc_id: str, monster: MonsterInst) -> None:
    state = game.locations[loc_id]
    if monster in state.monsters:
        state.monsters.remove(monster)
    if not game.monster_def(monster.def_id).epic:
        game.monster_cup.append(monster.def_id)
