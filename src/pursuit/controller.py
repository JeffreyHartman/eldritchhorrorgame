"""The interface between the rules engine and whoever makes decisions.

The engine never reads input or prints. It asks a `Controller` for each decision and
sends it an `Event` for each thing that happens. The terminal UI, the test scripts, and
the bots are all controllers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from pursuit.engine.state import Game, Investigator


@dataclass(frozen=True)
class Option:
    label: str
    value: Any = None
    detail: str = ""
    enabled: bool = True


@dataclass(frozen=True)
class Event:
    """Something that happened. `kind` tells a UI how to show it.

    Kinds: info, phase, turn, dice, gain, loss, encounter, portent, combat, monster,
    rift, clue, doom, dread, defeat, rite, awaken, outcome, condition, travel.
    """

    kind: str
    text: str
    data: dict[str, Any] = field(default_factory=dict)


class Controller(Protocol):
    def choose(
        self, game: Game, prompt: str, options: list[Option], *, kind: str, inv: Investigator | None = None
    ) -> int:
        """Return the index of an enabled option."""
        ...

    def confirm(self, game: Game, prompt: str, *, kind: str, inv: Investigator | None = None) -> bool: ...

    def notify(self, game: Game, event: Event) -> None: ...

    def checkpoint(self, game: Game) -> None:
        """Called at the start of each Day turn, where the state is safe to save."""
        ...
