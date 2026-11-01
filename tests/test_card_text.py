"""Tests that compare card text with card effects, for encounters and other cards with text.

Each check reads a phrase in the text and looks for the matching effect in the same section
or card. A check sees only the shipped text, so it cannot find a difference the text is silent
about. Issue 2 records the hand audit that these checks keep in place.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from pursuit.content.defs import MonsterDef
from pursuit.content.loader import DEFAULT_DATA_DIR, Content, load_content
from pursuit.effects.base import Effect, walk
from pursuit.effects.library import (
    AdvanceDoom,
    AdvanceOmen,
    Ambush,
    Choice,
    ClaimClue,
    CloseGate,
    Clues,
    Delay,
    GainAsset,
    GainCondition,
    Health,
    ImproveSkill,
    LoseAsset,
    Move,
    MoveClue,
    MoveMonsterHere,
    Pay,
    RetreatDoom,
    Sanity,
    SpawnClue,
    SpawnGate,
    Text,
)
from pursuit.effects.library import Test as SkillTest

MAY = re.compile(r"\b(?:you|he) may\b|\bunless (?:you|he)\b", re.IGNORECASE)

# Each entry is a scope label and why its "you may" wording needs no decision.
NO_DECISION_NEEDED = {
    "expedition_the_pyramids_3": '"you may be too distracted" is narration, not an option.',
    "asia_australia_6 sydney": '"unless you prove" describes the Influence test that follows.',
}

# Each entry is a `missing_components` result and why no `gain_condition` or `gain_asset` appears.
GIVEN_BY_CODE = {
    "paranoia: Kleptomania: Gain 1 : Detained": "`Kleptomania.apply` gives Detained after the value check.",
}

# Asset and Condition names the card text uses, where they differ from the `name` field.
ASSET_ALIASES = {"sword_of_st_jerome": ("Sword of Saint Jerome",), "shrivelling": ("Shriveling",)}
INJURY = r"(?<!Leg )(?<!Back )(?<!Internal )Injury Condition"
GAINS = r"\bgains? (?:(?!discard)[^.;])*?"


@dataclass(frozen=True)
class Scope:
    """Text and the effect tree that must carry it out."""

    label: str
    text: str
    effects: tuple[Effect, ...]
    encounter: bool = False

    def texts(self) -> list[str]:
        return [self.text, *(e.text for e in walk(self.effects) if isinstance(e, Text))]

    def tree(self) -> list[Effect]:
        return list(walk(self.effects))


def _monster_effects(mon: MonsterDef) -> tuple[Effect, ...]:
    found: list[Effect] = [*mon.on_spawn, *mon.reckoning]
    for effects in mon.combat_hooks().values():
        found.extend(effects)
    return tuple(found)


def encounter_scopes(content: Content) -> Iterable[Scope]:
    for enc in content.encounters.values():
        if enc.sections:
            for section in enc.sections:
                where = section.location or section.terrain
                yield Scope(f"{enc.id} {where}", section.text, section.effects, True)
        else:
            yield Scope(enc.id, enc.text, enc.effects, True)


def card_scopes(content: Content) -> Iterable[Scope]:
    yield from encounter_scopes(content)
    for mdef in content.mythos.values():
        effects = (*mdef.effects, *mdef.reckoning, *mdef.encounter_effects, *mdef.on_zero_eldritch)
        yield Scope(mdef.id, mdef.text, effects)
    for mon in content.monsters.values():
        yield Scope(mon.id, mon.text, _monster_effects(mon))
    for old in content.old_ones.values():
        yield Scope(f"{old.id} cultist", old.cultist.text, _monster_effects(old.cultist))
    for cond in content.conditions.values():
        for back in cond.backs:
            yield Scope(f"{cond.id}: {back.text[:20]}", back.text, back.effects)
    for adef in content.assets.values():
        for back in adef.backs:
            yield Scope(f"{adef.id}: {back.text[:20]}", back.text, back.effects)


def missing_decisions(content: Content, allowed: dict[str, str]) -> list[str]:
    """Encounter scopes with "you may" or "unless you" wording and no decision effect."""

    def decides(effect: Effect) -> bool:
        return isinstance(effect, Choice | Pay) or (
            isinstance(effect, SkillTest) and (effect.clue_bonus or effect.sanity_dice)
        )

    return [
        scope.label
        for scope in encounter_scopes(content)
        if any(MAY.search(text) for text in scope.texts())
        and not any(decides(e) for e in scope.tree())
        and scope.label not in allowed
    ]


def _gives_asset(asset_id: str) -> Callable[[Effect], bool]:
    def gives(effect: Effect) -> bool:
        return isinstance(effect, GainAsset) and effect.asset_id == asset_id

    return gives


def _gives_condition(condition_id: str) -> Callable[[Effect], bool]:
    def gives(effect: Effect) -> bool:
        return isinstance(effect, GainCondition) and effect.condition == condition_id

    return gives


def _gives_trait(trait: str) -> Callable[[Effect], bool]:
    def gives(effect: Effect) -> bool:
        return isinstance(effect, GainCondition) and effect.trait == trait

    return gives


def missing_components(content: Content) -> list[str]:
    """Scopes whose text gains a named Asset, Artifact, Spell, or Condition that no effect gives."""
    wanted: list[tuple[re.Pattern[str], Callable[[Effect], bool], str]] = []
    for adef in content.assets.values():
        for name in (adef.name, *ASSET_ALIASES.get(adef.id, ())):
            pattern = re.compile(GAINS + re.escape(name.removeprefix("The ")) + r"\b")
            wanted.append((pattern, _gives_asset(adef.id), adef.name))
    for cdef in content.conditions.values():
        pattern = re.compile(GAINS + re.escape(cdef.name) + r" Condition")
        wanted.append((pattern, _gives_condition(cdef.id), cdef.name))
    wanted.append((re.compile(GAINS + r"Madness Condition"), _gives_trait("madness"), "Madness"))
    wanted.append((re.compile(GAINS + INJURY), _gives_trait("injury"), "Injury"))
    problems = []
    for scope in card_scopes(content):
        tree = scope.tree()
        for pattern, gives, name in wanted:
            if any(pattern.search(text) for text in scope.texts()) and not any(gives(e) for e in tree):
                problems.append(f"{scope.label}: {name}")
    return problems


def _amount(cls: type, sign: int = 1) -> Callable[[re.Match[str], Sequence[Effect]], bool]:
    def has(match: re.Match[str], tree: Sequence[Effect]) -> bool:
        return any(isinstance(e, cls) and e.amount == sign * int(match[1]) for e in tree)  # type: ignore[attr-defined]

    return has


def _kind(cls: type) -> Callable[[re.Match[str], Sequence[Effect]], bool]:
    return lambda _match, tree: any(isinstance(e, cls) for e in tree)


def _improve(match: re.Match[str], tree: Sequence[Effect]) -> bool:
    return any(isinstance(e, ImproveSkill) and e.skill == match[1].lower() for e in tree)


def _improve_choice(_match: re.Match[str], tree: Sequence[Effect]) -> bool:
    return any(isinstance(e, ImproveSkill) and e.skill == "choose" for e in tree)


def _skill_test(match: re.Match[str], tree: Sequence[Effect]) -> bool:
    mod = int(match[2]) if match[2] else 0
    return any(isinstance(e, SkillTest) and e.skill == match[1].lower() and e.mod == mod for e in tree)


def _move_clue(match: re.Match[str], tree: Sequence[Effect]) -> bool:
    return any(isinstance(e, MoveClue) and e.terrain == match[1].lower() for e in tree)


def _kind_gain(match: re.Match[str], tree: Sequence[Effect]) -> bool:
    return any(isinstance(e, GainAsset) and e.asset_kind == match[1].lower() for e in tree)


def _trait_gain(match: re.Match[str], tree: Sequence[Effect]) -> bool:
    return any(isinstance(e, GainAsset) and e.trait == match[1].lower() for e in tree)


def _lose_asset(match: re.Match[str], tree: Sequence[Effect]) -> bool:
    return any(isinstance(e, LoseAsset) and e.asset_kind == match[1].lower() for e in tree)


def _ambush(match: re.Match[str], tree: Sequence[Effect]) -> bool:
    wanted = match[1].lower().replace(" ", "_").replace("-", "_")
    return any(isinstance(e, Ambush) and (e.monster or "") == wanted for e in tree)


PHRASES: list[tuple[str, Callable[[re.Match[str], Sequence[Effect]], bool]]] = [
    (r"\((Lore|Influence|Observation|Strength|Will)([+-]\d)?\)", _skill_test),
    (r"\bimprove (Lore|Influence|Observation|Strength|Will)\b", _improve),
    (r"\bimprove 1 skill of your choice\b", _improve_choice),
    (r"\bgain this Clue\b", _kind(ClaimClue)),
    (r"\bmove this Clue to the nearest (Sea|Wilderness) space\b", _move_clue),
    (r"\bclose this Gate\b", _kind(CloseGate)),
    (r"\badvance the Omen\b", _kind(AdvanceOmen)),
    (r"\badvance Doom by (\d)\b", _amount(AdvanceDoom)),
    (r"\bretreat Doom by (\d)\b", _amount(RetreatDoom)),
    (r"\bspawn \d Clues?\b", _kind(SpawnClue)),
    (r"\bspawn \d Gates?\b", _kind(SpawnGate)),
    (r"\bbecome Delayed\b", _kind(Delay)),
    (r"\bmove 1 space\b", _kind(Move)),
    (r"\bgain (\d) Clues?\b", _amount(Clues)),
    (r"\blose (\d) Health\b", _amount(Health, -1)),
    (r"\blose (\d) Sanity\b", _amount(Sanity, -1)),
    (r"\band (\d) Sanity\b", lambda m, tree: any(isinstance(e, Sanity) and abs(e.amount) == int(m[1]) for e in tree)),
    (r"\brecover (\d) Health\b", _amount(Health)),
    (r"\brecover (\d) Sanity\b", _amount(Sanity)),
    (r"\bgain 1 (Artifact|Spell)\b", _kind_gain),
    (r"\bgain 1 (Incantation|Ritual) Spell\b", _trait_gain),
    (r"\b(Tome|Weapon) (?:Artifact|Asset)\b", _trait_gain),
    (r"\bdiscard \d (Item|Ally|Spell)\b", _lose_asset),
    (r"\b(?:A|a) (Cultist|Deep One|Star Spawn|Goat Spawn|Dark Young) Monster ambushes you\b", _ambush),
    (r"\bmove it to your space\b", _kind(MoveMonsterHere)),
]


def missing_phrases(content: Content) -> list[str]:
    """Encounter scopes with a game phrase in the text that no effect carries out."""
    problems = []
    for scope in encounter_scopes(content):
        tree = scope.tree()
        for text in scope.texts():
            for pattern, carried_out in PHRASES:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    if not carried_out(match, tree):
                        problems.append(f"{scope.label}: {match[0]}")
    return sorted(set(problems))


def test_every_optional_encounter_offers_a_decision(content: Content) -> None:
    assert missing_decisions(content, NO_DECISION_NEEDED) == []


def test_every_named_gain_is_given(content: Content) -> None:
    assert [item for item in missing_components(content) if item not in GIVEN_BY_CODE] == []


def test_every_game_phrase_has_an_effect(content: Content) -> None:
    assert missing_phrases(content) == []


# --- the checks catch broken data -------------------------------------------------------


@pytest.fixture
def data_copy(tmp_path: Path) -> Path:
    target = tmp_path / "data"
    shutil.copytree(DEFAULT_DATA_DIR, target)
    return target


def load_card_edit(path: Path, deck: str, card_id: str, effects: list[dict[str, Any]]) -> Content:
    """Replace one card's effects in a copy of the data and load it."""
    file = path / "encounters" / f"{deck}.json"
    cards = json.loads(file.read_text(encoding="utf-8"))
    next(card for card in cards if card["id"] == card_id)["effects"] = effects
    file.write_text(json.dumps(cards), encoding="utf-8")
    return load_content.__wrapped__(str(path))


def test_a_lost_decision_fails_the_check(data_copy: Path) -> None:
    broken = load_card_edit(data_copy, "research_azathoth", "research_azathoth_sea_5", [{"type": "claim_clue"}])
    assert "research_azathoth_sea_5" in missing_decisions(broken, NO_DECISION_NEEDED)


def test_a_lost_named_gain_fails_the_check(data_copy: Path) -> None:
    edited = [{"type": "choice", "options": [{"label": "A", "effects": []}, {"label": "B", "effects": []}]}]
    broken = load_card_edit(data_copy, "research_yog_sothoth", "research_yog_sothoth_city_2", edited)
    assert "research_yog_sothoth_city_2: Necronomicon" in missing_components(broken)


def test_a_lost_phrase_fails_the_check(data_copy: Path) -> None:
    edited = [{"type": "test", "skill": "lore", "pass": [], "fail": []}]
    broken = load_card_edit(data_copy, "research_azathoth", "research_azathoth_sea_1", edited)
    assert "research_azathoth_sea_1: gain this Clue" in missing_phrases(broken)
