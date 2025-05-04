import json
import logging
import random

from typing import Optional

from game.entities.cards.mythos import MythosCard
from game.entities.components.component_factory import create_component


class MythosFactory:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.blue_cards = []
        self.yellow_cards = []
        self.green_cards = []

    def get_cards(self, color, count, difficulty):
        """
        Get the specified number of cards of the specified color and difficulty.

        Args:
            color: The color of cards to get ("blue", "yellow", or "green")
            count: The number of cards to get
            difficulty: The difficulty level to filter by

        Returns:
            A list of MythosCard objects
        """
        cards = []

        # Select the appropriate card pool based on color
        if color == "blue":
            card_pool = self.blue_cards
        elif color == "yellow":
            card_pool = self.yellow_cards
        elif color == "green":
            card_pool = self.green_cards
        else:
            self.logger.error(f"Invalid color: {color}")
            return []

        # Filter by difficulty if needed
        if difficulty:
            filtered_pool = [
                card for card in card_pool if card.difficulty == difficulty
            ]
            # If no cards match the difficulty, fall back to the full pool
            if not filtered_pool:
                filtered_pool = card_pool
        else:
            filtered_pool = card_pool

        # Get random cards up to the count

        if filtered_pool:
            # Don't try to get more cards than are available
            count = min(count, len(filtered_pool))
            cards = random.sample(filtered_pool, count)

        return cards

    def load_all_mythos_cards(self):
        # Load all mythos cards frmo JSON files
        self._load_mythos_cards_from_file("game/data/mythos/blue.json", "blue")
        self._load_mythos_cards_from_file("game/data/mythos/yellow.json", "yellow")
        self._load_mythos_cards_from_file("game/data/mythos/green.json", "green")

    def _load_mythos_cards_from_file(self, file_path, color):
        # Load mythos cards from a single JSON file
        try:
            with open(file_path, "r") as file:
                cards_data = json.load(file)

                # Process each card
                for card_data in cards_data:
                    card = self._process_card_data(card_data)
                    if card:
                        if color == "blue":
                            self.blue_cards.append(card)
                        elif color == "yellow":
                            self.yellow_cards.append(card)
                        elif color == "green":
                            self.green_cards.append(card)

                self.logger.info("Loaded mythos cards from: %s", file_path)
        except json.JSONDecodeError:
            self.logger.error("Error parsing JSON in %s", file_path)
        except Exception as e:
            self.logger.error(
                "Error loading mythos cards from %s: %s", file_path, str(e)
            )

    def _process_card_data(self, card_data) -> Optional[MythosCard]:
        # Process a single card's data and add it to the factory
        try:
            card = MythosCard(
                name=card_data["name"],
                traits=card_data["traits"],
                color=card_data["color"],
                difficulty=card_data["difficulty"],
                icons=card_data["icons"],
            )

            if "components" in card_data:
                for component_data in card_data["components"]:
                    component = create_component(component_data)
                    if component:
                        card.add_component(component)

            return card

        except Exception as e:
            self.logger.error(
                "Error processing mythos card %s: %s", card_data.get("name"), str(e)
            )
            return None
