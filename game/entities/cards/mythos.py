from enum import Enum
from game.entities.base.card import Card, CardType, CardSize, Expansion


class MythosTrait(Enum):
    EVENT = 1
    RUMOR = 2
    ONGOING = 3


class MythosIcons(Enum):
    ADVANCE_OMEN = 1
    RESOLVE_RECKONING_EFFECTS = 2
    SPAWN_GATES = 3
    MONSTER_SURGE = 4
    SPAWN_CLUES = 5
    PLACE_RUMOR_TOKEN = 6
    PLACE_ELDRITCH_TOKEN = 7
    RESOLVE_EFFECT = 8


class MythosCard(Card):
    def __init__(
        self, name, traits, color, difficulty, icons, effects, expansion=Expansion.CORE
    ):
        if not all(isinstance(t, MythosTrait) for t in traits):
            raise ValueError("Traits must be a list of MythosTrait enum values")
        if not all(isinstance(i, MythosIcons) for i in icons):
            raise ValueError("Icons must be a list of MythosIcons enum values")
        super().__init__(name, CardType.MYTHOS, CardSize.STANDARD, False, expansion)
        self.traits = traits
        self.color = color
        self.difficulty = difficulty
        self.icons = icons
        self.effects = effects
