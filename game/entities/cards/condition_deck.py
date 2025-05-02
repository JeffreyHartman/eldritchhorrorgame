from typing import List, Optional, Tuple
from game.entities.base.deck import Deck
from game.entities.cards.condition import Condition


class ConditionDeck(Deck):
    """
    Represents a deck of condition cards.
    Extends the base Deck class with condition-specific functionality.

    Conditions are drawn from the bottom of the deck, and when searching for
    conditions with specific traits, we search from the bottom up.
    """

    def __init__(self, conditions: List[Condition] = None, name: str = "Condition Deck"):
        super().__init__(conditions, name)
        self.conditions_by_trait = {}

        # Index conditions by trait for faster lookup
        if conditions:
            self._index_conditions_by_trait(conditions)

    def _index_conditions_by_trait(self, conditions: List[Condition]) -> None:
        """
        Index conditions by trait for faster lookup.

        Args:
            conditions: List of conditions to index
        """
        for condition in conditions:
            for trait in condition.traits:
                if trait not in self.conditions_by_trait:
                    self.conditions_by_trait[trait] = []
                self.conditions_by_trait[trait].append(condition)

    def draw(self, n=1):
        """
        Draw a condition from the bottom of the deck.

        If the deck is empty and there are cards in the discard pile,
        shuffle the discard pile into the deck first.

        Args:
            n: Number of cards to draw (always 1 for conditions)

        Returns:
            A condition from the bottom of the deck, or None if the deck is empty
        """
        if not self.cards and self.discard_pile:
            self.cards = self.discard_pile
            self.discard_pile = []
            self.shuffle()

        if not self.cards:
            return None

        # Draw from the bottom of the deck
        return self.cards.pop(-1)

    def search_by_id(self, condition_id: str) -> Tuple[Optional[Condition], int]:
        """
        Search for a condition by ID, starting from the bottom of the deck.

        Args:
            condition_id: ID of the condition to search for

        Returns:
            A tuple of (condition, index) if found, or (None, -1) if not found
        """
        # Search from the bottom up
        for i in range(len(self.cards) - 1, -1, -1):
            if self.cards[i].id == condition_id:
                return self.cards[i], i

        return None, -1

    def search_by_trait(self, trait: str) -> Tuple[Optional[Condition], int]:
        """
        Search for a condition with the specified trait, starting from the bottom of the deck.

        Args:
            trait: Trait to search for

        Returns:
            A tuple of (condition, index) if found, or (None, -1) if not found
        """
        # Search from the bottom up
        for i in range(len(self.cards) - 1, -1, -1):
            if trait in self.cards[i].traits:
                return self.cards[i], i

        return None, -1

    def draw_by_id(self, condition_id: str) -> Optional[Condition]:
        """
        Draw a specific condition by ID.

        Args:
            condition_id: ID of the condition to draw

        Returns:
            The condition if found, or None if not found
        """
        condition, index = self.search_by_id(condition_id)

        if condition:
            # Remove the condition from the deck
            self.cards.pop(index)
            return condition

        # If not found in the main deck, check if we can recycle from discard pile
        recycled = self.recycle_discarded_conditions_by_id(condition_id)
        if recycled and self.cards:
            # Try again after recycling
            return self.draw_by_id(condition_id)

        return None

    def draw_by_trait(self, trait: str) -> Optional[Condition]:
        """
        Draw a condition with the specified trait, starting from the bottom of the deck.

        Args:
            trait: Trait to filter by (e.g., "madness")

        Returns:
            A condition with the specified trait, or None if none are available
        """
        condition, index = self.search_by_trait(trait)

        if condition:
            # Remove the condition from the deck
            self.cards.pop(index)
            return condition

        # If not found in the main deck, check if we can recycle from discard pile
        recycled = self.recycle_discarded_conditions_by_trait(trait)
        if recycled and self.cards:
            # Try again after recycling
            return self.draw_by_trait(trait)

        return None

    def recycle_discarded_conditions_by_id(self, condition_id: str) -> bool:
        """
        Move conditions with the specified ID from the discard pile back to the main deck.

        Args:
            condition_id: ID of the conditions to recycle

        Returns:
            True if any conditions were recycled, False otherwise
        """
        if not self.discard_pile:
            return False

        # Find all matching conditions in the discard pile
        matching_conditions = []
        remaining_discard = []

        for condition in self.discard_pile:
            if condition.id == condition_id:
                matching_conditions.append(condition)
            else:
                remaining_discard.append(condition)

        if not matching_conditions:
            return False

        # Update the discard pile
        self.discard_pile = remaining_discard

        # Add the matching conditions to the main deck and shuffle
        self.cards.extend(matching_conditions)
        self.shuffle()

        return True

    def recycle_discarded_conditions_by_trait(self, trait: str) -> bool:
        """
        Move conditions with the specified trait from the discard pile back to the main deck.

        Args:
            trait: Trait of the conditions to recycle

        Returns:
            True if any conditions were recycled, False otherwise
        """
        if not self.discard_pile:
            return False

        # Find all matching conditions in the discard pile
        matching_conditions = []
        remaining_discard = []

        for condition in self.discard_pile:
            if trait in condition.traits:
                matching_conditions.append(condition)
            else:
                remaining_discard.append(condition)

        if not matching_conditions:
            return False

        # Update the discard pile
        self.discard_pile = remaining_discard

        # Add the matching conditions to the main deck and shuffle
        self.cards.extend(matching_conditions)
        self.shuffle()

        return True

    def return_to_deck(self, condition: Condition, to_bottom: bool = False) -> None:
        """
        Return a condition to the deck.

        Args:
            condition: The condition to return
            to_bottom: If True, add to bottom of deck; if False, add to top
        """
        if to_bottom:
            self.add_to_bottom(condition)
        else:
            self.add_to_top(condition)
