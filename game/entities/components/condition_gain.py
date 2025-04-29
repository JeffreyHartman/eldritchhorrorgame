from game.entities.base.component import EncounterComponent
from game.entities.investigator import Investigator


class ConditionGainComponent(EncounterComponent):
    def __init__(self, condition: str):
        self.condition = condition

    def process(self, state, investigator: Investigator, ui=None):
        investigator.add_condition(self.condition)
        return {"type": "condition_gain", "condition": self.condition}
