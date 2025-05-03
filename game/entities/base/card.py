from enum import Enum
from game.enums import Expansion


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
