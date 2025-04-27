from enum import Enum


class CardType(Enum):
    MYTHOS = 1
    MONSTER = 2
    ENCOUNTER = 3
    MYSTERY = 4
    ASSET = 5
    SPELL = 6
    CONDITION = 7
    ARTIFACT = 8
    RESEARCH = 9
    SPECIAL = 10


class Expansion(Enum):
    CORE = 1
    FORSAKEN_LORE = 2
    MOUNTAINS_OF_MADNESS = 3
    STRANGE_REMNANTS = 4
    UNDER_THE_PYRAMIDS = 5
    SIGNS_OF_CARCOSA = 6
    THE_DREAMLANDS = 7
    CITIES_IN_RUINS = 8
    MASKS_OF_NYARLATHOTEP = 9


class CardSize(Enum):
    STANDARD = 1
    MINI = 2


class Card:
    def __init__(self, name, type, size, double_sided, expansion):
        if not isinstance(type, CardType):
            raise ValueError("Card type must be a CardType enum value")
        if not isinstance(expansion, Expansion):
            raise ValueError("Expansion must be an Expansion enum value")

        self.name = name
        self.type = type
        self.expansion = expansion
        self.size = size
        self.double_sided = double_sided
