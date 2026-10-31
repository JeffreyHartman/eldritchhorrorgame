"""Computer controllers for soak tests and balance runs.

`RandomBot` picks any legal option, which finds crashes in odd corners of the rules.
`HeuristicBot` plays with simple goals, which gives a rough win rate per Old One.
"""

from __future__ import annotations

import random
from typing import Any

from pursuit.controller import Event, Option
from pursuit.engine import rules
from pursuit.engine.dice import dice_pool
from pursuit.engine.state import Game, Investigator

# A turn that loops through free actions this many times ends by force. It keeps a
# random bot from trading the same item back and forth forever.
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
            spent = all(o.value[0] in ("buy", "trade", "collect", "end") for o in options if o.enabled)
            if spent or self.visits > MAX_MENU_VISITS:
                self.visits = 0
                return end
        elif kind in ("trade", "buy", "collect") and self.rng.random() < 0.5:
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
        self.shopped: tuple[int, int] | None = None
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
        if kind == "boost" and inv is not None:
            return inv.sanity > 3 and inv.health > 2
        return True

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
        for rite in game.active_rites():
            rdef = game.rite_def(rite)
            if rite.done or rdef.where is None:
                continue
            has = {"clues": inv.clues, "funds": inv.funds, "trophies": inv.trophies}.get(rdef.resource or "", 1)
            if rdef.resource == "relic":
                has = sum(game.asset_def(c).kind == "relic" for c in inv.assets)
            if rdef.kind == "test" or has >= 2:
                for loc in game.content.locations:
                    if rdef.where.matches(game, loc):
                        goals.append((0, dist[loc], loc))
        lore = dice_pool(game, inv, "lore", 0, ("seal",))
        for loc, monster in game.all_monsters():
            mdef = game.content.monsters[monster.def_id]
            if mdef.epic:
                goals.append((1, dist[loc], loc))
        for loc in game.open_rifts():
            if lore >= 3:
                goals.append((1, dist[loc], loc))
        for loc, state in game.locations.items():
            if state.clue:
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
            dest = options[i].value
            if dest is None:
                continue
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
        order += ["rite", "seal", "investigate", "cure"]
        here_key = (game.round, inv.seat)
        if self.shopped != here_key and inv.funds >= 2:
            order.append("buy")
        if inv.funds < 3:
            order.append("earn")
        target = self._target(game, inv)
        if target is not None and target != inv.location:
            order.append("travel")
        order += ["ability", "asset"]
        if inv.health < inv.max_health or inv.sanity < inv.max_sanity:
            order.append("rest")
        if not state.monsters and target is None:
            order.append("travel")
        for key in order:
            pick = self._find(options, enabled, key)
            if pick is not None:
                if key == "buy":
                    self.shopped = here_key
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
        if pick is not None and rules.distances(game, target).get(options[pick].value, 999) < here:
            return pick
        return enabled[-1]

    def _combat(self, game: Game, options: list[Option], enabled: list[int], inv: Investigator | None) -> int | None:
        assert inv is not None
        here = game.locations[inv.location].monsters
        if not here:
            return 0
        monster = here[0]
        mdef = game.content.monsters[monster.def_id]
        rate = (7 - game.content.rules.success_on) / 6
        fight = dice_pool(game, inv, "brawn", mdef.fight_mod, ("combat",)) * rate
        evade = dice_pool(game, inv, "wits", mdef.evade_mod, ("evade",))
        remaining = rules.toughness(game, monster.def_id) - monster.wounds
        if mdef.epic and inv.health > mdef.damage:
            return 0  # Wounds stay on a monster, so chip away at an epic one.
        return 0 if fight >= remaining * 0.8 or evade < 2 else 1

    def _encounter(self, game: Game, options: list[Option], enabled: list[int], inv: Investigator | None) -> int | None:
        assert inv is not None
        if len(enabled) > 1 and dice_pool(game, inv, "lore", 0, ("encounter",)) >= 4 and inv.sanity > 3:
            return enabled[1]
        return enabled[0]

    def _buy(self, game: Game, options: list[Option], enabled: list[int], inv: Investigator | None) -> int | None:
        assert inv is not None
        owned = {c.def_id for c in inv.assets}
        best = None
        for i in enabled:
            uid = options[i].value
            card = next((c for c in game.market if c.uid == uid), None)
            if card is None or card.def_id in owned:
                continue
            adef = game.asset_def(card)
            score = len(adef.modifiers) + len(adef.boosts) + (1 if "weapon" in adef.traits else 0)
            if best is None or score > best[0]:
                best = (score, i)
        if best is not None and best[0] > 0:
            return best[1]
        return enabled[-1]

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
        skills = ["lore", "charm", "wits", "brawn", "nerve"]
        return min(enabled, key=lambda i: inv.skill(skills[i]))

    def _ability_target(
        self, game: Game, options: list[Option], enabled: list[int], inv: Investigator | None
    ) -> int | None:
        people = game.investigators_at(inv.location) if inv else []
        if not people:
            return None
        hurt = min(range(len(people)), key=lambda i: people[i].health + people[i].sanity)
        return hurt

    def _effect_choice(
        self, game: Game, options: list[Option], enabled: list[int], inv: Investigator | None
    ) -> int | None:
        return self.rng.choice(enabled)
