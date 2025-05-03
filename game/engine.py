"""
Engine module for the Eldritch Pursuit game.
Handles core game logic and main game loop.
"""

from typing import List, Dict, Optional, Any
from game.game_state import GameState
from game.enums import GamePhase
from game.phases.action_phase import ActionPhase
from game.phases.encounter_phase import EncounterPhase
from game.phases.mythos_phase import MythosPhase
from game.systems.setup_manager import SetupManager, SetupConfig


class GameEngine:
    """
    Core game engine, handles the main game loop and game flow
    """

    def __init__(self, ui):
        self.ui = ui
        self.state = GameState()
        self.setup_manager = SetupManager(self.state)

    def run(self):
        self.main_menu()

    def main_menu(self):
        choice = self.ui.show_main_menu()
        if choice == "1":
            self.start_game()
        elif choice == "2":
            self.ui.show_instructions()
            self.main_menu()
        elif choice == "3":
            self.quit_game()
        else:
            self.run()

    def start_game(self):
        """Initialize and start a new game."""
        # Get player count
        player_count = self.ui.show_player_count_selection()

        # Set up players and investigators
        player_names = []
        investigator_ids = []

        # Get player names and investigators
        for i in range(1, player_count + 1):
            # Get player name
            player_name = self.ui.show_player_name_entry(i)
            player_names.append(player_name)

            # Get available investigators
            available_investigators = self.setup_manager.get_available_investigators()

            # Let player select an investigator
            while True:
                investigator_id = self.ui.show_investigator_selection(
                    available_investigators, player_name
                )

                # Show investigator details and confirm selection
                investigator_data = (
                    self.state.investigator_factory.get_investigator_data(
                        investigator_id
                    )
                )
                if investigator_data and self.ui.show_investigator_details(
                    investigator_data
                ):
                    investigator_ids.append(investigator_id)
                    break

        # Create setup config with selected investigators
        config = SetupConfig(
            num_players=player_count,
            ancient_one_id=1,  # Default ancient one
            investigator_ids=investigator_ids,
            player_names=player_names,
        )

        # Initialize game with config
        self.setup_manager.initialize_game(config)

        # Start the game loop
        self.game_loop()

    def game_loop(self):
        """Main game loop."""

        phases = {
            GamePhase.ACTION: ActionPhase(self, self.state, self.ui),
            GamePhase.ENCOUNTER: EncounterPhase(self, self.state, self.ui),
            GamePhase.MYTHOS: MythosPhase(self, self.state, self.ui),
        }

        while (
            self.state.doom_track < self.state.max_doom
            and self.state.mysteries_solved < 3
        ):
            # Execute current phase
            phases[self.state.current_phase].execute()

            # Check for game over conditions
            all_investigators_defeated = True
            for player in self.state.players:
                if (
                    player.investigator
                    and player.investigator.health > 0
                    and player.investigator.sanity > 0
                ):
                    all_investigators_defeated = False
                    break

            if all_investigators_defeated:
                self.ui.show_defeat_screen("All investigators have been defeated!")
                return self.main_menu()

        # Game ended - check win/loss
        if self.state.mysteries_solved >= 3:
            self.ui.show_victory_screen()
        else:
            self.ui.show_defeat_screen("The Ancient One has awakened!")

        self.main_menu()

    def quit_game(self):
        self.ui.clear_screen()
        exit()
