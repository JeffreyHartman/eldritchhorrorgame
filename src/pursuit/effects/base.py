"""Effect base class, the effect registry, and the parser for effect lists in JSON."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, ClassVar

from pursuit.content.reader import ContentError, Reader

if TYPE_CHECKING:
    from pursuit.engine.state import ConditionInst, Game, Investigator


@dataclass(frozen=True)
class Ctx:
    """Who and what an effect applies to.

    `inv` is None for world effects, such as a portent with no target investigator.
    `condition` is set while a condition resolves its hidden outcome, so `remove_self`
    knows which card to discard.
    """

    game: Game
    inv: Investigator | None
    source: str
    condition: ConditionInst | None = None

    def stopped(self) -> bool:
        if self.game.outcome is not None:
            return True
        return self.inv is not None and self.inv.defeated

    def for_inv(self, inv: Investigator | None) -> Ctx:
        return replace(self, inv=inv)

    def need_inv(self, kind: str) -> Investigator:
        if self.inv is None:
            raise RuntimeError(f"effect '{kind}' from {self.source} needs an investigator")
        return self.inv


class Effect:
    kind: ClassVar[str] = ""

    @classmethod
    def parse(cls, r: Reader) -> Effect:
        raise NotImplementedError

    def apply(self, ctx: Ctx) -> None:
        raise NotImplementedError

    def children(self) -> Iterable[Sequence[Effect]]:
        """Nested effect lists, for content checks that walk the whole tree."""
        return ()

    def refs(self) -> Iterable[tuple[str, str]]:
        """(table, id) pairs this effect refers to, for cross-reference checks."""
        return ()

    def needs_investigator(self) -> bool:
        return True


REGISTRY: dict[str, type[Effect]] = {}


def register[E: type[Effect]](kind: str) -> Any:
    def wrap(cls: E) -> E:
        if kind in REGISTRY:
            raise ValueError(f"effect type '{kind}' registered twice")
        cls.kind = kind
        REGISTRY[kind] = cls
        return cls

    return wrap


def parse_effect(data: Any, path: str) -> Effect:
    r = Reader(data, path)
    kind = r.get_str("type")
    cls = REGISTRY.get(kind)
    if cls is None:
        raise ContentError(f"{path}: unknown effect type '{kind}'")
    effect = cls.parse(r)
    r.done()
    return effect


def parse_effects(data: Any, path: str) -> tuple[Effect, ...]:
    if not isinstance(data, list):
        raise ContentError(f"{path}: expected a list of effects")
    return tuple(parse_effect(item, f"{path}[{i}]") for i, item in enumerate(data))


def read_effects(r: Reader, key: str) -> tuple[Effect, ...]:
    """Read an optional effect list field. A missing key gives no effects."""
    return parse_effects(r.get_list(key, []), r.at(key))


def run_effects(effects: Sequence[Effect], ctx: Ctx) -> None:
    for effect in effects:
        if ctx.stopped():
            return
        effect.apply(ctx)


def walk(effects: Sequence[Effect]) -> Iterable[Effect]:
    for effect in effects:
        yield effect
        for child in effect.children():
            yield from walk(child)
