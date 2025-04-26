"""
Engine module for the Eldritch Pursuit game.
Handles core game logic and main game loop.
"""
from game.game_state import GameState

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
        while self.state.doom_track < self.state.max_doom and self.state.mysteries_solved < 3:
            if self.state.current_phase == "Action":
                self.action_phase()
            elif self.state.current_phase == "Encounter":
                self.encounter_phase()
            elif self.state.current_phase == "Mythos":
                self.mythos_phase()
                
            # Check for game over conditions
            if self.state.investigator["health"] <= 0 or self.state.investigator["sanity"] <= 0:
                self.ui.show_defeat_screen("Your investigator has been defeated!")
                self.main_menu()
            
        # Game ended - check win/loss
        if self.state.mysteries_solved >= 3:
            self.ui.show_victory_screen()
            self.main_menu()
        else:
            self.ui.show_defeat_screen("The Ancient One has awakened!")
            self.main_menu()

    def action_phase(self):
        """Handle the action phase."""
        choice = self.ui.show_action_phase(self.state)
        # wait for user input and then exit, just to test
        self.ui.input("\n[bold cyan]Press Enter to continue...[/]")
        
    
    def encounter_phase(self):
        """Handle the encounter phase."""
        pass
    
    def mythos_phase(self):
        """Handle the mythos phase."""
        pass
        
    def quit_game(self):
        self.ui.clear_screen()
        exit()
