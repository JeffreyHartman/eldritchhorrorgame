from typing import List, Dict, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum


class GameDifficulty(Enum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"
    INSANE = "insane"
    STAGED = "staged"


@dataclass
class SetupConfig:
    """Configuration for game setup"""

    num_players: int
    ancient_one_id: int
    investigator_ids: List[int] = field(default_factory=list)
    player_names: List[str] = field(default_factory=list)
    difficulty: GameDifficulty = GameDifficulty.NORMAL
    # future: add expansion ids


class SetupManager:
    def __init__(self, state, ui=None):
        self.state = state
        self.ui = ui

    def initialize_game(self, config: SetupConfig) -> None:
        """
        Initialize a new game with the given configuration.

        Args:
            config: Configuration for the game setup
        """
        # Store the config
        self.state.setup_config = config

        # Reset the game state
        self.state.reset_game(config.num_players)

        # Setup players and investigators
        if config.investigator_ids:
            self._setup_investigators(config.investigator_ids, config.player_names)
        else:
            pass

        # Setup ancient one
        self._setup_ancient_one(config.ancient_one_id)

        # Resolve any starting effects
        self._resolve_starting_effects()

    def setup_player_with_investigator(
        self, player_id: int, player_name: str, investigator_id: int
    ) -> bool:
        """
        Set up a player with the specified investigator.

        Args:
            player_id: ID for the player
            player_name: Name of the player
            investigator_id: ID of the investigator to assign

        Returns:
            True if successful, False otherwise
        """
        # Add the player with the specified investigator
        player = self.state.player_manager.add_player(
            player_id, player_name, investigator_id
        )
        if not player:
            return False

        # Mark the investigator as selected
        self.state.investigator_selector.select_investigator(investigator_id)

        # Add to the players list
        self.state.players.append(player)

        return True

    def _setup_investigators(
        self, investigator_ids: List[int], player_names: List[str]
    ) -> None:
        """
        Set up investigators for all players.

        Args:
            investigator_ids: List of investigator IDs to assign
            player_names: List of player names
        """
        # Reset player management
        self.state.players = []
        self.state.investigator_selector.reset_selections()

        # Create players with investigators
        for i, (investigator_id, player_name) in enumerate(
            zip(investigator_ids, player_names)
        ):
            self.setup_player_with_investigator(i + 1, player_name, investigator_id)

        # Reset turn order to start with the lead investigator
        self.state.player_manager.reset_turn_order()

    def _setup_ancient_one(self, ancient_one_id: int) -> None:
        """
        Set up the ancient one for the game.

        Args:
            ancient_one_id: ID of the ancient one to set up
        """
        # Create the appropriate ancient one instance based on ID
        if ancient_one_id == 1:
            from game.entities.ancient_ones.yog_sothoth import YogSothoth

            self.state.ancient_one = YogSothoth()
        # Add more ancient ones as they become available
        else:
            # Default to Yog-Sothoth if ID not found
            from game.entities.ancient_ones.yog_sothoth import YogSothoth

            self.state.ancient_one = YogSothoth()

        # Call the ancient one's setup method
        self.state.ancient_one.set_ui(self.ui)  # Set the UI reference
        self.state.ancient_one.on_setup(self.state)

    def _resolve_starting_effects(self) -> None:
        """
        Resolve any starting effects for the game.
        """
        # TODO: Implement starting effects
        pass

    def get_available_investigators(self) -> Dict[int, Dict[str, Any]]:
        """
        Get all available investigators that haven't been selected yet.

        Returns:
            Dict of investigator_id -> investigator data for available investigators
        """
        return self.state.investigator_selector.get_available_investigators()

    def get_available_ancient_ones(self) -> Dict[int, Dict[str, Any]]:
        """
        Get all available ancient ones.

        Returns:
            Dict of ancient_one_id -> ancient_one_data
        """
        # This would ideally come from a factory similar to investigator_factory
        # For now, we'll hardcode the available ancient ones
        ancient_ones = {
            1: {
                "id": 1,
                "name": "Yog-Sothoth",
                "subtitle": "The Lurker at the Threshold",
                "difficulty": "Low",
                "description": "For eons, sorcerers have called upon the power of Yog-Sothoth to bend reality to their will. This incomprehensible Ancient One exists parallel to all places and times, but is bound to the space between dimensions. Gates between worlds continue to open with more frequency and soon, Yog-Sothoth will be free.",
            },
            # Add more ancient ones as they become available
        }
        return ancient_ones
