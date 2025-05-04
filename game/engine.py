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
        self.setup_manager = SetupManager(self.state, self.ui)

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

        # Get ancient one selection
        ancient_one_id = 1  # Default to Yog-Sothoth
        available_ancient_ones = self.setup_manager.get_available_ancient_ones()

        while True:
            ancient_one_id = self.ui.show_ancient_one_selection(available_ancient_ones)

            # Show ancient one details and confirm selection
            ancient_one_data = available_ancient_ones.get(ancient_one_id)
            if ancient_one_data and self.ui.show_ancient_one_details(ancient_one_data):
                break

        # Create setup config with selected investigators and ancient one
        config = SetupConfig(
            num_players=player_count,
            ancient_one_id=ancient_one_id,
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

        while True:
            # Execute current phase
            phases[self.state.current_phase].execute()

            # Check for game over conditions
            if self.check_game_over():
                break

            # state.phase handled in phase classes

        self.main_menu()

    def check_game_over(self):
        """Check for game over conditions."""
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
            return True

        # Check Ancient One victory/defeat conditions
        game_over, investigators_win = self.state.ancient_one.check_defeat_conditions(
            self.state
        )

        if game_over:
            if investigators_win:
                self.ui.show_victory_screen()
            else:
                self.ui.show_defeat_screen("The Ancient One has awakened!")
            return True

        return False

    def quit_game(self):
        self.ui.clear_screen()
        exit()
