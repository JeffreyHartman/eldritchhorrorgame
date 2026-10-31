"""The round loop: Day (actions), Encounters, then Night (doom, a portent, conditions).

Each phase reads `game.phase` and `game.turn_index`, so a game loaded from a save resumes
at the same investigator's Day turn.
"""

from __future__ import annotations

from pursuit.controller import Option
from pursuit.effects.base import Ctx, run_effects
from pursuit.engine import actions, combat, rules
from pursuit.engine.state import Game, Investigator, Phase


def play(game: Game) -> str:
    """Run the game to the end. Returns 'win' or 'loss'."""
    while game.outcome is None:
        step(game)
    return game.outcome


def step(game: Game) -> None:
    if game.phase == Phase.DAY:
        day_phase(game)
    elif game.phase == Phase.ENCOUNTER:
        encounter_phase(game)
    else:
        night_phase(game)


def day_phase(game: Game) -> None:
    if game.turn_index == 0:
        rules.emit(game, "phase", f"Round {game.round}: Day", phase="day", round=game.round)
    while game.turn_index < len(game.investigators):
        inv = game.investigators[game.turn_index]
        if not inv.eliminated and not inv.defeated:
            game.ctl.checkpoint(game)
            day_turn(game, inv)
            rules.process_defeats(game)
            if game.outcome:
                return
        game.turn_index += 1
    game.phase = Phase.ENCOUNTER
    game.turn_index = 0


def day_turn(game: Game, inv: Investigator) -> None:
    rules.emit(game, "turn", f"{inv.name}'s Day turn.", investigator=inv.name, phase="day")
    if inv.delayed:
        inv.delayed = False
        inv.actions_taken = ["delayed"] * game.content.rules.actions_per_turn
        rules.emit(game, "info", f"{inv.name} is delayed and loses this turn's actions.")
    while not game.outcome and not inv.defeated:
        options = actions.day_options(game, inv)
        pick = rules.choose(game, f"{inv.name}, choose an action.", options, kind="action", inv=inv)
        value = options[pick].value
        if value[0] == "end":
            return
        actions.perform(game, inv, value)


def encounter_phase(game: Game) -> None:
    if game.turn_index == 0:
        rules.emit(game, "phase", f"Round {game.round}: Encounters", phase="encounter", round=game.round)
    while game.turn_index < len(game.investigators):
        inv = game.investigators[game.turn_index]
        if not inv.eliminated and not inv.defeated:
            encounter_turn(game, inv)
            rules.process_defeats(game)
            if game.outcome:
                return
        game.turn_index += 1
    game.phase = Phase.NIGHT
    game.turn_index = 0


def encounter_turn(game: Game, inv: Investigator) -> None:
    rules.emit(game, "turn", f"{inv.name}'s encounter.", investigator=inv.name, phase="encounter")
    if not combat.resolve_monsters(game, inv):
        return
    content = game.content
    state = game.locations[inv.location]
    ldef = content.locations[inv.location]
    deck_name = content.deck_for_location(inv.location)
    options = [Option(f"Explore {ldef.name}", deck_name, ldef.text)]
    if state.rift:
        options.append(Option("Step through the rift", "rift", "Dangerous. A success can seal the rift."))
    pick = rules.choose(game, "Choose your encounter.", options, kind="encounter", inv=inv, auto_single=True)
    deck_name = options[pick].value
    deck = game.encounter_decks[deck_name]
    enc_id = deck.draw(game.rng)
    if enc_id is None:
        return
    edef = content.encounters[enc_id]
    game.bump("encounters")
    rules.emit(game, "encounter", edef.text, title=edef.title, deck=deck_name, encounter=edef.id, location=inv.location)
    run_effects(edef.effects, Ctx(game, inv, f"encounter:{edef.id}"))
    deck.discard(enc_id)
    if not inv.defeated and not game.outcome:
        rules.trigger_conditions(game, inv, "encounter")


def night_phase(game: Game) -> None:
    old = game.old_one
    rules.emit(game, "phase", f"Round {game.round}: Night", phase="night", round=game.round)
    was_awake = game.awakened

    pressure = len(game.open_rifts()) >= old.rift_pressure
    reason = "night falls" + (", and the open rifts press on the world" if pressure else "")
    rules.advance_doom(game, game.content.rules.night_doom + (1 if pressure else 0), reason)
    if game.outcome:
        return

    portent_id = game.portent_deck.draw(game.rng)
    if portent_id is not None:
        pdef = game.content.portents[portent_id]
        tier = pdef.tier(game.dread)
        game.bump("portents")
        rules.emit(
            game,
            "portent",
            tier.text,
            title=pdef.name,
            flavor=pdef.flavor,
            portent=pdef.id,
            dread=game.dread,
        )
        run_effects(tier.effects, Ctx(game, None, f"portent:{pdef.id}"))
        game.portent_deck.discard(portent_id)
        rules.process_defeats(game)
        if game.outcome:
            return

    if game.awakened and was_awake:
        run_effects(old.awakening.night, Ctx(game, None, f"awakened:{old.id}"))
    elif not game.awakened:
        run_effects(old.night, Ctx(game, None, f"night:{old.id}"))
    rules.process_defeats(game)
    if game.outcome:
        return

    for inv in game.active_investigators():
        if not inv.defeated:
            rules.trigger_conditions(game, inv, "night")
    rules.process_defeats(game)
    if game.outcome:
        return

    rules.rotate_market(game)
    start_round(game)


def start_round(game: Game) -> None:
    game.round += 1
    game.phase = Phase.DAY
    game.turn_index = 0
    for inv in game.investigators:
        inv.actions_taken = []
        for card in inv.assets:
            card.exhausted = False
