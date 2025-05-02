import json
from game.entities.location import Location, LocationType
from game.entities.investigator import Investigator
from game.factories.encounter_factory import EncounterFactory
from game.factories.asset_factory import AssetFactory
from game.factories.condition_factory import ConditionFactory
from game.entities.cards.asset_deck import AssetDeck
from game.entities.cards.condition_deck import ConditionDeck
from game.entities.cards.encounter_deck import EncounterDeck
from game.enums import GamePhase, EncounterType


class GameState:
    """
    Core game state manager, tracks all game variables
    """

    def __init__(self):
        self.doom_track = 0
        self.max_doom = 15
        self.mysteries_solved = 0
        self.current_phase = GamePhase.ACTION
        self.defeated_investigators = []

        # Initialize factories
        self.encounter_factory = EncounterFactory()
        self.encounter_factory.load_all_encounter_types()

        self.asset_factory = AssetFactory()
        self.asset_factory.load_all_assets()

        self.condition_factory = ConditionFactory()
        self.condition_factory.load_all_conditions()

        # Initialize decks (will be fully set up in reset_game)
        self.asset_deck = None
        self.condition_deck = None
        self.encounter_decks = {}  # Dict of encounter_type -> EncounterDeck

        self.locations = {}
        self.investigator = {}

    def reset_game(self):
        """Reset the game state to starting values."""
        self.doom_track = 0
        self.mysteries_solved = 0
        self.current_phase = GamePhase.ACTION

        # Initialize all decks
        self._setup_asset_deck()
        self._setup_condition_deck()
        self._setup_encounter_decks()

        self.load_locations()
        # TODO: test investigator, replace with character selection
        self.investigator = Investigator(
            name="Anna Blackwood",
            health=4,
            max_health=5,
            sanity=5,
            max_sanity=5,
            skills={
                "lore": 2,
                "influence": 3,
                "observation": 2,
                "strength": 1,
                "will": 3,
            },
            items=[],
            clue_tokens=2,
            train_tickets=0,
            ship_tickets=0,
            is_delayed=False,
            actions=2,
            current_location="London",
        )

    def _setup_asset_deck(self):
        """Set up the asset deck with all available assets."""
        # Create a list of all assets
        all_assets = list(self.asset_factory.assets.values())

        # Create the asset deck
        self.asset_deck = AssetDeck(all_assets)

        # Shuffle the deck
        self.asset_deck.shuffle()

        # Set up the reserve
        self.asset_deck.setup_reserve(4)

    def load_locations(self):
        """Load location data from JSON file."""
        with open("game/data/locations.json", "r") as file:
            location_data = json.load(file)

        self.locations = {}
        for name, data in location_data.items():
            location_type = LocationType[data.get("location_type", "CITY")]
            self.locations[name] = Location(
                name=name,
                description=data["description"],
                connections=data["connections"],
                location_type=location_type,
                train_paths=data.get("train_paths"),
                ship_paths=data.get("ship_paths"),
                real_world_location=data.get("real_world_location"),
                continent=data.get("continent"),
            )

    def reset_action_phase(self):
        """Reset to the action phase and restore actions."""
        self.current_phase = GamePhase.ACTION
        self.investigator.actions = 2

    def use_action(self):
        """Use an action, return True if actions remaining, False if no actions left"""
        if self.investigator.actions > 0:
            self.investigator.actions -= 1
            return True
        return False

    def has_actions_left(self):
        """Check if the investigator has actions remaining."""
        return self.investigator.actions > 0

    def _setup_condition_deck(self):
        """Set up the condition deck with all available conditions."""
        # Create a list of all conditions
        all_conditions = list(self.condition_factory.conditions.values())

        # Create the condition deck
        self.condition_deck = ConditionDeck(all_conditions)

        # Shuffle the deck
        self.condition_deck.shuffle()

    def _setup_encounter_decks(self):
        """Set up encounter decks for each encounter type."""
        # Clear existing decks
        self.encounter_decks = {}

        # Create a deck for each encounter type
        for encounter_type in EncounterType:
            encounter_type_str = encounter_type.value

            # Get all encounters of this type from the factory
            encounters = []
            if encounter_type_str in self.encounter_factory.encounters:
                encounters = self.encounter_factory.encounters[encounter_type_str]

            # Create and shuffle the deck
            deck = EncounterDeck(encounters, f"{encounter_type_str.capitalize()} Encounters")
            deck.shuffle()

            # Store in the dictionary
            self.encounter_decks[encounter_type_str] = deck

    def draw_encounter(self, encounter_type: str, subtype: str = None):
        """
        Draw an encounter from the specified deck.

        Args:
            encounter_type: Type of encounter (general, research, etc.)
            subtype: Optional subtype for filtering (city, wilderness, etc.)

        Returns:
            An encounter card, or None if the deck is empty
        """
        # Get the appropriate deck
        deck = self.encounter_decks.get(encounter_type)
        if not deck:
            return None

        # If subtype is specified, try to draw a matching encounter
        if subtype:
            from game.entities.location import LocationType
            try:
                location_type = LocationType[subtype.upper()]
                return deck.draw_by_location_type(location_type)
            except (KeyError, ValueError):
                # Invalid location type, fall back to random draw
                pass

        # Draw a random encounter
        return deck.draw()

    def draw_condition(self, trait: str = None, condition_id: str = None):
        """
        Draw a condition from the condition deck.

        Args:
            trait: Optional trait to filter by (e.g., "madness")
            condition_id: Optional specific condition ID to draw

        Returns:
            A condition card, or None if the deck is empty or no matching condition found
        """
        if not self.condition_deck:
            return None

        if condition_id:
            # Draw a specific condition by ID
            return self.condition_deck.draw_by_id(condition_id)
        elif trait:
            # Draw a condition with a specific trait
            return self.condition_deck.draw_by_trait(trait)
        else:
            # Draw from the bottom of the deck
            return self.condition_deck.draw()

    def search_condition(self, trait: str = None, condition_id: str = None):
        """
        Search for a condition in the deck without removing it.

        Args:
            trait: Optional trait to filter by (e.g., "madness")
            condition_id: Optional specific condition ID to search for

        Returns:
            A tuple of (condition, index) if found, or (None, -1) if not found
        """
        if not self.condition_deck:
            return None, -1

        if condition_id:
            # Search for a specific condition by ID
            return self.condition_deck.search_by_id(condition_id)
        elif trait:
            # Search for a condition with a specific trait
            return self.condition_deck.search_by_trait(trait)

        return None, -1

    def recycle_conditions(self, trait: str = None, condition_id: str = None):
        """
        Recycle conditions from the discard pile back into the deck.

        Args:
            trait: Optional trait to filter by (e.g., "madness")
            condition_id: Optional specific condition ID to recycle

        Returns:
            True if any conditions were recycled, False otherwise
        """
        if not self.condition_deck:
            return False

        if condition_id:
            # Recycle conditions with a specific ID
            return self.condition_deck.recycle_discarded_conditions_by_id(condition_id)
        elif trait:
            # Recycle conditions with a specific trait
            return self.condition_deck.recycle_discarded_conditions_by_trait(trait)

        return False
