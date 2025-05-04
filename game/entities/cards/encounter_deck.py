from typing import List, Optional, Dict, Tuple
from game.entities.base.deck import Deck
from game.entities.cards.encounter import Encounter
from game.entities.location import LocationType


class EncounterDeck(Deck):
    """
    Represents a deck of encounter cards.
    Extends the base Deck class with encounter-specific functionality.
    """

    def __init__(
        self, encounters: List[Encounter] = None, name: str = "Encounter Deck"
    ):
        super().__init__(encounters, name)
        self.encounters_by_subtype = {}

        # Index encounters by subtype for faster lookup
        if encounters:
            self._index_encounters_by_subtype(encounters)

    def _index_encounters_by_subtype(self, encounters: List[Encounter]) -> None:
        """
        Index encounters by subtype for faster lookup.

        Args:
            encounters: List of encounters to index
        """
        for encounter in encounters:
            subtype = encounter.location_type
            if subtype not in self.encounters_by_subtype:
                self.encounters_by_subtype[subtype] = []
            self.encounters_by_subtype[subtype].append(encounter)

    def draw_by_location_type(self, location_type: LocationType) -> Optional[Encounter]:
        """
        Draw an encounter for a specific location type.

        Args:
            location_type: Type of location (city, wilderness, sea)

        Returns:
            An encounter for the specified location type, or None if none are available
        """
        # First check if we have any encounters for this location type in the deck
        matching_encounters = []
        for i, card in enumerate(self.cards):
            if card.location_type == location_type:
                matching_encounters.append((i, card))

        if matching_encounters:
            # Remove the encounter from the deck
            index, encounter = matching_encounters[0]
            self.cards.pop(index)
            return encounter

        # If no matching encounters in the main deck, check the discard pile
        if self.discard_pile:
            # Shuffle the discard pile back into the deck
            self.cards.extend(self.discard_pile)
            self.discard_pile = []
            self.shuffle()

            # Try again
            return self.draw_by_location_type(location_type)

        # No matching encounters found
        return None
