"""Rule operations that change the game state. Effects, actions, and phases call these."""

from __future__ import annotations

from collections import deque
from typing import Any

from pursuit.content.defs import MARKET_KINDS, Cost
from pursuit.controller import Event, Option
from pursuit.effects.base import Ctx, run_effects
from pursuit.engine.state import (
    AssetCard,
    ConditionInst,
    Deck,
    Game,
    Investigator,
    MonsterInst,
    RiteState,
)

# --- events and decisions -------------------------------------------------------------


def emit(game: Game, kind: str, text: str, **data: Any) -> None:
    game.log.append(text)
    if len(game.log) > game.LOG_LIMIT:
        del game.log[: len(game.log) - game.LOG_LIMIT]
    game.ctl.notify(game, Event(kind, text, data))


def choose(
    game: Game,
    prompt: str,
    options: list[Option],
    *,
    kind: str,
    inv: Investigator | None = None,
    auto_single: bool = False,
) -> int:
    enabled = [i for i, o in enumerate(options) if o.enabled]
    if not enabled:
        raise RuntimeError(f"no enabled options for '{prompt}'")
    if auto_single and len(enabled) == 1:
        return enabled[0]
    index = game.ctl.choose(game, prompt, options, kind=kind, inv=inv)
    if index not in enabled:
        raise ValueError(f"controller picked option {index}, which is not enabled, for '{prompt}'")
    return index


def confirm(game: Game, prompt: str, *, kind: str, inv: Investigator | None = None) -> bool:
    return bool(game.ctl.confirm(game, prompt, kind=kind, inv=inv))


# --- map helpers ----------------------------------------------------------------------


def neighbors(game: Game, loc_id: str) -> list[tuple[str, str]]:
    return game.content.adjacency[loc_id]


def distances(game: Game, start: str) -> dict[str, int]:
    dist = {start: 0}
    queue = deque([start])
    while queue:
        here = queue.popleft()
        for there, _kind in neighbors(game, here):
            if there not in dist:
                dist[there] = dist[here] + 1
                queue.append(there)
    return dist


def loc_name(game: Game, loc_id: str) -> str:
    return game.content.locations[loc_id].name


# --- outcome --------------------------------------------------------------------------


def win(game: Game, reason: str) -> None:
    if game.outcome is None:
        game.outcome = "win"
        game.outcome_reason = reason
        emit(game, "outcome", reason, result="win")


def lose(game: Game, reason: str) -> None:
    if game.outcome is None:
        game.outcome = "loss"
        game.outcome_reason = reason
        emit(game, "outcome", reason, result="loss")


# --- health, sanity, and defeat -------------------------------------------------------


def change_health(game: Game, inv: Investigator, amount: int) -> None:
    if amount == 0 or inv.defeated:
        return
    if amount > 0:
        gained = min(inv.max_health, inv.health + amount) - inv.health
        inv.health += gained
        if gained:
            emit(game, "gain", f"{inv.name} recovers {gained} Health.", stat="health")
        return
    inv.health = max(0, inv.health + amount)
    emit(game, "loss", f"{inv.name} loses {-amount} Health.", stat="health")
    if inv.health == 0:
        mark_defeated(game, inv, "wounds")


def change_sanity(game: Game, inv: Investigator, amount: int) -> None:
    if amount == 0 or inv.defeated:
        return
    if amount > 0:
        gained = min(inv.max_sanity, inv.sanity + amount) - inv.sanity
        inv.sanity += gained
        if gained:
            emit(game, "gain", f"{inv.name} recovers {gained} Sanity.", stat="sanity")
        return
    inv.sanity = max(0, inv.sanity + amount)
    emit(game, "loss", f"{inv.name} loses {-amount} Sanity.", stat="sanity")
    if inv.sanity == 0:
        mark_defeated(game, inv, "madness")


def change_funds(game: Game, inv: Investigator, amount: int) -> None:
    before = inv.funds
    inv.funds = max(0, inv.funds + amount)
    delta = inv.funds - before
    if delta > 0:
        emit(game, "gain", f"{inv.name} gains {delta} Funds.", stat="funds")
    elif delta < 0:
        emit(game, "loss", f"{inv.name} loses {-delta} Funds.", stat="funds")


def change_clues(game: Game, inv: Investigator, amount: int) -> None:
    before = inv.clues
    inv.clues = max(0, inv.clues + amount)
    delta = inv.clues - before
    if delta > 0:
        emit(game, "gain", f"{inv.name} gains {delta} Clue{'s' if delta > 1 else ''}.", stat="clues")
        game.bump("clues_gained", delta)
    elif delta < 0:
        emit(game, "loss", f"{inv.name} loses {-delta} Clue{'s' if delta < -1 else ''}.", stat="clues")


def mark_defeated(game: Game, inv: Investigator, cause: str) -> None:
    if inv.defeated:
        return
    inv.defeated = True
    emit(game, "defeat", f"{inv.name} is overcome by {cause}!", investigator=inv.name, cause=cause)


def process_defeats(game: Game) -> None:
    """Replace or eliminate every defeated investigator. Safe to call at any time."""
    for idx, inv in enumerate(game.investigators):
        if not inv.defeated or inv.eliminated or game.outcome:
            continue
        here = game.locations[inv.location]
        here.belongings.extend(inv.assets)
        for card in inv.assets:
            card.exhausted = False
        inv.assets = []
        inv.conditions = []
        game.bump("investigators_lost")
        emit(
            game,
            "defeat",
            f"{inv.name}'s belongings are left behind at {loc_name(game, inv.location)}.",
        )
        if game.awakened or not game.unused_investigators:
            inv.eliminated = True
            emit(game, "defeat", f"No one takes {inv.name}'s place.")
        else:
            advance_doom(game, game.content.rules.defeat_doom, f"the loss of {inv.name}")
            if game.outcome:
                return
            replacement = _choose_replacement(game, inv)
            game.investigators[idx] = replacement
        if not game.active_investigators():
            lose(game, "Every investigator has fallen. No one is left to stand against the dark.")
            return


def _choose_replacement(game: Game, old: Investigator) -> Investigator:
    from pursuit.engine.setup import create_investigator

    defs = [game.content.investigators[i] for i in game.unused_investigators]
    options = [Option(d.name, d.id, f"{d.occupation}, starts in {loc_name(game, d.start)}") for d in defs]
    pick = choose(game, f"Choose an investigator to replace {old.name}.", options, kind="replacement")
    def_id = defs[pick].id
    game.unused_investigators.remove(def_id)
    new = create_investigator(game, def_id, old.seat)
    # The new investigator arrives now but acts from the next round.
    new.actions_taken = ["arrived"] * game.content.rules.actions_per_turn
    emit(game, "turn", f"{new.name} joins the investigation at {loc_name(game, new.location)}.")
    return new


# --- doom, dread, awakening -----------------------------------------------------------


def dread_for_doom(game: Game) -> int:
    second, third = game.old_one.dread_at
    if game.doom <= third:
        return 3
    if game.doom <= second:
        return 2
    return 1


def update_dread(game: Game) -> None:
    target = 3 if game.awakened else max(game.dread, dread_for_doom(game))
    while game.dread < target:
        game.dread += 1
        new_cards = [p.id for p in game.content.portents.values() if p.min_dread == game.dread]
        game.portent_deck.shuffle_in(game.rng, new_cards)
        emit(game, "dread", f"Dread rises to level {game.dread}. Worse portents gather.", level=game.dread)


def advance_doom(game: Game, amount: int, reason: str = "") -> None:
    if amount <= 0 or game.outcome:
        return
    why = f" ({reason})" if reason else ""
    if game.awakened:
        game.endgame = max(0, game.endgame - amount)
        emit(game, "doom", f"The end draws closer{why}. Nights left: {game.endgame}.", value=game.endgame)
        if game.endgame == 0:
            lose(game, f"{game.old_one.name} remakes the world in its image. The investigators have failed.")
        return
    game.doom = max(0, game.doom - amount)
    emit(game, "doom", f"Doom advances by {amount}{why}. Doom: {game.doom}.", value=game.doom)
    if game.doom == 0:
        awaken(game)
    else:
        update_dread(game)


def retreat_doom(game: Game, amount: int) -> None:
    if amount <= 0 or game.outcome:
        return
    if game.awakened:
        cap = game.old_one.awakening.nights
        game.endgame = min(cap, game.endgame + amount)
        emit(game, "doom", f"The end is held back. Nights left: {game.endgame}.", value=game.endgame)
        return
    game.doom = min(game.start_doom, game.doom + amount)
    emit(game, "doom", f"Doom retreats by {amount}. Doom: {game.doom}.", value=game.doom)


def awaken(game: Game) -> None:
    if game.awakened:
        return
    old = game.old_one
    game.awakened = True
    game.endgame = old.awakening.nights
    final = old.awakening.final_rite
    game.final_rite = RiteState(final.id, final.required(len(game.active_investigators())), final=True)
    update_dread(game)
    emit(game, "awaken", old.awakening.text, old_one=old.id)
    if final.kind == "defeat" and final.monster:
        _spawn_rite_monster(game, final.monster, final.spawn_at)
    run_effects(old.awakening.effects, Ctx(game, None, f"awakening:{old.id}"))


# --- rites ----------------------------------------------------------------------------


def _spawn_rite_monster(game: Game, monster_id: str, spawn_at: str | None) -> None:
    if spawn_at and spawn_at in game.locations:
        loc = spawn_at
    else:
        sites = [loc.id for loc in game.content.locations.values() if loc.rift_site]
        loc = game.rng.choice(sites)
    spawn_monster(game, loc, monster_id)


def setup_rite_monsters(game: Game) -> None:
    for rite in game.rites:
        rdef = game.rite_def(rite)
        if rdef.kind == "defeat" and rdef.monster:
            _spawn_rite_monster(game, rdef.monster, rdef.spawn_at)


def add_rite_progress(game: Game, rite: RiteState, amount: int) -> None:
    if amount <= 0 or rite.done or game.outcome:
        return
    rite.progress = min(rite.required, rite.progress + amount)
    rdef = game.rite_def(rite)
    if rite.done:
        game.bump("rites_completed")
        emit(game, "rite", f"The rite '{rdef.name}' is complete!", rite=rdef.id, done=True)
    else:
        emit(game, "rite", f"'{rdef.name}': {rite.progress}/{rite.required}.", rite=rdef.id, done=False)
    check_rites(game)


def check_rites(game: Game) -> None:
    if game.outcome:
        return
    if game.awakened:
        if game.final_rite and game.final_rite.done:
            win(game, f"The final rite holds. {game.old_one.name} is cast back into the void between stars.")
    elif game.rites and all(r.done for r in game.rites):
        win(game, f"The rites are complete. {game.old_one.name} sinks back into its long sleep.")


# --- rifts, monsters, clues -----------------------------------------------------------


def open_rift(game: Game) -> None:
    loc_id = game.rift_deck.draw(game.rng)
    if loc_id is None:
        return
    game.rift_deck.discard(loc_id)
    state = game.locations[loc_id]
    if state.rift:
        emit(game, "rift", f"The rift at {loc_name(game, loc_id)} tears wider!", location=loc_id)
        spawn_monster(game, loc_id)
        advance_doom(game, 1, "a rift widens")
    else:
        state.rift = True
        game.bump("rifts_opened")
        emit(game, "rift", f"A rift tears open at {loc_name(game, loc_id)}!", location=loc_id)
        spawn_monster(game, loc_id)
    limit = game.old_one.rift_limit
    if limit and len(game.open_rifts()) >= limit:
        lose(game, f"{limit} rifts stand open at once. The way is open, and {game.old_one.name} steps through.")


def close_rift(game: Game, inv: Investigator, loc_id: str) -> None:
    state = game.locations[loc_id]
    if not state.rift:
        return
    state.rift = False
    trophies = 1 + perk(game, inv, "seal_bonus")
    inv.trophies += trophies
    game.bump("rifts_sealed")
    emit(game, "rift", f"{inv.name} seals the rift at {loc_name(game, loc_id)}.", location=loc_id, sealed=True)
    for rite in game.active_rites():
        rdef = game.rite_def(rite)
        if rdef.kind == "seal" and not rite.done and (rdef.where is None or rdef.where.matches(game, loc_id)):
            add_rite_progress(game, rite, 1)


def spawn_monster(game: Game, loc_id: str, def_id: str | None = None) -> MonsterInst | None:
    content = game.content
    if def_id is None:
        if not game.monster_cup:
            return None
        def_id = game.monster_cup.pop(game.rng.randrange(len(game.monster_cup)))
    elif not content.monsters[def_id].epic:
        if def_id not in game.monster_cup:
            return None
        game.monster_cup.remove(def_id)
    monster = MonsterInst(game.uid(), def_id)
    game.locations[loc_id].monsters.append(monster)
    mdef = content.monsters[def_id]
    emit(game, "monster", f"{mdef.name} appears at {loc_name(game, loc_id)}.", monster=def_id, location=loc_id)
    return monster


def toughness(game: Game, def_id: str) -> int:
    """A monster's full Health. Epic monsters grow with the number of investigators."""
    mdef = game.content.monsters[def_id]
    return mdef.toughness + mdef.toughness_per_investigator * len(game.investigators)


def defeat_monster(game: Game, inv: Investigator, loc_id: str, monster: MonsterInst) -> None:
    mdef = game.content.monsters[monster.def_id]
    state = game.locations[loc_id]
    if monster in state.monsters:
        state.monsters.remove(monster)
    if not mdef.epic:
        game.monster_cup.append(monster.def_id)
    game.bump("monsters_defeated")
    emit(game, "combat", f"{inv.name} defeats the {mdef.name}!", monster=mdef.id, defeated=True)
    run_effects(mdef.on_defeat, Ctx(game, inv, f"monster:{mdef.id}"))
    for rite in game.active_rites():
        rdef = game.rite_def(rite)
        if rdef.kind == "defeat" and rdef.monster == mdef.id and not rite.done:
            add_rite_progress(game, rite, rite.required - rite.progress)


def move_monsters(game: Game) -> None:
    """Each roaming monster steps one space toward the nearest investigator."""
    targets = {i.location for i in game.active_investigators() if not i.defeated}
    if not targets:
        return
    moves: list[tuple[str, str, MonsterInst]] = []
    for loc, monster in list(game.all_monsters()):
        if not game.content.monsters[monster.def_id].roams or loc in targets:
            continue
        dist = distances(game, loc)
        reachable = [t for t in targets if t in dist]
        if not reachable:
            continue
        goal = min(reachable, key=lambda t: (dist[t], t))
        step = _next_step(game, loc, goal)
        if step:
            moves.append((loc, step, monster))
    for src, dst, monster in moves:
        game.locations[src].monsters.remove(monster)
        game.locations[dst].monsters.append(monster)
        name = game.content.monsters[monster.def_id].name
        emit(game, "monster", f"The {name} moves from {loc_name(game, src)} to {loc_name(game, dst)}.")


def _next_step(game: Game, src: str, goal: str) -> str | None:
    back = distances(game, goal)
    options = [n for n, _ in neighbors(game, src) if back.get(n, 99) < back.get(src, 99)]
    return min(options) if options else None


def heal_monsters(game: Game) -> None:
    healed = 0
    for _loc, monster in game.all_monsters():
        if monster.wounds:
            monster.wounds = 0
            healed += 1
    if healed:
        emit(game, "monster", "Every wounded monster recovers.")


def spawn_clue(game: Game) -> None:
    for _ in range(len(game.clue_deck)):
        loc_id = game.clue_deck.draw(game.rng)
        if loc_id is None:
            return
        game.clue_deck.discard(loc_id)
        state = game.locations[loc_id]
        if not state.clue:
            state.clue = True
            emit(game, "clue", f"A clue surfaces at {loc_name(game, loc_id)}.", location=loc_id)
            return


# --- assets ---------------------------------------------------------------------------


def deck_for(game: Game, kind: str) -> Deck[AssetCard]:
    if kind == "spell":
        return game.spell_deck
    if kind == "relic":
        return game.relic_deck
    return game.asset_deck


def new_card(game: Game, def_id: str) -> AssetCard:
    return AssetCard(game.uid(), def_id)


def gain_card(game: Game, inv: Investigator, card: AssetCard) -> None:
    adef = game.asset_def(card)
    if adef.kind == "service":
        emit(game, "gain", f"{inv.name} uses the service: {adef.name}.", asset=adef.id)
        run_effects(adef.on_gain, Ctx(game, inv, f"asset:{adef.id}"))
        deck_for(game, adef.kind).discard(card)
        return
    inv.assets.append(card)
    emit(game, "gain", f"{inv.name} gains {adef.name}.", asset=adef.id)
    run_effects(adef.on_gain, Ctx(game, inv, f"asset:{adef.id}"))


def draw_matching(
    game: Game, *, asset_id: str | None = None, kind: str | None = None, trait: str | None = None
) -> AssetCard | None:
    content = game.content

    def match(card: AssetCard) -> bool:
        adef = content.assets[card.def_id]
        return (
            (asset_id is None or adef.id == asset_id)
            and (kind is None or adef.kind == kind)
            and (trait is None or trait in adef.traits)
        )

    if asset_id is not None:
        kind_of = content.assets[asset_id].kind
        decks = [deck_for(game, kind_of)]
    elif kind is not None:
        decks = [deck_for(game, kind)]
    else:
        decks = [game.asset_deck]
    for deck in decks:
        # Shuffle first so a filtered draw is random, not always the same card.
        game.rng.shuffle(deck.cards)
        card = deck.draw_where(game.rng, match)
        if card is not None:
            return card
    return None


def refill_market(game: Game) -> None:
    size = game.content.rules.market_size
    while len(game.market) < size:
        card = game.asset_deck.draw(game.rng)
        if card is None:
            return
        game.market.append(card)


def rotate_market(game: Game) -> None:
    if game.market:
        game.asset_deck.discard(game.market.pop(0))
    refill_market(game)


def discard_asset(game: Game, inv: Investigator, card: AssetCard) -> None:
    if card in inv.assets:
        inv.assets.remove(card)
    card.exhausted = False
    adef = game.asset_def(card)
    deck_for(game, adef.kind).discard(card)
    emit(game, "loss", f"{inv.name} discards {adef.name}.", asset=adef.id)


def market_price(game: Game, inv: Investigator, card: AssetCard) -> int:
    return max(0, game.asset_def(card).cost - perk(game, inv, "market_discount"))


def is_market_kind(kind: str) -> bool:
    return kind in MARKET_KINDS


# --- conditions -----------------------------------------------------------------------


def has_condition(inv: Investigator, cond_id: str) -> bool:
    return any(c.def_id == cond_id for c in inv.conditions)


def gain_condition(game: Game, inv: Investigator, cond_id: str) -> bool:
    cdef = game.content.conditions[cond_id]
    if has_condition(inv, cond_id):
        emit(game, "condition", f"{inv.name} already suffers from {cdef.name}.")
        return False
    inv.conditions.append(ConditionInst(game.uid(), cond_id))
    emit(game, "condition", f"{inv.name} gains the condition {cdef.name}: {cdef.text}", condition=cond_id)
    return True


def remove_condition(game: Game, inv: Investigator, inst: ConditionInst) -> None:
    if inst in inv.conditions:
        inv.conditions.remove(inst)
        cdef = game.content.conditions[inst.def_id]
        emit(game, "condition", f"{inv.name} is free of {cdef.name}.", condition=cdef.id, removed=True)


def resolve_condition(game: Game, inv: Investigator, inst: ConditionInst) -> None:
    cdef = game.content.conditions[inst.def_id]
    if not cdef.outcomes or inst not in inv.conditions:
        return
    outcome = game.rng.choices(cdef.outcomes, weights=[o.weight for o in cdef.outcomes])[0]
    emit(game, "condition", f"{cdef.name} comes due for {inv.name}. {outcome.text}", condition=cdef.id)
    run_effects(outcome.effects, Ctx(game, inv, f"condition:{cdef.id}", condition=inst))


def trigger_conditions(game: Game, inv: Investigator, when: str) -> None:
    for inst in list(inv.conditions):
        if inv.defeated or game.outcome:
            return
        cdef = game.content.conditions[inst.def_id]
        if cdef.trigger != when:
            continue
        if when == "night" and game.roll_die() > cdef.chance:
            continue
        resolve_condition(game, inv, inst)


def blocked(game: Game, inv: Investigator, action: str) -> str | None:
    for inst in inv.conditions:
        cdef = game.content.conditions[inst.def_id]
        if action in cdef.blocks:
            return cdef.name
    return None


# --- perks ----------------------------------------------------------------------------


def perk(game: Game, inv: Investigator, name: str) -> int:
    content = game.content
    total = content.investigators[inv.def_id].perks.get(name, 0)
    for card in inv.assets:
        total += content.assets[card.def_id].perks.get(name, 0)
    return total


def move_investigator(game: Game, inv: Investigator, loc_id: str, how: str = "") -> None:
    if inv.location == loc_id:
        return
    inv.location = loc_id
    suffix = f" by {how}" if how else ""
    emit(game, "travel", f"{inv.name} travels{suffix} to {loc_name(game, loc_id)}.", location=loc_id)


def pay_cost(game: Game, inv: Investigator, cost: Cost) -> None:
    if cost.funds:
        change_funds(game, inv, -cost.funds)
    if cost.clues:
        change_clues(game, inv, -cost.clues)
    if cost.trophies:
        inv.trophies -= cost.trophies
        emit(game, "loss", f"{inv.name} spends {cost.trophies} Trophy.", stat="trophies")
    if cost.sanity:
        change_sanity(game, inv, -cost.sanity)
    if cost.health:
        change_health(game, inv, -cost.health)
