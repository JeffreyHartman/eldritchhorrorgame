from game.entities.base.component import EncounterComponent


class NarrativeComponent(EncounterComponent):
    def __init__(self, text):
        self.text = text

    def process(self, state, investigator, ui=None):
        return {"type": "narrative", "text": self.text}
