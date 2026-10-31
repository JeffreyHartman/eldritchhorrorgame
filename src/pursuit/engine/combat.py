"""Combat: a horror check, then the investigator chooses to fight or evade.

Fight tests Brawn. Each success is 1 damage. If the monster survives, it strikes for its
full damage. Evade tests Wits. A pass slips away. A fail takes the strike. Wounds stay
on a monster until something heals it, so investigators can wear down a tough monster
together.
"""

from __future__ import annotations

from pursuit.controller import Option
from pursuit.engine import rules
from pursuit.engine.dice import dice_pool, run_test
from pursuit.engine.state import Game, Investigator, MonsterInst

DEFEATED = "defeated"
EVADED = "evaded"
STRUCK = "struck"
FELL = "fell"


def resolve_monsters(game: Game, inv: Investigator) -> bool:
    """Face every monster at the investigator's location in turn.

    Returns True if the investigator may still have a location encounter afterwards.
    """
    clear = True
    for monster in list(game.locations[inv.location].monsters):
        if inv.defeated or game.outcome:
            return False
        if monster not in game.locations[inv.location].monsters:
            continue
        if combat(game, inv, monster) in (STRUCK, FELL):
            clear = False
    return clear and not inv.defeated


def combat(game: Game, inv: Investigator, monster: MonsterInst) -> str:
    mdef = game.content.monsters[monster.def_id]
    rules.emit(
        game,
        "combat",
        f"{inv.name} faces the {mdef.name}. {mdef.text}",
        monster=mdef.id,
        start=True,
        wounds=monster.wounds,
    )
    if mdef.horror > 0:
        result = run_test(
            game, inv, "nerve", mdef.horror_mod, contexts=("horror",), label=f"the horror of the {mdef.name}"
        )
        if not result.passed:
            rules.change_sanity(game, inv, -mdef.horror)
        if inv.defeated:
            return FELL

    full = rules.toughness(game, monster.def_id)
    remaining = full - monster.wounds
    fight_dice = max(1, dice_pool(game, inv, "brawn", mdef.fight_mod, ("combat",)))
    evade_dice = max(1, dice_pool(game, inv, "wits", mdef.evade_mod, ("evade",)))
    options = [
        Option(
            "Fight",
            "fight",
            f"Roll {fight_dice} Brawn dice. Each success is 1 damage. It has {remaining} Health left.",
        ),
        Option(
            "Evade",
            "evade",
            f"Roll {evade_dice} Wits dice. Fail and it strikes you for {mdef.damage} Health.",
        ),
    ]
    pick = rules.choose(game, f"The {mdef.name} is upon you.", options, kind="combat", inv=inv)

    if options[pick].value == "fight":
        result = run_test(
            game,
            inv,
            "brawn",
            mdef.fight_mod,
            contexts=("combat",),
            needed=remaining,
            label=f"the fight with the {mdef.name}",
        )
        monster.wounds += result.successes
        if monster.wounds >= full:
            rules.defeat_monster(game, inv, inv.location, monster)
            return DEFEATED
        rules.emit(
            game,
            "combat",
            f"The {mdef.name} takes {result.successes} damage and strikes back!",
            monster=mdef.id,
        )
        rules.change_health(game, inv, -mdef.damage)
        return FELL if inv.defeated else STRUCK

    result = run_test(game, inv, "wits", mdef.evade_mod, contexts=("evade",), label=f"evading the {mdef.name}")
    if result.passed:
        rules.emit(game, "combat", f"{inv.name} slips past the {mdef.name}.", monster=mdef.id)
        return EVADED
    rules.emit(game, "combat", f"The {mdef.name} catches {inv.name}!", monster=mdef.id)
    rules.change_health(game, inv, -mdef.damage)
    return FELL if inv.defeated else STRUCK
