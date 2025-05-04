from enum import Enum
from game.entities.base.card import Card, CardType, CardSize, Expansion


class MythosTrait(Enum):
    EVENT = "event"
    RUMOR = "rumor"
    ONGOING = "ongoing"


class MythosIcons(Enum):
    ADVANCE_OMEN = "advance_omen"
    RECKONING = "reckoning"
    SPAWN_GATES = "spawn_gates"
    MONSTER_SURGE = "monster_surge"
    SPAWN_CLUES = "spawn_clues"
    SPAWN_RUMOR = "spawn_rumor"
    PLACE_ELDRITCH_TOKEN = "place_eldritch_token"


class MythosCard(Card):
    def __init__(
        self, name, traits, color, difficulty, icons, expansion=Expansion.CORE
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
        self.components = []

    def add_component(self, component):
        self.components.append(component)

    def process_components(self, state, **kwargs):
        results = []
        for component in self.components:
            result = component.process(state, **kwargs)
            results.append(result)
        return results
