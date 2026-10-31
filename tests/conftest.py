"""Shared fixtures: loaded content, scripted decisions, and scripted dice."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from typing import Any

import pytest

from pursuit.content.loader import Content, load_content
from pursuit.controller import Event, Option
from pursuit.engine.setup import GameConfig, new_game
from pursuit.engine.state import Game, Investigator

Answer = int | str | bool | Callable[[list[Option]], int]
MakeGame = Callable[..., Game]


class Script:
    """A controller that answers from a queue of (kind, answer) pairs.

    An int answer is an option index. A str answer picks the first enabled option whose
    label contains it. When the queue is empty, `fallback` decides: "first" picks the
    first enabled option and says no to every confirm, and "strict" fails the test.
    """

    def __init__(self, answers: Iterable[tuple[str, Answer]] = (), fallback: str = "first") -> None:
        self.queue: deque[tuple[str, Answer]] = deque(answers)
        self.fallback = fallback
        self.events: list[Event] = []
        self.asked: list[tuple[str, str]] = []
        self.checkpoints = 0

    def add(self, kind: str, answer: Answer) -> Script:
        self.queue.append((kind, answer))
        return self

    def _next(self, kind: str, prompt: str) -> Answer | None:
        self.asked.append((kind, prompt))
        if self.queue:
            want, answer = self.queue[0]
            if want in (kind, "*"):
                self.queue.popleft()
                return answer
            if self.fallback == "strict":
                raise AssertionError(f"expected a '{want}' decision, got '{kind}': {prompt}")
        elif self.fallback == "strict":
            raise AssertionError(f"unexpected '{kind}' decision: {prompt}")
        return None

    def choose(
        self, game: Game, prompt: str, options: list[Option], *, kind: str, inv: Investigator | None = None
    ) -> int:
        answer = self._next(kind, prompt)
        enabled = [i for i, o in enumerate(options) if o.enabled]
        if answer is None:
            # Free-action menus repeat until the player leaves, so the default leaves.
            if kind == "action":
                return next(i for i, o in enumerate(options) if o.value == ("end",))
            if kind in ("buy", "collect", "trade"):
                return enabled[-1]
            return enabled[0]
        if callable(answer) and not isinstance(answer, bool):
            return answer(options)
        if isinstance(answer, str):
            for i in enabled:
                if answer.lower() in options[i].label.lower():
                    return i
            labels = [o.label for o in options]
            raise AssertionError(f"no enabled option matches '{answer}' in {labels}")
        assert isinstance(answer, int)
        return answer

    def confirm(self, game: Game, prompt: str, *, kind: str, inv: Investigator | None = None) -> bool:
        answer = self._next(kind, prompt)
        return bool(answer) if answer is not None else False

    def notify(self, game: Game, event: Event) -> None:
        self.events.append(event)

    def checkpoint(self, game: Game) -> None:
        self.checkpoints += 1

    def texts(self, kind: str | None = None) -> list[str]:
        return [e.text for e in self.events if kind is None or e.kind == kind]


def set_dice(game: Game, *rolls: int) -> None:
    """Make the next dice rolls exact. Any roll past the end of the list fails the test."""
    queue = deque(rolls)

    def roll() -> int:
        if not queue:
            raise AssertionError("the test ran out of scripted dice")
        return queue.popleft()

    game.roll = roll


@pytest.fixture(scope="session")
def content() -> Content:
    return load_content()


@pytest.fixture
def script() -> Script:
    return Script()


@pytest.fixture
def make_game(content: Content, script: Script) -> MakeGame:
    def make(
        old_one: str = "king_in_yellow",
        investigators: tuple[str, ...] = ("hollis_grange", "miriam_achterberg"),
        difficulty: str = "normal",
        seed: int = 7,
        clean: bool = True,
    ) -> Game:
        game = new_game(content, GameConfig(old_one, investigators, difficulty, seed), script)
        if clean:
            clear_board(game)
        script.events.clear()
        return game

    return make


def clear_board(game: Game) -> None:
    """Remove random setup rifts, clues, and monsters, so a test can place its own."""
    for state in game.locations.values():
        state.rift = False
        state.clue = False
        for monster in state.monsters:
            mdef = game.content.monsters[monster.def_id]
            if not mdef.epic:
                game.monster_cup.append(monster.def_id)
        state.monsters = []


def first(game: Game) -> Investigator:
    return game.investigators[0]


def card_uids(game: Game) -> list[int]:
    """Every asset card uid in every zone of the game."""
    uids = [c.uid for c in game.market]
    for deck in (game.asset_deck, game.spell_deck, game.relic_deck):
        uids += [c.uid for c in deck.cards + deck.discards]
    for inv in game.investigators:
        uids += [c.uid for c in inv.assets]
    for state in game.locations.values():
        uids += [c.uid for c in state.belongings]
    return uids


def check_invariants(game: Game) -> None:
    for inv in game.investigators:
        if inv.eliminated:
            continue
        assert 0 <= inv.health <= inv.max_health, inv
        assert 0 <= inv.sanity <= inv.max_sanity, inv
        assert inv.funds >= 0 and inv.clues >= 0 and inv.trophies >= 0, inv
        assert inv.location in game.content.locations
        if not inv.defeated:
            assert inv.health > 0 and inv.sanity > 0, inv
    uids = card_uids(game)
    assert len(uids) == len(set(uids)), "an asset card is in two places at once"
    for rite in game.rites:
        assert 0 <= rite.progress <= rite.required
    assert game.doom >= 0
    assert 1 <= game.dread <= 3


def kinds(options: list[Any]) -> list[str]:
    return [o.value[0] for o in options if o.enabled]
