"""Encounter phase implementation"""

from game.phases.base_phase import GamePhase


class EncounterPhase(GamePhase):
    def execute(self):
        self.ui.show_message("Encounter phase not implemented yet.")
        self.state.current_phase = "Mythos"
