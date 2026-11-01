"""The round loop: Action Phase, Encounter Phase, then Mythos Phase.

Each phase reads `game.phase` and `game.turn_index`, so a game loaded from a save resumes
at the same investigator's turn.
"""

from __future__ import annotations

from pursuit.content.defs import LOCATION_DECKS, EncounterDef, EncounterSection
from pursuit.controller import Option
from pursuit.effects.base import Ctx, run_effects
from pursuit.engine import actions, combat, dice, rules
from pursuit.engine.state import ActiveMythos, FallenInvestigator, Game, Investigator, MysteryState, Phase


def play(game: Game) -> str:
    """Run the game to the end. Returns 'win' or 'loss'."""
    while game.outcome is None:
        step(game)
    return game.outcome


def step(game: Game) -> None:
    if game.phase == Phase.ACTION:
        action_phase(game)
    elif game.phase == Phase.ENCOUNTER:
        encounter_phase(game)
    else:
        mythos_phase(game)


def action_phase(game: Game) -> None:
    order = game.turn_order()
    if game.turn_index == 0:
        rules.emit(game, "phase", f"Round {game.round}: Action Phase", phase="action", round=game.round)
    while game.turn_index < len(order):
        inv = order[game.turn_index]
        if not inv.eliminated and not inv.defeated:
            game.ctl.checkpoint(game)
            action_turn(game, inv)
            rules.process_defeats(game)
            if game.outcome:
                return
        game.turn_index += 1
    game.phase = Phase.ENCOUNTER
    game.turn_index = 0


# Alias for backward compatibility
day_phase = action_phase


def action_turn(game: Game, inv: Investigator) -> None:
    rules.emit(game, "turn", f"{inv.name}'s Action turn.", investigator=inv.name, phase="action")
    if inv.delayed:
        inv.delayed = False
        inv.actions_taken = ["delayed"] * game.content.rules.actions_per_turn
        rules.emit(game, "info", f"{inv.name} stands up from being Delayed and cannot perform actions this turn.")
        return
    while not game.outcome and not inv.defeated and not inv.delayed:
        options = actions.action_options(game, inv)
        pick = rules.choose(game, f"{inv.name}, choose an action.", options, kind="action", inv=inv)
        value = options[pick].value
        if value[0] == "end":
            return
        actions.perform(game, inv, value)


day_turn = action_turn


def encounter_phase(game: Game) -> None:
    order = game.turn_order()
    if game.turn_index == 0:
        rules.emit(game, "phase", f"Round {game.round}: Encounter Phase", phase="encounter", round=game.round)
    while game.turn_index < len(order):
        inv = order[game.turn_index]
        if not inv.eliminated and not inv.defeated:
            encounter_turn(game, inv)
            rules.process_defeats(game)
            if game.outcome:
                return
        game.turn_index += 1
    game.phase = Phase.MYTHOS
    game.turn_index = 0


def encounter_turn(game: Game, inv: Investigator) -> None:
    rules.emit(game, "turn", f"{inv.name}'s encounter.", investigator=inv.name, phase="encounter")
    if not combat.resolve_monsters(game, inv, encounter_phase=True):
        return
    content = game.content
    state = game.locations[inv.location]
    ldef = content.locations[inv.location]

    options: list[Option] = []
    if ldef.region in LOCATION_DECKS and ldef.terrain == "city" and not ldef.id.startswith("space_"):
        region_label = ldef.region.replace("_", "/").title()
        options.append(Option(f"{ldef.name} ({region_label} Encounter)", ("deck", ldef.region), ldef.text))
    options.append(Option(f"General ({ldef.terrain.title()}) Encounter", ("deck", "general"), ldef.text))

    if state.clue:
        options.append(
            Option("Research Encounter (Clue token)", ("research",), "Draw a Research Encounter to claim this Clue.")
        )
    if state.gate:
        options.append(
            Option("Other World Encounter (Gate token)", ("other_world",), "Step through the Gate to try to close it.")
        )
    if game.active_expedition == inv.location:
        options.append(
            Option("Expedition Encounter", ("expedition",), "Explore the Active Expedition for an Artifact or reward.")
        )
    for active in game.active_mythos:
        if active.rumor_space == inv.location:
            mdef = content.mythos[active.def_id]
            options.append(Option(f"Rumor Encounter: {mdef.name}", ("rumor", active.def_id), mdef.encounter_text))
    for mys in game.active_mysteries():
        mys_def = game.mystery_def(mys)
        if _mystery_encounter_open(game, inv, mys):
            enabled = mys_def.kind != "spend" or inv.clues >= mys_def.clue_cost
            why = mys_def.text if enabled else f"needs {mys_def.clue_cost} Clues"
            options.append(Option(f"Mystery Encounter: {mys_def.name}", ("mystery", mys.def_id), why, enabled=enabled))
    for i, fallen in enumerate(state.fallen):
        kind_label = "Crippled" if fallen.cause == "health" else "Insane"
        options.append(
            Option(
                f"Encounter {fallen.name} ({kind_label})",
                ("fallen", i),
                "Retrieve possessions and attempt to retreat Doom.",
            )
        )

    pick = rules.choose(game, "Choose your encounter.", options, kind="encounter", inv=inv, auto_single=True)
    choice = options[pick].value
    tag = choice[0]
    game.bump("encounters")

    if tag == "deck":
        _draw_and_run_encounter(game, inv, choice[1])
    elif tag == "research":
        gained_before = game.stats.get("clues_gained", 0)
        _draw_and_run_encounter(game, inv, f"research_{game.old_one_id}")
        if game.stats.get("clues_gained", 0) > gained_before and not inv.defeated:
            _offer_research_mystery(game, inv)
    elif tag == "other_world":
        other_world = state.other_world
        if other_world is None:
            other_world = game.rng.choice(list(content.other_worlds))
            state.other_world = other_world
        _draw_and_run_encounter(game, inv, f"other_world_{other_world}")
    elif tag == "expedition":
        _draw_and_run_encounter(game, inv, "expedition")
        rules.update_expedition(game)
    elif tag == "rumor":
        found_rumor = next((a for a in game.active_mythos if a.def_id == choice[1]), None)
        if found_rumor is not None:
            mdef = content.mythos[found_rumor.def_id]
            rules.emit(game, "encounter", mdef.encounter_text, title=mdef.name, deck="rumor", location=inv.location)
            run_effects(mdef.encounter_effects, Ctx(game, inv, f"rumor:{mdef.id}", mythos=found_rumor))
    elif tag == "mystery":
        found_mys = next((m for m in game.active_mysteries() if m.def_id == choice[1]), None)
        if found_mys is not None:
            _resolve_mystery_encounter(game, inv, found_mys)
    elif tag == "fallen" and choice[1] < len(state.fallen):
        fallen = state.fallen.pop(choice[1])
        _resolve_fallen_encounter(game, inv, fallen)


def _encounter_section(game: Game, inv: Investigator, edef: EncounterDef) -> EncounterSection | None:
    """Pick the section matching the investigator's city or terrain."""
    ldef = game.content.locations[inv.location]
    for section in edef.sections:
        if section.location == inv.location or section.terrain == ldef.terrain:
            return section
    return None


def _draw_and_run_encounter(game: Game, inv: Investigator, deck_name: str) -> None:
    content = game.content
    deck = game.encounter_decks[deck_name]
    if deck_name.startswith("research_"):
        terrain = content.locations[inv.location].terrain
        enc_id = deck.draw_where(game.rng, lambda card: content.encounters[card].terrain == terrain)
    else:
        enc_id = deck.draw(game.rng)
    if enc_id is None:
        return
    edef = content.encounters[enc_id]
    section = _encounter_section(game, inv, edef)
    text = section.text if section is not None else edef.text
    effects = section.effects if section is not None else edef.effects
    rules.emit(
        game,
        "encounter",
        text,
        title=edef.title,
        deck=deck_name,
        encounter=edef.id,
        location=inv.location,
    )
    run_effects(effects, Ctx(game, inv, f"encounter:{edef.id}"))
    deck.discard(enc_id)


def _mystery_encounter_open(game: Game, inv: Investigator, mys: MysteryState) -> bool:
    mdef = game.mystery_def(mys)
    if mdef.kind not in ("encounter", "spend", "ambush", "special") or mys.ready:
        return False
    if mdef.needs_solved and not rules.enough_mysteries(game):
        return False
    return mdef.where is None or mdef.where.matches(game, inv.location)


def _offer_research_mystery(game: Game, inv: Investigator) -> None:
    for mys in game.active_mysteries():
        mdef = game.mystery_def(mys)
        if mdef.kind == "research" and not mys.ready and inv.clues > 0:
            prompt = f"Place 1 Clue you gained on '{mdef.name}'?"
            if rules.confirm(game, prompt, kind="mystery_spend", inv=inv):
                rules.change_clues(game, inv, -1)
                rules.add_mystery_progress(game, mys, mdef.amount)


def _advance_mystery(game: Game, inv: Investigator, mys: MysteryState) -> None:
    """Pay for a Mystery and put its token on the card. A token leaves the investigator's space."""
    mdef = game.mystery_def(mys)
    if not rules.pay_for_mystery(game, inv, mys):
        return
    if mdef.token:
        game.locations[inv.location].eldritch -= 1
    rules.add_mystery_progress(game, mys, mdef.amount)


def _resolve_mystery_encounter(game: Game, inv: Investigator, mys: MysteryState) -> None:
    mdef = game.mystery_def(mys)
    if mdef.kind == "special":
        assert mdef.deck is not None
        _draw_and_run_encounter(game, inv, mdef.deck)
        return
    rules.emit(game, "encounter", mdef.text, title=mdef.name, deck="mystery", location=inv.location)
    if mdef.kind == "spend":
        _advance_mystery(game, inv, mys)
    elif mdef.kind == "ambush":
        if combat.ambush(game, inv, mdef.monster) == combat.DEFEATED:
            _advance_mystery(game, inv, mys)
    elif mdef.skill is not None:
        res = dice.run_test(game, inv, mdef.skill, mdef.mod, contexts=("mystery", "encounter"), label=mdef.name)
        if res.passed:
            _advance_mystery(game, inv, mys)


def _resolve_fallen_encounter(game: Game, inv: Investigator, fallen: FallenInvestigator) -> None:
    idef = game.content.investigators[fallen.def_id]
    enc = idef.crippled if fallen.cause == "health" else idef.insane
    rules.emit(
        game,
        "encounter",
        enc.text,
        title=f"Fallen Investigator: {fallen.name}",
        deck="fallen",
        location=inv.location,
    )
    if fallen.clues:
        rules.change_clues(game, inv, fallen.clues)
    for t in fallen.tickets:
        rules.gain_ticket(game, inv, t)
    for card in fallen.assets:
        inv.assets.append(card)
        rules.emit(game, "gain", f"{inv.name} recovers {game.asset_def(card).name}.")
    res = dice.run_test(game, inv, enc.skill, enc.mod, contexts=("encounter",), label=fallen.name)
    if res.passed:
        rules.emit(game, "info", enc.pass_text)
        rules.retreat_doom(game, 1)
    else:
        rules.emit(game, "info", enc.fail_text)


def mythos_phase(game: Game) -> None:
    rules.emit(game, "phase", f"Round {game.round}: Mythos Phase", phase="mythos", round=game.round)
    if not game.mythos_deck:
        rules.lose(game, "The Mythos deck is empty, and time has run out for humanity.")
        return

    mythos_id = game.mythos_deck.pop(0)
    mdef = game.content.mythos[mythos_id]
    game.bump("mythos_drawn")
    rules.emit(
        game,
        "mythos",
        mdef.text,
        title=mdef.name,
        flavor=mdef.flavor,
        mythos=mdef.id,
        color=mdef.color,
        icons=list(mdef.icons),
        traits=list(mdef.traits),
    )

    ref = game.reference
    active_card: ActiveMythos | None = None
    if "ongoing" in mdef.traits or "rumor" in mdef.traits:
        active_card = ActiveMythos(def_id=mdef.id, eldritch=0, rumor_space=mdef.rumor_space)

    # Resolve the 7 Mythos elements in rulebook order:
    # 1. Advance Omen
    if "advance_omen" in mdef.icons and not game.outcome:
        rules.advance_omen(game, 1)
        rules.process_defeats(game)

    # 2. Resolve Reckoning Effects
    if "reckoning" in mdef.icons and not game.outcome:
        rules.resolve_reckoning(game)
        rules.process_defeats(game)

    # 3. Spawn Gates
    if "spawn_gates" in mdef.icons and not game.outcome:
        for _ in range(ref.spawn_gates):
            if game.outcome:
                break
            rules.spawn_gate(game)
        rules.process_defeats(game)

    # 4. Monster Surge
    if "monster_surge" in mdef.icons and not game.outcome:
        rules.monster_surge(game)
        rules.process_defeats(game)

    # 5. Spawn Clues
    if "spawn_clues" in mdef.icons and not game.outcome:
        for _ in range(ref.spawn_clues):
            rules.spawn_clue(game)

    # 6. Place Rumor Token
    if "place_rumor" in mdef.icons and active_card is not None and mdef.rumor_space and not game.outcome:
        active_card.rumor_space = mdef.rumor_space
        rules.emit(game, "mythos", f"A Rumor token is placed at {rules.loc_name(game, mdef.rumor_space)}.")

    # 7. Place Eldritch Tokens
    if "place_eldritch" in mdef.icons and active_card is not None and mdef.eldritch > 0 and not game.outcome:
        active_card.eldritch = mdef.eldritch
        rules.emit(game, "mythos", f"{mdef.eldritch} Eldritch token(s) are placed on '{mdef.name}'.")

    # Resolve Effect: an Ongoing card enters play here, after the Reckoning step.
    if active_card is not None:
        game.active_mythos.append(active_card)
    if mdef.effects and not game.outcome:
        run_effects(mdef.effects, Ctx(game, None, f"mythos:{mdef.id}", mythos=active_card))
        rules.process_defeats(game)

    if active_card is None:
        game.mythos_discards.append(mdef.id)

    if game.outcome:
        return

    rules.solve_ready_mystery(game)
    if game.outcome:
        return

    rules.replace_defeated_investigators(game)
    if game.outcome:
        return

    active_invs = [i for i in game.investigators if not i.eliminated and not i.defeated]
    if len(active_invs) > 1:
        options = [Option(i.name, i.seat, f"in {rules.loc_name(game, i.location)}") for i in active_invs]
        pick = rules.choose(
            game,
            "Pass the Lead Investigator token to whom?",
            options,
            kind="pass_lead",
            inv=game.lead_investigator(),
        )
        game.lead_seat = active_invs[pick].seat

    start_round(game)


night_phase = mythos_phase


def start_round(game: Game) -> None:
    game.round += 1
    game.phase = Phase.ACTION
    game.turn_index = 0
    for inv in game.investigators:
        inv.actions_taken = []
        inv.bonus_actions = 0
        for card in inv.assets:
            card.exhausted = False

