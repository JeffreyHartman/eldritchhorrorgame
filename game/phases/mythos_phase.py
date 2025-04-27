"""Mythos phase implementation"""

from game.phases.base_phase import GamePhase


class MythosPhase(GamePhase):
    def execute(self):
        self.ui.show_message("Mythos phase not implemented yet.")
        self.state.current_phase = "Action"
