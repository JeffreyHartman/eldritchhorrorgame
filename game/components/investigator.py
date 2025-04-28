import random
from typing import Dict, List, Tuple

from game.enums import TicketType


class Investigator:
    """Represents a player character in the game."""

    def __init__(
        self,
        name: str,
        health: int,
        max_health: int,
        sanity: int,
        max_sanity: int,
        skills: Dict[str, int],
        items: List[str],
        clue_tokens: int,
        train_tickets: int,
        ship_tickets: int,
        is_delayed: bool = False,
        actions: int = 2,
        current_location: str = "London",
    ):
        self.name = name
        self.health = health
        self.max_health = max_health
        self.sanity = sanity
        self.max_sanity = max_sanity
        self.skills = skills
        self.items = items
        self.clue_tokens = clue_tokens
        self.train_tickets = train_tickets
        self.ship_tickets = ship_tickets
        self.is_delayed = is_delayed
        self.actions = actions
        self.current_location = current_location
        self.conditions: List[str] = []

    def heal(self, amount: int = 1) -> int:
        """Heal the investigator's health.

        Args:
            amount: Amount of health to heal

        Returns:
            Current health after healing
        """
        self.health = min(self.health + amount, self.max_health)
        return self.health

    def restore_sanity(self, amount: int = 1) -> int:
        """Restore the investigator's sanity.

        Args:
            amount: Amount of sanity to restore

        Returns:
            Current sanity after restoration
        """
        self.sanity = min(self.sanity + amount, self.max_sanity)
        return self.sanity

    def take_damage(self, amount: int = 1) -> int:
        """Reduce the investigator's health.

        Args:
            amount: Amount of damage to take

        Returns:
            Current health after damage
        """
        self.health = max(self.health - amount, 0)
        return self.health

    def lose_sanity(self, amount: int = 1) -> int:
        """Reduce the investigator's sanity.

        Args:
            amount: Amount of sanity to lose

        Returns:
            Current sanity after loss
        """
        self.sanity = max(self.sanity - amount, 0)
        return self.sanity

    def gain_clue(self, amount: int = 1) -> int:
        """Add clue tokens to the investigator.

        Args:
            amount: Number of clue tokens to add

        Returns:
            Current clue token count
        """
        self.clue_tokens += amount
        return self.clue_tokens

    def use_clue(self, amount: int = 1) -> bool:
        """Use clue tokens from the investigator.

        Args:
            amount: Number of clue tokens to use

        Returns:
            True if clue tokens were successfully used, False otherwise
        """
        if self.clue_tokens >= amount:
            self.clue_tokens -= amount
            return True
        return False

    def add_ticket(self, ticket_type: str, amount: int = 1) -> Tuple[int, int]:
        """Add travel tickets to the investigator's inventory.

        Args:
            ticket_type: The type of ticket to add (train or ship)
            amount: The number of tickets to add

        Returns:
            A tuple of (train_tickets, ship_tickets) counts
        """
        if ticket_type == TicketType.TRAIN.value:
            self.train_tickets += amount
        elif ticket_type == TicketType.SHIP.value:
            self.ship_tickets += amount
        return self.train_tickets, self.ship_tickets

    def use_ticket(self, ticket_type: str, amount: int = 1) -> bool:
        """Use travel tickets from the investigator's inventory.

        Args:
            ticket_type: The type of ticket to use (train or ship)
            amount: The number of tickets to use

        Returns:
            True if tickets were successfully used, False otherwise
        """
        if ticket_type == TicketType.TRAIN.value:
            if self.train_tickets >= amount:
                self.train_tickets -= amount
                return True
        elif ticket_type == TicketType.SHIP.value:
            if self.ship_tickets >= amount:
                self.ship_tickets -= amount
                return True
        return False

    def perform_skill_test(
        self, skill: str, modifier: int = 0
    ) -> tuple[bool, list[int]]:
        """Perform a skill test using the investigator's skill value.

        Args:
            skill: The skill to test (lore, influence, observation, etc.)
            modifier: Modifier to apply to the skill value

        Returns:
            Tuple of (success, dice_rolls) where success is True if at least one die succeeded
        """
        skill_value = self.skills.get(skill, 0)
        skill_value += modifier
        successes = 0
        rolls = []

        for _ in range(skill_value):
            roll = random.randint(1, 6)
            rolls.append(roll)
            if roll >= 5:  # 5-6 is a success
                successes += 1

        return successes >= 1, rolls

    def add_condition(self, condition: str) -> List[str]:
        """Add a condition to the investigator.

        Args:
            condition: The condition to add

        Returns:
            The updated list of conditions
        """
        self.conditions.append(condition)
        return self.conditions
