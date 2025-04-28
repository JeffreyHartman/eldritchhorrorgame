"""
Engine module for the Eldritch Pursuit game.
Handles core game logic and main game loop.
"""

from game.game_state import GameState
from game.enums import GamePhase


class GameEngine:
    """
    Core game engine, handles the main game loop and game flow
    """

    def __init__(self, ui):
        self.ui = ui
        self.state = GameState()

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
        self.state.reset_game()
        self.game_loop()

    def game_loop(self):
        """Main game loop."""
        from game.phases.action_phase import ActionPhase
        from game.phases.encounter_phase import EncounterPhase
        from game.phases.mythos_phase import MythosPhase

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
            if (
                self.state.investigator.health <= 0
                or self.state.investigator.sanity <= 0
            ):
                self.ui.show_defeat_screen("Your investigator has been defeated!")
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
