"""Action Phase actions. Each investigator may perform up to 2 actions per round.

Each action (Travel, Rest, Trade, Prepare for Travel, Acquire Assets, or any single
component action) may be performed at most once per round.
"""

from __future__ import annotations

from typing import Any

from pursuit.content.defs import ActionAbility
from pursuit.controller import Option
from pursuit.effects.base import Ctx, run_effects
from pursuit.engine import rules
from pursuit.engine.dice import dice_pool, run_test
from pursuit.engine.state import AssetCard, ConditionInst, Game, Investigator

FREE_ACTIONS = ("end",)


def actions_left(game: Game, inv: Investigator) -> int:
    return max(0, game.content.rules.actions_per_turn + inv.bonus_actions - len(inv.actions_taken))


def _ability_ok(game: Game, inv: Investigator, ability: ActionAbility) -> bool:
    if not ability.cost.can_pay(inv):
        return False
    return ability.requires is None or ability.requires.matches(game, inv)


def _available_ticket_kinds(game: Game, loc_id: str) -> list[str]:
    kinds = {k for _, k in rules.neighbors(game, loc_id) if k in ("train", "ship")}
    return [k for k in ("train", "ship") if k in kinds]


def action_options(game: Game, inv: Investigator) -> list[Option]:
    content = game.content
    state = game.locations[inv.location]
    ldef = content.locations[inv.location]
    left = actions_left(game, inv)
    opts: list[Option] = []

    def action(key: str, value: Any, label: str, detail: str, ok: bool = True, why: str = "") -> None:
        base_key = key.split(":")[0]
        block = rules.blocked(game, inv, base_key)
        if left <= 0:
            ok, why = False, "no actions left"
        elif key in inv.actions_taken:
            ok, why = False, "already done this round"
        elif block:
            ok, why = False, f"{block} prevents this"
        opts.append(Option(label, value, detail if ok else why or detail, enabled=ok))

    action("travel", ("travel",), "Travel", "Move 1 space along any path, then spend travel tickets.")

    rest_amount = 1 + rules.perk(game, inv, "rest_bonus")
    action(
        "rest",
        ("rest",),
        "Rest",
        f"Recover {rest_amount} Health and {rest_amount} Sanity.",
        not state.monsters,
        "monsters are on your space",
    )

    ticket_kinds = _available_ticket_kinds(game, inv.location)
    can_prepare = ldef.terrain == "city" and bool(ticket_kinds)
    prepare_why = "only on a City space" if ldef.terrain != "city" else "no Train or Ship paths here"
    action(
        "prepare",
        ("prepare",),
        "Prepare for Travel",
        f"Gain 1 {' or '.join(k.title() for k in ticket_kinds)} Ticket." if can_prepare else "Gain 1 travel ticket.",
        can_prepare,
        prepare_why,
    )

    inf_dice = dice_pool(game, inv, "influence", 0, ("acquire",))
    can_acquire = ldef.terrain == "city" and not state.monsters and bool(game.reserve)
    acquire_why = (
        "only on a City space"
        if ldef.terrain != "city"
        else "monsters are on your space"
        if state.monsters
        else "the reserve is empty"
    )
    action(
        "acquire",
        ("acquire",),
        "Acquire Assets",
        f"Test Influence ({inf_dice} dice) to gain Assets from the reserve.",
        can_acquire,
        acquire_why,
    )

    others = [o for o in game.investigators_at(inv.location) if o is not inv]
    action(
        "trade",
        ("trade",),
        "Trade",
        "Trade Assets, Artifacts, Spells, Clues, and travel tickets with an investigator here.",
        bool(others),
        "no other investigator on your space",
    )

    # Component actions: investigator sheet, owned assets/spells/artifacts, conditions, and local actions on space
    idef = content.investigators[inv.def_id]
    if idef.action is not None:
        action(
            "component:ability",
            ("ability",),
            f"Action: {idef.name}",
            idef.action.text,
            _ability_ok(game, inv, idef.action),
            "requirements not met",
        )

    for card in inv.assets:
        adef = game.asset_def(card)
        if adef.action is None:
            continue
        action(
            f"component:asset:{card.uid}",
            ("asset", card.uid),
            f"Action: {adef.name}",
            adef.action.text,
            not card.exhausted and _ability_ok(game, inv, adef.action),
            "already used this round" if card.exhausted else "requirements not met",
        )

    for person in game.investigators_at(inv.location):
        for inst in person.conditions:
            cdef = content.conditions[inst.def_id]
            if cdef.action is None:
                continue
            if person is not inv and not cdef.action.local:
                continue
            owner_tag = "" if person is inv else f" ({person.name})"
            action(
                f"component:condition:{inst.uid}",
                ("condition", person.seat, inst.uid),
                f"{'Local ' if cdef.action.local else ''}Action: {cdef.name}{owner_tag}",
                cdef.action.text,
                _ability_ok(game, inv, cdef.action),
                "requirements not met",
            )

    opts.append(Option("End turn", ("end",), f"{left} action(s) left."))
    return opts


# Alias for backward compatibility in callers
day_options = action_options


def additional_action(game: Game, inv: Investigator) -> None:
    """Let `inv` perform 1 action now, outside their own turn."""
    if inv.delayed or inv.defeated:
        return
    inv.bonus_actions += 1
    options = action_options(game, inv)
    value = options[rules.choose(game, f"{inv.name}, perform 1 additional action.", options, kind="action", inv=inv)].value
    if value[0] == "end":
        inv.bonus_actions -= 1
    else:
        perform(game, inv, value)


def perform(game: Game, inv: Investigator, value: tuple) -> None:
    key = value[0]
    handlers = {
        "travel": _travel,
        "rest": _rest,
        "prepare": _prepare,
        "acquire": _acquire,
        "trade": _trade,
    }
    if key in handlers:
        if handlers[key](game, inv):
            inv.actions_taken.append(key)
    elif key == "ability":
        ability = game.content.investigators[inv.def_id].action
        if ability is not None and _run_ability(game, inv, ability, f"ability:{inv.def_id}"):
            inv.actions_taken.append("component:ability")
    elif key == "asset":
        card = next(c for c in inv.assets if c.uid == value[1])
        if _use_asset(game, inv, card):
            inv.actions_taken.append(f"component:asset:{card.uid}")
    elif key == "condition":
        owner = next(i for i in game.investigators if i.seat == value[1])
        inst = next((c for c in owner.conditions if c.uid == value[2]), None)
        if inst is not None and _use_condition(game, inv, owner, inst):
            inv.actions_taken.append(f"component:condition:{inst.uid}")
    else:
        raise ValueError(f"unknown action {value!r}")


# --- the actions ----------------------------------------------------------------------


def _travel(game: Game, inv: Investigator) -> bool:
    content = game.content
    near = rules.neighbors(game, inv.location)
    options = [Option(f"{content.locations[d].name}", d, f"{k} path, {content.locations[d].terrain}") for d, k in near]
    options.append(Option("Cancel", None))
    pick = rules.choose(game, "Travel where?", options, kind="travel", inv=inv)
    dest = options[pick].value
    if dest is None:
        return False
    kind = dict(near)[dest]
    rules.move_investigator(game, inv, dest, kind)

    while inv.tickets:
        onward = [
            (d, k)
            for d, k in rules.neighbors(game, inv.location)
            if k in ("train", "ship") and k in inv.tickets
        ]
        if not onward:
            break
        options = [
            Option(content.locations[d].name, (d, k), f"spend {k.title()} Ticket")
            for d, k in onward
        ]
        options.append(Option(f"Stop at {content.locations[inv.location].name}", None))
        pick = rules.choose(game, "Spend a travel ticket to continue?", options, kind="travel_onward", inv=inv)
        choice = options[pick].value
        if choice is None:
            break
        dest_id, route_kind = choice
        inv.tickets.remove(route_kind)
        rules.emit(game, "info", f"{inv.name} spends a {route_kind.title()} Ticket.")
        rules.move_investigator(game, inv, dest_id, route_kind)
    return True


def _rest(game: Game, inv: Investigator) -> bool:
    amount = 1 + rules.perk(game, inv, "rest_bonus")
    rules.emit(game, "info", f"{inv.name} rests.")
    rules.change_health(game, inv, amount)
    rules.change_sanity(game, inv, amount)
    for card in list(inv.assets):
        if (
            card.def_id == "arcane_tome"
            and not card.exhausted
            and rules.confirm(game, "Use Arcane Tome (test Lore -1 to gain 1 Spell)?", kind="rest_tome", inv=inv)
        ):
            card.exhausted = True
            res = run_test(game, inv, "lore", -1, contexts=("encounter",), label="Arcane Tome")
            if res.passed:
                spell = rules.draw_matching(game, kind="spell")
                if spell is not None:
                    rules.gain_card(game, inv, spell)
    return True


def _prepare(game: Game, inv: Investigator) -> bool:
    kinds = _available_ticket_kinds(game, inv.location)
    if not kinds:
        return False
    options = [Option(f"{k.title()} Ticket", k) for k in kinds]
    pick = rules.choose(game, "Gain which travel ticket?", options, kind="prepare_ticket", inv=inv, auto_single=True)
    rules.gain_ticket(game, inv, options[pick].value)
    return True


def _acquire(game: Game, inv: Investigator) -> bool:
    result = run_test(game, inv, "influence", contexts=("acquire",), label="Acquire Assets", open_ended=True)
    budget = result.successes + rules.perk(game, inv, "acquire_bonus")
    bought_any = False

    while game.reserve:
        affordable = [c for c in game.reserve if game.asset_def(c).cost <= budget]
        if not affordable:
            break
        options = []
        for card in game.reserve:
            adef = game.asset_def(card)
            options.append(
                Option(
                    f"{adef.name} (cost {adef.cost})",
                    card.uid,
                    adef.text,
                    enabled=adef.cost <= budget,
                )
            )
        options.append(Option("Done acquiring assets", None))
        pick = rules.choose(
            game,
            f"Acquire Assets: {budget} success(es) remaining.",
            options,
            kind="acquire",
            inv=inv,
        )
        uid = options[pick].value
        if uid is None:
            break
        card = next(c for c in game.reserve if c.uid == uid)
        game.reserve.remove(card)
        budget -= game.asset_def(card).cost
        bought_any = True
        game.bump("assets_acquired")

        recipient = inv
        if inv.def_id == "charlie_kane" and len(game.active_investigators()) > 1:
            people = [i for i in game.active_investigators() if not i.defeated]
            r_opts = [Option(p.name, p.seat, rules.loc_name(game, p.location)) for p in people]
            r_pick = rules.choose(
                game,
                f"Charlie Kane: who receives {game.asset_def(card).name}?",
                r_opts,
                kind="ability_target",
                inv=inv,
            )
            recipient = people[r_pick]
        rules.gain_card(game, recipient, card)

    if not bought_any and game.reserve:
        options = [Option(f"Discard {game.asset_def(c).name}", c.uid, game.asset_def(c).text) for c in game.reserve]
        options.append(Option("Keep reserve as is", None))
        pick = rules.choose(
            game,
            "You gained no cards. Discard 1 card from the reserve?",
            options,
            kind="acquire_discard",
            inv=inv,
        )
        uid = options[pick].value
        if uid is not None:
            card = next(c for c in game.reserve if c.uid == uid)
            game.reserve.remove(card)
            game.asset_deck.discard(card)
            rules.emit(game, "info", f"{inv.name} discards {game.asset_def(card).name} from the reserve.")

    rules.refill_reserve(game)
    return True


def _trade(game: Game, inv: Investigator) -> bool:
    others = [o for o in game.investigators_at(inv.location) if o is not inv]
    if not others:
        return False
    options = [Option(o.name, o.seat) for o in others]
    other = others[rules.choose(game, "Trade with whom?", options, kind="trade_partner", inv=inv, auto_single=True)]
    traded = False
    while True:
        options = [
            Option(f"Give a card to {other.name}", "give_asset", enabled=bool(inv.assets)),
            Option(f"Take a card from {other.name}", "take_asset", enabled=bool(other.assets)),
            Option(f"Give 1 Clue to {other.name}", "give_clue", enabled=inv.clues > 0),
            Option(f"Take 1 Clue from {other.name}", "take_clue", enabled=other.clues > 0),
            Option(f"Give a Ticket to {other.name}", "give_ticket", enabled=bool(inv.tickets)),
            Option(f"Take a Ticket from {other.name}", "take_ticket", enabled=bool(other.tickets)),
            Option("Done trading", "done"),
        ]
        what = options[rules.choose(game, "Trade possessions.", options, kind="trade", inv=inv)].value
        if what == "done":
            return traded
        giver, taker = (inv, other) if what.startswith("give") else (other, inv)
        if what.endswith("asset"):
            cards = giver.assets
            pick = rules.choose(
                game,
                "Which possession?",
                [Option(game.asset_def(c).name, c.uid) for c in cards],
                kind="trade_asset",
                inv=inv,
                auto_single=True,
            )
            card = cards.pop(pick)
            taker.assets.append(card)
            rules.emit(game, "info", f"{giver.name} trades {game.asset_def(card).name} to {taker.name}.")
            traded = True
        elif what.endswith("ticket"):
            ticket = giver.tickets.pop(0)
            rules.emit(game, "info", f"{giver.name} trades a {ticket.title()} Ticket to {taker.name}.")
            rules.gain_ticket(game, taker, ticket)
            traded = True
        else:
            giver.clues -= 1
            taker.clues += 1
            rules.emit(game, "info", f"{giver.name} gives 1 Clue to {taker.name}.")
            traded = True


def _run_ability(game: Game, inv: Investigator, ability: ActionAbility, source: str, **ctx_kwargs: Any) -> bool:
    target = inv
    if ability.target == "investigator_here":
        people = game.investigators_at(inv.location)
        options = [
            Option(p.name, p.seat, f"Health {p.health}/{p.max_health}, Sanity {p.sanity}/{p.max_sanity}")
            for p in people
        ]
        target = people[
            rules.choose(
                game, "Choose an investigator on your space.", options, kind="ability_target", inv=inv, auto_single=True
            )
        ]
    elif ability.target == "any_investigator":
        people = [p for p in game.active_investigators() if not p.defeated and p is not inv] or [inv]
        options = [
            Option(p.name, p.seat, f"in {rules.loc_name(game, p.location)}")
            for p in people
        ]
        target = people[
            rules.choose(
                game, "Choose an investigator.", options, kind="ability_target", inv=inv, auto_single=True
            )
        ]
    rules.pay_cost(game, inv, ability.cost)
    run_effects(ability.effects, Ctx(game, target, source, **ctx_kwargs))
    return True


def _use_asset(game: Game, inv: Investigator, card: AssetCard) -> bool:
    adef = game.asset_def(card)
    assert adef.action is not None
    rules.emit(game, "info", f"{inv.name} uses {adef.name}.")
    card.exhausted = True
    _run_ability(game, inv, adef.action, f"asset:{adef.id}", asset=card)
    if adef.action.discard and card in inv.assets:
        rules.discard_asset(game, inv, card)
    return True


def _use_condition(game: Game, actor: Investigator, owner: Investigator, inst: ConditionInst) -> bool:
    cdef = game.content.conditions[inst.def_id]
    assert cdef.action is not None
    rules.emit(game, "info", f"{actor.name} acts on {cdef.name}.")
    rules.pay_cost(game, actor, cdef.action.cost)
    run_effects(cdef.action.effects, Ctx(game, actor, f"condition_action:{cdef.id}", condition=inst))
    if cdef.action.discard and inst in owner.conditions:
        rules.remove_condition(game, owner, inst)
    return True

