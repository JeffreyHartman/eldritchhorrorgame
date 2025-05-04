"""Mythos phase implementation"""

from game.phases.base_phase import GamePhase
from game.enums import GamePhase as GamePhaseEnum


class MythosPhase(GamePhase):
    """Handles the Mythos phase of the game."""

    def execute(self):
        """Execute the Mythos phase logic."""
        self.ui.show_message("Mythos phase not implemented yet.")

        # Advance doom track (placeholder)
        self.state.doom_track -= 1
        self.ui.show_message(
            f"Doom advances to {self.state.doom_track}/{self.state.max_doom}"
        )

        # Reset turn order to start with the lead investigator
        self.state.player_manager.reset_turn_order()

        # Transition to Action phase
        self.state.current_phase = GamePhaseEnum.ACTION

        # Show lead investigator message if we have multiple players
        if len(self.state.players) > 1:
            lead_player = self.state.player_manager.get_lead_investigator()
            if lead_player:
                self.ui.show_message(
                    f"Starting new round with {lead_player.name} as the lead investigator."
                )
