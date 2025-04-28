from typing import List
from game.components.encounters.components.encounter_component import EncounterComponent
from game.components.investigator import Investigator


class SkillTestComponent(EncounterComponent):
    def __init__(
        self,
        skill: str,
        modifier: int,
        success_components: List[EncounterComponent],
        failure_components: List[EncounterComponent],
    ):
        self.skill = skill
        self.modifier = modifier
        self.success_components = success_components
        self.failure_components = failure_components

    def process(self, state, investigator: Investigator, ui=None):
        ui.show_message(f"Test {self.skill} ({self.modifier})")

        success, rolls = investigator.perform_skill_test(self.skill, self.modifier)
        ui.show_message(f"Rolls: {rolls}")
        if success:
            ui.show_message("Success!")
            for component in self.success_components:
                component.process(state, investigator, ui)
        else:
            ui.show_message("Failure!")
            for component in self.failure_components:
                component.process(state, investigator, ui)

        return {"type": "skill_test", "skill": self.skill, "success": success}
