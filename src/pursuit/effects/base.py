"""Effect base class, the effect registry, and the parser for effect lists in JSON."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, ClassVar

from pursuit.content.reader import ContentError, Reader

if TYPE_CHECKING:
    from pursuit.engine.state import ActiveMythos, AssetCard, ConditionInst, Game, Investigator, MonsterInst


def sourced(name: str, text: str) -> str:
    """Prefix `text` with a source's display name, unless the name is empty or already in the text."""
    return f"{name}: {text}" if name and name not in text else text


def _investigator_name(game: Game, def_id: str) -> str:
    return game.content.investigators[def_id].name


def _asset_name(game: Game, def_id: str) -> str:
    return game.content.assets[def_id].name


def _condition_name(game: Game, def_id: str) -> str:
    return game.content.conditions[def_id].name


def _monster_name(game: Game, def_id: str) -> str:
    return game.monster_def(def_id).name


def _mythos_name(game: Game, def_id: str) -> str:
    return game.content.mythos[def_id].name


def _old_one_name(game: Game, def_id: str) -> str:
    return game.content.old_ones[def_id].name


def _mystery_name(game: Game, def_id: str) -> str:
    old = game.old_one
    return next(m.name for m in (*old.mysteries, old.awakening.final_mystery) if m is not None and m.id == def_id)


def _encounter_name(game: Game, def_id: str) -> str:
    """Encounter titles are cut-off card text, so a source names the deck."""
    deck = game.content.encounters[def_id].deck
    group = deck.partition("_")[0] if deck.startswith(("research_", "special_")) else deck
    label = "Other World" if group == "other_world" else group.replace("_", "/").title()
    return f"{label} Encounter"


_SOURCE_NAMES: dict[str, Callable[[Game, str], str]] = {
    "ability": _investigator_name,
    "start": _investigator_name,
    "asset": _asset_name,
    "asset_back": _asset_name,
    "reckoning_asset": _asset_name,
    "condition": _condition_name,
    "condition_action": _condition_name,
    "reckoning_condition": _condition_name,
    "monster": _monster_name,
    "monster_spawn": _monster_name,
    "reckoning_monster": _monster_name,
    "mythos": _mythos_name,
    "mythos_zero": _mythos_name,
    "reckoning_mythos": _mythos_name,
    "rumor": _mythos_name,
    "setup": _old_one_name,
    "awakening": _old_one_name,
    "awakened_doom": _old_one_name,
    "reckoning_ao": _old_one_name,
    "eldritch_move": _old_one_name,
    "mystery": _mystery_name,
    "encounter": _encounter_name,
}


@dataclass(frozen=True)
class Ctx:
    """Who and what an effect applies to.

    `inv` is None for world effects, such as a Mythos card with no target investigator.
    `condition`, `asset`, `mythos`, and `monster` are set while resolving effects on those
    components. `tag` is an extra test context, such as "other_world". `chosen` is the
    investigator a Spell targets, and `inv` stays the caster.
    """

    game: Game
    inv: Investigator | None
    source: str
    condition: ConditionInst | None = None
    asset: AssetCard | None = None
    mythos: ActiveMythos | None = None
    monster: MonsterInst | None = None
    gate: str | None = None
    test_successes: int | None = None
    tag: str | None = None
    chosen: Investigator | None = None
    test_rolls: tuple[int, ...] = ()

    @property
    def source_name(self) -> str:
        """The player-facing name of `source`. A source with no `prefix:id` shape has no name."""
        prefix, _, def_id = self.source.partition(":")
        return _SOURCE_NAMES[prefix](self.game, def_id) if def_id else ""

    def sourced(self, text: str) -> str:
        return sourced(self.source_name, text)

    def stopped(self) -> bool:
        if self.game.outcome is not None:
            return True
        return self.inv is not None and self.inv.defeated

    def for_inv(self, inv: Investigator | None) -> Ctx:
        return replace(self, inv=inv)

    def need_monster(self, kind: str) -> MonsterInst:
        if self.monster is None:
            raise RuntimeError(f"effect '{kind}' from {self.source} needs a monster")
        return self.monster

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
