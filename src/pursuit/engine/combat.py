"""Combat: a Will test against horror, then a Strength test to fight.

Will test: if the monster's horror exceeds successes rolled, the investigator loses
Sanity equal to the difference.
Strength test: if the monster's damage exceeds successes rolled, the investigator loses
Health equal to the difference, and the monster loses Health equal to successes rolled.
If the monster reaches its toughness in wounds, it is defeated.
"""

from __future__ import annotations

from pursuit.controller import Option
from pursuit.engine import rules
from pursuit.engine.dice import run_test
from pursuit.engine.state import Game, Investigator, MonsterInst

DEFEATED = "defeated"
SURVIVED = "survived"
FELL = "fell"


def resolve_monsters(game: Game, inv: Investigator) -> bool:
    """Encounter every monster at the investigator's location in the order of their choice.

    Returns True if no monsters remain on the space and the investigator is not defeated.
    """
    state = game.locations[inv.location]
    fought: set[int] = set()
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
                    game.content.monsters[m.def_id].name,
                    m.uid,
                    f"Health {rules.toughness(game, m.def_id) - m.wounds}/{rules.toughness(game, m.def_id)}",
                )
                for m in remaining
            ]
            pick = rules.choose(game, "Encounter which monster next?", options, kind="monster_order", inv=inv)
            monster = remaining[pick]
        fought.add(monster.uid)
        combat(game, inv, monster)
    return not state.monsters and not inv.defeated


def combat(game: Game, inv: Investigator, monster: MonsterInst, *, ambush: bool = False) -> str:
    mdef = game.content.monsters[monster.def_id]
    old = game.old_one
    is_cultist = monster.def_id == "cultist"
    horror = old.cultist_horror if is_cultist else mdef.horror
    horror_mod = old.cultist_horror_mod if is_cultist else mdef.horror_mod
    damage = old.cultist_damage if is_cultist else mdef.damage
    fight_mod = old.cultist_fight_mod if is_cultist else mdef.fight_mod
    horror_test = old.cultist_horror_test if is_cultist else mdef.horror_test
    damage_test = old.cultist_damage_test if is_cultist else mdef.damage_test
    text = (old.cultist_text or mdef.text) if is_cultist else mdef.text

    rules.emit(
        game,
        "combat",
        f"{inv.name} encounters the {mdef.name}. {text}",
        monster=mdef.id,
        start=True,
        wounds=monster.wounds,
    )

    if horror_test:
        result = run_test(
            game,
            inv,
            "will",
            horror_mod,
            contexts=("combat", "horror"),
            needed=horror,
            label=f"Will test against the {mdef.name}",
        )
        s_red = sum(game.asset_def(c).sanity_reduction for c in inv.assets)
        sanity_loss = max(0, _reduced(horror, s_red) - result.successes)
        if sanity_loss > 0:
            rules.change_sanity(game, inv, -sanity_loss)
        if inv.defeated:
            if ambush:
                _return_ambush_monster(game, inv.location, monster)
            return FELL

    full = rules.toughness(game, monster.def_id)
    remaining_hp = full - monster.wounds

    if is_cultist and old.cultist_on_defeat and old.id == "azathoth" and not damage_test:
        # Azathoth cultist: After resolving the Will test, lose 1 Health and defeat this Monster.
        rules.change_health(game, inv, -1)
        rules.defeat_monster(game, inv, inv.location, monster)
        return FELL if inv.defeated else DEFEATED

    if not damage_test:
        if ambush:
            _return_ambush_monster(game, inv.location, monster)
        else:
            rules.emit(game, "combat", f"The {mdef.name} has no Strength test.", monster=mdef.id)
        return FELL if inv.defeated else SURVIVED

    result = run_test(
        game,
        inv,
        "strength",
        fight_mod,
        contexts=("combat", "fight"),
        needed=max(1, remaining_hp, damage),
        label=f"Strength test against the {mdef.name}",
    )
    d_red = sum(game.asset_def(c).damage_reduction for c in inv.assets)
    health_loss = max(0, _reduced(damage, d_red) - result.successes)
    if health_loss > 0:
        rules.change_health(game, inv, -health_loss)

    monster.wounds += result.successes
    if monster.wounds >= full:
        rules.defeat_monster(game, inv, inv.location, monster)
        return FELL if inv.defeated else DEFEATED

    if ambush:
        _return_ambush_monster(game, inv.location, monster)
    else:
        rules.emit(
            game,
            "combat",
            f"The {mdef.name} takes {result.successes} wound(s) and remains ({full - monster.wounds}/{full} Health).",
            monster=mdef.id,
        )
    return FELL if inv.defeated else SURVIVED


def _reduced(value: int, reduction: int) -> int:
    return max(1, value - reduction) if value > 0 and reduction else value


def _return_ambush_monster(game: Game, loc_id: str, monster: MonsterInst) -> None:
    state = game.locations[loc_id]
    if monster in state.monsters:
        state.monsters.remove(monster)
    mdef = game.content.monsters[monster.def_id]
    if not mdef.epic:
        game.monster_cup.append(monster.def_id)

