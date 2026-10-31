"""Day actions. Each costs one of the investigator's actions and works once per round.

Free actions (buy, trade, collect belongings) cost nothing and can repeat.
"""

from __future__ import annotations

from typing import Any

from pursuit.content.defs import ActionAbility
from pursuit.controller import Option
from pursuit.effects.base import Ctx, run_effects
from pursuit.engine import rules
from pursuit.engine.dice import dice_pool, run_test
from pursuit.engine.state import AssetCard, Game, Investigator, RiteState

FREE_ACTIONS = ("buy", "trade", "collect", "end")


def actions_left(game: Game, inv: Investigator) -> int:
    return max(0, game.content.rules.actions_per_turn - len(inv.actions_taken))


def seal_needed(game: Game) -> int:
    return max(1, 1 + game.old_one.seal_mod)


def rite_actions(game: Game, inv: Investigator) -> list[tuple[int, RiteState]]:
    found = []
    for i, rite in enumerate(game.active_rites()):
        rdef = game.rite_def(rite)
        if rite.done or rdef.kind not in ("spend", "test"):
            continue
        if rdef.where is not None and not rdef.where.matches(game, inv.location):
            continue
        found.append((i, rite))
    return found


def _can_contribute(game: Game, inv: Investigator, rite: RiteState) -> bool:
    rdef = game.rite_def(rite)
    if rdef.kind == "test":
        return True
    return {
        "clues": inv.clues > 0,
        "funds": inv.funds > 0,
        "trophies": inv.trophies > 0,
        "relic": any(game.asset_def(c).kind == "relic" for c in inv.assets),
    }[rdef.resource or ""]


def _ability_ok(game: Game, inv: Investigator, ability: ActionAbility) -> bool:
    if not ability.cost.can_pay(inv):
        return False
    return ability.requires is None or ability.requires.matches(game, inv)


def day_options(game: Game, inv: Investigator) -> list[Option]:
    content = game.content
    state = game.locations[inv.location]
    ldef = content.locations[inv.location]
    left = actions_left(game, inv)
    opts: list[Option] = []

    def action(key: str, value: Any, label: str, detail: str, ok: bool = True, why: str = "") -> None:
        block = rules.blocked(game, inv, key.split(":")[0])
        if left <= 0:
            ok, why = False, "no actions left"
        elif key in inv.actions_taken:
            ok, why = False, "already done this round"
        elif block:
            ok, why = False, f"{block} prevents this"
        opts.append(Option(label, value, detail if ok else why or detail, enabled=ok))

    action("travel", ("travel",), "Travel", "Move along a route. Pay Funds to continue by rail or sea.")
    rest_amount = 1 + rules.perk(game, inv, "rest_bonus")
    action(
        "rest",
        ("rest",),
        "Rest",
        f"Recover {rest_amount} Health and {rest_amount} Sanity.",
        not state.monsters,
        "monsters are here",
    )
    action(
        "investigate",
        ("investigate",),
        "Investigate",
        f"Test Wits ({dice_pool(game, inv, 'wits', 0, ('investigate',))} dice) to take the Clue here.",
        state.clue,
        "there is no clue here",
    )
    need = seal_needed(game)
    action(
        "seal",
        ("seal",),
        "Seal the rift",
        f"Test Lore ({dice_pool(game, inv, 'lore', 0, ('seal',))} dice), {need} success(es) needed.",
        state.rift and not state.monsters,
        "no rift here" if not state.rift else "monsters guard the rift",
    )
    action(
        "earn",
        ("earn",),
        "Raise funds",
        f"Test Charm ({dice_pool(game, inv, 'charm', 0, ('funds',))} dice). Gain 1 Funds plus 1 per success.",
        ldef.terrain == "city",
        "only in a city",
    )
    for i, rite in rite_actions(game, inv):
        rdef = game.rite_def(rite)
        action(
            "rite",
            ("rite", i),
            f"Perform rite: {rdef.name}",
            f"{rite.progress}/{rite.required}. {rdef.text}",
            _can_contribute(game, inv, rite),
            "you have nothing to give this rite",
        )
    for card in inv.assets:
        adef = game.asset_def(card)
        if adef.action is None:
            continue
        action(
            f"asset:{card.uid}",
            ("asset", card.uid),
            f"Use {adef.name}",
            adef.action.text,
            not card.exhausted and _ability_ok(game, inv, adef.action),
            "already used this round" if card.exhausted else "requirements not met",
        )
    idef = content.investigators[inv.def_id]
    if idef.action is not None:
        action(
            "ability",
            ("ability",),
            "Use your ability",
            idef.action.text,
            _ability_ok(game, inv, idef.action),
            "requirements not met",
        )
    for inst in inv.conditions:
        cdef = content.conditions[inst.def_id]
        if cdef.cure is not None:
            action(
                "cure",
                ("cure", inst.uid),
                f"Deal with {cdef.name}",
                cdef.cure.text,
                cdef.cure.cost.can_pay(inv),
                f"costs {cdef.cure.cost.describe()}",
            )

    in_city = ldef.terrain == "city" and bool(game.market) and not rules.blocked(game, inv, "buy")
    others = [o for o in game.investigators_at(inv.location) if o is not inv]
    opts.append(Option("Visit the market", ("buy",), "Free. Buy assets with Funds.", enabled=in_city))
    opts.append(Option("Trade", ("trade",), "Free. Swap with an investigator here.", enabled=bool(others)))
    opts.append(
        Option(
            "Collect belongings", ("collect",), "Free. Take what the fallen left here.", enabled=bool(state.belongings)
        )
    )
    opts.append(Option("End turn", ("end",), f"{left} action(s) left."))
    return opts


def perform(game: Game, inv: Investigator, value: tuple) -> None:
    key = value[0]
    handlers = {
        "travel": _travel,
        "rest": _rest,
        "investigate": _investigate,
        "seal": _seal,
        "earn": _earn,
    }
    if key in handlers:
        if handlers[key](game, inv):
            inv.actions_taken.append(key)
    elif key == "rite":
        rite = game.active_rites()[value[1]]
        if _rite(game, inv, rite):
            inv.actions_taken.append("rite")
    elif key == "asset":
        card = next(c for c in inv.assets if c.uid == value[1])
        if _use_asset(game, inv, card):
            inv.actions_taken.append(f"asset:{card.uid}")
    elif key == "ability":
        ability = game.content.investigators[inv.def_id].action
        if ability is not None and _run_ability(game, inv, ability, f"ability:{inv.def_id}"):
            inv.actions_taken.append("ability")
    elif key == "cure":
        if _cure(game, inv, value[1]):
            inv.actions_taken.append("cure")
    elif key == "buy":
        _buy(game, inv)
    elif key == "trade":
        _trade(game, inv)
    elif key == "collect":
        _collect(game, inv)
    else:
        raise ValueError(f"unknown action {value!r}")


# --- the actions ----------------------------------------------------------------------


def _travel(game: Game, inv: Investigator) -> bool:
    content = game.content
    near = rules.neighbors(game, inv.location)
    options = [Option(f"{content.locations[d].name}", d, f"by {k}, {content.locations[d].terrain}") for d, k in near]
    options.append(Option("Cancel", None))
    pick = rules.choose(game, "Travel where?", options, kind="travel", inv=inv)
    dest = options[pick].value
    if dest is None:
        return False
    kind = dict(near)[dest]
    rules.move_investigator(game, inv, dest, kind)
    free = rules.perk(game, inv, "free_travel_steps")
    for _ in range(content.rules.max_paid_steps):
        cost = 0 if free > 0 else content.rules.step_cost
        onward = [(d, k) for d, k in rules.neighbors(game, inv.location) if k in ("rail", "sea")]
        if not onward or inv.funds < cost:
            break
        price = "free" if cost == 0 else f"{cost} Funds"
        options = [Option(content.locations[d].name, d, f"by {k}, {price}") for d, k in onward]
        options.append(Option(f"Stop at {content.locations[inv.location].name}", None))
        pick = rules.choose(game, f"Continue by rail or sea ({price})?", options, kind="travel_onward", inv=inv)
        dest = options[pick].value
        if dest is None:
            break
        if cost:
            rules.change_funds(game, inv, -cost)
        else:
            free -= 1
        rules.move_investigator(game, inv, dest, dict(onward)[dest])
    return True


def _rest(game: Game, inv: Investigator) -> bool:
    amount = 1 + rules.perk(game, inv, "rest_bonus")
    rules.emit(game, "info", f"{inv.name} rests.")
    rules.change_health(game, inv, amount)
    rules.change_sanity(game, inv, amount)
    rules.trigger_conditions(game, inv, "rest")
    return True


def _investigate(game: Game, inv: Investigator) -> bool:
    state = game.locations[inv.location]
    result = run_test(game, inv, "wits", contexts=("investigate",), label="the investigation")
    if result.passed and state.clue:
        state.clue = False
        rules.change_clues(game, inv, 1 + rules.perk(game, inv, "investigate_bonus"))
    else:
        rules.emit(game, "info", "The trail goes cold, for now.")
    return True


def _seal(game: Game, inv: Investigator) -> bool:
    need = seal_needed(game)
    result = run_test(game, inv, "lore", contexts=("seal",), needed=need, label="sealing the rift")
    if result.passed:
        rules.close_rift(game, inv, inv.location)
    else:
        rules.emit(game, "info", "The rift resists, and something on the other side notices you.")
        rules.change_sanity(game, inv, -1)
    return True


def _earn(game: Game, inv: Investigator) -> bool:
    result = run_test(game, inv, "charm", contexts=("funds",), needed=1, label="raising funds")
    rules.change_funds(game, inv, 1 + result.successes + rules.perk(game, inv, "earn_bonus"))
    return True


def _rite(game: Game, inv: Investigator, rite: RiteState) -> bool:
    rdef = game.rite_def(rite)
    remaining = rite.required - rite.progress
    if rdef.kind == "test":
        assert rdef.skill is not None
        result = run_test(game, inv, rdef.skill, rdef.mod, contexts=("rite",), needed=remaining, label=rdef.name)
        if result.successes:
            rules.add_rite_progress(game, rite, result.successes)
        else:
            rules.emit(game, "info", "The rite falters. Nothing is gained.")
        return True
    if rdef.resource == "relic":
        relics = [c for c in inv.assets if game.asset_def(c).kind == "relic"]
        options = [Option(game.asset_def(c).name, c.uid) for c in relics] + [Option("Cancel", None)]
        pick = rules.choose(game, "Offer which relic to the rite?", options, kind="rite_relic", inv=inv)
        if options[pick].value is None:
            return False
        rules.discard_asset(game, inv, relics[pick])
        rules.add_rite_progress(game, rite, 1)
        return True
    have = {"clues": inv.clues, "funds": inv.funds, "trophies": inv.trophies}[rdef.resource or ""]
    most = min(have, remaining)
    options = [Option(f"Give {n}", n) for n in range(most, 0, -1)] + [Option("Cancel", 0)]
    pick = rules.choose(game, f"Give how many {rdef.resource} to '{rdef.name}'?", options, kind="rite_amount", inv=inv)
    amount = options[pick].value
    if not amount:
        return False
    if rdef.resource == "clues":
        rules.change_clues(game, inv, -amount)
    elif rdef.resource == "funds":
        rules.change_funds(game, inv, -amount)
    else:
        inv.trophies -= amount
    rules.add_rite_progress(game, rite, amount)
    return True


def _run_ability(game: Game, inv: Investigator, ability: ActionAbility, source: str) -> bool:
    target = inv
    if ability.target == "investigator_here":
        people = game.investigators_at(inv.location)
        options = [
            Option(p.name, p.seat, f"Health {p.health}/{p.max_health}, Sanity {p.sanity}/{p.max_sanity}")
            for p in people
        ]
        target = people[
            rules.choose(
                game, "Choose an investigator here.", options, kind="ability_target", inv=inv, auto_single=True
            )
        ]
    rules.pay_cost(game, inv, ability.cost)
    run_effects(ability.effects, Ctx(game, target, source))
    return True


def _use_asset(game: Game, inv: Investigator, card: AssetCard) -> bool:
    adef = game.asset_def(card)
    assert adef.action is not None
    rules.emit(game, "info", f"{inv.name} uses {adef.name}.")
    card.exhausted = True
    _run_ability(game, inv, adef.action, f"asset:{adef.id}")
    if adef.action.discard and card in inv.assets:
        rules.discard_asset(game, inv, card)
    return True


def _cure(game: Game, inv: Investigator, uid: int) -> bool:
    inst = next((c for c in inv.conditions if c.uid == uid), None)
    if inst is None:
        return False
    cdef = game.content.conditions[inst.def_id]
    cure = cdef.cure
    assert cure is not None
    rules.pay_cost(game, inv, cure.cost)
    if cure.skill is not None:
        result = run_test(game, inv, cure.skill, cure.mod, label=f"dealing with {cdef.name}")
        if not result.passed:
            rules.emit(game, "info", f"{cdef.name} still clings to {inv.name}.")
            return True
    rules.remove_condition(game, inv, inst)
    return True


def _buy(game: Game, inv: Investigator) -> None:
    while game.market:
        options = []
        for card in game.market:
            adef = game.asset_def(card)
            price = rules.market_price(game, inv, card)
            options.append(Option(f"{adef.name} ({price} Funds)", card.uid, adef.text, enabled=inv.funds >= price))
        options.append(Option("Leave the market", None))
        pick = rules.choose(game, f"The market. You have {inv.funds} Funds.", options, kind="buy", inv=inv)
        if options[pick].value is None:
            return
        card = game.market.pop(pick)
        rules.change_funds(game, inv, -rules.market_price(game, inv, card))
        game.bump("assets_bought")
        rules.gain_card(game, inv, card)
        rules.refill_market(game)


def _trade(game: Game, inv: Investigator) -> None:
    others = [o for o in game.investigators_at(inv.location) if o is not inv]
    if not others:
        return
    options = [Option(o.name, o.seat) for o in others]
    other = others[rules.choose(game, "Trade with whom?", options, kind="trade_partner", inv=inv, auto_single=True)]
    while True:
        options = [
            Option(f"Give an asset to {other.name}", "give_asset", enabled=bool(inv.assets)),
            Option(f"Take an asset from {other.name}", "take_asset", enabled=bool(other.assets)),
            Option(f"Give 1 Funds to {other.name}", "give_funds", enabled=inv.funds > 0),
            Option(f"Take 1 Funds from {other.name}", "take_funds", enabled=other.funds > 0),
            Option(f"Give 1 Clue to {other.name}", "give_clue", enabled=inv.clues > 0),
            Option(f"Take 1 Clue from {other.name}", "take_clue", enabled=other.clues > 0),
            Option("Done trading", "done"),
        ]
        what = options[rules.choose(game, "Trade.", options, kind="trade", inv=inv)].value
        if what == "done":
            return
        giver, taker = (inv, other) if what.startswith("give") else (other, inv)
        if what.endswith("asset"):
            cards = giver.assets
            pick = rules.choose(
                game,
                "Which asset?",
                [Option(game.asset_def(c).name, c.uid) for c in cards],
                kind="trade_asset",
                inv=inv,
            )
            card = cards.pop(pick)
            taker.assets.append(card)
            rules.emit(game, "info", f"{giver.name} hands {game.asset_def(card).name} to {taker.name}.")
        elif what.endswith("funds"):
            giver.funds -= 1
            taker.funds += 1
            rules.emit(game, "info", f"{giver.name} gives 1 Funds to {taker.name}.")
        else:
            giver.clues -= 1
            taker.clues += 1
            rules.emit(game, "info", f"{giver.name} gives 1 Clue to {taker.name}.")


def _collect(game: Game, inv: Investigator) -> None:
    pile = game.locations[inv.location].belongings
    while pile:
        options = [Option(game.asset_def(c).name, c.uid, game.asset_def(c).text) for c in pile]
        options.append(Option("Done", None))
        pick = rules.choose(game, "Take what?", options, kind="collect", inv=inv)
        if options[pick].value is None:
            return
        card = pile.pop(pick)
        inv.assets.append(card)
        rules.emit(game, "gain", f"{inv.name} takes {game.asset_def(card).name}.")
