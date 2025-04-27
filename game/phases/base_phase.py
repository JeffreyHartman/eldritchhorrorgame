"""Base class for game phases"""


class GamePhase:
    def __init__(self, engine, state, ui):
        self.engine = engine
        self.state = state
        self.ui = ui

    def execute(self):
        """Execute this phase's logic. Must be implemented by subclasses."""
        raise NotImplementedError
