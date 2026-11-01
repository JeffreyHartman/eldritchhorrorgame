"""Rule operations that change the game state. Effects, actions, and phases call these."""

from __future__ import annotations

from collections import deque
from typing import Any

from pursuit.content.defs import OMEN_TRACK, RESERVE_KINDS, CardBack, Cost
from pursuit.controller import Event, Option
from pursuit.effects.base import Ctx, run_effects
from pursuit.engine.state import (
    ActiveMythos,
    AssetCard,
    ConditionInst,
    Deck,
    FallenInvestigator,
    Game,
    Investigator,
    MonsterInst,
    MysteryState,
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


def nearest_city(game: Game, loc_id: str) -> str:
    dist = distances(game, loc_id)
    cities = [loc for loc in dist if game.content.locations[loc].terrain == "city"]
    return min(cities, key=lambda loc: (dist[loc], loc)) if cities else loc_id


def random_space(game: Game) -> str:
    loc_id = game.clue_deck.draw(game.rng)
    if loc_id is not None:
        game.clue_deck.discard(loc_id)
        return loc_id
    return game.rng.choice(sorted(game.locations))


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


# --- health, sanity, clues, tickets, and defeat ---------------------------------------


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


def change_clues(game: Game, inv: Investigator, amount: int) -> None:
    before = inv.clues
    inv.clues = max(0, inv.clues + amount)
    delta = inv.clues - before
    if delta > 0:
        emit(game, "gain", f"{inv.name} gains {delta} Clue{'s' if delta > 1 else ''}.", stat="clues")
        game.bump("clues_gained", delta)
    elif delta < 0:
        emit(game, "loss", f"{inv.name} discards {-delta} Clue{'s' if delta < -1 else ''}.", stat="clues")


def gain_ticket(game: Game, inv: Investigator, kind: str) -> None:
    inv.tickets.append(kind)
    emit(game, "gain", f"{inv.name} gains a {kind.title()} Ticket.", stat="tickets")
    enforce_ticket_limit(game, inv)


def enforce_ticket_limit(game: Game, inv: Investigator) -> None:
    limit = game.content.rules.max_tickets
    while len(inv.tickets) > limit:
        options = [Option(f"Discard {t.title()} Ticket", i) for i, t in enumerate(inv.tickets)]
        pick = choose(
            game,
            f"You may hold at most {limit} travel tickets. Discard which one?",
            options,
            kind="discard_ticket",
            inv=inv,
            auto_single=len(set(inv.tickets)) == 1,
        )
        dropped = inv.tickets.pop(pick)
        emit(game, "loss", f"{inv.name} discards a {dropped.title()} Ticket.")


def mark_defeated(game: Game, inv: Investigator, cause: str) -> None:
    if inv.defeated:
        return
    inv.defeated = True
    inv.defeated_awake = game.awakened
    emit(game, "defeat", f"{inv.name} is defeated ({cause})!", investigator=inv.name, cause=cause)


def devour_investigator(game: Game, inv: Investigator) -> None:
    if inv.defeated:
        return
    inv.defeated = True
    inv.defeated_awake = game.awakened
    inv.devoured = True
    emit(game, "defeat", f"{inv.name} is devoured!", investigator=inv.name, cause="devoured")


def process_defeats(game: Game) -> None:
    """Resolve steps 1-4 of Defeated Investigators immediately.

    Replacements are chosen at the end of the Mythos Phase. An investigator defeated after
    the awakening is eliminated, and one whose defeat causes the awakening is not.
    """
    for inv in game.investigators:
        if not inv.defeated or inv.eliminated or game.outcome:
            continue
        if inv.actions_taken == ["defeated_resolved"]:
            continue
        inv.actions_taken = ["defeated_resolved"]
        game.bump("investigators_lost")

        # Step 1: Advance Doom by 1
        advance_doom(game, game.content.rules.defeat_doom, f"the defeat of {inv.name}")
        if game.outcome:
            return

        if inv.devoured:
            for card in list(inv.assets):
                discard_asset(game, inv, card)
            inv.assets = []
            inv.conditions = []
            inv.clues = 0
            inv.tickets = []
        else:
            # Step 2 & 3: Move token to nearest City space and leave possessions on sheet
            city = nearest_city(game, inv.location)
            cause = "health" if inv.health == 0 else "sanity"
            for card in inv.assets:
                card.exhausted = False
            fallen = FallenInvestigator(
                def_id=inv.def_id,
                name=inv.name,
                cause=cause,
                clues=inv.clues,
                tickets=list(inv.tickets),
                assets=list(inv.assets),
            )
            game.locations[city].fallen.append(fallen)
            inv.assets = []
            inv.conditions = []
            inv.clues = 0
            inv.tickets = []
            emit(
                game,
                "defeat",
                f"{inv.name} is relocated to {loc_name(game, city)} ({'Crippled' if cause == 'health' else 'Insane'}).",
                location=city,
            )

        # Step 4: Pass Lead Investigator if needed
        if game.lead_seat == inv.seat:
            others = [o for o in game.investigators if not o.defeated and not o.eliminated]
            if others:
                options = [Option(o.name, o.seat, loc_name(game, o.location)) for o in others]
                pick = choose(
                    game,
                    "Choose the new Lead Investigator.",
                    options,
                    kind="lead_investigator",
                    auto_single=True,
                )
                game.lead_seat = others[pick].seat

        if inv.defeated_awake or not game.unused_investigators:
            inv.eliminated = True
            emit(game, "defeat", f"{inv.name} is eliminated from the game.")
            if not game.active_investigators():
                lose(game, "Every investigator has been eliminated. Humanity is doomed.")
                return


def replace_defeated_investigators(game: Game) -> None:
    """At the end of the Mythos Phase, replace any defeated investigators."""
    from pursuit.engine.setup import create_investigator

    for idx, inv in enumerate(game.investigators):
        if not inv.defeated or inv.eliminated or game.outcome:
            continue
        if inv.defeated_awake or not game.unused_investigators:
            inv.eliminated = True
            if not game.active_investigators():
                lose(game, "Every investigator has been eliminated. Humanity is doomed.")
                return
            continue
        defs = [game.content.investigators[i] for i in game.unused_investigators]
        options = [Option(d.name, d.id, f"{d.occupation}, starts in {loc_name(game, d.start)}") for d in defs]
        pick = choose(game, f"Choose a new investigator to replace {inv.name}.", options, kind="replacement")
        def_id = defs[pick].id
        game.unused_investigators.remove(def_id)
        new = create_investigator(game, def_id, inv.seat)
        game.investigators[idx] = new
        emit(game, "turn", f"{new.name} joins the investigation at {loc_name(game, new.location)}.")


# --- omen, doom, awakening ------------------------------------------------------------


def advance_omen(game: Game, amount: int = 1, *, advance_doom_from_gates: bool = True) -> None:
    for _ in range(amount):
        if game.outcome:
            return
        game.omen_index = (game.omen_index + 1) % len(OMEN_TRACK)
        color = game.omen_color
        emit(game, "omen", f"The Omen advances to {color} ({game.omen_space}).", omen=game.omen_space, color=color)
        if advance_doom_from_gates:
            matching = len(game.matching_gates())
            if matching:
                advance_doom(game, matching, f"{matching} {color} Gate(s) match the Omen")
        if game.old_one.omen_green_eldritch_doom and game.omen_space == "green" and game.green_eldritch > 0:
            advance_doom(game, game.green_eldritch, f"{game.green_eldritch} Eldritch token(s) on the green Omen")


def advance_doom(game: Game, amount: int, reason: str = "") -> None:
    if amount <= 0 or game.outcome:
        return
    why = f" ({reason})" if reason else ""
    if game.awakened:
        old = game.old_one
        for _ in range(amount):
            if game.outcome:
                return
            emit(game, "doom", f"Doom would advance{why}.", value=0)
            if old.awakening.doom_advance_effects:
                run_effects(old.awakening.doom_advance_effects, Ctx(game, None, f"awakened_doom:{old.id}"))
        return
    game.doom = max(0, game.doom - amount)
    emit(game, "doom", f"Doom advances by {amount}{why}. Doom: {game.doom}.", value=game.doom)
    if game.doom == 0:
        awaken(game)


def retreat_doom(game: Game, amount: int) -> None:
    if amount <= 0 or game.outcome or game.awakened:
        return
    game.doom = min(20, game.doom + amount)
    emit(game, "doom", f"Doom retreats by {amount}. Doom: {game.doom}.", value=game.doom)


def awaken(game: Game) -> None:
    if game.awakened:
        return
    old = game.old_one
    game.awakened = True
    emit(game, "awaken", old.awakening.text, old_one=old.id)
    if old.awakening.lose_immediately:
        lose(game, old.awakening.text)
        return
    final = old.awakening.final_mystery
    if final is not None:
        n = len(game.investigators)
        game.final_mystery = MysteryState(final.id, final.required(n), final=True)
        if final.kind == "defeat" and final.monster:
            _spawn_mystery_monster(game, final.monster, final.spawn_at)
        run_effects(final.on_enter, Ctx(game, None, f"mystery:{final.id}"))
    run_effects(old.awakening.effects, Ctx(game, None, f"awakening:{old.id}"))
    check_mysteries(game)


# --- mysteries ------------------------------------------------------------------------


def _spawn_mystery_monster(game: Game, monster_id: str, spawn_at: str | None) -> None:
    if spawn_at == "random" or spawn_at is None:
        loc = random_space(game)
    elif spawn_at in game.locations:
        loc = spawn_at
    else:
        loc = random_space(game)
    spawn_monster(game, loc, monster_id)


def draw_mystery(game: Game) -> None:
    if game.active_mystery is not None and not game.active_mystery.done:
        return
    if not game.mystery_deck:
        return
    mys_id = game.mystery_deck.pop(0)
    mdef = next(m for m in game.old_one.mysteries if m.id == mys_id)
    n = len(game.investigators)
    game.active_mystery = MysteryState(mdef.id, mdef.required(n))
    emit(game, "mystery", f"New Mystery: {mdef.name}. {mdef.text}", mystery=mdef.id)
    if mdef.kind == "defeat" and mdef.monster:
        _spawn_mystery_monster(game, mdef.monster, mdef.spawn_at)
    run_effects(mdef.on_enter, Ctx(game, None, f"mystery:{mdef.id}"))


def add_mystery_progress(game: Game, mys: MysteryState, amount: int) -> None:
    if amount <= 0 or mys.done or game.outcome:
        return
    mys.progress = min(mys.required, mys.progress + amount)
    mdef = game.mystery_def(mys)
    emit(game, "mystery", f"'{mdef.name}': {mys.progress}/{mys.required}.", mystery=mdef.id, done=False)
    if mys.final and mys.ready:
        solve_mystery(game, mys)


def solve_mystery(game: Game, mys: MysteryState) -> None:
    mys.solved = True
    mdef = game.mystery_def(mys)
    if not mys.final:
        game.solved_mysteries.append(mys.def_id)
        game.bump("mysteries_solved")
    emit(game, "mystery", f"The Mystery '{mdef.name}' is solved!", mystery=mdef.id, done=True)
    check_mysteries(game)
    if not game.outcome and not mys.final and len(game.solved_mysteries) < game.old_one.mysteries_needed:
        draw_mystery(game)


def solve_ready_mystery(game: Game) -> None:
    """Every Core Game Mystery card solves at the end of the Mythos Phase."""
    mys = game.active_mystery
    if mys is not None and not mys.done and mys.ready:
        solve_mystery(game, mys)


def check_mysteries(game: Game) -> None:
    if game.outcome:
        return
    enough = len(game.solved_mysteries) >= game.old_one.mysteries_needed
    if game.awakened:
        if enough and game.final_mystery and game.final_mystery.done:
            win(game, f"The Final Mystery is solved! {game.old_one.name} is banished from this world.")
    elif enough:
        win(game, f"{game.old_one.mysteries_needed} Mysteries are solved! {game.old_one.name} is banished.")


# --- gates, monsters, clues, expeditions ----------------------------------------------


def spawn_gate(game: Game, loc_id: str | None = None) -> str | None:
    if loc_id is None:
        for _ in range(len(game.gate_deck)):
            drawn = game.gate_deck.draw(game.rng)
            if drawn is None:
                return None
            if not game.locations[drawn].gate:
                loc_id = drawn
                break
            game.gate_deck.discard(drawn)
        if loc_id is None:
            return None
    state = game.locations[loc_id]
    if state.gate:
        return loc_id
    state.gate = True
    state.other_world = game.other_world_deck.draw(game.rng)
    if state.other_world is None and game.content.other_worlds:
        state.other_world = game.rng.choice(list(game.content.other_worlds))
    game.bump("gates_spawned")
    color = game.content.locations[loc_id].gate_color or "red"
    emit(game, "gate", f"A {color} Gate opens at {loc_name(game, loc_id)}!", location=loc_id, color=color)
    spawn_monster(game, loc_id)
    return loc_id


def discard_gate(game: Game, loc_id: str) -> bool:
    state = game.locations[loc_id]
    if not state.gate:
        return False
    state.gate = False
    if state.other_world is not None:
        game.other_world_deck.discard(state.other_world)
        state.other_world = None
    game.gate_deck.discard(loc_id)
    return True


def close_gate(game: Game, inv: Investigator, loc_id: str) -> None:
    state = game.locations[loc_id]
    if not state.gate:
        return
    discard_gate(game, loc_id)
    game.bump("gates_closed")
    emit(game, "gate", f"{inv.name} closes the Gate at {loc_name(game, loc_id)}!", location=loc_id, closed=True)

    for mys in game.active_mysteries():
        mdef = game.mystery_def(mys)
        if mdef.kind == "gate" and not mys.done and (mdef.where is None or mdef.where.matches(game, loc_id)):
            if mdef.clue_cost > 0:
                if inv.clues >= mdef.clue_cost and confirm(
                    game,
                    f"Spend {mdef.clue_cost} Clue(s) to advance '{mdef.name}'?",
                    kind="mystery_spend",
                    inv=inv,
                ):
                    change_clues(game, inv, -mdef.clue_cost)
                    add_mystery_progress(game, mys, 1)
            else:
                add_mystery_progress(game, mys, 1)

    if inv.def_id == "akachi_onyele":
        targets = [
            loc
            for loc, st in game.locations.items()
            if loc != inv.location and (st.gate or st.clue)
        ]
        if targets:
            options = [Option(loc_name(game, t), t) for t in targets] + [Option("Stay here", None)]
            pick = choose(
                game,
                "Akachi's gift: move to a space with a Gate or Clue?",
                options,
                kind="move",
                inv=inv,
            )
            dest = options[pick].value
            if dest:
                move_investigator(game, inv, dest)


def monster_surge(game: Game) -> None:
    matching = game.matching_gates()
    if not matching:
        emit(game, "monster", "No Gate matches the current Omen; a new Gate spawns instead.")
        spawn_gate(game)
        return
    count = game.reference.monster_surge
    emit(game, "monster", f"Monster Surge! {count} Monster(s) spawn at each {game.omen_color} Gate.")
    for loc_id in matching:
        for _ in range(count):
            spawn_monster(game, loc_id)


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
    emit(game, "monster", f"{mdef.name} spawns at {loc_name(game, loc_id)}.", monster=def_id, location=loc_id)
    if mdef.on_spawn:
        run_effects(mdef.on_spawn, Ctx(game, None, f"monster_spawn:{mdef.id}"))
    return monster


def toughness(game: Game, def_id: str) -> int:
    """A monster's full Health. Epic monsters can scale with investigator count."""
    if def_id == "cultist":
        return game.old_one.cultist_toughness
    mdef = game.content.monsters[def_id]
    return mdef.toughness + mdef.toughness_per_investigator * len(game.investigators)


def defeat_monster(game: Game, inv: Investigator | None, loc_id: str, monster: MonsterInst) -> None:
    mdef = game.content.monsters[monster.def_id]
    state = game.locations[loc_id]
    if monster in state.monsters:
        state.monsters.remove(monster)
    if not mdef.epic:
        game.monster_cup.append(monster.def_id)
    game.bump("monsters_defeated")
    who = f"{inv.name} defeats" if inv else "Defeated"
    emit(game, "combat", f"{who} the {mdef.name}!", monster=mdef.id, defeated=True)
    if inv is not None:
        effects = game.old_one.cultist_on_defeat if mdef.id == "cultist" else mdef.on_defeat
        if effects and not (mdef.id == "cultist" and game.old_one.id == "azathoth"):
            run_effects(effects, Ctx(game, inv, f"monster:{mdef.id}"))
    for mys in game.active_mysteries():
        mys_def = game.mystery_def(mys)
        if mys_def.kind == "defeat" and mys_def.monster == mdef.id and not mys.done:
            add_mystery_progress(game, mys, mys.required - mys.progress)
        elif mys_def.kind == "combat" and not mys.done:
            add_mystery_progress(game, mys, 1)


def discard_monster(game: Game, loc_id: str, monster: MonsterInst) -> None:
    """Remove a Monster without resolving defeat effects or Mystery progress."""
    state = game.locations[loc_id]
    if monster in state.monsters:
        state.monsters.remove(monster)
    mdef = game.content.monsters[monster.def_id]
    if not mdef.epic:
        game.monster_cup.append(monster.def_id)
    game.bump("monsters_discarded")
    emit(game, "monster", f"The {mdef.name} is discarded.", monster=mdef.id, location=loc_id)


def move_monsters(game: Game, monster_id: str | None = None, toward: str = "investigator") -> None:
    """Move roaming (or specified) monsters 1 space toward their target."""
    if toward == "investigator":
        targets = {i.location for i in game.active_investigators() if not i.defeated}
    else:
        targets = {loc for loc, m in game.all_monsters() if m.def_id == toward}
    if not targets:
        return
    moves: list[tuple[str, str, MonsterInst]] = []
    for loc, monster in list(game.all_monsters()):
        mdef = game.content.monsters[monster.def_id]
        if monster_id is not None:
            if monster.def_id != monster_id:
                continue
        elif not mdef.roams:
            continue
        if loc in targets:
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
        if monster in game.locations[src].monsters:
            game.locations[src].monsters.remove(monster)
            game.locations[dst].monsters.append(monster)
            name = game.content.monsters[monster.def_id].name
            emit(game, "monster", f"The {name} moves from {loc_name(game, src)} to {loc_name(game, dst)}.")


def _next_step(game: Game, src: str, goal: str) -> str | None:
    back = distances(game, goal)
    options = [n for n, _ in neighbors(game, src) if back.get(n, 99) < back.get(src, 99)]
    return min(options) if options else None


def heal_monsters(game: Game, amount: int = 99) -> None:
    healed = 0
    for _loc, monster in game.all_monsters():
        if monster.wounds:
            monster.wounds = max(0, monster.wounds - amount)
            healed += 1
    if healed:
        emit(game, "monster", "Monsters recover Health.")


def spawn_clue(game: Game) -> str | None:
    for _ in range(len(game.clue_deck)):
        loc_id = game.clue_deck.draw(game.rng)
        if loc_id is None:
            return None
        game.clue_deck.discard(loc_id)
        state = game.locations[loc_id]
        if not state.clue:
            state.clue = True
            emit(game, "clue", f"A Clue spawns at {loc_name(game, loc_id)}.", location=loc_id)
            return loc_id
    return None


def update_expedition(game: Game) -> None:
    deck = game.encounter_decks.get("expedition")
    if not deck:
        game.active_expedition = None
        return
    if not deck.cards and deck.discards:
        deck.cards = deck.discards
        deck.discards = []
        game.rng.shuffle(deck.cards)
    if deck.cards:
        top = game.content.encounters[deck.cards[0]]
        game.active_expedition = top.location
    else:
        game.active_expedition = None


# --- assets, spells, artifacts --------------------------------------------------------


def deck_for(game: Game, kind: str) -> Deck[AssetCard]:
    if kind == "spell":
        return game.spell_deck
    if kind == "artifact":
        return game.artifact_deck
    return game.asset_deck


def new_card(game: Game, def_id: str) -> AssetCard:
    return AssetCard(game.uid(), def_id)


def take_starting_card(game: Game, def_id: str) -> AssetCard:
    adef = game.content.assets[def_id]
    deck = deck_for(game, adef.kind)
    found = deck.draw_where(game.rng, lambda c: c.def_id == def_id)
    return found if found is not None else new_card(game, def_id)


def gain_card(game: Game, inv: Investigator, card: AssetCard) -> None:
    adef = game.asset_def(card)
    if adef.kind == "service" and adef.on_gain and adef.action is None:
        emit(game, "gain", f"{inv.name} uses the service: {adef.name}.", asset=adef.id)
        run_effects(adef.on_gain, Ctx(game, inv, f"asset:{adef.id}"))
        deck_for(game, adef.kind).discard(card)
        return
    if adef.kind == "spell" and any(c.def_id == adef.id for c in inv.assets):
        emit(game, "info", f"{inv.name} already has {adef.name}.")
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
        game.rng.shuffle(deck.cards)
        card = deck.draw_where(game.rng, match)
        if card is not None:
            return card
    return None


def refill_reserve(game: Game) -> None:
    size = game.content.rules.reserve_size
    while len(game.reserve) < size:
        card = game.asset_deck.draw(game.rng)
        if card is None:
            return
        game.reserve.append(card)


def discard_asset(game: Game, inv: Investigator, card: AssetCard) -> None:
    if card in inv.assets:
        inv.assets.remove(card)
    card.exhausted = False
    adef = game.asset_def(card)
    deck_for(game, adef.kind).discard(card)
    emit(game, "loss", f"{inv.name} discards {adef.name}.", asset=adef.id)


def is_reserve_kind(kind: str) -> bool:
    return kind in RESERVE_KINDS


def _pick_back(game: Game, backs: tuple[CardBack, ...], successes: int | None = None) -> CardBack:
    matching = [
        b
        for b in backs
        if (b.min_successes is None or (successes is not None and successes >= b.min_successes))
        and (b.max_successes is None or (successes is not None and successes <= b.max_successes))
    ]
    pool = matching or list(backs)
    return game.rng.choices(pool, weights=[b.weight for b in pool])[0]


def flip_asset(game: Game, inv: Investigator, card: AssetCard, successes: int | None = None) -> None:
    adef = game.asset_def(card)
    if not adef.backs:
        return
    back = _pick_back(game, adef.backs, successes)
    emit(game, "info", f"{inv.name} flips {adef.name}: {back.text}")
    run_effects(back.effects, Ctx(game, inv, f"asset_back:{adef.id}", asset=card))


# --- conditions -----------------------------------------------------------------------


def has_condition(inv: Investigator, cond_id: str) -> bool:
    return any(c.def_id == cond_id for c in inv.conditions)


def gain_condition(game: Game, inv: Investigator, cond_id: str) -> bool:
    if cond_id == "blessed" and has_condition(inv, "cursed"):
        for inst in list(inv.conditions):
            if inst.def_id == "cursed":
                remove_condition(game, inv, inst)
        return False
    if cond_id == "cursed" and has_condition(inv, "blessed"):
        for inst in list(inv.conditions):
            if inst.def_id == "blessed":
                remove_condition(game, inv, inst)
        return False
    cdef = game.content.conditions[cond_id]
    if has_condition(inv, cond_id):
        emit(game, "condition", f"{inv.name} already has {cdef.name}.")
        return False
    inv.conditions.append(ConditionInst(game.uid(), cond_id))
    emit(game, "condition", f"{inv.name} gains {cdef.name} ({', '.join(cdef.traits)}): {cdef.text}", condition=cond_id)
    return True


def remove_condition(game: Game, inv: Investigator, inst: ConditionInst) -> None:
    if inst in inv.conditions:
        inv.conditions.remove(inst)
        cdef = game.content.conditions[inst.def_id]
        emit(game, "condition", f"{inv.name} discards {cdef.name}.", condition=cdef.id, removed=True)


def flip_condition(game: Game, inv: Investigator, inst: ConditionInst, successes: int | None = None) -> None:
    cdef = game.content.conditions[inst.def_id]
    if not cdef.backs or inst not in inv.conditions:
        return
    back = _pick_back(game, cdef.backs, successes)
    emit(game, "condition", f"{inv.name} flips {cdef.name}: {back.text}", condition=cdef.id)
    run_effects(back.effects, Ctx(game, inv, f"condition:{cdef.id}", condition=inst))
    if inst in inv.conditions:
        remove_condition(game, inv, inst)


def blocked(game: Game, inv: Investigator, action: str) -> str | None:
    for inst in inv.conditions:
        cdef = game.content.conditions[inst.def_id]
        if action in cdef.blocks:
            return cdef.name
    return None


# --- reckoning ------------------------------------------------------------------------


def resolve_reckoning(game: Game) -> None:
    """Resolve Reckoning effects in rulebook order:
    1. Monsters
    2. Ancient One sheet
    3. Ongoing Mythos cards
    4. Investigator possessions and Conditions
    """
    emit(game, "reckoning", "Reckoning effects resolve!")

    # 1. Monsters
    for _loc, monster in list(game.all_monsters()):
        if game.outcome:
            return
        if monster.def_id == "cultist":
            effects = game.old_one.cultist_reckoning
        else:
            effects = game.content.monsters[monster.def_id].reckoning
        if effects:
            run_effects(effects, Ctx(game, None, f"reckoning_monster:{monster.def_id}"))
            process_defeats(game)

    # 2. Ancient One sheet
    if not game.outcome:
        ao_effects = game.old_one.awakening.reckoning if game.awakened else game.old_one.reckoning
        if ao_effects:
            run_effects(ao_effects, Ctx(game, None, f"reckoning_ao:{game.old_one_id}"))
            process_defeats(game)

    # 3. Ongoing Mythos cards
    for active in list(game.active_mythos):
        if game.outcome:
            return
        mdef = game.content.mythos[active.def_id]
        if mdef.reckoning:
            run_effects(mdef.reckoning, Ctx(game, None, f"reckoning_mythos:{mdef.id}", mythos=active))
            process_defeats(game)

    # 4. Investigator possessions and Conditions (in turn order starting from Lead)
    for inv in game.turn_order():
        if game.outcome:
            return
        if inv.defeated or inv.eliminated:
            continue
        for card in list(inv.assets):
            if inv.defeated or game.outcome:
                break
            adef = game.asset_def(card)
            if adef.reckoning:
                run_effects(adef.reckoning, Ctx(game, inv, f"reckoning_asset:{adef.id}", asset=card))
        for inst in list(inv.conditions):
            if inv.defeated or game.outcome:
                break
            cdef = game.content.conditions[inst.def_id]
            if cdef.reckoning:
                run_effects(cdef.reckoning, Ctx(game, inv, f"reckoning_condition:{cdef.id}", condition=inst))
        process_defeats(game)


def solve_rumor(game: Game, active: ActiveMythos, *, solved: bool = True) -> None:
    if active in game.active_mythos:
        game.active_mythos.remove(active)
        game.mythos_discards.append(active.def_id)
        mdef = game.content.mythos[active.def_id]
        word = "solved" if solved else "discarded"
        emit(game, "mythos", f"Rumor '{mdef.name}' is {word}!")


# --- perks, movement, costs -----------------------------------------------------------


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
    emit(game, "travel", f"{inv.name} moves{suffix} to {loc_name(game, loc_id)}.", location=loc_id)


def pay_cost(game: Game, inv: Investigator, cost: Cost) -> None:
    if cost.clues:
        change_clues(game, inv, -cost.clues)
    if cost.tickets:
        for _ in range(min(cost.tickets, len(inv.tickets))):
            inv.tickets.pop(0)
        emit(game, "loss", f"{inv.name} spends {cost.tickets} Ticket(s).", stat="tickets")
    if cost.sanity:
        change_sanity(game, inv, -cost.sanity)
    if cost.health:
        change_health(game, inv, -cost.health)

