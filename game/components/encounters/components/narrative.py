from game.components.encounters.components.encounter_component import EncounterComponent


class NarrativeComponent(EncounterComponent):
    def __init__(self, text):
        self.text = text

    def process(self, state, investigator, ui=None):
        if ui:
            ui.show_message(self.text)
        return {"type": "narrative", "text": self.text}
