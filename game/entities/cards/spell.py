from enum import Enum
from game.entities.base.card import Card, CardType, CardSize, Expansion


class SpellTrait(Enum):
    RITUAL = 1
    INCANTATION = 2


class SpellCard(Card):
    def __init__(
        self,
        name,
        trait,
        expansion=Expansion.CORE,
    ):
        super().__init__(name, CardType.SPELL, CardSize.MINI, True, expansion)
        self.effects = effects
        self.trait = trait
        self.effects = effects
        self.action = action
        self.skill_bonus = skill_bonus
        self.reroll = reroll
        self.additional_dice = additional_dice
        self.result_manipulation = result_manipulation
        self.reckoning = reckoning
