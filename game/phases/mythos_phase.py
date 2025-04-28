"""Mythos phase implementation"""

from game.phases.base_phase import GamePhase
from game.enums import GamePhase as GamePhaseEnum


class MythosPhase(GamePhase):
    """Handles the Mythos phase of the game."""

    def execute(self):
        """Execute the Mythos phase logic."""
        self.ui.show_message("Mythos phase not implemented yet.")
        self.state.current_phase = GamePhaseEnum.ACTION
