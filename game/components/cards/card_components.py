from abc import ABC, abstractmethod
from typing import List, Optional, Callable, Any


class CardComponent(ABC):
    @abstractmethod
    def apply(self, game_state, card_owner, target=None, **kwargs):
        """Apply this comonent's effect"""
        pass


class ActionComponent(CardComponent):
    """Defines an action a card enables"""

    def __init__(
        self,
        name: str,
        test_type=None,
        test_difficulty=None,
        action_function: Callable = None,
    ):
        self.name = name
        self.test_type = test_type
        self.test_difficulty = test_difficulty
        self.action_function = action_function

    def apply(self, game_state, card_owner, target=None, **kwargs):
        if self.action_function:
            self.action_function(game_state, card_owner, target, **kwargs)
        return False


class PassiveEffectComponent(CardComponent):
    """A passive effect that's always active"""

    def __init__(self, effect_function: Callable):
        self.effect_function = effect_function

    def apply(self, game_state, card_owner, target=None, **kwargs):
        if self.effect_function:
            self.effect_function(game_state, card_owner, target, **kwargs)
        return False


class TestModifierComponent(CardComponent):
    """Modifies test results (rerolls, bonus dice, etc.)"""

    def __init__(
        self,
        applies_to_tests: List[str] = None,
        additional_dice: int = 0,
        allows_rerolls: bool = False,
        reroll_count: int = 0,
        success_manipulation: Callable = None,
    ):
        self.applies_to_tests = applies_to_tests or ["all"]
        self.additional_dice = additional_dice
        self.allows_rerolls = allows_rerolls
        self.reroll_count = reroll_count
        self.success_manipulation = success_manipulation

    def apply(self, game_state, card_owner, target=None, **kwargs):
        # Implementation depends on your test resolution system
        pass


class SkillBonusComponent(CardComponent):
    """Provides bonuses to specific skills"""

    def __init__(self, skill_bonuses: Dict[str, int]):
        self.skill_bonuses = skill_bonuses

    def apply(self, game_state, card_owner, target=None, **kwargs):
        # Apply skill bonuses to the card owner
        pass


class EventTriggerComponent(CardComponent):
    """Triggered by specific game events"""

    def __init__(self, trigger_event: str, trigger_function: Callable):
        self.trigger_event = trigger_event
        self.trigger_function = trigger_function

    def apply(self, game_state, card_owner, target=None, **kwargs):
        if self.trigger_function:
            return self.trigger_function(game_state, card_owner, target, **kwargs)
        return False
