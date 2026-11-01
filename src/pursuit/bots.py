"""Computer controllers for soak tests and balance runs.

`RandomBot` picks any legal option, which finds crashes in odd corners of the rules.
`HeuristicBot` plays with simple goals, which gives a rough win rate per Ancient One.
"""

from __future__ import annotations

import random
from typing import Any

from pursuit.controller import Event, Option
from pursuit.engine import rules
from pursuit.engine.dice import dice_pool
from pursuit.engine.state import Game, Investigator

MAX_MENU_VISITS = 40


class RandomBot:
    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed)
        self.visits = 0
        self.events = 0

    def choose(
        self, game: Game, prompt: str, options: list[Option], *, kind: str, inv: Investigator | None = None
    ) -> int:
        enabled = [i for i, o in enumerate(options) if o.enabled]
        if kind == "action":
            self.visits += 1
            end = next(i for i, o in enumerate(options) if o.value == ("end",))
            spent = all(o.value[0] in ("end",) for o in options if o.enabled)
            if spent or self.visits > MAX_MENU_VISITS:
                self.visits = 0
                return end
        elif kind in ("trade", "acquire") and self.rng.random() < 0.5:
            return enabled[-1]
        return self.rng.choice(enabled)

    def confirm(self, game: Game, prompt: str, *, kind: str, inv: Investigator | None = None) -> bool:
        return self.rng.random() < 0.5

    def notify(self, game: Game, event: Event) -> None:
        self.events += 1

    def checkpoint(self, game: Game) -> None:
        self.visits = 0


class HeuristicBot:
    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed)
        self.visits = 0

    # --- protocol ---------------------------------------------------------------------

    def choose(
        self, game: Game, prompt: str, options: list[Option], *, kind: str, inv: Investigator | None = None
    ) -> int:
        enabled = [i for i, o in enumerate(options) if o.enabled]
        handler = getattr(self, f"_{kind}", None)
        pick = handler(game, options, enabled, inv) if handler else None
        if pick is None or pick not in enabled:
            pick = enabled[0]
        return pick

    def confirm(self, game: Game, prompt: str, *, kind: str, inv: Investigator | None = None) -> bool:
        if kind == "bank_loan" and inv is not None:
            return not rules.has_condition(inv, "debt") and self.rng.random() < 0.3
        return kind != "reroll_extra"

    def notify(self, game: Game, event: Event) -> None:
        pass

    def checkpoint(self, game: Game) -> None:
        self.visits = 0

    # --- helpers ----------------------------------------------------------------------

    @staticmethod
    def _find(options: list[Option], enabled: list[int], key: str) -> int | None:
        for i in enabled:
            value = options[i].value
            if isinstance(value, tuple) and value and value[0] == key:
                return i
        return None

    def _target(self, game: Game, inv: Investigator) -> str | None:
        dist = rules.distances(game, inv.location)
        goals: list[tuple[int, int, str]] = []
        for mys in game.active_mysteries():
            mdef = game.mystery_def(mys)
            if mys.done:
                continue
            if mdef.where is not None and (mdef.clue_cost == 0 or inv.clues >= mdef.clue_cost):
                for loc in game.content.locations:
                    if mdef.where.matches(game, loc):
                        goals.append((0, dist[loc], loc))
        for active in game.active_mythos:
            rumor_at = rules.rumor_location(game, active)
            if rumor_at and rumor_at in dist:
                goals.append((0, dist[rumor_at], rumor_at))
        for loc, monster in game.all_monsters():
            mon_def = game.content.monsters[monster.def_id]
            if mon_def.epic:
                goals.append((1, dist[loc], loc))
        for loc in game.open_gates():
            goals.append((1, dist[loc], loc))
        for loc, state in game.locations.items():
            if state.clues:
                goals.append((2, dist[loc], loc))
        if not goals:
            return None
        goals.sort(key=lambda g: (g[1] + g[0] * 2, g[2]))
        return goals[0][2]

    def _closer(self, game: Game, options: list[Option], enabled: list[int], target: str | None) -> int | None:
        if target is None:
            moves = [i for i in enabled if options[i].value is not None]
            return self.rng.choice(moves) if moves else None
        back = rules.distances(game, target)
        best = None
        best_d = 999
        for i in enabled:
            val = options[i].value
            if val is None:
                continue
            dest = val[0] if isinstance(val, tuple) else val
            d = back.get(dest, 999)
            if d < best_d:
                best, best_d = i, d
        return best

    # --- decisions --------------------------------------------------------------------

    def _action(self, game: Game, options: list[Option], enabled: list[int], inv: Investigator | None) -> int | None:
        assert inv is not None
        self.visits += 1
        end = self._find(options, enabled, "end")
        if self.visits > MAX_MENU_VISITS:
            return end
        state = game.locations[inv.location]
        low = inv.health <= 2 or inv.sanity <= 2
        order: list[str] = []
        if low:
            order.append("rest")
        order.append("condition")
        target = self._target(game, inv)
        if target is not None and target != inv.location:
            if len(inv.tickets) < game.content.rules.max_tickets:
                order.append("prepare")
            order.append("travel")
        if dice_pool(game, inv, "influence", 0, ("acquire",)) >= 3 and len(inv.assets) < 3:
            order.append("acquire")
        order += ["ability", "asset"]
        if inv.health < inv.max_health or inv.sanity < inv.max_sanity:
            order.append("rest")
        if len(inv.tickets) < game.content.rules.max_tickets:
            order.append("prepare")
        order.append("acquire")
        if not state.monsters and target is None:
            order.append("travel")
        for key in order:
            pick = self._find(options, enabled, key)
            if pick is not None:
                return pick
        return end

    def _travel(self, game: Game, options: list[Option], enabled: list[int], inv: Investigator | None) -> int | None:
        assert inv is not None
        return self._closer(game, options, enabled, self._target(game, inv))

    def _travel_onward(
        self, game: Game, options: list[Option], enabled: list[int], inv: Investigator | None
    ) -> int | None:
        assert inv is not None
        target = self._target(game, inv)
        if target is None or target == inv.location:
            return enabled[-1]
        here = rules.distances(game, target).get(inv.location, 999)
        pick = self._closer(game, options, enabled, target)
        if pick is not None:
            val = options[pick].value
            dest = val[0] if isinstance(val, tuple) else val
            if rules.distances(game, target).get(dest, 999) < here:
                return pick
        return enabled[-1]

    def _encounter(self, game: Game, options: list[Option], enabled: list[int], inv: Investigator | None) -> int | None:
        for pref in ("mystery", "rumor", "other_world", "research", "fallen", "expedition"):
            for i in enabled:
                val = options[i].value
                if isinstance(val, tuple) and val and val[0] == pref:
                    return i
        return enabled[0]

    def _acquire(self, game: Game, options: list[Option], enabled: list[int], inv: Investigator | None) -> int | None:
        assert inv is not None
        owned = {c.def_id for c in inv.assets}
        best = None
        for i in enabled:
            uid = options[i].value
            if uid is None:
                continue
            card = next((c for c in game.reserve if c.uid == uid), None)
            if card is None or card.def_id in owned:
                continue
            adef = game.asset_def(card)
            score = adef.cost + len(adef.modifiers) + (1 if "weapon" in adef.traits else 0)
            if best is None or score > best[0]:
                best = (score, i)
        if best is not None:
            return best[1]
        return enabled[-1]

    def _acquire_discard(
        self, game: Game, options: list[Option], enabled: list[int], inv: Investigator | None
    ) -> int | None:
        return enabled[0]

    def _trade(self, game: Game, options: list[Option], enabled: list[int], inv: Investigator | None) -> int | None:
        return enabled[-1]

    def _lose_asset(
        self, game: Game, options: list[Option], enabled: list[int], inv: Investigator | None
    ) -> int | None:
        assert inv is not None
        cheapest = min(enabled, key=lambda i: game.content.assets[self._def_of(inv, options[i].value)].cost)
        return cheapest

    @staticmethod
    def _def_of(inv: Investigator, uid: Any) -> str:
        return next(c.def_id for c in inv.assets if c.uid == uid)

    def _improve(self, game: Game, options: list[Option], enabled: list[int], inv: Investigator | None) -> int | None:
        assert inv is not None
        from pursuit.content.defs import SKILLS

        return min(enabled, key=lambda i: inv.skill(SKILLS[i]))

    def _ability_target(
        self, game: Game, options: list[Option], enabled: list[int], inv: Investigator | None
    ) -> int | None:
        people = game.investigators_at(inv.location) if inv else []
        if not people or len(people) != len(options):
            return enabled[0]
        hurt = min(enabled, key=lambda i: people[i].health + people[i].sanity)
        return hurt

    def _effect_choice(
        self, game: Game, options: list[Option], enabled: list[int], inv: Investigator | None
    ) -> int | None:
        return self.rng.choice(enabled)

