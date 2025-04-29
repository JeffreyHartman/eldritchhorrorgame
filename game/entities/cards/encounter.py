from typing import List
from game.entities.base.component import EncounterComponent
from game.entities.location import LocationType


class Encounter:
    def __init__(self, encounter_id: int, text: str, location_type: LocationType):
        self.id = encounter_id
        self.text = text
        self.location_type = location_type
        self.components: List[EncounterComponent] = []

    def add_component(self, component):
        self.components.append(component)

    def resolve(self, state, investigator, ui=None):
        # Display the encounter text
        results = []

        # Process each component in sequence
        for component in self.components:
            result = component.process(state, investigator, ui)
            results.append(result)

            # Check if we need to abort processing further components
            if isinstance(result, dict) and result.get("abort", False):
                break

        return results
