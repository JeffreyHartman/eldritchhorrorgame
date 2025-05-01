from game.entities.base.component import EncounterComponent

class SpawnClueComponent(EncounterComponent):
    def __init__(self, count: int = 1):
        self.count = count

    def process(self, state, investigator, ui=None):
        # Spawn the specified number of clues
        for _ in range(self.count):
            state.spawn_clue()  # not implemented
        return {"type": "spawn_clue", "count": self.count}
