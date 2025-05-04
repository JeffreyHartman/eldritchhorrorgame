from typing import Dict, Any
from game.entities.base.component import EncounterComponent


class NarrativeComponent(EncounterComponent):
    def __init__(self, text):
        self.text = text

    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> "NarrativeComponent":
        """Create a narrative component from data dictionary"""
        text = data.get("text", "")
        return cls(text)

    def process(self, state, investigator, ui=None):
        return {"type": "narrative", "text": self.text}
